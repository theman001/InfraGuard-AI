"""
core/rag/init_db.py — 법령 전체 초기 수집 CLI

사용법:
    python -m core.rag.init_db              # 전체 수집 (시행일자 변경된 법령만)
    python -m core.rag.init_db --mst 270351 # 특정 MST만 재수집
    python -m core.rag.init_db --force      # 전체 강제 재수집

수집 흐름:
    law_registry (DB) → API 조회 → 청킹 → sync_law_chunks (증분 동기화) → DB 시행일자 갱신
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run(mst_id: str | None = None, force: bool = False) -> None:
    from core.db import init_db
    from core.models import get_all_laws, update_effective_date
    from core.rag.collector import fetch_law_xml, get_law_name_from_xml
    from core.rag.chunker import parse_chunks
    from core.rag.chroma_store import sync_law_chunks, get_collection_count

    # DB 초기화 (테이블 + 시드 데이터)
    init_db()

    laws = get_all_laws(active_only=True)
    if mst_id:
        laws = [l for l in laws if l.mst_id == mst_id]
        if not laws:
            logger.error(f"MST={mst_id} 를 law_registry에서 찾을 수 없습니다.")
            sys.exit(1)

    total_upserted = 0
    failed = []

    logger.info(f"수집 대상: {len(laws)}개 법령")

    for entry in laws:
        logger.info(f"\n[{entry.law_name}] MST={entry.mst_id}")
        try:
            soup, effective_date = fetch_law_xml(entry.mst_id)
            law_name = get_law_name_from_xml(soup) or entry.law_name

            if not force and entry.last_effective_date == effective_date:
                logger.info(f"  → 시행일 동일 ({effective_date}), 스킵")
                continue

            chunks = parse_chunks(
                soup          = soup,
                mst_id        = entry.mst_id,
                law_name      = law_name,
                law_type      = entry.law_type or "",
                effective_date= effective_date,
                category      = entry.category,
                sector        = entry.sector,
                cert          = entry.cert,
            )

            # 법령 단위 증분 동기화 (추가/수정/삭제 조문만 처리)
            sync_result = sync_law_chunks(entry.mst_id, chunks)
            update_effective_date(entry.mst_id, effective_date)

            logger.info(
                f"  → 추가 {sync_result['inserted']}개 / "
                f"수정 {sync_result['updated']}개 / "
                f"삭제 {sync_result['deleted']}개 / "
                f"유지 {sync_result['unchanged']}개 "
                f"(시행일: {effective_date})"
            )
            total_upserted += sync_result["inserted"] + sync_result["updated"]

        except Exception as e:
            logger.error(f"  → 실패: {e}")
            failed.append({"law_name": entry.law_name, "mst_id": entry.mst_id, "error": str(e)})

    logger.info(f"\n{'='*50}")
    logger.info(f"수집 완료 — 총 {total_upserted}개 조문 추가/수정")
    logger.info(f"ChromaDB 전체 청크 수: {get_collection_count()}")
    if failed:
        logger.warning(f"실패 {len(failed)}건:")
        for f in failed:
            logger.warning(f"  - {f['law_name']} (MST={f['mst_id']}): {f['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="법령 초기 수집 CLI")
    parser.add_argument("--mst",   type=str, default=None, help="특정 MST ID만 수집")
    parser.add_argument("--force", action="store_true",   help="시행일자 무관 전체 재수집")
    args = parser.parse_args()

    run(mst_id=args.mst, force=args.force)
