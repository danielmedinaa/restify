import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

_hasher = PasswordHasher()

# Hash fijo para igualar tiempos cuando el usuario no existe (evita enumeración por timing)
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

API_KEY_PREFIX_LEN = 8


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def create_access_token(user_id: int, token_version: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tv": token_version,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp", "iat", "type", "tv"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Tipo de token inválido")
    return payload


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def new_public_token() -> str:
    """Token opaco para QR de mesa y links de seguimiento (no adivinable)."""
    return secrets.token_urlsafe(24)


def new_api_key() -> tuple[str, str, str]:
    """Devuelve (clave completa, prefijo, hash). La clave completa solo se muestra una vez."""
    prefix = secrets.token_hex(API_KEY_PREFIX_LEN // 2)
    key = f"rk_{prefix}_{secrets.token_urlsafe(32)}"
    return key, prefix, sha256(key)


def parse_api_key_prefix(key: str) -> str | None:
    parts = key.split("_", 2)
    if len(parts) != 3 or parts[0] != "rk" or len(parts[1]) != API_KEY_PREFIX_LEN:
        return None
    return parts[1]
