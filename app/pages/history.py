"""
app/pages/history.py — 자문 이력 목록 + 보고서 상세

mode A (목록): view_report_id 없을 때
  - 검색/필터 (키워드, 날짜 범위, 회색지대 여부)
  - 보고서 카드 목록: 날짜 / 한줄요약 / 사용 템플릿 / 회색지대 / [보기][삭제]

mode B (상세): view_report_id 있을 때
  - [← 목록으로] 버튼
  - 섹션별 보고서 표시 (법령 / 판례 / 결론 / 회색지대 / 유사 이력)
"""

import json
from datetime import date, timedelta

import streamlit as st

from app.components.auth import get_current_user, require_login
from app.components.pdf_export import generate_report_pdf
from core.advisor.gray_area import has_gray_area, format_gray_area_text
from core.models import get_reports_by_user, get_report_by_id, delete_report


_HISTORY_CSS = """
<style>
/* 이력 페이지 전용 */
.hist-table-header {
    display: grid;
    grid-template-columns: 100px 1fr 110px 60px 100px;
    gap: 0.5rem;
    background: #eef2fa;
    border-radius: 8px 8px 0 0;
    padding: 0.5rem 0.75rem;
    font-size: 0.8rem;
    font-weight: 600;
    color: #1a3c6e;
    border: 1px solid #dde3ed;
    border-bottom: none;
    margin-bottom: 0;
}
.hist-row {
    border: 1px solid #dde3ed;
    border-top: none;
    padding: 0.6rem 0.75rem;
    background: #fff;
    transition: background 0.15s;
}
.hist-row:hover {
    background: #f5f8ff;
}
.hist-row:last-child {
    border-radius: 0 0 8px 8px;
}
.gray-badge {
    display: inline-block;
    background: #fff3e0;
    color: #e67e22;
    border: 1px solid #f5c07a;
    border-radius: 4px;
    padding: 0.1rem 0.4rem;
    font-size: 0.72rem;
    font-weight: 600;
}
.result-section-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    background: #1a3c6e;
    color: #fff;
    border-radius: 50%;
    font-size: 0.72rem;
    font-weight: 700;
    margin-right: 0.4rem;
    vertical-align: middle;
}
.result-header {
    display: flex;
    align-items: center;
    font-size: 1rem;
    font-weight: 600;
    color: #1a1f2e;
    margin: 1.25rem 0 0.5rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 2px solid #e8edf5;
}
.hist-count-badge {
    display: inline-block;
    background: #1a3c6e;
    color: #fff;
    border-radius: 20px;
    padding: 0.1rem 0.6rem;
    font-size: 0.78rem;
    font-weight: 600;
    margin-left: 0.4rem;
}
</style>
"""


def render() -> None:
    require_login()
    user = get_current_user()

    st.markdown(_HISTORY_CSS, unsafe_allow_html=True)

    view_id = st.session_state.get("view_report_id")

    if view_id:
        _render_detail(user, view_id)
    else:
        _render_list(user)


# ─────────────────────────────────────────────────────────────────────────────
# mode A: 목록 뷰
# ─────────────────────────────────────────────────────────────────────────────

def _parse_reports(reports: list) -> list:
    """각 보고서에 gray_flag, tpl_name, date_str, summary 파생 필드 추가."""
    parsed = []
    for r in reports:
        gray_flag = False
        try:
            result_dict = json.loads(r["result"] or "{}")
            gray_flag = has_gray_area(result_dict)
        except Exception:
            result_dict = {}

        tpl_name = "-"
        if r.get("template_snapshot"):
            try:
                snap = json.loads(r["template_snapshot"])
                sector_item = snap.get("sector", {})
                if isinstance(sector_item, dict) and sector_item.get("enabled"):
                    tpl_name = sector_item.get("value", "-")
                else:
                    tpl_name = "템플릿 사용"
            except Exception:
                tpl_name = "템플릿 사용"

        parsed.append({
            **r,
            "_gray": gray_flag,
            "_tpl": tpl_name,
            "_date": r["created_at"][:10] if r.get("created_at") else "-",
            "_summary": r["summary"] or "(요약 없음)",
            "_result": result_dict,
        })
    return parsed


