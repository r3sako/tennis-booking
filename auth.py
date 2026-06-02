"""JWT session helpers. Login itself is handled by the deep-link bot."""
from datetime import datetime, timedelta, timezone

from fastapi import Request
from jose import JWTError, jwt

from config import COOKIE_NAME, JWT_ALGORITHM, JWT_EXPIRE_DAYS, SECRET_KEY


def create_session_token(tg_user_id: int, tg_username: str | None, tg_name: str) -> str:
    """Create a signed JWT for the session cookie."""
    now = datetime.now(timezone.utc)
    payload = {
        "tg_user_id": tg_user_id,
        "tg_username": tg_username,
        "tg_name": tg_name,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> dict | None:
    """Decode and validate a JWT; return payload dict or None."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


def get_current_user(request: Request) -> dict | None:
    """Read the session cookie and return the user payload, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_session_token(token)
    if not payload or "tg_user_id" not in payload:
        return None
    return {
        "tg_user_id": payload["tg_user_id"],
        "tg_username": payload.get("tg_username"),
        "tg_name": payload.get("tg_name", ""),
    }
