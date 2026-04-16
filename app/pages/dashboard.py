"""
app/pages/dashboard.py — 자문 요청 메인 페이지

구성:
  좌측 (35%): 템플릿 선택 / 생성 / 수정 / 삭제
  우측 (65%): 현재 상황 + 자문 요청 + history ON/OFF + [자문 요청 시작]
  하단:       결과 표시 + [보고서 저장]
"""

import json

import streamlit as st

from app.components.auth import get_current_user, require_login, navigate
from core.advisor.claude_client import generate_advisory
from core.advisor.gray_area import has_gray_area, format_gray_area_text
from core.models import (
    get_templates_by_user, get_template_by_id,
    create_template, update_template, delete_template,
    get_reports_by_user, create_report,
    get_report_by_id, get_user_api_keys,
)

# 템플릿 항목 정의 (순서 유지)
_TEMPLATE_FIELDS = [
    ("size",          "회사 규모",         ["대기업", "중견기업", "중소기업", "스타트업"]),
    ("sector",        "업종",              ["IT/소프트웨어", "금융/핀테크", "제조", "의료/헬스케어", "공공/공급망", "유통/이커머스", "기타"]),
    ("cert",          "보유 인증",         ["없음", "ISMS-P", "ISO27001", "ISMS-P + ISO27001"]),
    ("privacy",       "개인정보 처리",     ["처리", "처리 안 함"]),
    ("employees",     "임직원 수",         ["50명 이하", "51~300명", "300명 초과"]),
    ("privacy_scale", "개인정보 처리 규모",["1만명 미만", "1만~100만명", "100만명 초과"]),
    ("overseas",      "해외 서비스",       ["없음", "있음"]),
    ("listed",        "상장 여부",         ["비상장", "상장"]),
    ("data_type",     "주요 데이터 유형",  ["개인정보", "민감정보", "기술자료", "복합"]),
]

_DASHBOARD_CSS = """
<style>
/* 대시보드 전용 */
.panel-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
}
.panel-header .panel-icon {
    width: 28px;
    height: 28px;
    background: #1a3c6e;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    flex-shrink: 0;
}
.panel-header h3 {
    margin: 0 !important;
    font-size: 1rem !important;
    font-weight: 600 !important;
    color: #1a1f2e !important;
}
.tpl-tag {
    display: inline-block;
    background: #eef2fa;
    color: #1a3c6e;
    border-radius: 5px;
    padding: 0.12rem 0.55rem;
    font-size: 0.78rem;
    font-weight: 500;
    margin: 0.15rem 0.1rem;
    border: 1px solid #cdd7ee;
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
.save-success-box {
    background: #edf7ed;
    border: 1px solid #b2dfb2;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    color: #2e7d32;
    font-weight: 500;
}
</style>
"""


def render() -> None:
    require_login()
    user = get_current_user()

    st.markdown(_DASHBOARD_CSS, unsafe_allow_html=True)
    st.title("자문 요청")

    col_left, col_right = st.columns([35, 65])

    with col_left:
        _render_template_panel(user)

    with col_right:
        _render_request_form(user)

    # 자문 결과 표시
    if st.session_state.get("advisor_result"):
        st.divider()
        _render_result(user)


# ─────────────────────────────────────────────────────────────────────────────
# 좌측: 템플릿 패널
# ─────────────────────────────────────────────────────────────────────────────