def _apply_filters(reports: list, keyword: str, date_from: date | None,
                   date_to: date | None, gray_only: bool) -> list:
    result = reports
    if keyword:
        kw = keyword.lower()
        result = [r for r in result if kw in r["_summary"].lower() or kw in (r.get("prompt") or "").lower()]
    if date_from:
        result = [r for r in result if r["_date"] >= str(date_from)]
    if date_to:
        result = [r for r in result if r["_date"] <= str(date_to)]
    if gray_only:
        result = [r for r in result if r["_gray"]]
    return result


def _render_list(user: dict) -> None:
    st.title("자문 이력")

    all_reports = get_reports_by_user(user["id"])

    if not all_reports:
        st.info("자문 이력이 없습니다.")
        if st.button("자문 요청하기"):
            st.session_state["page"] = "dashboard"
            st.rerun()
        return

    parsed = _parse_reports(all_reports)

    # ── 필터 UI ───────────────────────────────────────────────────────────────
    with st.expander("🔍 검색 / 필터", expanded=False):
        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
        keyword   = col1.text_input("키워드", placeholder="요약 또는 요청 내용 검색", key="hist_kw")
        date_from = col2.date_input("시작일", value=None, key="hist_from")
        date_to   = col3.date_input("종료일", value=None, key="hist_to")
        gray_only = col4.checkbox("회색지대만", key="hist_gray")

        if st.button("초기화", key="hist_reset"):
            for k in ("hist_kw", "hist_from", "hist_to", "hist_gray"):
                st.session_state.pop(k, None)
            st.rerun()

    reports = _apply_filters(parsed, keyword or "", date_from, date_to, gray_only)

    total    = len(all_reports)
    filtered = len(reports)
    count_html = (
        f'전체 {total}건 중 <span class="hist-count-badge">{filtered}건</span> 표시'
        if filtered < total
        else f'전체 <span class="hist-count-badge">{total}건</span>'
    )
    st.markdown(count_html, unsafe_allow_html=True)
    st.write("")

    if not reports:
        st.warning("조건에 맞는 이력이 없습니다.")
        return

    # ── 헤더 ─────────────────────────────────────────────────────────────────
    hdr = st.columns([2, 5, 2, 1, 2])
    for col, label in zip(hdr, ["날짜", "한줄요약", "사용 템플릿", "회색지대", "작업"]):
        col.markdown(f"<span style='font-size:0.82rem;font-weight:600;color:#1a3c6e'>{label}</span>",
                     unsafe_allow_html=True)

    # ── 보고서 행 ─────────────────────────────────────────────────────────────
    for r in reports:
        rid = r["id"]
        st.divider()
        cols = st.columns([2, 5, 2, 1, 2])
        cols[0].caption(r["_date"])
        cols[1].write(r["_summary"][:60] + ("..." if len(r["_summary"]) > 60 else ""))
        cols[2].caption(r["_tpl"])

        if r["_gray"]:
            cols[3].markdown('<span class="gray-badge">⚠</span>', unsafe_allow_html=True)
        else:
            cols[3].write("—")

        btn_col1, btn_col2 = cols[4].columns(2)
        if btn_col1.button("보기", key=f"view_{rid}", use_container_width=True):
            st.session_state["view_report_id"] = rid
            st.rerun()
        if btn_col2.button("삭제", key=f"del_{rid}", use_container_width=True):
            st.session_state["confirm_delete_id"] = rid

        if st.session_state.get("confirm_delete_id") == rid:
            st.warning("이 이력을 삭제하시겠습니까? 삭제 시 연결된 보고서도 함께 삭제됩니다.")
            c1, c2, _ = st.columns([1, 1, 4])
            if c1.button("확인", key=f"del_yes_{rid}"):
                delete_report(rid)
                st.session_state.pop("confirm_delete_id", None)
                st.rerun()
            if c2.button("취소", key=f"del_no_{rid}"):
                st.session_state.pop("confirm_delete_id", None)
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# mode B: 상세 뷰
# ─────────────────────────────────────────────────────────────────────────────

