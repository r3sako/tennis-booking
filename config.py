"""Centralized configuration loaded from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()


def _normalize_db_url(url: str) -> str:
    """Force the asyncpg driver regardless of how the URL is provided.

    Render (and most managed Postgres) hand out URLs like
    ``postgres://...`` or ``postgresql://...``. SQLAlchemy's async engine
    needs the ``postgresql+asyncpg://...`` driver scheme, so we rewrite it
    here — paste the Render URL as-is and it just works.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    # Strip a libpq-style ?sslmode=... query that asyncpg doesn't accept.
    if "?" in url:
        url = url.split("?", 1)[0]
    return url


DATABASE_URL = _normalize_db_url(os.getenv("DATABASE_URL", ""))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TG_BOT_USERNAME = os.getenv("TG_BOT_USERNAME", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "change_me_random_string")
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()
NOTIFY_CHAT_ID = os.getenv("NOTIFY_CHAT_ID", "").strip()
NOTIFY_NEW_BOOKING = os.getenv("NOTIFY_NEW_BOOKING", "false").lower() == "true"
# If set, only members of this Telegram chat may log in (residents' group).
# The bot must be a member/admin of this chat. Empty = no restriction.
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()


def _parse_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                pass
    return ids


# Telegram IDs exempt from the "1 booking per day" limit (e.g. the trainer).
# Comma-separated, e.g. "111111111,222222222".
UNLIMITED_USER_IDS = _parse_ids(os.getenv("UNLIMITED_USER_IDS", ""))

# Send the user a DM this many hours before their slot. 0 = reminders off.
try:
    REMINDER_HOURS_BEFORE = int(os.getenv("REMINDER_HOURS_BEFORE", "2"))
except ValueError:
    REMINDER_HOURS_BEFORE = 2
PORT = int(os.getenv("PORT", "8000"))
# Set to false for local HTTP testing (cookie won't be sent over http otherwise).
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

# Business constants
MOSCOW_TZ = "Europe/Moscow"
OPEN_HOUR = 8          # first slot starts at 08:00
CLOSE_HOUR = 22        # court closes at 22:00
LAST_SLOT_HOUR = 21    # last bookable slot starts at 21:00
BOOKING_WINDOW_DAYS = 14  # how many days ahead booking is open (today + 14)

COOKIE_NAME = "session"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30
