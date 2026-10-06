import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# Direct bcrypt usage avoids passlib bug with bcrypt>=4.1.0/5.0.0
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """Return the bcrypt hash of *plain*. Truncates to 72 bytes safely."""
    # bcrypt max password length is 72 bytes
    pwd_bytes = plain.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password."""
    try:
        pwd_bytes = plain.encode("utf-8")[:72]
        hashed_bytes = hashed.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(user_id: str) -> str:
    """
    Create a signed JWT containing only the user_id as the subject.
    Business context (role, permissions) is NOT embedded in the token —
    it is resolved per-request via the X-Business-Id header (FEAT-08).
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {
        "sub": user_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """
    Decode and validate a JWT. Returns the user_id (sub claim).
    Raises JWTError on invalid/expired tokens.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise JWTError("Token payload missing 'sub' claim")
    return user_id