def _render_detail(user: dict, report_id: int) -> None:
    if st.button("← 목록으로"):
        st.session_state.pop("view_report_id", None)
        st.rerun()

    report = get_report_by_id(report_id)
    if not report:
        st.error("보고서를 찾을 수 없습니다.")
        st.session_state.pop("view_report_id", None)
        st.rerun()
        return

    if report["user_id"] != user["id"]:
        st.error("접근 권한이 없습니다.")
        st.session_state.pop("view_report_id", None)
        st.rerun()
        return

    try:
        result: dict = json.loads(report["result"] or "{}")
    except Exception:
        st.error("보고서 데이터가 손상되었습니다.")
        return

    date_str = report["created_at"][:10] if report.get("created_at") else "-"

    col_title, col_pdf = st.columns([7, 3])
    col_title.markdown("## 법률 자문 보고서")
    col_title.caption(f"작성일: {date_str}")

    with col_pdf:
        st.write("")
        _render_pdf_download(report, result, date_str)

    st.divider()

    summary = result.get("summary") or report.get("summary") or ""
    if summary:
        st.info(f"**요청 요약:** {summary}")

    # 1. 적용 법령
    laws = result.get("applicable_laws", [])
    st.markdown(
        '<div class="result-header"><span class="result-section-badge">1</span>적용 법령</div>',
        unsafe_allow_html=True,
    )
    if laws:
        for law in laws:
            with st.expander(f"{law.get('law_name', '')} {law.get('article', '')}", expanded=True):
                st.write(law.get("content", ""))
    else:
        st.caption("해당 법령 없음")

    # 2. 관련 판례
    precs = result.get("precedents", [])
    st.markdown(
        '<div class="result-header"><span class="result-section-badge">2</span>관련 판례</div>',
        unsafe_allow_html=True,
    )
    if precs:
        for p in precs:
            with st.expander(p.get("case_no", "판례"), expanded=False):
                if p.get("summary"):
                    st.write(f"**판결 요지:** {p['summary']}")
                if p.get("relevance"):
                    st.write(f"**관련성:** {p['relevance']}")
    else:
        st.caption("관련 판례 없음")

    # 3. 결론
    conclusion = result.get("conclusion", "")
    st.markdown(
        '<div class="result-header"><span class="result-section-badge">3</span>결론</div>',
        unsafe_allow_html=True,
    )
    if conclusion:
        st.markdown(conclusion)
    else:
        st.caption("-")

    # 4. 회색지대
    if has_gray_area(result):
        st.markdown(
            '<div class="result-header"><span class="result-section-badge" style="background:#e67e22;">⚠</span>불확실 영역</div>',
            unsafe_allow_html=True,
        )
        st.warning(format_gray_area_text(result))

    # 5. 유사 과거 요청
    similar_ids: list = result.get("similar_history", [])
    if similar_ids:
        st.markdown(
            '<div class="result-header"><span class="result-section-badge">5</span>유사 과거 요청</div>',
            unsafe_allow_html=True,
        )
        reports_map = {r["id"]: r for r in get_reports_by_user(user["id"])}
        found_any = False
        for rid in similar_ids:
            if rid == report_id:
                continue
            r = reports_map.get(rid)
            if r:
                found_any = True
                d = r["created_at"][:10] if r.get("created_at") else "-"
                s = r["summary"] or "(요약 없음)"
                if st.button(f"📄 {d} — {s}", key=f"sim_hist_{rid}"):
                    st.session_state["view_report_id"] = rid
                    st.rerun()
        if not found_any:
            st.caption("유사 이력 없음")

    prompt_text = report.get("prompt", "")
    if prompt_text:
        with st.expander("자문 요청 원문 보기", expanded=False):
            st.text(prompt_text)


# ─────────────────────────────────────────────────────────────────────────────
# PDF 다운로드 버튼
# ─────────────────────────────────────────────────────────────────────────────

def _render_pdf_download(report: dict, result: dict, date_str: str) -> None:
    cache_key = f"pdf_cache_{report['id']}"
    filename = f"법률자문보고서_{date_str}.pdf"

    if cache_key in st.session_state:
        st.download_button(
            label="📥 PDF 다운로드",
            data=st.session_state[cache_key],
            file_name=filename,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
            key=f"dl_{report['id']}",
        )
        return

    if st.button("📄 PDF 생성", use_container_width=True, key=f"gen_{report['id']}"):
        with st.spinner("PDF 생성 중..."):
            try:
                st.session_state[cache_key] = generate_report_pdf(report, result)
                st.rerun()
            except Exception as e:
                st.error(f"PDF 생성 실패: {e}")
