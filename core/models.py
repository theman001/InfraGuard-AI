"""
core/models.py — DB CRUD 함수 모음

law_registry: 관리자가 MST ID를 직접 수정/추가/삭제 가능
  - 수정된 MST ID는 다음 스케줄러 실행 시 자동 반영
"""

import sqlite3
from dataclasses import dataclass
from typing import Optional
from core.db import get_conn


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────

@dataclass
class LawEntry:
    id: int
    law_name: str
    mst_id: str
    law_type: Optional[str]
    category: Optional[str]
    sector: Optional[str]
    cert: Optional[str]
    is_active: bool
    last_effective_date: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class User:
    id: int
    username: str
    role: str
    status: str
    totp_secret: Optional[str]
    totp_enabled: bool
    created_at: str


@dataclass
class Template:
    id: int
    user_id: int
    template_name: str
    items: str        # JSON string
    created_at: str
    updated_at: str


@dataclass
class Report:
    id: int
    user_id: int
    template_id: Optional[int]
    template_snapshot: Optional[str]
    summary: Optional[str]
    prompt: Optional[str]
    result: Optional[str]
    created_at: str


# ── law_registry CRUD ─────────────────────────────────────────────────────────

def get_all_laws(active_only: bool = False) -> list[LawEntry]:
    with get_conn() as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM law_registry WHERE is_active = 1 ORDER BY category, sector, law_name"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM law_registry ORDER BY category, sector, law_name"
            ).fetchall()
    return [LawEntry(**dict(r)) for r in rows]


def get_law_by_id(law_id: int) -> Optional[LawEntry]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM law_registry WHERE id = ?", (law_id,)).fetchone()
    return LawEntry(**dict(row)) if row else None


def add_law(law_name: str, mst_id: str, law_type: str = None,
            category: str = None, sector: str = None, cert: str = None) -> LawEntry:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO law_registry (law_name, mst_id, law_type, category, sector, cert)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (law_name, mst_id, law_type, category, sector, cert),
        )
        return get_law_by_id(cursor.lastrowid)


def update_law(law_id: int, law_name: str = None, mst_id: str = None,
               law_type: str = None, category: str = None,
               sector: str = None, cert: str = None,
               is_active: bool = None) -> Optional[LawEntry]:
    """
    변경된 필드만 업데이트. mst_id가 변경되면 last_effective_date를 초기화해
    다음 스케줄러 실행 시 전체 재수집이 트리거되도록 한다.
    """
    entry = get_law_by_id(law_id)
    if not entry:
        return None

    mst_changed = mst_id is not None and mst_id != entry.mst_id

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE law_registry SET
                law_name            = COALESCE(?, law_name),
                mst_id              = COALESCE(?, mst_id),
                law_type            = COALESCE(?, law_type),
                category            = COALESCE(?, category),
                sector              = COALESCE(?, sector),
                cert                = COALESCE(?, cert),
                is_active           = COALESCE(?, is_active),
                last_effective_date = CASE WHEN ? THEN NULL ELSE last_effective_date END,
                updated_at          = datetime('now','localtime')
            WHERE id = ?
            """,
            (law_name, mst_id, law_type, category, sector, cert,
             int(is_active) if is_active is not None else None,
             mst_changed, law_id),
        )
    return get_law_by_id(law_id)


def delete_law(law_id: int) -> bool:
    with get_conn() as conn:
        affected = conn.execute(
            "DELETE FROM law_registry WHERE id = ?", (law_id,)
        ).rowcount
    return affected > 0


def update_effective_date(mst_id: str, effective_date: str) -> None:
    """수집 성공 후 시행일자 갱신 (변경 감지 기준값)"""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE law_registry
            SET last_effective_date = ?,
                updated_at = datetime('now','localtime')
            WHERE mst_id = ?
            """,
            (effective_date, mst_id),
        )


# ── users CRUD ────────────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_all_users() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, role, status, totp_enabled, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_user(username: str, totp_secret: str) -> dict:
    """회원가입 완료 시 호출 — OTP 검증 후 계정 생성 (즉시 active)"""
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, role, status, totp_secret, totp_enabled) VALUES (?, 'user', 'active', ?, 1)",
            (username, totp_secret),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_user_status(user_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))


