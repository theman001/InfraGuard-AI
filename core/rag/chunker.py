"""
core/rag/chunker.py — 조문 XML → LawChunk (조 단위)

청킹 전략:
- 단위: 조(Article) 전체를 하나의 청크로 저장
- 항/호/목 계층 구조를 들여쓰기로 보존
- 메타데이터: 법령명, 조번호, 조제목, 업종태그, 시행일자, 개정일자

chunk_id 규칙 (결정론적):
    우선순위 1: "{mst_id}_{조문키}" — XML 조문단위 태그의 조문키 속성 사용
    우선순위 2: "{mst_id}_{article_label_sanitized}" — 조문키 없을 때 fallback
    조문번호 기반 순서 idx는 사용하지 않음 (조문 추가/삭제 시 ID 밀림 방지)
"""

import re
from dataclasses import dataclass
from bs4 import BeautifulSoup


_REVISION_RE = re.compile(r"<(?:개정|신설|삭제)[^>]*>")


def _clean(text: str) -> str:
    return " ".join(_REVISION_RE.sub("", text).split())


@dataclass
class LawChunk:
    chunk_id: str           # "{mst_id}_{조문키}" 또는 "{mst_id}_{article_label_sanitized}"
    law_name: str
    mst_id: str
    law_type: str
    article_no: str         # "15"
    article_title: str      # "개인정보의 수집·이용"
    article_label: str      # "제15조(개인정보의 수집·이용)"
    full_text: str          # 조 전체 텍스트 (임베딩 + LLM 컨텍스트)
    effective_date: str     # "YYYYMMDD"
    category: str           # "공통" / "업종별" / "인증별"
    sector: str             # "금융/핀테크" 등, 없으면 ""
    cert: str               # "ISMS-P" 등, 없으면 ""


def _build_full_text(unit) -> str:
    """
    조문단위 태그에서 전체 텍스트 재구성.
    항/호/목 계층을 들여쓰기로 표현.
    """
    parts = []

    content_tag = unit.find("조문내용")
    if content_tag and content_tag.text.strip():
        parts.append(content_tag.text.strip())

    for 항 in unit.find_all("항", recursive=False):
        항내용 = 항.find("항내용")
        if 항내용 and 항내용.text.strip():
            parts.append(항내용.text.strip())

        for 호 in 항.find_all("호", recursive=False):
            호내용 = 호.find("호내용")
            if 호내용 and 호내용.text.strip():
                parts.append("  " + 호내용.text.strip())

            for 목 in 호.find_all("목", recursive=False):
                목내용 = 목.find("목내용")
                if 목내용 and 목내용.text.strip():
                    parts.append("    " + 목내용.text.strip())

    return "\n".join(parts)


def parse_chunks(
    soup: BeautifulSoup,
    mst_id: str,
    law_name: str,
    law_type: str,
    effective_date: str,
    category: str,
    sector: str | None,
    cert: str | None,
) -> list[LawChunk]:
    """
    XML soup → LawChunk 리스트 반환.
    조문여부 == "조문" 인 태그만 처리 (전문/부칙 제외).
    """
    chunks: list[LawChunk] = []
    seen_ids: set[str] = set()

    for unit in soup.find_all("조문단위"):
        gubun_tag = unit.find("조문여부")
        gubun = gubun_tag.text.strip() if gubun_tag else ""
        if gubun != "조문":
            continue

        no_tag    = unit.find("조문번호")
        title_tag = unit.find("조문제목")
        date_tag  = unit.find("조문시행일자")

        article_no    = no_tag.text.strip()    if no_tag    else ""
        article_title = title_tag.text.strip() if title_tag else ""
        art_eff_date  = date_tag.text.strip()  if date_tag  else effective_date

        if not article_no:
            continue

        if article_title:
            article_label = f"제{article_no}조({article_title})"
        else:
            article_label = f"제{article_no}조"

        full_text = _build_full_text(unit)
        if not full_text.strip():
            continue

        # 임베딩 입력: "법령명 조문라벨 본문"
        embed_text = _clean(f"{law_name} {article_label} {full_text}")

        # chunk_id (결정론적):
        #   1순위: XML 조문키 속성 — 법령 시스템 고유 식별자
        #   2순위: article_label 기반 sanitize — 조문키 없을 때 fallback
        조문키_val = unit.get("조문키", "").strip()
        if 조문키_val:
            chunk_id = f"{mst_id}_{조문키_val}"
        else:
            safe_label = re.sub(r"[^\w가-힣]", "_", article_label)
            chunk_id = f"{mst_id}_{safe_label}"

        # 동일 chunk_id 중복 방지 (같은 법령 내 극히 드문 엣지케이스)
        if chunk_id in seen_ids:
            base, n = chunk_id, 1
            while chunk_id in seen_ids:
                chunk_id = f"{base}_{n}"
                n += 1
        seen_ids.add(chunk_id)

        chunks.append(LawChunk(
            chunk_id      = chunk_id,
            law_name      = law_name,
            mst_id        = mst_id,
            law_type      = law_type,
            article_no    = article_no,
            article_title = article_title,
            article_label = article_label,
            full_text     = embed_text,
            effective_date= art_eff_date,
            category      = category or "",
            sector        = sector or "",
            cert          = cert or "",
        ))

    return chunks
