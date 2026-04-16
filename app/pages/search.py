"""
app/pages/search.py — 법령 직접 검색

ChromaDB에 저장된 법령 조문을 의미 기반(벡터 유사도)으로 검색.
필터: 업종 / 인증 / 결과 수
"""

import streamlit as st

from app.components.auth import require_login
# chroma_store는 render() 진입 시 지연 임포트

_SECTOR_OPTIONS = ["없음", "금융/핀테크", "의료/헬스케어", "제조", "공공/공급망", "유통/이커머스", "IT/소프트웨어"]
_CERT_OPTIONS   = ["없음", "ISMS-P", "ISO27001"]


def render() -> None:
    require_login()

    st.title("법령 검색")
    st.caption("ChromaDB에 저장된 법령 조문을 의미 기반으로 검색합니다.")

    # ── 검색 폼 ──────────────────────────────────────────────────────────────
    query = st.text_input(
        "검색어",
        placeholder="예) CCTV 설치 개인정보 고지 의무",
        key="search_query",
    )

    col1, col2, col3 = st.columns([3, 3, 2])
    sector = col1.selectbox("업종 필터", _SECTOR_OPTIONS, key="search_sector")
    cert   = col2.selectbox("인증 필터", _CERT_OPTIONS,   key="search_cert")
    n_results = col3.slider("결과 수", min_value=1, max_value=20, value=5, key="search_n")

    search_btn = st.button("검색", type="primary")

    st.divider()

    # ── 검색어 없을 때: DB 현황 표시 ──────────────────────────────────────────
    if not query.strip() and not search_btn:
        try:
            from core.rag.chroma_store import get_collection_count
            count = get_collection_count()
            st.info(f"현재 **{count}개** 법령 조문이 저장되어 있습니다.")
        except Exception as e:
            st.warning(f"ChromaDB 연결 확인 필요: {e}")
        return

    if not query.strip():
        st.error("검색어를 입력하세요.")
        return

    # ── 검색 실행 ────────────────────────────────────────────────────────────
    sector_val = sector if sector != "없음" else None
    cert_val   = cert   if cert   != "없음" else None

    try:
        from core.rag.chroma_store import search
        results = search(
            query=query.strip(),
            n_results=n_results,
            sector=sector_val,
            cert=cert_val,
        )
    except Exception as e:
        st.error(f"검색 실패: {e}")
        return

    if not results:
        st.warning("관련 법령 조문을 찾지 못했습니다. 다른 키워드로 시도해보세요.")
        return

    st.markdown(f"**검색 결과 {len(results)}건**")

    # ── 결과 표시 ─────────────────────────────────────────────────────────────
    for i, r in enumerate(results, 1):
        similarity = max(0.0, 1.0 - r["distance"])
        label = f"{i}. {r['law_name']}  {r['article_label']}"

        with st.expander(label, expanded=(i == 1)):
            col_meta1, col_meta2, col_meta3 = st.columns(3)
            col_meta1.metric("유사도", f"{similarity:.2%}")
            col_meta2.caption(f"시행일: {r.get('effective_date', '-')}")
            col_meta3.caption(f"MST: {r.get('mst_id', '-')}")

            st.divider()
            st.write(r["full_text"])
