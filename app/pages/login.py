"""
app/pages/login.py — 로그인 / 회원가입 UI

로그인 탭:
  - 아이디 + OTP 입력
  - admin 최초 로그인(totp_enabled=False) 시 OTP 필드 숨김

회원가입 탭 (2단계):
  Step 1: 아이디 입력 + 중복 확인
  Step 2: QR 코드 표시 → OTP 검증 → 계정 생성
"""

import streamlit as st
from app.components.auth import login_with_otp, login_admin_first, navigate
from core.auth import generate_totp_secret, generate_qr_code, verify_otp
from core.models import get_user_by_username, create_user


_LOGIN_CSS = """
<style>
/* 로그인 페이지 전용 */
.login-hero {
    text-align: center;
    padding: 2.5rem 0 1.5rem 0;
}
.login-hero .brand-icon {
    font-size: 3rem;
    line-height: 1;
    margin-bottom: 0.5rem;
}
.login-hero h1 {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    color: #1a3c6e !important;
    margin: 0 !important;
    letter-spacing: -0.03em;
}
.login-hero .brand-sub {
    font-size: 0.875rem;
    color: #6b7a99;
    margin-top: 0.35rem;
    font-weight: 400;
}
.login-card {
    background: #ffffff;
    border: 1px solid #dde3ed;
    border-radius: 16px;
    padding: 2rem 2rem 1.5rem 2rem;
    box-shadow: 0 4px 24px rgba(26,60,110,0.08);
    margin-bottom: 1.5rem;
}
.login-divider {
    height: 1px;
    background: #eef1f7;
    margin: 1.25rem 0;
}
.login-footer {
    text-align: center;
    color: #9ba8bf;
    font-size: 0.78rem;
    margin-top: 1rem;
}
</style>
"""


def render() -> None:
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # 중앙 정렬을 위한 컬럼
    _, col_center, _ = st.columns([1, 2, 1])

    with col_center:
        # 브랜드 헤더
        st.markdown("""
        <div class="login-hero">
            <div class="brand-icon">⚖️</div>
            <h1>한국 법 자문 서비스</h1>
            <div class="brand-sub">AI 기반 법령 검색 및 법률 자문 플랫폼</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="login-card">', unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["로그인", "회원가입"])

        with tab_login:
            _render_login()

        with tab_register:
            _render_register()

        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(
            '<div class="login-footer">보안을 위해 OTP(TOTP) 인증을 사용합니다.</div>',
            unsafe_allow_html=True,
        )


def _render_login() -> None:
    st.write("")
    username = st.text_input("아이디", key="login_username", placeholder="아이디 입력")

    # admin 최초 로그인 여부 판단
    is_admin_first = False
    if username.strip() == "admin":
        user = get_user_by_username("admin")
        if user and not user["totp_enabled"]:
            is_admin_first = True

    if is_admin_first:
        st.info("관리자 최초 로그인입니다. OTP 등록 후 이용 가능합니다.")
        if st.button("관리자 최초 로그인", type="primary", key="btn_admin_first", use_container_width=True):
            ok, msg = login_admin_first(username)
            if ok:
                for key in ("login_username", "login_otp"):
                    st.session_state.pop(key, None)
                st.rerun()
            else:
                st.error(msg)
    else:
        otp_code = st.text_input("OTP 코드", max_chars=6, key="login_otp", placeholder="6자리 숫자")
        st.write("")
        if st.button("로그인", type="primary", key="btn_login", use_container_width=True):
            if not username.strip():
                st.error("아이디를 입력하세요.")
            elif not otp_code.strip():
                st.error("OTP 코드를 입력하세요.")
            else:
                ok, msg = login_with_otp(username, otp_code)
                if ok:
                    for key in ("login_username", "login_otp"):
                        st.session_state.pop(key, None)
                    st.rerun()
                else:
                    st.error(msg)


def _render_register() -> None:
    st.write("")
    step = st.session_state.get("register_step", 1)

    if step == 1:
        _register_step1()
    else:
        _register_step2()


def _register_step1() -> None:
    st.caption("사용할 아이디를 입력하세요. (3자 이상)")
    username = st.text_input("아이디", key="reg_username", placeholder="영문/숫자 3자 이상")

    st.write("")
    if st.button("다음 →", type="primary", key="btn_reg_next", use_container_width=True):
        username = username.strip()
        if not username:
            st.error("아이디를 입력하세요.")
            return
        if len(username) < 3:
            st.error("아이디는 3자 이상이어야 합니다.")
            return
        if get_user_by_username(username):
            st.error("이미 사용 중인 아이디입니다.")
            return

        secret = generate_totp_secret()
        st.session_state["register_step"] = 2
        st.session_state["register_username"] = username
        st.session_state["register_secret"] = secret
        st.rerun()


def _register_step2() -> None:
    username = st.session_state.get("register_username", "")
    secret = st.session_state.get("register_secret", "")

    st.markdown(f"**아이디:** `{username}`")
    st.caption("Google Authenticator 앱으로 아래 QR 코드를 스캔하세요.")

    qr_bytes = generate_qr_code(username, secret)

    _, qr_col, _ = st.columns([1, 2, 1])
    with qr_col:
        st.image(qr_bytes, use_container_width=True)

    otp_code = st.text_input("앱 표시 코드", max_chars=6, key="reg_otp", placeholder="6자리 숫자 입력")

    st.write("")
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("← 이전", key="btn_reg_back", use_container_width=True):
            st.session_state["register_step"] = 1
            st.session_state.pop("register_username", None)
            st.session_state.pop("register_secret", None)
            st.rerun()
    with col2:
        if st.button("등록 완료", type="primary", key="btn_reg_done", use_container_width=True):
            if not otp_code.strip():
                st.error("OTP 코드를 입력하세요.")
                return
            if not verify_otp(secret, otp_code):
                st.error("OTP 코드가 올바르지 않습니다. 앱 시간 동기화를 확인하고 다시 시도하세요.")
                return

            create_user(username, secret)

            st.session_state.pop("register_step", None)
            st.session_state.pop("register_username", None)
            st.session_state.pop("register_secret", None)

            st.success("회원가입이 완료됐습니다. 로그인 탭에서 로그인하세요.")
