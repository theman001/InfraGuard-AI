"""
app/pages/admin.py — 관리자 패널

탭 1 — 계정 관리:
  - 전체 계정 목록 (정지/활성화, OTP 초기화)
  - 관리자 본인 OTP 등록/재등록 (탭 하단)

탭 2 — 법령 관리:
  - law_registry CRUD (MST ID 수정/추가/삭제, 활성화 토글)

탭 3 — RAG 데이터 관리:
  - ChromaDB 현황 (저장된 조문 수)
  - 초기 수집 / 전체 강제 재수집 버튼
  - 특정 법령 단건 재수집
"""

import streamlit as st
from app.components.auth import require_admin, get_current_user
from core.auth import generate_totp_secret, generate_qr_code, verify_otp
from core.models import (
    get_all_users, update_user_status, reset_user_otp, update_user_totp,
    update_user_role, delete_user,
    get_all_laws, add_law, update_law, delete_law,
)
# chroma_store는 사용 시점에 지연 임포트


_ADMIN_CSS = """
<style>
/* 관리자 패널 전용 */
.admin-table-header {
    display: flex;
    background: #eef2fa;
    border: 1px solid #dde3ed;
    border-radius: 8px 8px 0 0;
    padding: 0.5rem 0.5rem;
    font-size: 0.78rem;
    font-weight: 700;
    color: #1a3c6e;
    letter-spacing: 0.02em;
}
.user-status-badge {
    display: inline-block;
    border-radius: 5px;
    padding: 0.1rem 0.45rem;
    font-size: 0.73rem;
    font-weight: 600;
}
.user-status-active {
    background: #edf7ed;
    color: #2e7d32;
    border: 1px solid #b2dfb2;
}
.user-status-suspended {
    background: #fdecea;
    color: #c62828;
    border: 1px solid #f5a9a9;
}
.role-badge {
    display: inline-block;
    border-radius: 5px;
    padding: 0.1rem 0.45rem;
    font-size: 0.73rem;
    font-weight: 600;
}
.role-admin {
    background: #e8edf8;
    color: #1a3c6e;
    border: 1px solid #bfcce8;
}
.role-user {
    background: #f5f7fa;
    color: #4a5568;
    border: 1px solid #dde3ed;
}
.otp-badge-on {
    display: inline-block;
    background: #edf7ed;
    color: #2e7d32;
    border-radius: 5px;
    padding: 0.1rem 0.45rem;
    font-size: 0.73rem;
    font-weight: 600;
    border: 1px solid #b2dfb2;
}
.otp-badge-off {
    display: inline-block;
    background: #fff8e1;
    color: #c77700;
    border-radius: 5px;
    padding: 0.1rem 0.45rem;
    font-size: 0.73rem;
    font-weight: 600;
    border: 1px solid #ffe082;
}
.rag-stat-card {
    background: #fff;
    border: 1px solid #dde3ed;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 2px 8px rgba(26,60,110,0.05);
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1.25rem;
}
.rag-stat-card .stat-num {
    font-size: 2rem;
    font-weight: 700;
    color: #1a3c6e;
    line-height: 1;
}
.rag-stat-card .stat-label {
    font-size: 0.83rem;
    color: #6b7a99;
    font-weight: 500;
}
.rag-action-card {
    background: #fff;
    border: 1px solid #dde3ed;
    border-radius: 10px;
    padding: 1rem 1.1rem;
    height: 100%;
    box-shadow: 0 1px 4px rgba(26,60,110,0.04);
}
.rag-action-card h5 {
    margin: 0 0 0.25rem 0 !important;
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    color: #1a1f2e !important;
}
.rag-action-card p {
    margin: 0 0 0.6rem 0 !important;
    font-size: 0.78rem !important;
    color: #6b7a99 !important;
}
</style>
"""


def render() -> None:
    require_admin()
    user = get_current_user()

    st.markdown(_ADMIN_CSS, unsafe_allow_html=True)

    # admin OTP 미등록 경고 배너
    if not user["totp_enabled"]:
        st.warning("⚠️ OTP가 등록되어 있지 않습니다. 아래 [계정 관리] 탭에서 OTP를 등록하세요.")

    st.title("관리자 패널")
    tab_accounts, tab_laws, tab_rag = st.tabs(["👤 계정 관리", "📋 법령 관리", "🗄 RAG 데이터"])

    with tab_accounts:
        _render_accounts(user)

    with tab_laws:
        _render_laws()

    with tab_rag:
        _render_rag()


# ── 탭 1: 계정 관리 ────────────────────────────────────────────────────────────