def _render_template_panel(user: dict) -> None:
    st.markdown("""
    <div class="panel-header">
      <div class="panel-icon">🏢</div>
      <h3>회사 컨텍스트</h3>
    </div>
    """, unsafe_allow_html=True)

    templates = get_templates_by_user(user["id"])

    # ── 템플릿 selectbox ─────────────────────────────────────────────────────
    options = ["템플릿 없음"] + [t["template_name"] for t in templates]
    saved_id = st.session_state.get("selected_template_id")

    valid_ids = {t["id"] for t in templates}
    if saved_id not in valid_ids:
        st.session_state["selected_template_id"] = None
        saved_id = None

    saved_name = None
    if saved_id:
        for t in templates:
            if t["id"] == saved_id:
                saved_name = t["template_name"]
                break

    default_idx = 0
    if saved_name and saved_name in options:
        default_idx = options.index(saved_name)

    selected_name = st.selectbox(
        "템플릿 선택",
        options,
        index=default_idx,
        key="template_selectbox",
    )

    selected_template = None
    if selected_name != "템플릿 없음":
        for t in templates:
            if t["template_name"] == selected_name:
                selected_template = t
                st.session_state["selected_template_id"] = t["id"]
                break
    else:
        st.session_state["selected_template_id"] = None

    # ── 선택된 템플릿 항목 표시 ───────────────────────────────────────────────
    if selected_template:
        items = json.loads(selected_template["items"])
        tag_html = ""
        for key, label, _ in _TEMPLATE_FIELDS:
            item = items.get(key, {})
            if item.get("enabled", True):
                tag_html += f'<span class="tpl-tag">{label}: {item.get("value", "-")}</span>'
        if tag_html:
            st.markdown(tag_html, unsafe_allow_html=True)
            st.write("")

        col_edit, col_del = st.columns(2)
        if col_edit.button("✏️ 수정", key="btn_tpl_edit", use_container_width=True):
            st.session_state["template_edit_mode"] = True
            st.session_state["template_create_mode"] = False
        if col_del.button("🗑 삭제", key="btn_tpl_del", use_container_width=True):
            st.session_state["template_delete_confirm"] = True

    # ── 삭제 확인 ────────────────────────────────────────────────────────────
    if st.session_state.get("template_delete_confirm") and selected_template:
        st.warning(f"**{selected_template['template_name']}** 을(를) 삭제하시겠습니까?")
        del_mode = st.radio(
            "삭제 범위",
            ["템플릿만 삭제 (연결된 보고서 이력 유지)", "템플릿 + 연결된 보고서 이력 모두 삭제"],
            key="del_mode_radio",
        )
        c1, c2 = st.columns(2)
        if c1.button("확인", key="btn_del_confirm"):
            delete_reports = "모두 삭제" in del_mode
            delete_template(selected_template["id"], delete_reports=delete_reports)
            st.session_state.pop("template_delete_confirm", None)
            st.session_state["selected_template_id"] = None
            st.rerun()
        if c2.button("취소", key="btn_del_cancel"):
            st.session_state.pop("template_delete_confirm", None)
            st.rerun()

    # ── 새 템플릿 만들기 버튼 ────────────────────────────────────────────────
    st.divider()
    if not st.session_state.get("template_create_mode") and not st.session_state.get("template_edit_mode"):
        if st.button("＋ 새 템플릿 만들기", use_container_width=True):
            st.session_state["template_create_mode"] = True
            st.session_state["template_edit_mode"] = False
            st.rerun()

    # ── 템플릿 생성 폼 ────────────────────────────────────────────────────────
    if st.session_state.get("template_create_mode"):
        _render_template_form(user, mode="create", existing=None)

    # ── 템플릿 수정 폼 ────────────────────────────────────────────────────────
    if st.session_state.get("template_edit_mode") and selected_template:
        _render_template_form(user, mode="edit", existing=selected_template)


def _render_template_form(user: dict, mode: str, existing: dict | None) -> None:
    """템플릿 생성/수정 폼."""
    title = "새 템플릿" if mode == "create" else "템플릿 수정"
    st.markdown(f"**{title}**")

    existing_items = json.loads(existing["items"]) if existing else {}
    existing_name = existing["template_name"] if existing else ""

    template_name = st.text_input("템플릿 이름", value=existing_name, key=f"tpl_name_{mode}")

    items: dict = {}
    for key, label, choices in _TEMPLATE_FIELDS:
        ex = existing_items.get(key, {})
        enabled_default = ex.get("enabled", True)
        value_default = ex.get("value", choices[0])

        col_chk, col_sel = st.columns([1, 3])
        enabled = col_chk.checkbox("사용", value=enabled_default, key=f"tpl_{mode}_{key}_en")

        if value_default in choices:
            val_idx = choices.index(value_default)
        else:
            val_idx = 0

        value = col_sel.selectbox(label, choices, index=val_idx, key=f"tpl_{mode}_{key}_val", disabled=not enabled)
        items[key] = {"value": value, "enabled": enabled}

    col1, col2 = st.columns(2)
    if col1.button("저장", type="primary", key=f"btn_tpl_{mode}_save"):
        if not template_name.strip():
            st.error("템플릿 이름을 입력하세요.")
        else:
            items_json = json.dumps(items, ensure_ascii=False)
            if mode == "create":
                create_template(user["id"], template_name.strip(), items_json)
            else:
                update_template(existing["id"], template_name=template_name.strip(), items=items_json)
            st.session_state.pop("template_create_mode", None)
            st.session_state.pop("template_edit_mode", None)
            st.rerun()

    if col2.button("취소", key=f"btn_tpl_{mode}_cancel"):
        st.session_state.pop("template_create_mode", None)
        st.session_state.pop("template_edit_mode", None)
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# 우측: 자문 요청 폼
# ─────────────────────────────────────────────────────────────────────────────

