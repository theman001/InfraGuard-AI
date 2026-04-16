"""
core/auth.py — Passwordless TOTP 인증

제공 함수:
- generate_totp_secret()      TOTP 시크릿 생성
- generate_qr_code()          QR 코드 PNG 바이트 생성
- verify_otp()                OTP 검증
- ensure_admin_exists()       최초 실행 시 admin 계정 생성
"""

import io
import pyotp
import qrcode
from qrcode.image.pil import PilImage

ISSUER = "한국 법 자문 서비스"


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def generate_qr_code(username: str, secret: str) -> bytes:
    """otpauth:// URI → QR 코드 PNG 바이트"""
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name=ISSUER,
    )
    img = qrcode.make(uri, image_factory=PilImage)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def verify_otp(secret: str, otp_code: str) -> bool:
    """±30초 오차 허용 (valid_window=1)"""
    try:
        return pyotp.TOTP(secret).verify(otp_code.strip(), valid_window=1)
    except Exception:
        return False


def ensure_admin_exists() -> None:
    """users 테이블에 admin 계정이 없으면 기본 계정 생성 (totp_enabled=0)"""
    from core.db import get_conn
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = 'admin'"
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO users (username, role, status, totp_secret, totp_enabled)
                VALUES ('admin', 'admin', 'active', NULL, 0)
                """
            )
            print("[auth] admin 계정 생성 완료 (OTP 미등록 상태)")