def _render_accounts(current_user: dict) -> None:
    st.subheader("전체 계정 목록")
    users = get_all_users()

    # 헤더
    h = st.columns([2, 1.2, 1.2, 1.2, 2, 1, 1, 1, 1])
    labels = ["아이디", "역할", "상태", "OTP", "가입일", "정지/활성", "OTP초기화", "권한변경", "삭제"]
    for col, label in zip(h, labels):
        col.markdown(f"<span style='font-size:0.8rem;font-weight:700;color:#1a3c6e'>{label}</span>",
                     unsafe_allow_html=True)
    st.divider()

    for u in users:
        is_self = u["id"] == current_user["id"]
        uid = u["id"]

        row = st.columns([2, 1.2, 1.2, 1.2, 2, 1, 1, 1, 1])

        # 아이디
        row[0].write(u["username"] + (" *(나)*" if is_self else ""))

        # 역할 배지
        role_cls = "role-admin" if u["role"] == "admin" else "role-user"
        row[1].markdown(f'<span class="role-badge {role_cls}">{u["role"]}</span>', unsafe_allow_html=True)

        # 상태 배지
        st_cls = "user-status-active" if u["status"] == "active" else "user-status-suspended"
        row[2].markdown(f'<span class="user-status-badge {st_cls}">{u["status"]}</span>', unsafe_allow_html=True)

        # OTP 배지
        otp_cls = "otp-badge-on" if u["totp_enabled"] else "otp-badge-off"
        otp_txt = "등록" if u["totp_enabled"] else "미등록"
        row[3].markdown(f'<span class="{otp_cls}">{otp_txt}</span>', unsafe_allow_html=True)

        # 가입일
        row[4].caption((u["created_at"] or "")[:10])

        if is_self:
            for col in row[5:]:
                col.write("—")
        else:
            # 정지/활성화
            if u["status"] == "active":
                if row[5].button("정지", key=f"suspend_{uid}", use_container_width=True):
                    update_user_status(uid, "suspended")
                    st.rerun()
            else:
                if row[5].button("활성", key=f"activate_{uid}", use_container_width=True):
                    update_user_status(uid, "active")
                    st.rerun()

            # OTP 초기화
            if row[6].button("초기화", key=f"otp_reset_{uid}", use_container_width=True):
                st.session_state[f"confirm_otp_{uid}"] = True

            # 권한 변경
            new_role   = "user" if u["role"] == "admin" else "admin"
            role_label = "→user" if u["role"] == "admin" else "→admin"
            if row[7].button(role_label, key=f"role_{uid}", use_container_width=True):
                st.session_state[f"confirm_role_{uid}"] = new_role

            # 삭제
            if row[8].button("삭제", key=f"del_{uid}", type="primary", use_container_width=True):
                st.session_state[f"confirm_del_{uid}"] = True

        # ── 확인 팝업 ─────────────────────────────────────────────────────────
        if st.session_state.get(f"confirm_otp_{uid}"):
            st.warning(f"**{u['username']}** OTP를 초기화하면 다음 로그인 시 재등록해야 합니다.")
            c1, c2, _ = st.columns([1, 1, 6])
            if c1.button("확인", key=f"otp_yes_{uid}"):
                reset_user_otp(uid)
                st.session_state.pop(f"confirm_otp_{uid}", None)
                st.success(f"{u['username']} OTP 초기화 완료")
                st.rerun()
            if c2.button("취소", key=f"otp_no_{uid}"):
                st.session_state.pop(f"confirm_otp_{uid}", None)
                st.rerun()

        if st.session_state.get(f"confirm_role_{uid}"):
            target_role = st.session_state[f"confirm_role_{uid}"]
            st.warning(f"**{u['username']}** 역할을 **{target_role}**(으)로 변경하시겠습니까?")
            c1, c2, _ = st.columns([1, 1, 6])
            if c1.button("확인", key=f"role_yes_{uid}"):
                update_user_role(uid, target_role)
                st.session_state.pop(f"confirm_role_{uid}", None)
                st.success(f"{u['username']} 역할 변경 → {target_role}")
                st.rerun()
            if c2.button("취소", key=f"role_no_{uid}"):
                st.session_state.pop(f"confirm_role_{uid}", None)
                st.rerun()

        if st.session_state.get(f"confirm_del_{uid}"):
            st.error(f"**{u['username']}** 계정 및 연결된 보고서·템플릿을 모두 삭제합니다.")
            c1, c2, _ = st.columns([1, 1, 6])
            if c1.button("삭제 확인", key=f"del_yes_{uid}"):
                delete_user(uid)
                st.session_state.pop(f"confirm_del_{uid}", None)
                st.success(f"{u['username']} 삭제 완료")
                st.rerun()
            if c2.button("취소", key=f"del_no_{uid}"):
                st.session_state.pop(f"confirm_del_{uid}", None)
                st.rerun()

        st.divider()

    # ── 관리자 OTP 관리 ──────────────────────────────────────────────────────
    st.subheader("관리자 OTP 관리")
    _render_admin_otp(current_user)


