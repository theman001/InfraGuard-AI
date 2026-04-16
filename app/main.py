"""
app/main.py — Streamlit 앱 진입점

실행: streamlit run app/main.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import streamlit as st
import extra_streamlit_components as stx

from core.db import init_db
from core.auth import ensure_admin_exists
from core.rag.scheduler import start_scheduler
from app.components.auth import (
    get_current_user, logout, restore_session, process_pending_cookie,
)

# ── 앱 설정 ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="한국 법 자문 서비스",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="auto",
)


# ── 전역 UI 스타일 ────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── 폰트 ── */
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', sans-serif !important;
}

/* ── 전체 배경 ── */
.stApp { background-color: #f5f7fa; }

/* ── 메인 컨텐츠 영역 ── */
.main .block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1200px;
}

/* ── 제목 스타일 ── */
h1 { font-weight: 700 !important; color: #1a3c6e !important; letter-spacing: -0.02em; }
h2 { font-weight: 600 !important; color: #1a3c6e !important; }
h3 { font-weight: 600 !important; color: #2d4f8a !important; }

/* ── 사이드바 ── */
[data-testid="stSidebar"] {
    background-color: #1a3c6e !important;
    border-right: none;
}
[data-testid="stSidebar"] * { color: #e8edf5 !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.15) !important; }
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    color: #e8edf5 !important;
    border-radius: 8px !important;
    transition: background 0.2s, transform 0.15s !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.18) !important;
    transform: translateX(3px) !important;
}

/* ── 버튼 ── */
.stButton > button[kind="primary"] {
    background-color: #1a3c6e !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em;
    transition: background 0.2s, transform 0.15s, box-shadow 0.2s !important;
}
.stButton > button[kind="primary"]:hover {
    background-color: #2d5499 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(26,60,110,0.3) !important;
}
.stButton > button:not([kind="primary"]) {
    border-radius: 8px !important;
    border: 1px solid #dde3ed !important;
    font-weight: 500 !important;
    transition: background 0.2s, transform 0.15s !important;
}
.stButton > button:not([kind="primary"]):hover {
    background-color: #eef3fb !important;
    border-color: #1a3c6e !important;
    transform: translateY(-1px) !important;
}

/* ── 입력 필드 ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    border-radius: 8px !important;
    border: 1.5px solid #dde3ed !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #1a3c6e !important;
    box-shadow: 0 0 0 3px rgba(26,60,110,0.1) !important;
    outline: none !important;
}

/* ── 카드 (expander) ── */
.streamlit-expanderHeader {
    background-color: #eef3fb !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    color: #1a3c6e !important;
    border: 1px solid #dde3ed !important;
}
.streamlit-expanderContent {
    border: 1px solid #dde3ed !important;
    border-top: none !important;
    border-radius: 0 0 8px 8px !important;
    background: #ffffff !important;
}

/* ── 탭 ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 2px solid #dde3ed;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0 !important;
    font-weight: 500 !important;
    padding: 8px 20px !important;
    transition: background 0.2s !important;
}
.stTabs [aria-selected="true"] {
    background-color: #1a3c6e !important;
    color: white !important;
}

/* ── 메트릭 ── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #dde3ed;
    border-radius: 12px;
    padding: 1rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
[data-testid="stMetricLabel"] { font-weight: 600 !important; color: #6b7a99 !important; }
[data-testid="stMetricValue"] { color: #1a3c6e !important; font-weight: 700 !important; }

/* ── divider ── */
hr { border-color: #dde3ed !important; margin: 1.5rem 0 !important; }

/* ── info / warning / success / error ── */
[data-testid="stAlert"] { border-radius: 10px !important; border-left-width: 4px !important; }

/* ── Deploy 버튼 숨기기 ── */
[data-testid="stDeployButton"],
[data-testid="stToolbarActions"] > *:not([data-testid="stStatusWidget"]) {
    display: none !important;
}

/* ── 코드 폰트 ── */
code, pre { font-family: 'IBM Plex Mono', monospace !important; }

/* ── 스크롤바 ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #f5f7fa; }
::-webkit-scrollbar-thumb { background: #c5cfe0; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #1a3c6e; }

/* ── 사이드바 현재 페이지 강조 ── */
[data-testid="stSidebar"] .stButton > button.nav-active {
    background: rgba(255,255,255,0.22) !important;
    border-color: rgba(255,255,255,0.35) !important;
    font-weight: 700 !important;
    transform: translateX(4px) !important;
}

/* ── 사이드바 사용자 정보 ── */
.sidebar-user-info {
    background: rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 0.6rem 0.75rem;
    margin-bottom: 0.25rem;
}
.sidebar-user-info .uname {
    font-weight: 700;
    font-size: 0.9rem;
    color: #fff;
}
.sidebar-user-info .urole {
    font-size: 0.75rem;
    color: rgba(255,255,255,0.65);
}

/* ── Caption 색상 ── */
.stCaption { color: #6b7a99 !important; }
</style>
""", unsafe_allow_html=True)

