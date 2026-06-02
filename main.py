"""FastAPI app: lifespan, routes, startup cleanup."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

import bookings as bk
from auth import create_session_token, get_current_user, verify_telegram_auth
from bot import close_bot, is_chat_member, notify_cancellation, notify_new_booking
from config import (
    ADMIN_KEY,
    BOOKING_WINDOW_DAYS,
    COOKIE_NAME,
    COOKIE_SECURE,
    JWT_EXPIRE_DAYS,
    TG_BOT_USERNAME,
)
from database import SessionLocal, get_session, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Data retention: drop everything before today (Moscow).
    async with SessionLocal() as session:
        deleted = await bk.cleanup_old_bookings(session)
        logger.info("Startup cleanup: removed %d past bookings", deleted)
    yield
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

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "user": user,
            "dates": dates,
            "today_iso": today.isoformat(),
            "current_booking": current,
        },
    )


@app.get("/login")
async def login(request: Request, error: str = ""):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)
    errors = {
        "auth": "Проверка Telegram не пройдена. Попробуйте ещё раз.",
        "forbidden": "Доступ только для жильцов дома — участников чата.",
    }
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "bot_username": TG_BOT_USERNAME,
            "error": errors.get(error, ""),
        },
    )


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.post("/auth/telegram")
async def auth_telegram(
    id: int = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    username: str = Form(""),
    photo_url: str = Form(""),
    auth_date: int = Form(...),
    hash: str = Form(...),
):
    data = {
        "id": str(id),
        "auth_date": str(auth_date),
        "hash": hash,
    }
    if first_name:
        data["first_name"] = first_name
    if last_name:
        data["last_name"] = last_name
    if username:
        data["username"] = username
    if photo_url:
        data["photo_url"] = photo_url

    if not verify_telegram_auth(data):
        return RedirectResponse(url="/login?error=auth", status_code=302)

    # Restrict access to members of the residents' chat (if configured).
    if not await is_chat_member(id):
        return RedirectResponse(url="/login?error=forbidden", status_code=302)

    name = (first_name + " " + last_name).strip() or username or str(id)
    token = create_session_token(id, username or None, name)

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
