"""aiogram 3 bot setup and notification helper.

The bot is optional: if BOT_TOKEN is not set, all calls become no-ops so the
app runs fine without Telegram notifications.
"""
import asyncio
import logging
import secrets
import time

from config import (
    ALLOWED_CHAT_ID,
    BOT_TOKEN,
    NOTIFY_CHAT_ID,
    NOTIFY_NEW_BOOKING,
    TG_BOT_USERNAME,
)

logger = logging.getLogger("bot")

_bot = None

# --------------------------------------------------------------------------- #
# Deep-link login token store (in-memory; single-process app).
#   token -> {"status": "pending"|"ok"|"forbidden", "user": {...}|None, "ts": float}
# --------------------------------------------------------------------------- #
_LOGIN_TTL = 300  # seconds a login link stays valid
_login_tokens: dict[str, dict] = {}


def _prune_tokens() -> None:
    now = time.time()
    for tok in [k for k, v in _login_tokens.items() if now - v["ts"] > _LOGIN_TTL]:
        _login_tokens.pop(tok, None)


def create_login_token() -> str:
    _prune_tokens()
    token = secrets.token_urlsafe(16)
    _login_tokens[token] = {"status": "pending", "user": None, "ts": time.time()}
    return token


def login_url(token: str) -> str:
    return f"https://t.me/{TG_BOT_USERNAME}?start={token}"


def get_login_entry(token: str) -> dict | None:
    _prune_tokens()
    return _login_tokens.get(token)


def consume_login_token(token: str) -> None:
    _login_tokens.pop(token, None)


def _get_bot():
    """Lazily build an aiogram Bot, or return None if disabled."""
    global _bot
    if not BOT_TOKEN:
        return None
    if _bot is None:
        from aiogram import Bot

        _bot = Bot(token=BOT_TOKEN)
    return _bot


async def _send(text: str) -> None:
    bot = _get_bot()
    if bot is None or not NOTIFY_CHAT_ID:
        return
    try:
        await bot.send_message(chat_id=NOTIFY_CHAT_ID, text=text)
    except Exception as exc:  # never let a notification failure break a request
        logger.warning("Failed to send Telegram notification: %s", exc)


async def send_dm(user_id: int, text: str) -> bool:
    """Send a private message to a user (who has started the bot). Best-effort."""
    bot = _get_bot()
    if bot is None:
        return False
    try:
        await bot.send_message(chat_id=user_id, text=text)
        return True
    except Exception as exc:  # user blocked the bot / never started it, etc.
        logger.info("DM to %s failed: %s", user_id, exc)
        return False


async def is_chat_member(user_id: int) -> bool:
    """Return True if the user may log in.

    If ALLOWED_CHAT_ID is empty or the bot is disabled, access is open
    (returns True). Otherwise the bot checks membership in that chat via
    getChatMember; only active members are allowed.
    """
    if not ALLOWED_CHAT_ID:
        return True  # no restriction configured
    bot = _get_bot()
    if bot is None:
        # Can't verify without a bot token; fail closed when a restriction
        # is configured so access isn't silently left open.
        logger.warning("ALLOWED_CHAT_ID set but BOT_TOKEN missing — denying login")
        return False
    try:
        member = await bot.get_chat_member(chat_id=ALLOWED_CHAT_ID, user_id=user_id)
    except Exception as exc:
        # User unknown to the chat / never joined → Telegram raises.
        logger.info("Membership check failed for %s: %s", user_id, exc)
        return False
    # Allowed statuses: creator, administrator, member, and restricted users
    # who are still in the chat. left/kicked are rejected.
    status = getattr(member, "status", None)
    if status in ("creator", "administrator", "member"):
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


def _who(username: str | None, name: str) -> str:
    return f"@{username}" if username else name


def _fmt_date(d) -> str:
    return d.strftime("%d.%m.%Y")


async def notify_cancellation(d, hour: int, username: str | None, name: str) -> None:
    text = (
        f"❌ {_who(username, name)} отменил бронь на "
        f"{_fmt_date(d)} {hour}:00–{hour + 1}:00. Слот снова свободен!"
    )
    await _send(text)


async def notify_new_booking(d, hour: int, username: str | None, name: str) -> None:
    if not NOTIFY_NEW_BOOKING:
        return
    text = (
        f"✅ {_who(username, name)} забронировал корт на "
        f"{_fmt_date(d)} {hour}:00–{hour + 1}:00"
    )
    await _send(text)


async def run_login_bot() -> None:
    """Listen for /start <token> deep links and complete website logins.

    The user opens https://t.me/<bot>?start=<token>, presses Start, and the
    bot binds their verified Telegram identity to that login token. The
    website (polling /auth/tg/poll) then receives a session. No-op if the
    bot is disabled.
    """
    bot = _get_bot()
    if bot is None:
        logger.info("BOT_TOKEN not set — deep-link login disabled")
        return

    from aiogram import Dispatcher
    from aiogram.filters import CommandStart

    dp = Dispatcher()

    async def on_start(message, command) -> None:
        token = (command.args or "").strip()
        logger.info(
            "Login /start from user=%s token=%r known_tokens=%d",
            message.from_user.id, token, len(_login_tokens),
        )
        if not token:
            await message.answer(
                "Это бот для авторизации на сайте бронирования теннисного корта.\n\n"
                "Писать сюда ничего не нужно — вход выполняется автоматически с сайта."
            )
            return
        entry = _login_tokens.get(token)
        if not entry or entry["status"] != "pending":
            await message.answer(
                "Ссылка для входа устарела. Обновите страницу входа и попробуйте снова."
            )
            return

        u = message.from_user
        if not await is_chat_member(u.id):
            entry["status"] = "forbidden"
            await message.answer("Доступ только для жильцов дома — участников чата.")
            return

        name = ((u.first_name or "") + " " + (u.last_name or "")).strip()
        name = name or (u.username or str(u.id))
        entry["user"] = {
            "tg_user_id": u.id,
            "tg_username": u.username,
            "tg_name": name,
        }
        entry["status"] = "ok"
        await message.answer("✅ Готово! Вернитесь на сайт — вы уже вошли.")

    dp.message.register(on_start, CommandStart())

    logger.info("Login bot started (long polling)")
    try:
        await dp.start_polling(bot, handle_signals=False, drop_pending_updates=True)
    except asyncio.CancelledError:
        pass


async def close_bot() -> None:
    bot = _get_bot()
    if bot is not None:
        await bot.session.close()
