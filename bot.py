"""aiogram 3 bot setup and notification helper.

The bot is optional: if BOT_TOKEN is not set, all calls become no-ops so the
app runs fine without Telegram notifications.
"""
import logging

from config import BOT_TOKEN, NOTIFY_CHAT_ID, NOTIFY_NEW_BOOKING

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