def _render_admin_otp(current_user: dict) -> None:
    if current_user["totp_enabled"]:
        st.success("OTP가 등록되어 있습니다.")
        if st.button("OTP 재등록", key="btn_otp_reregister"):
            st.session_state["admin_otp_step"] = "qr"
            st.rerun()
    else:
        st.info("OTP가 등록되어 있지 않습니다. 지금 등록하세요.")
        if st.button("OTP 등록", type="primary", key="btn_otp_register"):
            st.session_state["admin_otp_step"] = "qr"
            st.rerun()

    if st.session_state.get("admin_otp_step") == "qr":
        _render_admin_otp_setup(current_user)


def _render_admin_otp_setup(current_user: dict) -> None:
    if "admin_otp_secret" not in st.session_state:
        st.session_state["admin_otp_secret"] = generate_totp_secret()

    secret = st.session_state["admin_otp_secret"]
    qr_bytes = generate_qr_code(current_user["username"], secret)

    st.write("아래 QR 코드를 Google Authenticator 앱으로 스캔하세요.")

    _, qr_col, _ = st.columns([1, 2, 1])
    with qr_col:
        st.image(qr_bytes, use_container_width=True)

    otp_code = st.text_input("앱에 표시된 6자리 코드 입력", max_chars=6, key="admin_otp_input",
                              placeholder="123456")

    col1, col2 = st.columns(2)
    if col1.button("등록 완료", type="primary", key="btn_admin_otp_done", use_container_width=True):
        if not verify_otp(secret, otp_code):
            st.error("OTP 코드가 올바르지 않습니다.")
        else:
            update_user_totp(current_user["username"], secret, 1)
            st.session_state["user"]["totp_enabled"] = True
            st.session_state.pop("admin_otp_step", None)
            st.session_state.pop("admin_otp_secret", None)
            st.success("OTP 등록 완료!")
            st.rerun()

    if col2.button("취소", key="btn_admin_otp_cancel", use_container_width=True):
        st.session_state.pop("admin_otp_step", None)
        st.session_state.pop("admin_otp_secret", None)
        st.rerun()


# ── 탭 2: 법령 관리 ────────────────────────────────────────────────────────────

def _render_laws() -> None:
    st.subheader("법령 추가")
    _render_law_add_form()

    st.divider()
    st.subheader("등록된 법령 목록")
    _render_law_list()


def _render_law_add_form() -> None:
    with st.form("form_add_law", clear_on_submit=True):
        col1, col2 = st.columns(2)
        law_name = col1.text_input("법령명 *")
        mst_id   = col2.text_input("MST ID *")

        col3, col4, col5 = st.columns(3)
        law_type = col3.selectbox("법령구분", ["법률", "대통령령", "총리령", "부령", "기타"])
        category = col4.selectbox("카테고리", ["공통", "업종별", "인증별"])
        sector   = col5.text_input("업종/인증 (선택)", placeholder="예: 금융/핀테크, ISMS-P")

        submitted = st.form_submit_button("추가하기", type="primary")
        if submitted:
            if not law_name.strip() or not mst_id.strip():
                st.error("법령명과 MST ID는 필수입니다.")
            else:
                from core.db import get_conn
                with get_conn() as conn:
                    dup = conn.execute(
                        "SELECT 1 FROM law_registry WHERE mst_id = ?", (mst_id.strip(),)
                    ).fetchone()
                if dup:
                    st.error("이미 등록된 MST ID입니다.")
                else:
                    cert   = sector.strip() if category == "인증별" else None
                    s_val  = sector.strip() if category == "업종별" else None
                    add_law(law_name.strip(), mst_id.strip(), law_type, category, s_val, cert)
                    st.success(f"'{law_name}' 추가 완료")
                    st.rerun()