# ── 쿠키 매니저: 매 렌더 최상단에서 렌더링 (set/delete JS 실행 보장) ──────────
_cookie_mgr = stx.CookieManager(key="ig_cm")
st.session_state["_cookie_manager"] = _cookie_mgr

# ── 1회 초기화 ────────────────────────────────────────────────────────────────
if "initialized" not in st.session_state:
    init_db()
    ensure_admin_exists()
    start_scheduler()
    from core.models import purge_expired_sessions
    purge_expired_sessions()
    st.session_state["initialized"] = True

# ── 세션 기본값 ───────────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state["page"] = "login"
if "user" not in st.session_state:
    st.session_state["user"] = None

# ── 쿠키로 세션 복원 (새로고침 시) ──────────────────────────────────────────
restore_session()

# ── 예약된 쿠키 set/delete 처리 (CookieManager 렌더 직후) ────────────────────
process_pending_cookie(_cookie_mgr)

user = get_current_user()

# ── 미로그인 → 로그인 페이지 ─────────────────────────────────────────────────
if not user:
    st.session_state["page"] = "login"
    from app.pages import login
    login.render()
    st.stop()

# ── admin OTP 미등록 → admin 페이지 강제 ─────────────────────────────────────
if user["role"] == "admin" and not user["totp_enabled"]:
    st.session_state["page"] = "admin"

page = st.session_state["page"]

# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    # 사용자 정보
    st.markdown(f"""
    <div class="sidebar-user-info">
      <div class="uname">⚖️ {user['username']}</div>
      <div class="urole">{user['role']}</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    if user["role"] == "admin" and not user["totp_enabled"]:
        st.warning("OTP 등록 후 다른 메뉴를 이용할 수 있습니다.")
    else:
        nav_items = [
            ("dashboard", "🏠 대시보드"),
            ("search",    "🔍 법령 검색"),
            ("history",   "📋 자문 기록"),
            ("mypage",    "👤 마이페이지"),
        ]
        if user["role"] == "admin":
            nav_items.append(("admin", "⚙️ 관리자 패널"))

        for nav_page, nav_label in nav_items:
            is_active = page == nav_page
            label = f"**{nav_label}**" if is_active else nav_label
            if st.button(label, use_container_width=True, key=f"nav_{nav_page}"):
                st.session_state["page"] = nav_page
                st.rerun()

    st.divider()
    if st.button("🚪 로그아웃", use_container_width=True):
        logout()

# ── 페이지 라우팅 ─────────────────────────────────────────────────────────────
if page == "admin":
    from app.pages import admin
    admin.render()

elif page == "dashboard":
    from app.pages import dashboard
    dashboard.render()

elif page == "search":
    from app.pages import search
    search.render()

elif page == "history":
    from app.pages import history
    history.render()

elif page == "mypage":
    from app.pages import mypage
    mypage.render()

else:
    st.session_state["page"] = "dashboard"
    st.rerun()
