# CoinKeeper

Веб-приложение для учёта коллекции монет: общий каталог выпусков, личные позиции, личная
коллекция, покупки и расходы, рыночные цены, комплектность по сериям.

Общий каталог доступен пользователю только на чтение — его ведут администратор и фоновая
задача по официальному каталогу НБУ. Чего в нём нет, пользователь заводит личными позициями
или подгружает импортом; они видны только ему. Регистрация открыта, интерфейс на украинском
и английском.

Преемник закрытого десктопного приложения (Electron + SQLite). Пишется с нуля:
Python-бэкенд, PostgreSQL, React-фронтенд.

## Стек

FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis · ARQ · Playwright ·
MinIO · React 19 · TypeScript · Vite · Docker Compose

## Структура

```
docs/       спецификации — читать перед кодом
legacy/     артефакты десктопной версии: схема, эталонный код, ТЗ, тексты интерфейса
backend/    FastAPI-приложение
frontend/   React-приложение
```

## С чего начать

1. [`docs/00-overview.md`](docs/00-overview.md) — карта документов и предыстория
2. [`docs/01-scope-mvp.md`](docs/01-scope-mvp.md) — границы MVP
3. [`docs/11-roadmap.md`](docs/11-roadmap.md) — этапы и текущая задача
4. [`CLAUDE.md`](CLAUDE.md) — правила проекта

## Документация

| | |
|---|---|
| [00-overview](docs/00-overview.md) | Обзор, что уцелело от прошлой версии |
| [01-scope-mvp](docs/01-scope-mvp.md) | Что делаем и что откладываем |
| [02-data-model](docs/02-data-model.md) | Схема PostgreSQL |
| [03-api-contract](docs/03-api-contract.md) | REST-эндпоинты |
| [04-business-rules](docs/04-business-rules.md) | Комплектность, валюты, дедупликация, права на записи |
| [05-integrations](docs/05-integrations.md) | НБУ (курсы и каталог), UA-Coins, uCoin |
| [06-media-storage](docs/06-media-storage.md) | Хранение изображений, происхождение и права |
| [07-auth](docs/07-auth.md) | Аутентификация, регистрация, доступ |
| [08-ui-map](docs/08-ui-map.md) | Экраны и тексты |
| [09-data-migration](docs/09-data-migration.md) | Перенос SQLite → PostgreSQL |
| [10-infra](docs/10-infra.md) | Docker Compose, Hetzner, почта, бэкапы |
| [11-roadmap](docs/11-roadmap.md) | Порядок работ |
| [12-user-facing-scope](docs/12-user-facing-scope.md) | Что умеет приложение, простыми словами |

## Статус

Этап 0 (документация) завершён. Следующий — каркас бэкенда: схема, аутентификация с
подтверждением email и восстановлением пароля, отправка почты, ограничение частоты
(`docs/11-roadmap.md`, этап 1).

## Данные

Реальная база коллекции и фотографии лежат в `legacy/data/` и **исключены из git**:
репозиторий публичный, а там личные данные — покупки, суммы, даты.
