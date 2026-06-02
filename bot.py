"""aiogram 3 bot setup and notification helper.

The bot is optional: if BOT_TOKEN is not set, all calls become no-ops so the
app runs fine without Telegram notifications.
"""
import logging

from config import ALLOWED_CHAT_ID, BOT_TOKEN, NOTIFY_CHAT_ID, NOTIFY_NEW_BOOKING

logger = logging.getLogger("bot")

_bot = None


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


async def close_bot() -> None:
    bot = _get_bot()
    if bot is not None:
        await bot.session.close()
