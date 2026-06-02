# Деплой на свой VPS (Hetzner)

Весь стек — приложение, PostgreSQL и HTTPS-прокси Caddy — поднимается одной
командой на одной машине. Отдельная платная БД не нужна.

## 0. Что понадобится
- Аккаунт [Hetzner Cloud](https://console.hetzner.cloud).
- Домен (дешёвый или бесплатный — см. шаг 2).
- Бот в @BotFather (`BOT_TOKEN`, username).

## 1. Создать сервер
1. Hetzner Cloud → **Add Server**.
2. Тип: **CAX11** (ARM, 2 vCPU / 4 ГБ, ~€3.8/мес) — с запасом.
3. Образ: **Ubuntu 24.04**.
4. Добавь свой SSH-ключ (тот самый `id_ed25519.pub`).
5. Create. Запиши публичный **IP** сервера.

## 2. Домен → IP
Нужен домен, потому что Telegram-логин требует HTTPS, а Caddy выдаёт сертификат на домен.

**Платный** (Cloudflare/Namecheap, ~$1–10/год): создай **A-запись**
`tennis` (или @) → IP сервера.

**Бесплатный** через [DuckDNS](https://www.duckdns.org): получишь
`твоёимя.duckdns.org`, привяжешь к IP. Telegram и Caddy с ним работают.

Проверь, что резолвится:
```bash
dig +short tennis.example.com   # должен вернуть IP сервера
```

## 3. Поставить Docker на сервер
```bash
ssh root@IP_СЕРВЕРА
curl -fsSL https://get.docker.com | sh
```

## 4. Забрать код
```bash
# если репозиторий приватный — сначала добавь deploy-ключ на сервере
git clone git@github.com:r3sako/tennis-booking.git
cd tennis-booking
```

## 5. Заполнить переменные
```bash
cp .env.prod.example .env
nano .env
```
Заполни: `DOMAIN`, `POSTGRES_PASSWORD`, `SECRET_KEY`, `ADMIN_KEY`,
`BOT_TOKEN`, `TG_BOT_USERNAME`. Для уведомлений — `NOTIFY_CHAT_ID` и
`NOTIFY_NEW_BOOKING=true`.

> `.env` в git не попадает (он в `.gitignore`) — секреты остаются только на сервере.

## 6. Запустить
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
Caddy сам получит TLS-сертификат за ~10–30 сек. Открой `https://ТВОЙ_ДОМЕН`.

## 7. Привязать домен в Telegram
@BotFather → `/setdomain` → твой бот → отправь домен **без https://**:
```
tennis.example.com
```
Теперь вход через Telegram работает.

## Эксплуатация
```bash
# логи
docker compose -f docker-compose.prod.yml logs -f app

# обновить после git push
git pull && docker compose -f docker-compose.prod.yml up -d --build

# рестарт
docker compose -f docker-compose.prod.yml restart

# бэкап БД
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U tennis tennis > backup_$(date +%F).sql
```

## Заметки
- **Засыпаний нет** — сервис работает всегда, cron-пинг из README не нужен.
- Порт приложения наружу не торчит: открыты только 80/443 (Caddy).
- Данные БД в томе `pgdata`, сертификаты в `caddy_data` — переживают
  `up -d --build` и перезагрузки сервера.
- Файрвол (по желанию): оставь открытыми только 22, 80, 443.