def update_user_totp(username: str, totp_secret: str, totp_enabled: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET totp_secret = ?, totp_enabled = ? WHERE username = ?",
            (totp_secret, totp_enabled, username),
        )


def reset_user_otp(user_id: int) -> None:
    """OTP 초기화 — 다음 로그인 시 재등록 필요"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET totp_secret = NULL, totp_enabled = 0 WHERE id = ?",
            (user_id,),
        )


def update_user_role(user_id: int, role: str) -> None:
    """사용자 역할 변경 (user ↔ admin)."""
    with get_conn() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def delete_user(user_id: int) -> None:
    """사용자 삭제 (연결된 보고서·템플릿도 함께 삭제)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM reports   WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM templates WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users     WHERE id = ?",      (user_id,))


def get_user_api_keys(user_id: int) -> dict:
    """
    사용자의 암호화된 API 키를 복호화해서 반환.
    Returns: {"law_api_key": str, "llm_api_key": str}  (없으면 빈 문자열)
    """
    from core.crypto import decrypt_key
    with get_conn() as conn:
        row = conn.execute(
            "SELECT law_api_key, llm_api_key FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not row:
        return {"law_api_key": "", "llm_api_key": ""}
    return {
        "law_api_key": decrypt_key(row["law_api_key"] or ""),
        "llm_api_key": decrypt_key(row["llm_api_key"] or ""),
    }


def update_user_api_keys(
    user_id: int,
    law_api_key: str | None = None,
    llm_api_key: str | None = None,
) -> None:
    """
    사용자의 API 키를 암호화해서 저장.
    None인 값은 변경하지 않음. 빈 문자열("")은 키를 삭제 처리.
    """
    from core.crypto import encrypt_key
    with get_conn() as conn:
        if law_api_key is not None:
            conn.execute(
                "UPDATE users SET law_api_key = ? WHERE id = ?",
                (encrypt_key(law_api_key) if law_api_key.strip() else None, user_id),
            )
        if llm_api_key is not None:
            conn.execute(
                "UPDATE users SET llm_api_key = ? WHERE id = ?",
                (encrypt_key(llm_api_key) if llm_api_key.strip() else None, user_id),
            )


# ── templates CRUD ────────────────────────────────────────────────────────────

def get_templates_by_user(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM templates WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_template_by_id(template_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    return dict(row) if row else None


def create_template(user_id: int, template_name: str, items: str) -> dict:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO templates (user_id, template_name, items) VALUES (?, ?, ?)",
            (user_id, template_name, items),
        )
        row = conn.execute("SELECT * FROM templates WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def update_template(template_id: int, template_name: str = None, items: str = None) -> Optional[dict]:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE templates SET
                template_name = COALESCE(?, template_name),
                items         = COALESCE(?, items),
                updated_at    = datetime('now','localtime')
            WHERE id = ?
            """,
            (template_name, items, template_id),
        )
        row = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    return dict(row) if row else None


def delete_template(template_id: int, delete_reports: bool = False) -> None:
    with get_conn() as conn:
        if delete_reports:
            conn.execute("DELETE FROM reports WHERE template_id = ?", (template_id,))
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))


# ── reports CRUD ──────────────────────────────────────────────────────────────

def get_reports_by_user(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_report_by_id(report_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def create_report(user_id: int, template_id: int, template_snapshot: str,
                  summary: str, prompt: str, result: str) -> dict:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO reports (user_id, template_id, template_snapshot, summary, prompt, result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, template_id, template_snapshot, summary, prompt, result),
        )
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def delete_report(report_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))


# ── 세션 토큰 ─────────────────────────────────────────────────────────────────

def create_session_token(user_id: int, token: str, expires_at: str) -> None:
    """로그인 시 세션 토큰 DB 저장."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )


def get_session_user(token: str) -> Optional[dict]:
    """토큰으로 유효한 사용자 조회. 만료됐거나 없으면 None."""
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.totp_enabled, u.status
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
              AND s.expires_at > datetime('now','localtime')
              AND u.status = 'active'
            """,
            (token,),
        ).fetchone()
    return dict(row) if row else None


def delete_session_token(token: str) -> None:
    """로그아웃 시 토큰 삭제."""
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def purge_expired_sessions() -> None:
    """만료된 세션 정리 (앱 시작 시 호출)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= datetime('now','localtime')")
