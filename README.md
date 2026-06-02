# 🎾 Tennis Court Booking

Веб-приложение для бронирования теннисного корта в жилом комплексе. Просмотр
расписания открыт всем; бронирование и отмена — через вход по Telegram.

## Стек
- **Backend:** Python 3.12, FastAPI, Uvicorn
- **БД:** PostgreSQL (asyncpg + SQLAlchemy async)
- **Auth:** Telegram Login Widget + JWT в httpOnly-cookie
- **Бот:** aiogram 3 (уведомления в группу)
- **Frontend:** Jinja2 + Tailwind (CDN) + vanilla JS

## Правила
- Часы работы корта: **07:00–22:00** (МСК), слоты по 1 часу — старт 07:00…21:00 (15 слотов).
- Бронь доступна на **сегодня + 13 дней** (окно 14 дней).
- **1 активная бронь на пользователя в день.**
- Нельзя бронировать прошедший слот.
- При старте приложения удаляются все брони с датой раньше сегодняшней (МСК) — БД остаётся компактной.

---

## Локальный запуск

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # заполните переменные
uvicorn main:app --reload
```

Нужен доступный PostgreSQL и корректный `DATABASE_URL`
(`postgresql+asyncpg://user:pass@host:5432/dbname`).

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | Строка подключения к PostgreSQL (`postgresql+asyncpg://…`). На Render задаётся автоматически. |
| `BOT_TOKEN` | Токен бота из @BotFather. Если пусто — уведомления отключаются молча. |
| `TG_BOT_USERNAME` | Username бота (без `@`) для виджета входа. |
| `SECRET_KEY` | Секрет для подписи JWT. Задайте длинную случайную строку. |
| `ADMIN_KEY` | Ключ для доступа к `/admin`. |
| `NOTIFY_CHAT_ID` | ID чата/группы для уведомлений. |
| `NOTIFY_NEW_BOOKING` | `true`/`false` — слать ли уведомление о новой брони. |
| `PORT` | Порт (Render задаёт сам). |

---

## Развёртывание на Render.com

1. Запушьте репозиторий на GitHub.
2. В Render: **New → Blueprint** или **New → Web Service**, подключите репозиторий.
3. Тип — **Docker** (в репозитории есть `Dockerfile`). Render сам прокинет `PORT`.
4. Создайте базу: **New → PostgreSQL**. После создания скопируйте **Internal Database URL**.
   > ⚠️ Render выдаёт URL вида `postgres://…`. Замените схему на
   > `postgresql+asyncpg://…` (остальное оставьте как есть) и впишите в `DATABASE_URL` web-сервиса.
5. В разделе **Environment** web-сервиса добавьте переменные из таблицы выше
   (`SECRET_KEY`, `BOT_TOKEN`, `TG_BOT_USERNAME`, `ADMIN_KEY`, `NOTIFY_CHAT_ID`, `NOTIFY_NEW_BOOKING`).
6. **Health Check Path:** `/health`.
7. Deploy. После сборки приложение будет доступно по адресу `https://<имя>.onrender.com`.

---

## Создание Telegram-бота (@BotFather)

1. Откройте [@BotFather](https://t.me/BotFather) → `/newbot`, задайте имя и username.
2. Скопируйте токен → переменная `BOT_TOKEN`. Username (без `@`) → `TG_BOT_USERNAME`.
3. Привяжите домен для Login Widget:
   - `/setdomain` → выберите бота → отправьте домен **без https://**, например `my-app.onrender.com`.
   - Без этого виджет входа работать не будет.

---

## Добавление бота в группу и получение `NOTIFY_CHAT_ID`

1. Создайте группу и добавьте туда бота.
2. Дайте боту право писать сообщения (для приватных групп — сделайте админом).
3. Узнать ID группы:
   - Напишите любое сообщение в группе.
   - Откройте `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` в браузере.
   - Найдите `"chat":{"id":-1001234567890,...}` — это и есть `NOTIFY_CHAT_ID`
     (у групп ID отрицательный).
4. Впишите значение в `NOTIFY_CHAT_ID`. Для уведомлений о новых бронях
   поставьте `NOTIFY_NEW_BOOKING=true`.

---

## Защита от «засыпания» (cron-job.org)

Бесплатный план Render усыпляет сервис при простое. Чтобы держать его «живым»:

1. Зарегистрируйтесь на [cron-job.org](https://cron-job.org).
2. **Create cronjob.**
3. URL: `https://<имя>.onrender.com/health`
4. Расписание: каждые **10 минут** (`*/10 * * * *`).
5. Сохраните и включите. Эндпоинт отдаёт `{"status":"ok"}`.

---

## Админ-панель

`GET /admin?key=<ADMIN_KEY>` — список броней на 14 дней с возможностью отмены любой.
