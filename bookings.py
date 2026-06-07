"""Booking CRUD, slot generation, time helpers and validation."""
import uuid
from datetime import date as date_cls
from datetime import datetime, timedelta

import pytz
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    BOOKING_WINDOW_DAYS,
    LAST_SLOT_HOUR,
    MOSCOW_TZ,
    OPEN_HOUR,
    UNLIMITED_USER_IDS,
)
from database import Booking

TZ = pytz.timezone(MOSCOW_TZ)


class BookingError(Exception):
    """Domain error carrying a Russian user-facing message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def now_moscow() -> datetime:
    return datetime.now(TZ)


def today_moscow() -> date_cls:
    return now_moscow().date()


def all_hours() -> list[int]:
    """The 15 bookable slot start hours: 07..21."""
    return list(range(OPEN_HOUR, LAST_SLOT_HOUR + 1))


def parse_date(value: str) -> date_cls:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise BookingError("Неверная дата")


def window_dates() -> list[date_cls]:
    """All bookable dates: today through 14 days ahead."""
    today = today_moscow()
    return [today + timedelta(days=i) for i in range(BOOKING_WINDOW_DAYS + 1)]


def is_within_window(d: date_cls) -> bool:
    """True if the date is within the booking window (today .. today+14)."""
    today = today_moscow()
    return today <= d <= today + timedelta(days=BOOKING_WINDOW_DAYS)


def is_past_slot(d: date_cls, hour: int) -> bool:
    """True if the slot start time is already in the past (Moscow time)."""
    now = now_moscow()
    slot_start = TZ.localize(datetime(d.year, d.month, d.day, hour, 0, 0))
    return slot_start <= now


async def cleanup_old_bookings(session: AsyncSession) -> int:
    """Delete every booking with date < today (Moscow). Returns row count."""
    today = today_moscow()
    result = await session.execute(delete(Booking).where(Booking.date < today))
    await session.commit()
    return result.rowcount or 0


async def get_slots(session: AsyncSession, d: date_cls) -> list[dict]:
    """Return slot state for a date: free/booked plus booker info."""
    result = await session.execute(
        select(Booking).where(Booking.date == d, Booking.cancelled.is_(False))
    )
    booked = {b.hour: b for b in result.scalars().all()}

    slots = []
    for hour in all_hours():
        b = booked.get(hour)
        if b:
            slots.append(
                {
                    "hour": hour,
                    "status": "booked",
                    "tg_user_id": b.tg_user_id,
                    "tg_username": b.tg_username,
                    "tg_name": b.tg_name,
                    "booking_id": str(b.id),
                    "past": is_past_slot(d, hour),
                }
            )
        else:
            slots.append(
                {
                    "hour": hour,
                    "status": "free",
                    "past": is_past_slot(d, hour),
                }
            )
    return slots


async def get_today_bookings(session: AsyncSession) -> list[dict]:
    """Active bookings for today, ordered by hour."""
    today = today_moscow()
    result = await session.execute(
        select(Booking)
        .where(
            Booking.date == today,
            Booking.cancelled.is_(False),
        )
        .order_by(Booking.hour)
    )
    return [
        {
            "hour": b.hour,
            "tg_username": b.tg_username,
            "tg_name": b.tg_name,
            "booking_id": str(b.id),
        }
        for b in result.scalars().all()
    ]


async def get_current_booking(session: AsyncSession) -> dict | None:
    """The booking covering the current hour today, if any."""
    today = today_moscow()
    hour = now_moscow().hour
    result = await session.execute(
        select(Booking).where(
            Booking.date == today,
            Booking.hour == hour,
            Booking.cancelled.is_(False),
        )
    )
    b = result.scalar_one_or_none()
    if not b:
        return None
    return {"hour": b.hour, "tg_username": b.tg_username, "tg_name": b.tg_name}


async def user_has_booking_on(
    session: AsyncSession, tg_user_id: int, d: date_cls
) -> bool:
    result = await session.execute(
        select(Booking).where(
            Booking.date == d,
            Booking.tg_user_id == tg_user_id,
            Booking.cancelled.is_(False),
        )
    )
    return result.first() is not None


async def create_booking(
    session: AsyncSession,
    d: date_cls,
    hour: int,
    tg_user_id: int,
    tg_username: str | None,
    tg_name: str,
) -> Booking:
    """Validate business rules and insert a booking. Raises BookingError."""
    if hour not in all_hours():
        raise BookingError("Этот слот уже занят")

    if not is_within_window(d):
        raise BookingError("Бронирование доступно только на 14 дней вперёд")

    if is_past_slot(d, hour):
        raise BookingError("Этот слот уже прошёл")

    # One active booking per user per day — except privileged users (trainer).
    if tg_user_id not in UNLIMITED_USER_IDS and await user_has_booking_on(
        session, tg_user_id, d
    ):
        raise BookingError("Вы уже бронировали корт на этот день")

    # Slot must be free (active booking on same date+hour).
    existing = await session.execute(
        select(Booking).where(
            Booking.date == d,
            Booking.hour == hour,
            Booking.cancelled.is_(False),
        )
    )
    if existing.first() is not None:
        raise BookingError("Этот слот уже занят")

    booking = Booking(
        date=d,
        hour=hour,
        tg_user_id=tg_user_id,
        tg_username=tg_username,
        tg_name=tg_name,
        cancelled=False,
    )
    session.add(booking)
    try:
        await session.commit()
    except Exception:
        # Likely the UNIQUE(date, hour) constraint — slot taken concurrently.
        await session.rollback()
        raise BookingError("Этот слот уже занят")
    await session.refresh(booking)
    return booking


async def get_booking(session: AsyncSession, booking_id: str) -> Booking | None:
    try:
        bid = uuid.UUID(booking_id)
    except (ValueError, TypeError):
        return None
    result = await session.execute(select(Booking).where(Booking.id == bid))
    return result.scalar_one_or_none()


async def cancel_booking(session: AsyncSession, booking: Booking) -> None:
    """Hard-delete the booking so the slot frees up (and UNIQUE is released)."""
    await session.delete(booking)
    await session.commit()
