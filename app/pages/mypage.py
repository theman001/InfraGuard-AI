"""
app/pages/mypage.py — 마이페이지

탭 1: API 키 관리
  - 국가법령 API 키 (LAW_OC_ID)
  - LLM API 키 (Claude)
  - 각 키는 암호화 저장, 입력 시 마스킹

탭 2: OTP 재등록 (본인 계정)
"""

import streamlit as st

from app.components.auth import get_current_user, require_login
from core.auth import generate_totp_secret, generate_qr_code, verify_otp
from core.models import get_user_api_keys, update_user_api_keys, update_user_totp


_MYPAGE_CSS = """
<style>
/* 마이페이지 전용 */
.api-card {
    background: #fff;
    border: 1px solid #dde3ed;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 8px rgba(26,60,110,0.05);
}
.api-card-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.6rem;
}
.api-card-header .api-icon {
    font-size: 1.25rem;
}
.api-card-header h4 {
    margin: 0 !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: #1a1f2e !important;
}
.api-status-ok {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: #edf7ed;
    color: #2e7d32;
    border: 1px solid #b2dfb2;
    border-radius: 6px;
    padding: 0.2rem 0.6rem;
    font-size: 0.8rem;
    font-weight: 600;
}
.api-status-missing {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: #fff8e1;
    color: #c77700;
    border: 1px solid #ffe082;
    border-radius: 6px;
    padding: 0.2rem 0.6rem;
    font-size: 0.8rem;
    font-weight: 600;
}
.api-masked-key {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    background: #f0f3fa;
    border-radius: 5px;
    padding: 0.2rem 0.5rem;
    color: #3a4a6b;
    margin-left: 0.4rem;
}
.summary-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-top: 0.5rem;
}
.summary-cell {
    background: #f5f7fa;
    border: 1px solid #dde3ed;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    text-align: center;
}
.summary-cell .cell-label {
    font-size: 0.78rem;
    color: #6b7a99;
    font-weight: 500;
    margin-bottom: 0.25rem;
}
.summary-cell .cell-value {
    font-size: 1rem;
    font-weight: 700;
}
.summary-cell.ok .cell-value { color: #2e7d32; }
.summary-cell.missing .cell-value { color: #c77700; }
</style>
"""


def render() -> None:
    require_login()
    user = get_current_user()

    st.markdown(_MYPAGE_CSS, unsafe_allow_html=True)
    st.title("마이페이지")
    st.caption(f"계정: **{user['username']}** ({user['role']})")

    try:
        tab_api, tab_otp = st.tabs(["API 키 관리", "OTP 재등록"])

        with tab_api:
            _render_api_keys(user)

        with tab_otp:
            _render_otp_reregister(user)
    except Exception as e:
        st.error(f"마이페이지 로드 오류: {e}")
        import traceback
        st.code(traceback.format_exc())


# ─────────────────────────────────────────────────────────────────────────────
# 탭 1: API 키 관리
# ─────────────────────────────────────────────────────────────────────────────

