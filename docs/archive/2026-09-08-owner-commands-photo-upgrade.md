# Команды владельца — photo-upgrade, общая замена фото (2026-09-08)

Код и тесты — в `main`. К боевой базе сессия ничего не применяла. Подробности —
`backend/README.md`, раздел «photo-upgrade», и `docs/05-integrations.md`,
раздел 13. Здесь — только последовательность команд и что смотреть между
прогонами.

## Права на запись отчётов (наболевшее, проверено в тестовом контейнере)

Контейнер `api` (прод-образ, `target: production` в `docker-compose.yml`)
всегда работает как `uid=1001 gid=1001` (пользователь `app`), не root —
проверено `docker run ... id`. Примонтированная директория, принадлежащая
вашему обычному пользователю на хосте, для него не пишется — отсюда и ушла
первая волна в `/tmp`.

Рабочая схема, тоже проверенная (`docker run --user "$(id -u):$(id -g)"
ghcr.io/coinkeeper/coinkeeper-api:latest ...` — запись в примонтированную
директорию прошла, `import app` внутри тоже сработал под чужим uid): вместо
`chown` директории в `1001:1001` (нужен `sudo`, и если разных отчётов
несколько — начинают путаться, кто чем владеет) **запускайте контейнер под
своим же хостовым uid/gid**:

```bash
mkdir -p migration-reports/photo-upgrade
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/migration-reports:/reports" \
  api python -c "import app; print('ok')"
```

Если это напечатало `ok` без ошибок доступа — директория готова. Дальше
везде ниже — с тем же `--user "$(id -u):$(id -g)"`.

Если `migration-reports/` (без поддиректории) у вас уже когда-то был
`chown`-нут в `1001:1001` под легаси-миграцию или первую волну упаковочного
скана — не смешивайте схемы в одной директории. `migration-reports/
photo-upgrade/` — отдельная, ваша, только под этот шаг.

## Ревью-файл этому шагу не обязателен

В отличие от `bridge`/`scan_coin_photo_packaging.py`, здесь стоп-точка —
просто **посмотреть диф глазами**. `--apply` без ревью-файла применяет
дифф целиком, ровно то, что показал dry-run (страницы и картинки кэшированы
— повторный прогон бесплатный и детерминированный). `--apply-photo-upgrade-
review` со строками `decision=yes` — если хотите применить только часть;
редактировать URL-колонки в CSV бессмысленно — шаг их не читает обратно, он
пересчитывает тот же результат из кэша.

## Шаг 1 (dry-run) — посмотреть дифф

```bash
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --dry-run \
    --steps photo-upgrade \
    --photo-upgrade-out /reports/photo-upgrade/diff.csv \
    --report /reports/photo-upgrade/report.json \
    --cache-dir /reports/ukraine-cache
```

Ничего не пишется. `diff.csv` — только строки с заменой: `itemId`, `title`,
`year`, `currentScore`/`candidateScore`, `tier` (`metadata`/`geometry`),
`obverseUrl`/`reverseUrl`.

**СТОП-ТОЧКА.** Открыть `diff.csv` и `report.json`. Смотреть:

- `report.json` → `steps.photo-upgrade` → `scanned`/`withReplacement`/
  `withoutPage`/`fallbacks`/`failed` — порядок величин разумный (`scanned`
  около тысячи — записей с известной страницей ua-coins.info).
- В `diff.csv` должны найтись сувенирные буклеты первой волны («Служба
  зовнішньої розвідки України», «Тримаймо стрій!» и родня — около 47
  записей с геометрией буклета) — если их там нет, что-то не так с самим
  парсингом галереи, дальше не идти.
- «Писанка» и «Пектораль» — в `diff.csv` их быть НЕ должно (защита
  фигурных монет срабатывает автоматически, без special-case в коде —
  `05-integrations.md`, раздел 13).
- 12 записей «Ми сильні. Ми разом.%» — в `diff.csv` их тоже быть не
  должно: они уже заменены первой волной (`docs/2026-09-08-owner-
  commands.md`), их текущий скор уже высокий, `photo-upgrade` их не
  тронет повторно.
- `report.json` → `details.photo-upgrade.duplicateTitles` — список пар
  одинаковых `title_original`+`issue_year` (например «Український
  борщ» ×2). Это только отчёт, ничего не трогает; разбор — после этого
  прогона, `docs/BACKLOG.md`.

Дальше — только если дифф выглядит разумно.

## Шаг 2 (apply) — заменить

Весь дифф разом:

```bash
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply \
    --steps photo-upgrade \
    --report /reports/photo-upgrade/apply-report.json \
    --cache-dir /reports/ukraine-cache
```

Или только часть — поставить `yes` в `decision` нужных строк `diff.csv` и:

```bash
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply \
    --steps photo-upgrade \
    --apply-photo-upgrade-review /reports/photo-upgrade/diff.csv \
    --report /reports/photo-upgrade/apply-report.json \
    --cache-dir /reports/ukraine-cache
```

`apply-report.json` → `steps.photo-upgrade` → `replaced`/`failedApply`.
Строка, у которой не скачалась картинка — в `failed`, старое фото этой
записи остаётся как было (никакого частичного состояния).

## Шаг 3 — проверка идемпотентности

Повторить шаг 1 (тот же `--dry-run`, можно в тот же `diff.csv` — перезапишет):

```bash
docker compose run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --dry-run \
    --steps photo-upgrade \
    --photo-upgrade-out /reports/photo-upgrade/diff-after.csv \
    --report /reports/photo-upgrade/report-after.json \
    --cache-dir /reports/ukraine-cache
```

Ожидается: `diff-after.csv` — пустой (только заголовок), кроме строк, для
которых apply шага 2 упал в `failed` (их можно повторить отдельно). Заменённое
фото само стало «текущим» с высоким скором — второй прогон его не тронет.

## Проверка на фронте

Карточки заменённых записей — чистые фото монет, не буклеты/ролики, в
обеих темах (глазами).
