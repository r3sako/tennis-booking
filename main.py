"""FastAPI app: lifespan, routes, startup cleanup."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

import bookings as bk
from auth import create_session_token, get_current_user
from bot import (
    close_bot,
    consume_login_token,
    create_login_token,
    get_login_entry,
    is_chat_member,
    login_url,
    notify_cancellation,
    notify_new_booking,
    run_login_bot,
)
from config import (
    ADMIN_KEY,
    BOOKING_WINDOW_DAYS,
    BOT_TOKEN,
    COOKIE_NAME,
    COOKIE_SECURE,
    JWT_EXPIRE_DAYS,
    TG_BOT_USERNAME,
    UNLIMITED_USER_IDS,
)
from database import SessionLocal, get_session, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


CLEANUP_INTERVAL_SECONDS = 24 * 3600  # run retention cleanup once a day


async def _run_cleanup(label: str) -> None:
    async with SessionLocal() as session:
        deleted = await bk.cleanup_old_bookings(session)
    if deleted or label == "Startup":
        logger.info("%s cleanup: removed %d past bookings", label, deleted)


async def _periodic_cleanup() -> None:
    """Drop past-date bookings on a timer, so retention works even when the
    process runs for weeks without a restart (typical on a VPS)."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            await _run_cleanup("Periodic")
        except Exception as exc:  # never let the loop die on a transient error
            logger.warning("Periodic cleanup failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Data retention: drop everything before today (Moscow), now and on a timer.
    await _run_cleanup("Startup")
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    bot_task = asyncio.create_task(run_login_bot())
    yield
    cleanup_task.cancel()
    bot_task.cancel()
    await close_bot()


app = FastAPI(title="Tennis Court Booking", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/")
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    # Public page: schedule is viewable without login; booking requires auth.
    user = get_current_user(request)

    today = bk.today_moscow()
    dates = [
        {
            "iso": (today + bk.timedelta(days=i)).isoformat(),
            "day": (today + bk.timedelta(days=i)).day,
            "weekday": _ru_weekday(today + bk.timedelta(days=i)),
            "is_today": i == 0,
        }
        for i in range(BOOKING_WINDOW_DAYS)
    ]
    current = await bk.get_current_booking(session)
    unlimited = bool(user and user["tg_user_id"] in UNLIMITED_USER_IDS)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "user": user,
            "dates": dates,
            "today_iso": today.isoformat(),
            "current_booking": current,
            "unlimited": unlimited,
        },
    )


@app.get("/login")
async def login(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "bot_username": TG_BOT_USERNAME},
    )


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.get("/auth/dev")
async def auth_dev():
    """DEV-ONLY shortcut to obtain a session without Telegram.

    Disabled unless DEV_LOGIN=true. Never enable on a public deployment.
    """
    if os.getenv("DEV_LOGIN", "false").lower() != "true":
        return JSONResponse({"error": "Недоступно"}, status_code=404)
    token = create_session_token(999000001, "dev_user", "Dev User")
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=JWT_EXPIRE_DAYS * 86400,
    )
    return response