def _render_api_keys(user: dict) -> None:
    st.markdown(
        "입력한 API 키는 **AES 암호화(Fernet)**되어 DB에 저장됩니다. "
        "다른 사용자의 키는 절대 공유되지 않습니다.",
    )
    st.write("")

    keys = get_user_api_keys(user["id"])
    has_law_key = bool(keys["law_api_key"])
    has_llm_key = bool(keys["llm_api_key"])

    # ── 국가법령 API 키 카드 ──────────────────────────────────────────────────
    st.markdown('<div class="api-card">', unsafe_allow_html=True)
    st.markdown("""
    <div class="api-card-header">
      <span class="api-icon">📜</span>
      <h4>국가법령정보 API 키 (OC ID)</h4>
    </div>
    """, unsafe_allow_html=True)
    st.caption("https://open.law.go.kr 에서 발급. 판례·법령 실시간 검색에 사용됩니다.")

    if has_law_key:
        masked = keys["law_api_key"][:4] + "****" + keys["law_api_key"][-2:] if len(keys["law_api_key"]) > 6 else "****"
        st.markdown(
            f'<span class="api-status-ok">✅ 등록됨</span>'
            f'<span class="api-masked-key">{masked}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<span class="api-status-missing">⚠ 미등록</span>', unsafe_allow_html=True)
    st.write("")

    law_key_input = st.text_input(
        "새 키 입력",
        type="password",
        placeholder="예: username (OC_ID 값)",
        key="input_law_key",
        label_visibility="collapsed",
    )
    col1, col2, col3 = st.columns([2, 2, 6])
    if col1.button("저장", key="btn_save_law", use_container_width=True, type="primary"):
        if not law_key_input.strip():
            st.error("API 키를 입력하세요.")
        else:
            update_user_api_keys(user["id"], law_api_key=law_key_input.strip())
            st.success("국가법령 API 키가 저장되었습니다.")
            st.rerun()
    if has_law_key:
        if col2.button("삭제", key="btn_del_law", use_container_width=True):
            update_user_api_keys(user["id"], law_api_key="")
            st.success("국가법령 API 키가 삭제되었습니다.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── LLM API 키 카드 ────────────────────────────────────────────────────
    st.markdown('<div class="api-card">', unsafe_allow_html=True)
    st.markdown("""
    <div class="api-card-header">
      <span class="api-icon">🤖</span>
      <h4>Claude LLM API 키</h4>
    </div>
    """, unsafe_allow_html=True)
    st.caption("https://console.anthropic.com 에서 발급. 자문 생성에 사용됩니다.")

    if has_llm_key:
        masked = keys["llm_api_key"][:8] + "****" + keys["llm_api_key"][-4:] if len(keys["llm_api_key"]) > 12 else "****"
        st.markdown(
            f'<span class="api-status-ok">✅ 등록됨</span>'
            f'<span class="api-masked-key">{masked}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<span class="api-status-missing">⚠ 미등록 — 자문 요청이 불가합니다</span>', unsafe_allow_html=True)
    st.write("")

    llm_key_input = st.text_input(
        "새 키 입력",
        type="password",
        placeholder="sk-ant-api03-...",
        key="input_llm_key",
        label_visibility="collapsed",
    )
    col3, col4, col5 = st.columns([2, 2, 6])
    if col3.button("저장", key="btn_save_llm", use_container_width=True, type="primary"):
        if not llm_key_input.strip():
            st.error("API 키를 입력하세요.")
        elif not llm_key_input.strip().startswith("sk-"):
            st.error("올바른 Claude API 키 형식이 아닙니다. (sk-ant-api03-... 형식)")
        else:
            update_user_api_keys(user["id"], llm_api_key=llm_key_input.strip())
            st.success("LLM API 키가 저장되었습니다.")
            st.rerun()
    if has_llm_key:
        if col4.button("삭제", key="btn_del_llm", use_container_width=True):
            update_user_api_keys(user["id"], llm_api_key="")
            st.success("LLM API 키가 삭제되었습니다.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── 키 상태 요약 ──────────────────────────────────────────────────────────
    law_cls   = "ok" if has_law_key else "missing"
    llm_cls   = "ok" if has_llm_key else "missing"
    law_val   = "등록됨 ✅" if has_law_key else "미등록 ⚠"
    llm_val   = "등록됨 ✅" if has_llm_key else "미등록 ⚠"

    st.markdown(f"""
    <div class="summary-grid">
      <div class="summary-cell {law_cls}">
        <div class="cell-label">국가법령 API</div>
        <div class="cell-value">{law_val}</div>
      </div>
      <div class="summary-cell {llm_cls}">
        <div class="cell-label">LLM API (Claude)</div>
        <div class="cell-value">{llm_val}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not has_law_key or not has_llm_key:
        st.write("")
        st.info(
            "두 키가 모두 등록되어야 자문 서비스를 정상 이용할 수 있습니다.\n\n"
            "- **국가법령 API**: 판례·법령 실시간 검색에 필요\n"
            "- **LLM API**: Claude 자문 생성에 필요"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 탭 2: OTP 재등록
# ─────────────────────────────────────────────────────────────────────────────

def _render_otp_reregister(user: dict) -> None:
    st.subheader("OTP 재등록")
    st.caption("Google Authenticator 앱을 변경했거나 기기를 교체한 경우 재등록하세요.")

    if not st.session_state.get("mypage_otp_step"):
        if st.button("OTP 재등록 시작", type="primary", key="btn_otp_start"):
            st.session_state["mypage_otp_step"] = "qr"
            st.session_state.pop("mypage_otp_secret", None)
            st.rerun()
        return

    # QR 생성 단계
    if "mypage_otp_secret" not in st.session_state:
        st.session_state["mypage_otp_secret"] = generate_totp_secret()

    secret = st.session_state["mypage_otp_secret"]
    qr_bytes = generate_qr_code(user["username"], secret)

    st.write("아래 QR 코드를 Google Authenticator 앱으로 스캔하세요.")

    _, qr_col, _ = st.columns([1, 2, 1])
    with qr_col:
        st.image(qr_bytes, use_container_width=True)

    otp_code = st.text_input("앱에 표시된 6자리 코드 입력", max_chars=6, key="mypage_otp_code",
                              placeholder="123456")

    col1, col2 = st.columns(2)
    if col1.button("등록 완료", type="primary", key="btn_otp_done", use_container_width=True):
        if not otp_code.strip():
            st.error("OTP 코드를 입력하세요.")
        elif not verify_otp(secret, otp_code):
            st.error("OTP 코드가 올바르지 않습니다. 앱 시간 동기화를 확인하세요.")
        else:
            update_user_totp(user["username"], secret, 1)
            st.session_state["user"]["totp_enabled"] = True
            st.session_state.pop("mypage_otp_step", None)
            st.session_state.pop("mypage_otp_secret", None)
            st.success("OTP 재등록 완료!")
            st.rerun()

    if col2.button("취소", key="btn_otp_cancel", use_container_width=True):
        st.session_state.pop("mypage_otp_step", None)
        st.session_state.pop("mypage_otp_secret", None)
        st.rerun()