def _render_law_list() -> None:
    laws = get_all_laws()
    if not laws:
        st.info("등록된 법령이 없습니다.")
        return

    # 헤더
    hcols = st.columns([3, 1.5, 1.5, 0.8, 2])
    for col, label in zip(hcols, ["법령명", "MST ID", "카테고리", "활성", "작업"]):
        col.markdown(f"<span style='font-size:0.8rem;font-weight:700;color:#1a3c6e'>{label}</span>",
                     unsafe_allow_html=True)

    for law in laws:
        st.divider()
        col_name, col_mst, col_cat, col_active, col_act = st.columns([3, 1.5, 1.5, 0.8, 2])
        col_name.write(law.law_name)
        col_mst.caption(law.mst_id)
        col_cat.caption(law.category or "")
        col_active.write("✅" if law.is_active else "⬜")

        btn1, btn2 = col_act.columns(2)
        if btn1.button("수정", key=f"edit_{law.id}", use_container_width=True):
            st.session_state[f"editing_{law.id}"] = True

        if btn2.button("삭제", key=f"del_{law.id}", use_container_width=True):
            st.session_state[f"confirm_del_{law.id}"] = True

        # 수정 폼
        if st.session_state.get(f"editing_{law.id}"):
            _render_law_edit_form(law)

        # 삭제 확인
        if st.session_state.get(f"confirm_del_{law.id}"):
            st.warning(f"**{law.law_name}** 을 삭제하면 ChromaDB에서도 해당 법령 청크가 제거됩니다.")
            c1, c2, _ = st.columns([1, 1, 4])
            if c1.button("삭제 확인", key=f"del_yes_{law.id}"):
                try:
                    from core.rag.chroma_store import delete_by_mst_id
                    delete_by_mst_id(law.mst_id)
                except Exception as e:
                    st.warning(f"ChromaDB 삭제 실패 (무시하고 진행): {e}")
                delete_law(law.id)
                st.session_state.pop(f"confirm_del_{law.id}", None)
                st.rerun()
            if c2.button("취소", key=f"del_no_{law.id}"):
                st.session_state.pop(f"confirm_del_{law.id}", None)
                st.rerun()


def _render_law_edit_form(law) -> None:
    with st.form(f"form_edit_{law.id}"):
        st.write(f"**{law.law_name}** 수정")
        new_name    = st.text_input("법령명", value=law.law_name)
        new_mst     = st.text_input("MST ID", value=law.mst_id)
        new_type    = st.selectbox("법령구분", ["법률", "대통령령", "총리령", "부령", "기타"],
                                   index=["법률", "대통령령", "총리령", "부령", "기타"].index(law.law_type or "법률"))
        new_active  = st.checkbox("활성화", value=bool(law.is_active))

        if new_mst != law.mst_id:
            st.warning("MST ID 변경 시 다음 스케줄 실행 시 해당 법령 전체 재수집됩니다.")

        col1, col2 = st.columns(2)
        saved   = col1.form_submit_button("저장", type="primary")
        cancel  = col2.form_submit_button("취소")

        if saved:
            update_law(
                law.id,
                law_name  = new_name.strip() or None,
                mst_id    = new_mst.strip() or None,
                law_type  = new_type,
                is_active = new_active,
            )
            st.session_state.pop(f"editing_{law.id}", None)
            st.success("수정 완료")
            st.rerun()

        if cancel:
            st.session_state.pop(f"editing_{law.id}", None)
            st.rerun()


# ── 탭 3: RAG 데이터 관리 ──────────────────────────────────────────────────────

