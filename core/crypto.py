"""
core/crypto.py — API 키 암호화/복호화

Fernet 대칭 암호화 (AES-128-CBC + HMAC-SHA256).
마스터 키: .env의 ENCRYPTION_KEY (없으면 자동 생성 후 출력)

사용:
  from core.crypto import encrypt_key, decrypt_key

  encrypted = encrypt_key("sk-ant-api03-...")   # str (암호문, DB 저장용)
  original  = decrypt_key(encrypted)             # str (원문)
"""

import os
import sys

from cryptography.fernet import Fernet, InvalidToken

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = os.environ.get("ENCRYPTION_KEY", "")

    if not key:
        # 키 없으면 자동 생성 후 경고 출력 — .env에 추가 권고
        new_key = Fernet.generate_key().decode()
        print(
            "\n[crypto] ENCRYPTION_KEY가 .env에 설정되지 않았습니다.\n"
            f"  아래 키를 .env에 추가하세요 (재시작 필요):\n"
            f"  ENCRYPTION_KEY={new_key}\n",
            file=sys.stderr,
        )
        # 이번 프로세스 수명 동안만 사용 (재시작 시 암호문 복호화 불가 — 주의)
        key = new_key

    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise RuntimeError(f"ENCRYPTION_KEY가 유효하지 않습니다: {e}") from e

    return _fernet


def encrypt_key(plaintext: str) -> str:
    """평문 API 키 → 암호문 (str). DB에 저장할 값."""
    if not plaintext or not plaintext.strip():
        return ""
    return _get_fernet().encrypt(plaintext.strip().encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    """암호문 → 평문 API 키. 복호화 실패 시 빈 문자열 반환."""
    if not ciphertext or not ciphertext.strip():
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.strip().encode()).decode()
    except (InvalidToken, Exception):
        return ""


def is_encrypted(value: str) -> bool:
    """값이 Fernet 암호문 형식인지 간단 체크 (gAAAAA로 시작)."""
    return bool(value and value.startswith("gAAAAA"))
