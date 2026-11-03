"""Hash seguro de contraseñas (PBKDF2-HMAC-SHA256)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

ITERATIONS = 310_000
SALT_BYTES = 24


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
        )
        return hmac.compare_digest(digest.hex(), password_hash)
    except (ValueError, TypeError):
        return False
