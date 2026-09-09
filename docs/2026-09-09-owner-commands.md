# Команды владельца — миграция 0006 и «джерело» в карточке (2026-09-09)

Код, тесты и доки — в `main`. К боевой базе сессия ничего не применяла.

Задача целиком в двух вещах: схема (одна миграция) и приоритет источника
ссылки на карточке монеты. Второе — чистое чтение, применяется вместе с
образом и никаких ручных шагов не требует. Ниже — только про миграцию,
потому что она **удаляет строки** и это единственное место, где стоит
посмотреть глазами до применения.

## Что делает миграция 0006

Четыре добавления и одна пересборка констрейнта:

- `coin_series.is_official` — boolean NOT NULL DEFAULT false. Бэкфилла нет,
  флаг проставит `load-series` из coin-parser.
- `catalog_items.status` — text NOT NULL DEFAULT `'active'` +
  CHECK (`draft` / `active` / `rejected`). Существующие строки становятся
  `'active'` через server_default. **Ни API, ни выборки каталога колонку не
  читают** — фильтрация драфтов это задача этапа админки.
- `catalog_items.edited_fields` — jsonb, пока никто не пишет.
- `catalog_items.quality` — text, качество чеканки каноническим кодом.
- `uq_market_price_snapshots_item_source_grade_observed` пересоздаётся как
  `UNIQUE NULLS NOT DISTINCT`. **Перед пересозданием миграция удаляет
  дубли** — в каждой группе с `grade IS NULL` и одинаковыми
  `catalog_item_id` / `source` / `observed_at` остаётся строка с
  минимальным `id`. Без этого констрейнт просто не создастся.

## Шаг 1 (только посмотреть) — сколько строк снимет дедупликация

Ничего не меняет, безопасно запускать на боевой базе.

```bash
docker compose exec postgres psql -U coinkeeper -d coinkeeper -c "
SELECT count(*) AS to_delete
FROM (
  SELECT id, row_number() OVER (
           PARTITION BY catalog_item_id, source, observed_at ORDER BY id
         ) AS n
  FROM market_price_snapshots
  WHERE grade IS NULL
) t
WHERE t.n > 1;"
```

Если хочется увидеть сами группы, а не число:

```bash
docker compose exec postgres psql -U coinkeeper -d coinkeeper -c "
SELECT catalog_item_id, source, observed_at, count(*), array_agg(id ORDER BY id),
       array_agg(price ORDER BY id)
FROM market_price_snapshots
WHERE grade IS NULL
GROUP BY catalog_item_id, source, observed_at
HAVING count(*) > 1
ORDER BY count(*) DESC
LIMIT 50;"
```

**СТОП-ТОЧКА.** Смотрим на `array_agg(price)` в группах: если внутри
группы цены одинаковые — это ровно те дубли, ради которых констрейнт и
затягивается, удалять их не жалко. Если цены **разные** при одинаковой
метке времени до микросекунды, значит загрузчик когда-то записал две
разные цены одним `observed_at`; выживет меньший `id`, остальные уйдут.
Сессия боевую базу не видела и обещать, что таких групп нет, не может —
поэтому шаг и вынесен отдельно.

Если хочется сохранить снимок удаляемого перед применением:

```bash
docker compose exec postgres psql -U coinkeeper -d coinkeeper -c "
COPY (
  SELECT * FROM market_price_snapshots s
  WHERE s.grade IS NULL
    AND EXISTS (SELECT 1 FROM market_price_snapshots k
                WHERE k.grade IS NULL
                  AND k.catalog_item_id = s.catalog_item_id
                  AND k.source = s.source
                  AND k.observed_at = s.observed_at
                  AND k.id < s.id)
) TO STDOUT WITH CSV HEADER" > migration-reports/0006-dropped-snapshots.csv
```

## Шаг 2 — применить миграцию

Обычный деплой её и накатит (контейнер `api` стартует с
`alembic upgrade head`). Руками, если нужно отдельно:

```bash
docker compose run --rm api alembic upgrade head
```

## Шаг 3 — проверить результат

```bash
docker compose exec postgres psql -U coinkeeper -d coinkeeper -c "
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'uq_market_price_snapshots_item_source_grade_observed';"
```

Ожидаемо: `UNIQUE NULLS NOT DISTINCT (catalog_item_id, source, grade, observed_at)`.

```bash
docker compose exec postgres psql -U coinkeeper -d coinkeeper -c "
SELECT count(*) FILTER (WHERE status = 'active') AS active,
       count(*) FILTER (WHERE status <> 'active') AS other
FROM catalog_items;"
```

Ожидаемо: всё в `active`, `other` = 0.

## Откат

`alembic downgrade 0005` вернёт констрейнт без `NULLS NOT DISTINCT` и снимет
четыре колонки. Удалённые снимки откат **не вернёт** — для этого и есть CSV
из шага 1.

## Чего эта сессия не делала (намеренно)

- Не трогала фронт, парсеры и `ukraine_pipeline`.
- Не добавляла фильтрацию `status` в API и выборки каталога.
- Не удаляла строки uCoin из `price_source_links` и их снимки цен —
  приоритет источника изменён только на чтении, данные на месте.
- Не индексировала jsonb-колонки.
- Не проставляла `is_official` — это работа `load-series` из coin-parser.
