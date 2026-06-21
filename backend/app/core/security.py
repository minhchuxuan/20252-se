"""Authentication primitives (NFR-SEC).

* Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes — never plaintext
  (NFR-SEC-3). PBKDF2 is used (stdlib ``hashlib``) to avoid native build deps
  while remaining a sound, salted, iterated KDF.
* Sessions use signed JWT bearer tokens (NFR-SEC-2).
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from ..config import settings

_PBKDF2_ITERATIONS = 200_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_{_ALGO}${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        assert scheme == f"pbkdf2_{_ALGO}"
        dk = hashlib.pbkdf2_hmac(_ALGO, password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AssertionError):
        return False


def create_access_token(subject: str, role: str, home_id: int | None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "home_id": home_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