def _render_rag() -> None:
    # 현황 카드
    try:
        from core.rag.chroma_store import get_collection_count
        count = get_collection_count()
        count_str = f"{count:,}"
    except Exception as e:
        count_str = "연결 오류"
        st.warning(f"ChromaDB 연결 실패: {e}")

    st.markdown(f"""
    <div class="rag-stat-card">
      <div>
        <div class="stat-num">{count_str}</div>
        <div class="stat-label">ChromaDB 저장 법령 조문 수</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("**법령 수집**")
    st.caption(
        "law_registry에 등록된 활성 법령을 국가법령정보 API에서 수집해 ChromaDB에 저장합니다. "
        "최초 배포 후 또는 대규모 변경 시 실행하세요."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown('<div class="rag-action-card">', unsafe_allow_html=True)
        st.markdown("**증분 수집**")
        st.caption("시행일자가 변경된 법령만 업데이트")
        if st.button("수집 시작", key="btn_rag_sync", use_container_width=True, type="primary"):
            st.session_state["rag_confirm"] = "sync"
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="rag-action-card">', unsafe_allow_html=True)
        st.markdown("**전체 강제 재수집**")
        st.caption("기존 데이터 유지 + 모든 법령 upsert")
        if st.button("강제 재수집", key="btn_rag_force", use_container_width=True):
            st.session_state["rag_confirm"] = "force"
        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="rag-action-card">', unsafe_allow_html=True)
        st.markdown("**초기화 후 재수집**")
        st.caption("DB 전체 삭제 후 처음부터 새로 수집")
        if st.button("초기화 + 재수집", key="btn_rag_reset", use_container_width=True):
            st.session_state["rag_confirm"] = "reset"
        st.markdown('</div>', unsafe_allow_html=True)

    # 확인 팝업
    if st.session_state.get("rag_confirm"):
        mode = st.session_state["rag_confirm"]
        labels = {"sync": "증분 수집", "force": "전체 강제 재수집", "reset": "초기화 후 재수집"}
        label = labels[mode]
        warn_msg = (
            f"**{label}**을 시작합니다. 법령 수에 따라 수 분 이상 소요될 수 있습니다."
            if mode != "reset"
            else "**ChromaDB 전체를 삭제하고 처음부터 재수집합니다.** 기존 벡터 데이터가 모두 사라집니다."
        )
        st.warning(warn_msg)
        c1, c2, _ = st.columns([1, 1, 4])
        if c1.button("확인", key="rag_yes"):
            st.session_state.pop("rag_confirm", None)
            _run_rag_sync(force=(mode in ("force", "reset")), reset=(mode == "reset"))
        if c2.button("취소", key="rag_no"):
            st.session_state.pop("rag_confirm", None)
            st.rerun()

    st.divider()

    # ── 단건 재수집 ───────────────────────────────────────────────────────────
    st.markdown("**특정 법령 재수집**")
    st.caption("특정 법령 1건만 선택해서 즉시 재수집합니다.")

    laws = get_all_laws(active_only=True)
    if not laws:
        st.info("활성화된 법령이 없습니다.")
        return

    options = {f"{l.law_name} ({l.mst_id})": l.mst_id for l in laws}
    selected = st.selectbox("법령 선택", list(options.keys()), key="rag_single_select")

    if st.button("이 법령 재수집", key="btn_rag_single", type="primary"):
        mst = options[selected]
        _run_rag_sync(mst_id=mst, force=True)


def _run_rag_sync(mst_id: str | None = None, force: bool = False, reset: bool = False) -> None:
    """RAG 수집 실행 — 진행 로그를 st.status 안에 실시간 표시."""
    from core.models import get_all_laws

    target = f"MST={mst_id}" if mst_id else ("전체 강제" if force else "증분")
    laws = get_all_laws(active_only=True)
    if mst_id:
        laws = [l for l in laws if l.mst_id == mst_id]
    total = len(laws)

    with st.status(f"법령 수집 중... ({target}, {total}개 대상)", expanded=True) as status:
        results = {"updated": [], "skipped": [], "failed": []}

        if reset:
            st.write("ChromaDB 초기화 중...")
            from core.rag.chroma_store import reset_collection
            reset_collection()
            st.write("초기화 완료. 수집 시작...")

        from core.rag.collector import fetch_law_xml, get_law_name_from_xml
        from core.rag.chunker import parse_chunks
        from core.rag.chroma_store import sync_law_chunks, get_collection_count
        from core.models import update_effective_date

        for i, entry in enumerate(laws, 1):
            st.write(f"[{i}/{total}] {entry.law_name} 처리 중...")
            try:
                soup, effective_date = fetch_law_xml(entry.mst_id)
                law_name = get_law_name_from_xml(soup) or entry.law_name

                if not force and entry.last_effective_date == effective_date:
                    st.write(f"  → 시행일 동일 ({effective_date}), 스킵")
                    results["skipped"].append(entry.law_name)
                    continue

                chunks = parse_chunks(
                    soup=soup, mst_id=entry.mst_id, law_name=law_name,
                    law_type=entry.law_type or "", effective_date=effective_date,
                    category=entry.category, sector=entry.sector, cert=entry.cert,
                )
                r = sync_law_chunks(entry.mst_id, chunks)
                update_effective_date(entry.mst_id, effective_date)
                st.write(f"  → 추가 {r['inserted']} / 수정 {r['updated']} / 삭제 {r['deleted']} / 유지 {r['unchanged']}")
                results["updated"].append(entry.law_name)

            except Exception as e:
                st.write(f"  → 실패: {e}")
                results["failed"].append({"law_name": entry.law_name, "error": str(e)})

        final_count = get_collection_count()
        status.update(label="수집 완료!", state="complete", expanded=False)

    st.success(
        f"완료 — 업데이트 {len(results['updated'])}건 / "
        f"스킵 {len(results['skipped'])}건 / "
        f"실패 {len(results['failed'])}건 | "
        f"ChromaDB 총 조문 수: {final_count:,}개"
    )
    if results["failed"]:
        for f in results["failed"]:
            st.error(f"실패: {f['law_name']} — {f['error']}")
