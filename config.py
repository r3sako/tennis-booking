"""Centralized configuration loaded from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TG_BOT_USERNAME = os.getenv("TG_BOT_USERNAME", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "change_me_random_string")
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()
NOTIFY_CHAT_ID = os.getenv("NOTIFY_CHAT_ID", "").strip()
NOTIFY_NEW_BOOKING = os.getenv("NOTIFY_NEW_BOOKING", "false").lower() == "true"
PORT = int(os.getenv("PORT", "8000"))
# Set to false for local HTTP testing (cookie won't be sent over http otherwise).
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

# Business constants
MOSCOW_TZ = "Europe/Moscow"
OPEN_HOUR = 7          # first slot starts at 07:00
CLOSE_HOUR = 22        # court closes at 22:00
LAST_SLOT_HOUR = 21    # last bookable slot starts at 21:00
BOOKING_WINDOW_DAYS = 14  # today + 13 days ahead

COOKIE_NAME = "session"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30