@app.post("/auth/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


# --------------------------------------------------------------------------- #
# Deep-link login via the bot
# --------------------------------------------------------------------------- #
@app.post("/auth/tg/start")
async def tg_login_start():
    """Issue a one-time login token and the t.me deep link to open the bot."""
    if not BOT_TOKEN or not TG_BOT_USERNAME:
        return JSONResponse(
            {"error": "Вход через Telegram не настроен"}, status_code=503
        )
    token = create_login_token()
    return {"token": token, "url": login_url(token)}


@app.get("/auth/tg/poll")
async def tg_login_poll(token: str):
    """Frontend polls this until the user confirms in Telegram.

    Returns: pending | ok (sets session cookie) | forbidden | expired.
    """
    entry = get_login_entry(token)
    if entry is None:
        return {"status": "expired"}
    if entry["status"] == "forbidden":
        consume_login_token(token)
        return {"status": "forbidden"}
    if entry["status"] == "ok":
        u = entry["user"]
        consume_login_token(token)
        jwt_token = create_session_token(
            u["tg_user_id"], u["tg_username"], u["tg_name"]
        )
        response = JSONResponse({"status": "ok"})
        response.set_cookie(
            key=COOKIE_NAME,
            value=jwt_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            max_age=JWT_EXPIRE_DAYS * 86400,
        )
        return response
    return {"status": "pending"}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/slots")
async def api_slots(date: str, session: AsyncSession = Depends(get_session)):
    try:
        d = bk.parse_date(date)
    except bk.BookingError as e:
        return JSONResponse({"error": e.message}, status_code=400)
    slots = await bk.get_slots(session, d)
    return {"date": d.isoformat(), "slots": slots}


@app.get("/api/today")
async def api_today(session: AsyncSession = Depends(get_session)):
    bookings = await bk.get_today_bookings(session)
    current = await bk.get_current_booking(session)
    return {"current": current, "bookings": bookings}


@app.post("/api/book")
async def api_book(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Необходима авторизация"}, status_code=401)

    # Re-verify chat membership on every booking so a resident who was removed
    # from the chat loses access immediately (their session is also cleared).
    if not await is_chat_member(user["tg_user_id"]):
        response = JSONResponse(
            {"error": "Доступ только для жильцов дома — участников чата."},
            status_code=403,
        )
        response.delete_cookie(COOKIE_NAME)
        return response

    body = await request.json()
    try:
        d = bk.parse_date(str(body.get("date", "")))
        hour = int(body.get("hour"))
    except (bk.BookingError, TypeError, ValueError):
        return JSONResponse({"error": "Неверные данные"}, status_code=400)

    try:
        booking = await bk.create_booking(
            session,
            d,
            hour,
            user["tg_user_id"],
            user["tg_username"],
            user["tg_name"],
        )
    except bk.BookingError as e:
        return JSONResponse({"error": e.message}, status_code=400)

    await notify_new_booking(d, hour, user["tg_username"], user["tg_name"])
    return {"booking_id": str(booking.id)}


@app.delete("/api/cancel/{booking_id}")
async def api_cancel(
    booking_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    user = get_current_user(request)
    admin_key = request.query_params.get("admin_key") or request.headers.get(
        "X-Admin-Key"
    )
    is_admin = bool(ADMIN_KEY) and admin_key == ADMIN_KEY

    if not user and not is_admin:
        return JSONResponse({"error": "Необходима авторизация"}, status_code=401)

    booking = await bk.get_booking(session, booking_id)
    if not booking or booking.cancelled:
        return JSONResponse({"error": "Бронь не найдена"}, status_code=404)

    if not is_admin and booking.tg_user_id != user["tg_user_id"]:
        return JSONResponse({"error": "Можно отменять только свою бронь"}, status_code=403)

    d, hour = booking.date, booking.hour
    username, name = booking.tg_username, booking.tg_name
    await bk.cancel_booking(session, booking)
    await notify_cancellation(d, hour, username, name)
    return {"status": "cancelled"}


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
@app.get("/admin")
async def admin(
    request: Request,
    key: str = "",
    session: AsyncSession = Depends(get_session),
):
    provided = key or request.headers.get("X-Admin-Key", "")
    if not ADMIN_KEY or provided != ADMIN_KEY:
        return JSONResponse({"error": "Необходима авторизация"}, status_code=401)

    today = bk.today_moscow()
    dates = []
    for i in range(BOOKING_WINDOW_DAYS):
        d = today + bk.timedelta(days=i)
        slots = await bk.get_slots(session, d)
        dates.append(
            {
                "iso": d.isoformat(),
                "label": d.strftime("%d.%m.%Y"),
                "weekday": _ru_weekday(d),
                "slots": [s for s in slots if s["status"] == "booked"],
            }
        )

    return templates.TemplateResponse(
        request,
        "admin.html",
        {"request": request, "dates": dates, "admin_key": ADMIN_KEY},
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_RU_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _ru_weekday(d) -> str:
    return _RU_WEEKDAYS[d.weekday()]
