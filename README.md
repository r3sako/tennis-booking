# 🎾 Tennis Court Booking

Веб-приложение для бронирования теннисного корта в жилом комплексе.
Просмотр расписания открыт всем; бронирование и отмена — после входа через
Telegram. Вход устроен через бота (deep-link), без номера телефона и сторонних
окон. Доступ можно ограничить только участниками чата жильцов.

## Возможности
- 📅 Публичное расписание на 14 дней (сегодня + 13).
- 🔐 Вход через Telegram-бота: кнопка на сайте → «Запустить» в боте → готово.
- 🏠 Опционально: вход только для участников чата жильцов (`getChatMember`).
- 🔔 Уведомления в чат при отмене брони (и опц. при новой брони).
- 🧹 Авто-очистка: хранятся только сегодня + будущее, прошлое удаляется.
- 🛠 Админ-панель для отмены любых броней.

## Стек
- **Backend:** Python 3.12, FastAPI, Uvicorn
- **БД:** PostgreSQL (asyncpg + SQLAlchemy async)
- **Auth:** Telegram deep-link login + JWT в httpOnly-cookie
- **Бот:** aiogram 3 (long polling, в том же процессе)
- **Frontend:** Jinja2 + Tailwind (self-hosted) + vanilla JS
- **Прод:** Docker Compose (app + Postgres + Caddy с авто-HTTPS)

## Правила бронирования
- Часы корта: **07:00–22:00** (МСК), слоты по 1 часу — старт 07:00…21:00 (15 слотов).
- Бронь доступна на **сегодня + 13 дней**.
- **1 активная бронь на пользователя в день.**
- Нельзя бронировать прошедший слот.
- Старые брони (дата < сегодня по МСК) удаляются при старте и раз в сутки.

---

## Как работает вход
1. На `/login` пользователь жмёт «Войти через Telegram».
2. Сайт создаёт одноразовый токен и открывает `https://t.me/<bot>?start=<token>`.
3. Пользователь нажимает «Запустить» — бот получает токен и проверенную личность.
4. Если задан `ALLOWED_CHAT_ID`, бот проверяет членство в чате жильцов.
5. Сайт (опрашивает `/auth/tg/poll`) получает сессию — JWT в httpOnly-cookie на 30 дней.

> Для входа обязательны `BOT_TOKEN` и `TG_BOT_USERNAME`. `/setdomain` в BotFather
> при таком способе **не нужен**.

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | Строка подключения к PostgreSQL. Принимает `postgres://`, `postgresql://` или `postgresql+asyncpg://` — приводится к asyncpg автоматически. |
| `BOT_TOKEN` | Токен бота от @BotFather. Без него вход и уведомления отключены. |
| `TG_BOT_USERNAME` | Username бота без `@` (для deep-link ссылки). |
| `SECRET_KEY` | Секрет для подписи JWT. Длинная случайная строка. Не меняйте после запуска. |
| `ADMIN_KEY` | Ключ доступа к `/admin`. |
| `NOTIFY_CHAT_ID` | ID чата для уведомлений об отменах. Пусто = не слать. |
| `NOTIFY_NEW_BOOKING` | `true`/`false` — слать ли уведомления о новых бронях. |
| `ALLOWED_CHAT_ID` | Если задан — войти могут только участники этого чата. Бот должен быть его участником/админом. Пусто = вход открыт. |
| `COOKIE_SECURE` | `true` на проде (HTTPS). `false` только для локального HTTP. |
| `DEV_LOGIN` | `true` включает `/auth/dev` (вход без Telegram). Только для разработки! |
| `PORT` | Порт приложения (по умолчанию 8000). |

---

## Локальная разработка

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

docker compose up -d          # Postgres на localhost:5433
cp .env.example .env          # выставьте COOKIE_SECURE=false, DEV_LOGIN=true

uvicorn main:app --reload
```

Откройте http://localhost:8000 — расписание. Для входа без Telegram при
`DEV_LOGIN=true` зайдите на http://localhost:8000/auth/dev.

---

## Деплой в прод (VPS)

Полная пошаговая инструкция (сервер, домен, Docker, Caddy, HTTPS) —
в **[DEPLOY-hetzner.md](DEPLOY-hetzner.md)**. Кратко:

```bash
# на сервере
git clone https://github.com/r3sako/tennis-booking.git
cd tennis-booking
cp .env.prod.example .env      # заполнить значения
docker compose -f docker-compose.prod.yml up -d --build
```

Поднимает app + Postgres + Caddy (авто-SSL Let's Encrypt) на одной машине.
БД и сертификаты — в Docker-томах, переживают перезапуски.

Обновление после `git push`:
```bash
git pull && docker compose -f docker-compose.prod.yml up -d --build
```

---

## Настройка Telegram-бота

### 1. Создать бота
@BotFather → `/newbot` → имя и username. Сохрани токен → `BOT_TOKEN`,
username (без `@`) → `TG_BOT_USERNAME`.

Описание и «о боте» (по желанию): `/setdescription`, `/setabouttext`.
Команды боту не нужны — вход выполняется автоматически.

### 2. Добавить бота в чат жильцов
Добавь бота в чат и сделай **админом** (иначе не сможет писать и проверять участников).

### 3. Узнать ID чата
1. Напиши любое сообщение в чате.
2. Открой `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`.
3. Найди `"chat":{"id":-100…}` — это ID (у групп отрицательный).

Впиши его в `.env`:
```
NOTIFY_CHAT_ID=-1001234567890     # уведомления об отменах
ALLOWED_CHAT_ID=-1001234567890    # вход только для участников этого чата
```
Обычно это один и тот же чат. После правки `.env`:
```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## Админ-панель
`GET /admin?key=<ADMIN_KEY>` — список броней на 14 дней с возможностью отмены любой.

## Эндпоинты API
- `GET /health` — `{"status":"ok"}`
- `GET /api/slots?date=YYYY-MM-DD` — расписание дня (публично)
- `GET /api/today` — брони на сегодня (публично)
- `POST /api/book` — создать бронь (нужна авторизация)
- `DELETE /api/cancel/{id}` — отменить свою бронь (или любую с `?admin_key=`)
