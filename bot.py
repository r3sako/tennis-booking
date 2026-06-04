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
    SITE_URL,
)

logger = logging.getLogger("bot")

_bot = None

# --------------------------------------------------------------------------- #
# Login token store (in-memory; single-process app). The bot creates a token
# bound to a verified user and sends back a "log in" link; the site consumes it.
#   token -> {"user": {...}, "ts": float}
# --------------------------------------------------------------------------- #
_LOGIN_TTL = 600  # seconds a login link stays valid
_login_tokens: dict[str, dict] = {}


def _prune_tokens() -> None:
    now = time.time()
    for tok in [k for k, v in _login_tokens.items() if now - v["ts"] > _LOGIN_TTL]:
        _login_tokens.pop(tok, None)


def create_login_token(user: dict) -> str:
    """Store a verified user and return a one-time token for the login link."""
    _prune_tokens()
    token = secrets.token_urlsafe(24)
    _login_tokens[token] = {"user": user, "ts": time.time()}
    return token


def consume_login_token(token: str) -> dict | None:
    """Return the user for a valid token (and invalidate it), else None."""
    _prune_tokens()
    entry = _login_tokens.pop(token, None)
    return entry["user"] if entry else None


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
    """Listen for /start and send the user a one-time "log in" link.

    The user opens the bot (from the site button or by username) and presses
    Start. The bot verifies chat membership, then replies with an inline button
    linking to {SITE_URL}/auth/tg/enter?token=..., which logs them in when
    tapped. No polling needed — robust inside the Telegram in-app browser.
    No-op if the bot is disabled.
    """
    bot = _get_bot()
    if bot is None:
        logger.info("BOT_TOKEN not set — login bot disabled")
        return

    from aiogram import Dispatcher
    from aiogram.filters import CommandStart
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    dp = Dispatcher()

    async def on_start(message, command) -> None:
        u = message.from_user
        logger.info("Login /start from user=%s", u.id)

        if not await is_chat_member(u.id):
            await message.answer("Доступ только для жильцов дома — участников чата.")
            return

        if not SITE_URL:
            await message.answer(
                "Сайт не настроен (не задан SITE_URL). Обратитесь к администратору."
            )
            return

        name = ((u.first_name or "") + " " + (u.last_name or "")).strip()
        name = name or (u.username or str(u.id))
        token = create_login_token(
            {"tg_user_id": u.id, "tg_username": u.username, "tg_name": name}
        )
        url = f"{SITE_URL}/auth/tg/enter?token={token}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🎾 Войти на сайт", url=url)]]
        )
        await message.answer(
            "Нажмите кнопку ниже, чтобы войти на сайт ⤵️\n"
            "Ссылка действует 10 минут.",
            reply_markup=kb,
        )

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
