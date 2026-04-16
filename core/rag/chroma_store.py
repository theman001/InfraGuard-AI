"""
core/rag/chroma_store.py — ChromaDB 저장/조회/업데이트

컬렉션명: legal_advisory
저장 단위: 조(Article) 전체 (LawChunk)

변경 감지 (sync_law_chunks):
- 법령 단위 증분 동기화: 추가/수정/삭제 조문만 처리
- 전체 법령 삭제 후 재삽입 방식 사용 안 함
"""

import os
from pathlib import Path

import chromadb
from chromadb.config import Settings

from core.rag.chunker import LawChunk
from core.rag.embedder import embed_texts, embed_query

_DEFAULT_CHROMA = Path(__file__).parent.parent.parent / "data" / "chroma_db"
CHROMA_PATH = Path(os.environ.get("CHROMA_PATH", str(_DEFAULT_CHROMA)))
COLLECTION_NAME = os.environ.get("CHROMA_COLLECTION", "legal_advisory")
UPSERT_BATCH = 100

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def upsert_chunks(chunks: list[LawChunk]) -> int:
    """청크 리스트를 ChromaDB에 upsert. 기존 동일 ID 존재 시 덮어씀."""
    if not chunks:
        return 0

    col = _get_collection()
    total = 0

    for start in range(0, len(chunks), UPSERT_BATCH):
        batch = chunks[start: start + UPSERT_BATCH]
        vectors = embed_texts([c.full_text for c in batch])

        col.upsert(
            ids        = [c.chunk_id for c in batch],
            embeddings = vectors,
            documents  = [c.full_text for c in batch],
            metadatas  = [
                {
                    "law_name":      c.law_name,
                    "mst_id":        c.mst_id,
                    "law_type":      c.law_type,
                    "article_no":    c.article_no,
                    "article_title": c.article_title,
                    "article_label": c.article_label,
                    "effective_date":c.effective_date,
                    "category":      c.category,
                    "sector":        c.sector,
                    "cert":          c.cert,
                }
                for c in batch
            ],
        )
        total += len(batch)

    return total


def delete_by_mst_id(mst_id: str) -> int:
    """특정 법령(mst_id)의 청크 전체 삭제. 반환값: 삭제된 수."""
    col = _get_collection()
    results = col.get(where={"mst_id": mst_id})
    ids = results.get("ids", [])
    if ids:
        col.delete(ids=ids)
    return len(ids)


def sync_law_chunks(mst_id: str, new_chunks: list[LawChunk]) -> dict:
    """
    법령 단위 증분 동기화.

    기존 청크와 새 파싱 결과를 chunk_id + 본문 내용으로 비교하여
    변경된 조문만 upsert, 삭제된 조문만 delete, 동일한 조문은 skip.

    Returns:
        {"inserted": n, "updated": n, "deleted": n, "unchanged": n}
    """
    col = _get_collection()

    # 기존 청크 조회 (id + document 내용)
    existing = col.get(where={"mst_id": mst_id}, include=["documents"])
    existing_ids: set[str] = set(existing["ids"])
    existing_docs: dict[str, str] = dict(zip(
        existing["ids"],
        existing.get("documents") or [],
    ))

    new_id_map: dict[str, LawChunk] = {c.chunk_id: c for c in new_chunks}
    new_ids: set[str] = set(new_id_map.keys())

    # 1. 삭제: 기존에 있지만 새 파싱에 없는 조문
    to_delete = list(existing_ids - new_ids)
    if to_delete:
        col.delete(ids=to_delete)

    # 2. 추가 또는 수정: 새 청크 중 없거나 내용이 다른 것만 upsert
    to_upsert: list[LawChunk] = []
    inserted_count = 0
    updated_count = 0

    for chunk_id, chunk in new_id_map.items():
        if chunk_id not in existing_ids:
            to_upsert.append(chunk)
            inserted_count += 1
        elif existing_docs.get(chunk_id) != chunk.full_text:
            to_upsert.append(chunk)
            updated_count += 1

    unchanged_count = len(new_chunks) - len(to_upsert)

    if to_upsert:
        upsert_chunks(to_upsert)

    return {
        "inserted": inserted_count,
        "updated": updated_count,
        "deleted": len(to_delete),
        "unchanged": unchanged_count,
    }


def search(
    query: str,
    n_results: int = 5,
    sector: str | None = None,
    cert: str | None = None,
    law_type: str | None = None,
) -> list[dict]:
    """
    자연어 쿼리 + 메타데이터 필터로 관련 조문 검색.

    필터 원칙:
    - 공통 법령(category="공통")은 sector/cert 무관하게 항상 포함
    - sector/cert가 지정된 경우 해당 업종/인증 법령도 함께 포함 ($or 조건)
    - law_type은 위 조건에 추가로 $and 적용 (특정 법률 유형 한정 시)

    Returns:
        [{"law_name", "article_label", "full_text", "effective_date",
          "mst_id", "distance"}, ...]
    """
    col = _get_collection()
    query_vec = embed_query(query)

    # 메타데이터 필터 구성
    # 공통 법령은 항상 포함 — $or 기반 구성
    or_conditions: list[dict] = [{"category": {"$eq": "공통"}}]
    if sector:
        or_conditions.append({"sector": {"$eq": sector}})
    if cert:
        or_conditions.append({"cert": {"$eq": cert}})

    if len(or_conditions) == 1:
        # sector/cert 미지정: 공통 법령만
        where: dict | None = {"category": {"$eq": "공통"}}
    else:
        where = {"$or": or_conditions}

    # law_type 추가 필터: 위 조건에 $and로 결합
    if law_type and where:
        where = {"$and": [where, {"law_type": {"$eq": law_type}}]}
    elif law_type:
        where = {"law_type": {"$eq": law_type}}

    kwargs = {
        "query_embeddings": [query_vec],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = col.query(**kwargs)

    output = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        output.append({
            "law_name":      meta.get("law_name", ""),
            "article_label": meta.get("article_label", ""),
            "article_no":    meta.get("article_no", ""),
            "full_text":     doc,
            "effective_date":meta.get("effective_date", ""),
            "mst_id":        meta.get("mst_id", ""),
            "distance":      dist,
        })

    return output


def get_collection_count() -> int:
    return _get_collection().count()


def reset_collection() -> None:
    """
    컬렉션 전체 삭제 후 재생성.
    전역 _client/_collection 캐시도 초기화해 다음 호출 시 새로 연결.
    """
    global _client, _collection
    # 컬렉션이 아직 없으면 그냥 초기화만
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass  # 컬렉션이 없어도 무시
    client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    # 캐시 초기화 → 다음 _get_collection() 호출 시 새 컬렉션 연결
    _client = None
    _collection = None
