"""Telegram Login Widget verification and JWT session helpers."""
import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone

from fastapi import Request
from jose import JWTError, jwt

from config import BOT_TOKEN, COOKIE_NAME, JWT_ALGORITHM, JWT_EXPIRE_DAYS, SECRET_KEY


def verify_telegram_auth(data: dict) -> bool:
    """Verify the hash from the Telegram Login Widget.

    Algorithm (Telegram standard):
      secret_key = SHA256(BOT_TOKEN)
      check_string = "\n".join(f"{k}={v}" for k,v sorted by k, excluding hash)
      expected = HMAC_SHA256(check_string, secret_key)
      valid if expected == provided hash
    """
    if not BOT_TOKEN:
        return False

    received_hash = data.get("hash")
    if not received_hash:
        return False

    pairs = sorted(
        f"{key}={value}" for key, value in data.items() if key != "hash"
    )
    check_string = "\n".join(pairs)

    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    expected_hash = hmac.new(
        secret_key, check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return False

    # Reject stale auth_date (older than 1 day) to limit replay.
    try:
        auth_date = int(data.get("auth_date", "0"))
    except (TypeError, ValueError):
        return False
    if time.time() - auth_date > 86400:
        return False

    return True


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