def _render_request_form(user: dict) -> None:
    env_context = st.text_area(
        "현재 상황",
        height=110,
        placeholder="예) 사무실 내 CCTV 8대 신규 설치 예정. 직원 및 방문자 출입 관리 목적.",
        key="env_context_input",
    )

    user_query = st.text_area(
        "자문 요청",
        height=140,
        placeholder="예) CCTV 설치 시 개인정보 처리방침 고지 의무와 직원 동의 절차가 어떻게 되나요?",
        key="user_query_input",
    )

    col_toggle, col_btn = st.columns([2, 3])
    with col_toggle:
        history_on = st.toggle(
            "과거 이력 참고",
            value=(st.session_state.get("history_mode", "OFF") == "ON"),
            key="history_toggle",
        )
        st.session_state["history_mode"] = "ON" if history_on else "OFF"
        if history_on:
            st.caption("과거 자문 이력을 참고하여 더 정확한 맥락을 제공합니다.")

    with col_btn:
        st.write("")
        submitted = st.button("⚖️ 자문 요청 시작", type="primary", use_container_width=True)

    if submitted:
        if not user_query.strip():
            st.error("자문 요청 내용을 입력하세요.")
            return

        template_id = st.session_state.get("selected_template_id")
        template_dict = None
        if template_id:
            tpl = get_template_by_id(template_id)
            if tpl:
                raw = json.loads(tpl["items"])
                template_dict = {
                    k: v["value"]
                    for k, v in raw.items()
                    if v.get("enabled", True)
                }

        reports = get_reports_by_user(user["id"])
        history_list = [
            {"id": r["id"], "summary": r["summary"] or ""}
            for r in reports
        ][-100:]

        history_mode = st.session_state.get("history_mode", "OFF")

        user_keys = get_user_api_keys(user["id"])
        claude_key = user_keys["llm_api_key"]
        law_key    = user_keys["law_api_key"]

        if not claude_key:
            st.error("LLM API 키가 등록되지 않았습니다. 마이페이지에서 Claude API 키를 등록하세요.")
            return

        with st.spinner("자문 생성 중... (30초~2분 소요)"):
            try:
                result = generate_advisory(
                    template=template_dict,
                    env_context=env_context.strip(),
                    user_query=user_query.strip(),
                    history_list=history_list,
                    history_mode=history_mode,
                    claude_api_key=claude_key,
                    law_api_key=law_key,
                )
                st.session_state["advisor_result"] = result
                st.session_state["advisor_saved"] = False
                st.session_state["advisor_prompt"] = user_query.strip()
                st.session_state["advisor_env_context"] = env_context.strip()
                st.rerun()
            except Exception as e:
                st.error(f"자문 생성 실패: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 하단: 결과 표시
# ─────────────────────────────────────────────────────────────────────────────

def _render_result(user: dict) -> None:
    result: dict = st.session_state["advisor_result"]

    st.subheader("자문 결과")

    # 요청 요약
    summary = result.get("summary", "")
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
                st.write(f"**판결 요지:** {p.get('summary', '')}")
                st.write(f"**관련성:** {p.get('relevance', '')}")
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
        for rid in similar_ids:
            r = reports_map.get(rid)
            if r:
                date = r["created_at"][:10]
                summary = r["summary"] or "(요약 없음)"
                if st.button(f"📄 {date} — {summary}", key=f"sim_{rid}"):
                    st.session_state["page"] = "history"
                    st.session_state["view_report_id"] = rid
                    st.rerun()

    st.divider()

    # 보고서 저장
    if st.session_state.get("advisor_saved"):
        st.markdown(
            '<div class="save-success-box">✅ 보고서가 저장되었습니다. 자문 이력에서 확인하세요.</div>',
            unsafe_allow_html=True,
        )
    else:
        if st.button("💾 보고서 저장", type="primary", use_container_width=True):
            _save_report(user, result)


def _save_report(user: dict, result: dict) -> None:
    template_id = st.session_state.get("selected_template_id")
    tpl = get_template_by_id(template_id) if template_id else None
    template_snapshot = tpl["items"] if tpl else None

    env_context = st.session_state.get("advisor_env_context", "")
    user_query = st.session_state.get("advisor_prompt", "")

    prompt_text = ""
    if env_context:
        prompt_text += f"[현재 상황]\n{env_context}\n\n"
    prompt_text += f"[자문 요청]\n{user_query}"

    create_report(
        user_id=user["id"],
        template_id=template_id,
        template_snapshot=template_snapshot,
        summary=result.get("summary", ""),
        prompt=prompt_text,
        result=json.dumps(result, ensure_ascii=False),
    )
    st.session_state["advisor_saved"] = True
    st.rerun()
