"""
core/db.py — SQLite 연결 및 테이블 초기화

- DB 파일: db/app.db
- 앱 시작 시 init_db() 한 번 호출 → 테이블 없으면 생성
- law_registry는 laws_registry.json 시드 데이터로 최초 1회 삽입
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import os

_DEFAULT_DB = Path(__file__).parent.parent / "db" / "app.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(_DEFAULT_DB)))
SEED_PATH = Path(__file__).parent.parent / "data" / "laws_registry.json"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    from core.auth import ensure_admin_exists
    with get_conn() as conn:
        _create_tables(conn)
        _seed_law_registry(conn)
    ensure_admin_exists()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS law_registry (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            law_name            TEXT    NOT NULL,
            mst_id              TEXT    NOT NULL UNIQUE,
            law_type            TEXT,
            category            TEXT,
            sector              TEXT,
            cert                TEXT,
            is_active           INTEGER NOT NULL DEFAULT 1,
            last_effective_date TEXT,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT    NOT NULL UNIQUE,
            role            TEXT    NOT NULL DEFAULT 'user',
            status          TEXT    NOT NULL DEFAULT 'active',
            totp_secret     TEXT,
            totp_enabled    INTEGER NOT NULL DEFAULT 0,
            law_api_key     TEXT,
            llm_api_key     TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS templates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id),
            template_name   TEXT    NOT NULL,
            items           TEXT    NOT NULL DEFAULT '{}',
            created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS reports (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id             INTEGER NOT NULL REFERENCES users(id),
            template_id         INTEGER REFERENCES templates(id) ON DELETE SET NULL,
            template_snapshot   TEXT,
            summary             TEXT,
            prompt              TEXT,
            result              TEXT,
            created_at          TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT    PRIMARY KEY,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)
    # 기존 DB 마이그레이션 — 컬럼 없으면 추가 (idempotent)
    _migrate_users_api_keys(conn)
    _migrate_sessions(conn)


def _migrate_users_api_keys(conn: sqlite3.Connection) -> None:
    """users 테이블에 law_api_key / llm_api_key 컬럼이 없으면 추가."""
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }
    if "law_api_key" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN law_api_key TEXT")
    if "llm_api_key" not in existing:
        conn.execute("ALTER TABLE users ADD COLUMN llm_api_key TEXT")


def _migrate_sessions(conn: sqlite3.Connection) -> None:
    """sessions 테이블이 없으면 생성 (기존 DB 마이그레이션용)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT    PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            expires_at  TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)


def _seed_law_registry(conn: sqlite3.Connection) -> None:
    """DB에 law_registry 데이터가 없을 때만 JSON 시드 삽입"""
    count = conn.execute("SELECT COUNT(*) FROM law_registry").fetchone()[0]
    if count > 0:
        return

    with open(SEED_PATH, encoding="utf-8") as f:
        laws = json.load(f)

    conn.executemany(
        """
        INSERT INTO law_registry (law_name, mst_id, law_type, category, sector, cert)
        VALUES (:law_name, :mst_id, :law_type, :category, :sector, :cert)
        """,
        laws,
    )
    print(f"[db] law_registry 시드 데이터 {len(laws)}건 삽입 완료")
