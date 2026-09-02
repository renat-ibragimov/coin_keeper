# 10. Инфраструктура и деплой

## Целевая площадка

Собственный сервер Hetzner + домен. Слабая конфигурация — этого достаточно: одновременных
пользователей единицы, база небольшая, тяжёлые операции фоновые.

Минимум: 2 vCPU, 4 ГБ RAM, 40 ГБ диска. Playwright с Chromium — самый прожорливый компонент,
под него держим запас памяти и ограничиваем одновременные задачи скрейпинга до одной.

## Состав

```
┌─ Caddy ──────────── HTTPS, Let's Encrypt, reverse proxy, отдача фронтенда
├─ api ────────────── FastAPI (uvicorn)
├─ worker ─────────── ARQ, фоновые задачи
├─ postgres ───────── PostgreSQL 16
├─ redis ──────────── очередь задач и rate limiting
└─ minio ──────────── S3-совместимое хранилище изображений
```

Всё в одном `docker-compose.yml`. Kubernetes на этом масштабе — лишняя сложность.

## Конфигурация

Только через переменные окружения. Файл `.env` на сервере, в репозитории — `.env.example`
с пустыми значениями.

```
DATABASE_URL=postgresql+asyncpg://coinkeeper:***@postgres:5432/coinkeeper
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://minio:9000
S3_BUCKET=coinkeeper-media
S3_ACCESS_KEY=***
S3_SECRET_KEY=***
JWT_SECRET=***
CORS_ORIGINS=https://<домен>
ALLOW_REGISTRATION=false
NBU_API_BASE=https://bank.gov.ua/NBUStatService/v1/statdirectory
LOG_LEVEL=INFO
```

`ALLOW_REGISTRATION=false` на старте: пока нет подтверждения email, публичная регистрация
на открытом домене соберёт ботов. Владелец создаётся скриптом миграции.

## Caddy

Автоматический HTTPS без ручной возни с сертификатами.

```
<домен> {
    handle /api/* {
        reverse_proxy api:8000
    }
    handle /media/* {
        reverse_proxy minio:9000
    }
    handle {
        root * /srv/frontend
        try_files {path} /index.html
        file_server
    }
    encode gzip zstd
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options nosniff
        Referrer-Policy strict-origin-when-cross-origin
    }
}
```

Фронтенд собирается в статику (`vite build`) и отдаётся Caddy напрямую — отдельный
Node-процесс не нужен.

## Бэкапы

В десктопной версии бэкап был функцией приложения: ZIP с базой, медиа, манифестом и
SHA-256. В вебе это задача сервера, из интерфейса убирается.

**База:**

```
ежедневно  pg_dump -Fc → /backups/db/coinkeeper-YYYY-MM-DD.dump
хранение   7 ежедневных, 4 еженедельных, 6 ежемесячных
```

**Изображения:** MinIO синхронизируется на внешнее хранилище (Hetzner Storage Box или
Backblaze B2) через `rclone`.

**Обязательно:** проверка восстановления. Бэкап, который ни разу не разворачивали, —
не бэкап. Раз в месяц восстанавливать дамп в отдельную базу и сверять количество записей.

Хранить бэкапы только на том же сервере нельзя.

## Миграции схемы

Alembic. Применяются при старте контейнера `api` до приёма трафика:

```
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Перед миграцией на боевой базе — свежий дамп. Автоматический откат не делаем: каждая
миграция должна быть обратимой или заведомо безопасной.

## Логи и наблюдение

На старте — минимум:

- Структурированные логи в JSON в stdout, собираются `docker compose logs`.
- Эндпоинт `GET /health`: проверка базы, Redis, S3.
- Отдельно логируются: все обращения к внешним источникам с URL и кодом ответа,
  все отклонённые цены с причиной, все ошибки фоновых задач.

Sentry, Prometheus, Grafana — когда появится реальная нагрузка. Раньше это трата времени.

## Ресурсные ограничения

```
worker:  1 одновременная задача скрейпинга, память ограничена в compose
api:     2 воркера uvicorn
postgres: shared_buffers 512MB, work_mem 16MB
```

Chromium в Playwright запускать с `--no-sandbox --disable-dev-shm-usage`
и монтировать увеличенный `/dev/shm`, иначе падает в контейнере.

## Выкладка

Вручную на первом этапе, этого достаточно:

```
git pull
docker compose build
docker compose up -d
```

GitHub Actions добавляем, когда выкладки станут частыми. Сборка фронтенда — в образе,
не на сервере: `node_modules` на слабой машине собирается долго.

## Домен и почта

- Домен указывает на IP сервера, Caddy получает сертификат автоматически.
- Почта понадобится для подтверждения email и восстановления пароля — внешний SMTP
  (Resend, Postmark, Mailgun). Свой почтовый сервер не поднимаем.

## Безопасность сервера

- Вход по SSH-ключу, парольная аутентификация отключена.
- Firewall: наружу открыты только 80, 443 и SSH. Postgres, Redis, MinIO — только внутри
  docker-сети, портов на хост не публикуем.
- Автоматические обновления безопасности.
- Регулярное обновление базовых образов.

## Чек-лист первого деплоя

```
□ Сервер, SSH-ключ, firewall
□ Домен указывает на сервер
□ docker и docker compose установлены
□ .env заполнен, JWT_SECRET сгенерирован случайно
□ docker compose up -d, все контейнеры healthy
□ HTTPS работает, сертификат выдан
□ alembic upgrade head прошёл
□ Скрипт миграции данных отработал, проверки из 09-data-migration.md пройдены
□ Владелец может войти
□ Бэкап настроен и один раз проверен восстановлением
□ ALLOW_REGISTRATION=false
```
