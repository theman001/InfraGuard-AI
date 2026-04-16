"""
app/components/auth.py — Streamlit 세션 기반 인증 헬퍼

세션 유지 방식:
  - 로그인 시: 토큰 생성 → DB 저장 → session_state["_pending_cookie"] 예약
  - main.py가 CookieManager를 렌더한 뒤 예약된 쿠키를 설정 (JS 실행 보장)
  - 새로고침 시: st.context.cookies(HTTP 헤더)에서 토큰 읽기 → 복원
  - 로그아웃 시: session_state["_pending_cookie_delete"] 예약 → main.py에서 처리

핵심: mgr.set()을 st.rerun() 이전 같은 렌더 사이클에서 호출하면
      JS가 실행되기 전에 WebSocket이 재연결돼 쿠키가 저장되지 않음.
      → set/delete를 다음 렌더로 지연해 CookieManager 렌더 후 처리.
"""

import secrets
from datetime import datetime, timedelta

import streamlit as st
import extra_streamlit_components as stx

from core.models import (
    get_user_by_username,
    create_session_token,
    get_session_user,
    delete_session_token,
)
from core.auth import verify_otp

_COOKIE_NAME = "infraguard_session"
_SESSION_DAYS = 7


# ─────────────────────────────────────────────────────────────────────────────
# 쿠키 읽기: st.context.cookies (HTTP 헤더, 동기, 항상 신뢰 가능)
# 쿠키 쓰기/삭제: main.py에서 CookieManager 렌더 후 처리 (지연 방식)
# ─────────────────────────────────────────────────────────────────────────────

def _read_cookie(name: str) -> str | None:
    """HTTP 요청 헤더에서 직접 쿠키 읽기."""
    return st.context.cookies.get(name)


def process_pending_cookie(mgr: stx.CookieManager) -> None:
    """
    main.py에서 CookieManager 렌더 직후 호출.
    예약된 쿠키 set/delete를 처리한다.
    """
    if "_pending_cookie" in st.session_state:
        token, expires = st.session_state.pop("_pending_cookie")
        mgr.set(_COOKIE_NAME, token, expires_at=expires)

    if st.session_state.pop("_pending_cookie_delete", False):
        mgr.delete(_COOKIE_NAME)


# ─────────────────────────────────────────────────────────────────────────────
# 세션 복원 — main.py 최상단에서 1회 호출
# ─────────────────────────────────────────────────────────────────────────────

def restore_session() -> None:
    """
    새로고침 시 쿠키 토큰으로 session_state["user"] 복원.
    이미 로그인 상태면 아무것도 하지 않음.
    """
    if st.session_state.get("user"):
        return

    token = _read_cookie(_COOKIE_NAME)
    if not token:
        return

    user = get_session_user(token)
    if not user:
        st.session_state["_pending_cookie_delete"] = True
        return

    _apply_session(user)


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def get_current_user() -> dict | None:
    return st.session_state.get("user")


def navigate(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


def logout() -> None:
    token = _read_cookie(_COOKIE_NAME)
    if token:
        delete_session_token(token)
    # 쿠키 삭제를 다음 렌더(main.py CookieManager 렌더 후)로 예약
    st.session_state["_pending_cookie_delete"] = True

    for key in ("login_username", "login_otp"):
        st.session_state.pop(key, None)
    st.session_state["user"] = None
    st.session_state["page"] = "login"
    st.rerun()


def login_with_otp(username: str, otp_code: str) -> tuple[bool, str]:
    """일반 로그인 (OTP 등록된 계정)."""
    clean_username = username.strip()
    if not clean_username:
        return False, "아이디를 입력하세요."

    user = get_user_by_username(clean_username)
    if not user:
        return False, "등록되지 않은 아이디입니다."
    if user["username"] != clean_username:
        return False, "인증 오류가 발생했습니다. 다시 시도하세요."
    if user["status"] == "suspended":
        return False, "정지된 계정입니다. 관리자에게 문의하세요."
    if not user["totp_enabled"]:
        return False, "OTP가 등록되지 않은 계정입니다."
    if not verify_otp(user["totp_secret"], otp_code):
        return False, "OTP 코드가 올바르지 않습니다."

    _set_session(user)
    return True, ""


def login_admin_first(username: str) -> tuple[bool, str]:
    """admin 최초 로그인 — totp_enabled=0인 admin 계정만 OTP 없이 1회 허용."""
    if username.strip() != "admin":
        return False, "등록되지 않은 아이디입니다."

    user = get_user_by_username("admin")
    if not user:
        return False, "admin 계정을 찾을 수 없습니다."
    if user["totp_enabled"]:
        return False, "이미 OTP가 등록된 계정입니다. OTP 코드를 입력하세요."
    if user["status"] == "suspended":
        return False, "정지된 계정입니다."

    _set_session(user)
    return True, ""


def require_login() -> None:
    if not get_current_user():
        st.session_state["page"] = "login"
        st.rerun()


def require_admin() -> None:
    require_login()
    user = get_current_user()
    if user and user["role"] != "admin":
        st.warning("접근 권한이 없습니다.")
        navigate("dashboard")


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _set_session(user: dict) -> None:
    """
    로그인 성공 시: 토큰 생성 → DB 저장 → 쿠키 예약 → session_state 설정.
    쿠키 set은 main.py에서 CookieManager 렌더 후 처리 (JS 실행 보장).
    """
    token = secrets.token_urlsafe(32)
    expires_at_str = (datetime.now() + timedelta(days=_SESSION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    expires_at_dt  = datetime.now() + timedelta(days=_SESSION_DAYS)

    create_session_token(user["id"], token, expires_at_str)

    # 쿠키 저장을 다음 렌더로 예약 (st.rerun()과의 race condition 방지)
    st.session_state["_pending_cookie"] = (token, expires_at_dt)

    _apply_session(user)


def _apply_session(user: dict) -> None:
    """session_state에 유저 정보 적용."""
    st.session_state["user"] = {
        "id":           user["id"],
        "username":     user["username"],
        "role":         user["role"],
        "totp_enabled": bool(user["totp_enabled"]),
    }
    if not st.session_state.get("page") or st.session_state["page"] == "login":
        if user["role"] == "admin" and not user["totp_enabled"]:
            st.session_state["page"] = "admin"
        else:
            st.session_state["page"] = "dashboard"
