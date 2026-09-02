# 02. Модель данных

Целевая схема PostgreSQL. Полный DDL старой SQLite-базы — `legacy/legacy-schema.sql`,
он приложен как справка, но **копировать его один-в-один нельзя** (причины ниже).

## Что меняем относительно legacy и почему

| Было в SQLite | Стало в PostgreSQL | Причина |
|---|---|---|
| `REAL` для денег | `NUMERIC(14,2)` | плавающая точка в деньгах даёт ошибки округления |
| `TEXT` для дат | `DATE` / `TIMESTAMPTZ` | сортировка, диапазоны, арифметика дат |
| `INTEGER` 0/1 для флагов | `BOOLEAN` | нативный тип |
| `CHECK (x IN (...))` | `ENUM` | валидация на уровне типа, видно в схеме |
| Нет пользователей | `users` + `owner_id` | сервис многопользовательский |
| `original_path` — путь или URL вперемешку | раздельные `storage_key` и `external_url` | см. `06-media-storage.md` |
| Единая база на человека | Общий каталог + личные позиции + личные коллекции | см. ниже |
| `title_original / title_ru / title_en` колонками | остаётся колонками, добавляется `title_uk` | переводов немного, отдельная таблица избыточна |

## Разделение общего и личного

Ключевое архитектурное решение. Данные делятся на **три слоя**: общий каталог, личные позиции
каталога, личная коллекция.

**Общее (одно на всех):** `countries`, `currencies`, `denominations`, `coin_series`,
`catalog_items` с `created_by IS NULL`, `catalog_variants`, `media_files` для каталожных фото,
`exchange_rates`.

Каталог монет — это объективный справочник: тираж, металл, диаметр не зависят от того, кто
смотрит. Держать копию на каждого пользователя бессмысленно и дорого.

**Личное (привязано к `owner_id` или `created_by`):** `catalog_items` с
`created_by = <пользователь>`, `collection_items`, `expenses`, `sales`, `purchase_offers`,
`collection_goals`, `media_files` для фото собственных монет, `settings`.

### Кто наполняет общий каталог

Общий каталог (`created_by IS NULL`) наполняет и правит **только администратор** — вручную и
через системные фоновые задачи (каталог НБУ, см. `05-integrations.md`). Обычный пользователь
общий каталог **не создаёт, не меняет и не удаляет** — только читает.

Поле `users.role` (`user` / `admin`) закладываем сразу.

### Личная позиция каталога

Если нужного выпуска в общем каталоге нет, пользователь заводит **личную позицию**:
`catalog_items.created_by = <его id>`. Она видна только автору, у неё полный CRUD и свои фото.
Во всех выборках, фильтрах, сериях, комплектности и статистике владельца личные позиции
участвуют наравне с общими.

Фильтр видимости каталога — **в репозиторийном слое**, рядом с фильтром `owner_id`
(см. `07-auth.md`):

```sql
WHERE catalog_items.created_by IS NULL OR catalog_items.created_by = :user_id
```

Импорт (Excel-выгрузка, uCoin по URL) создаёт **только личные позиции**; общий каталог
импортом не пополняется — правило дедупликации в `04-business-rules.md`, п. 3.

`collection_items` может ссылаться и на общую, и на личную позицию — разницы для экземпляра нет.

«Повышение» удачной личной позиции в общий каталог администратором — после MVP
(`01-scope-mvp.md`).

### Цены (`market_price_snapshots`)

Снимок цены принадлежит позиции каталога, но его **видимость определяется полем `created_by`**:

| `created_by` | Откуда | Кто видит |
|---|---|---|
| `NULL` | центральная суточная задача обновления цен | все |
| `<пользователь>` | ручной ввод, обновление своей личной позиции, Excel-импорт | только автор |

В расчёте стоимости коллекции у пользователя участвуют общие снимки **плюс его собственные**.
Правила обновления — `04-business-rules.md`, п. 7, и `05-integrations.md`.

## Перечисления

```sql
CREATE TYPE collection_group AS ENUM ('circulation', 'commemorative', 'collector', 'other');
CREATE TYPE metal_kind       AS ENUM ('precious', 'base', 'unknown');
CREATE TYPE media_role       AS ENUM ('obverse', 'reverse', 'edge', 'additional');
CREATE TYPE media_source     AS ENUM ('user_upload', 'ucoin', 'nbu', 'manual');
CREATE TYPE match_status     AS ENUM ('suggested', 'confirmed', 'rejected');
CREATE TYPE offer_status     AS ENUM ('considering', 'ordered', 'purchased', 'rejected', 'unavailable');
CREATE TYPE user_role        AS ENUM ('user', 'admin');
CREATE TYPE expense_category AS ENUM (
    'coin_purchase', 'delivery', 'album', 'holder', 'storage',
    'grading', 'literature', 'photo_equipment', 'other'
);
```

Категории расходов перенесены из legacy без изменений — они описаны в исходном ТЗ (раздел 7)
и покрывают реальные траты на хобби.

## Таблицы

### users

```
id              bigserial PK
email           citext UNIQUE NOT NULL
password_hash   text NOT NULL          -- argon2id
display_name    text
role            user_role NOT NULL DEFAULT 'user'
is_active       boolean NOT NULL DEFAULT true
email_verified  boolean NOT NULL DEFAULT false
locale          text NOT NULL DEFAULT 'uk'   -- 'uk' | 'en'
created_at      timestamptz NOT NULL DEFAULT now()
updated_at      timestamptz NOT NULL DEFAULT now()
```

Требуется расширение `citext` — email сравниваем без учёта регистра.

### countries

```
id                bigserial PK
code              text UNIQUE           -- ISO, опционально: у СССР его нет
name_original     text NOT NULL
name_ru, name_en  text
collect_variants  boolean NOT NULL DEFAULT false
is_active         boolean NOT NULL DEFAULT true
created_at, updated_at timestamptz
UNIQUE (name_original)
```

`collect_variants` — режим учёта разновидностей для страны из ТЗ (раздел 5). В MVP не
используется, но поле сохраняем.

### currencies

```
code            text PK          -- 'UAH', 'USD', 'EUR'
name            text NOT NULL
symbol          text
decimal_places  smallint NOT NULL DEFAULT 2
```

### denominations

```
id                bigserial PK
country_id        bigint NOT NULL FK countries
currency_code     text FK currencies
value_minor_units bigint          -- номинал в копейках/центах, для сортировки
label_original    text NOT NULL   -- '5 гривен', '1 cent'
label_ru, label_en text
sort_order        int NOT NULL DEFAULT 0
is_active         boolean NOT NULL DEFAULT true
UNIQUE (country_id, label_original)
```

### coin_series

```
id                bigserial PK
country_id        bigint NOT NULL FK countries ON DELETE CASCADE
name_original     text NOT NULL
name_ru, name_en  text
description       text
start_year, end_year int
created_at, updated_at timestamptz
UNIQUE (country_id, name_original)
```

### catalog_items

Центральная таблица. Описывает **выпуск**, а не конкретную монету.

```
id                 bigserial PK
item_type          text NOT NULL DEFAULT 'coin'
country_id         bigint NOT NULL FK countries
series_id          bigint FK coin_series ON DELETE SET NULL
denomination_id    bigint FK denominations ON DELETE SET NULL
collection_group   collection_group NOT NULL
subtype            text
title_original     text NOT NULL
title_uk, title_ru, title_en  text
issue_year         int NOT NULL
issue_date         date
mintage_announced  bigint
mintage_actual     bigint
material           text
metal_kind         metal_kind NOT NULL DEFAULT 'unknown'
weight_grams       numeric(10,3)
diameter_mm        numeric(8,2)
thickness_mm       numeric(8,2)
shape, edge, orientation  text
catalog_km, catalog_uc, catalog_numista  text
notes              text
source_key         text              -- ключ дедупликации импорта, см. 04-business-rules
created_by         bigint FK users ON DELETE CASCADE    -- NULL = общая (системная) запись
created_at, updated_at timestamptz
```

`created_by` определяет слой: `NULL` — общая запись, значение — личная позиция автора.
Здесь именно `ON DELETE CASCADE`, а не `SET NULL`: иначе удаление пользователя молча
превратило бы все его личные позиции в записи общего каталога. Общих записей каскад не
касается — у них `created_by IS NULL`.

### Отображение названия

Первое заполненное из:

```
title_uk → title_original → title_en → title_ru
```

`title_ru` не удаляем: в мигрированных данных лежат русские названия из uCoin, и для части
позиций это единственное название кроме оригинала.

Индексы:

```sql
CREATE INDEX ON catalog_items (country_id, issue_year);
CREATE INDEX ON catalog_items (series_id);
CREATE INDEX ON catalog_items (created_by);

-- три отдельных индекса, а не один составной: поиск идёт по любому одному
-- каталожному номеру, составной индекс работал бы только по первой колонке
CREATE INDEX ON catalog_items (catalog_km);
CREATE INDEX ON catalog_items (catalog_uc);
CREATE INDEX ON catalog_items (catalog_numista);

-- уникальность source_key: глобальная для общих записей,
-- в пределах владельца — для личных
CREATE UNIQUE INDEX catalog_items_source_key_shared_idx ON catalog_items (source_key)
  WHERE source_key IS NOT NULL AND created_by IS NULL;
CREATE UNIQUE INDEX catalog_items_source_key_own_idx ON catalog_items (created_by, source_key)
  WHERE source_key IS NOT NULL AND created_by IS NOT NULL;

-- полнотекстовый поиск по всем вариантам названия
CREATE INDEX catalog_items_search_idx ON catalog_items
  USING gin (to_tsvector('simple',
    coalesce(title_original,'') || ' ' || coalesce(title_uk,'') || ' ' ||
    coalesce(title_ru,'')       || ' ' || coalesce(title_en,'')));
```

Два частичных индекса выбраны вместо одного по `(source_key, coalesce(created_by, 0))`:
условие читается прямо в определении, и общие записи защищены отдельно от личных. Один и тот же
`source_key` может существовать один раз в общем каталоге и по одному разу у каждого
пользователя — это и есть правило дедупликации импорта из `04-business-rules.md`, п. 3.

Поиск делаем через `simple`-конфигурацию, а не `russian`: в каталоге украинские, русские и
английские названия вперемешку, стемминг по одному языку испортит остальные. Дополнительно
стоит включить `pg_trgm` для поиска по опечаткам.

### catalog_variants

```
id               bigserial PK
catalog_item_id  bigint NOT NULL FK catalog_items ON DELETE CASCADE
name             text NOT NULL
mint_name, mint_mark, variety_code, notes  text
UNIQUE (catalog_item_id, name, mint_mark)
```

Создаём, в MVP не используем.

### collection_items

Физические экземпляры пользователя.

```
id                bigserial PK
owner_id          bigint NOT NULL FK users ON DELETE CASCADE
catalog_item_id   bigint NOT NULL FK catalog_items ON DELETE RESTRICT
variant_id        bigint FK catalog_variants ON DELETE SET NULL
quantity          int NOT NULL DEFAULT 1 CHECK (quantity > 0)
grade             text
condition_notes   text
acquisition_date  date
acquisition_place text
seller            text
purchase_price    numeric(14,2)
purchase_currency text FK currencies
purchase_rate_uah numeric(14,6)      -- курс НБУ на дату покупки
storage_location  text
grading_company, grading_number, grading_grade  text
is_for_swap       boolean NOT NULL DEFAULT false
is_for_sale       boolean NOT NULL DEFAULT false
needs_replacement boolean NOT NULL DEFAULT false
notes             text
created_at, updated_at timestamptz
```

```sql
CREATE INDEX ON collection_items (owner_id, catalog_item_id);
CREATE INDEX ON collection_items (owner_id, acquisition_date DESC);
```

`ON DELETE RESTRICT` на каталог — нельзя удалить позицию, если у кого-то есть экземпляр.
Это правило было в legacy («Нельзя удалить монету с покупками») и его сохраняем.

Сумма в гривне не хранится, а считается: `purchase_price * purchase_rate_uah`. Исходная сумма
и валюта не теряются — требование ТЗ (раздел 6).

### market_price_snapshots

История цен. Не перезаписывается — каждая проверка создаёт новую строку.

```
id               bigserial PK
catalog_item_id  bigint NOT NULL FK catalog_items ON DELETE CASCADE
source           text NOT NULL        -- 'uCoin', 'UA-Coins', 'Manual'
grade            text
price            numeric(14,2) NOT NULL CHECK (price >= 0)
currency_code    text NOT NULL FK currencies
observed_at      timestamptz NOT NULL
source_url       text
raw_payload      jsonb                -- сырой ответ источника, для разбора багов
created_by       bigint FK users ON DELETE SET NULL   -- NULL = снимок центральной задачи
UNIQUE (catalog_item_id, source, grade, observed_at)
```

```sql
CREATE INDEX ON market_price_snapshots (catalog_item_id, observed_at DESC);
CREATE INDEX ON market_price_snapshots (created_by);
```

`created_by` задаёт видимость снимка (см. «Разделение общего и личного»). Выборка цен для
пользователя всегда сужается условием:

```sql
WHERE created_by IS NULL OR created_by = :user_id
```

`raw_payload` был `TEXT` с JSON — переводим в `jsonb`. Это важно: в legacy цены ломались,
и без сырых данных разобраться было нечем.

### price_source_links

Подтверждённое соответствие позиции каталога записи во внешнем источнике.

```
id               bigserial PK
catalog_item_id  bigint NOT NULL FK catalog_items ON DELETE CASCADE
source           text NOT NULL
external_id      text NOT NULL       -- URL или идентификатор на стороне источника
match_status     match_status NOT NULL DEFAULT 'confirmed'
matched_at       timestamptz
UNIQUE (catalog_item_id, source)
```

### media_files

```
id                bigserial PK
catalog_item_id   bigint FK catalog_items ON DELETE CASCADE
collection_item_id bigint FK collection_items ON DELETE CASCADE
owner_id          bigint FK users ON DELETE CASCADE   -- NULL для каталожных
role              media_role NOT NULL
source            media_source NOT NULL DEFAULT 'user_upload'
license           text            -- условия использования, если известны
attribution       text            -- обязательная подпись к изображению, если требуется
storage_key       text            -- ключ в S3, если файл наш
external_url      text            -- если изображение с чужого сервера
thumbnail_key     text
mime_type         text
width, height     int
size_bytes        bigint
sha256            text
created_at        timestamptz
CHECK (catalog_item_id IS NOT NULL OR collection_item_id IS NOT NULL)
CHECK (storage_key IS NOT NULL OR external_url IS NOT NULL)
```

Разделение `storage_key` / `external_url` — исправление legacy, где в одном поле лежали
и локальные пути, и ссылки на `i.ucoin.net`. Подробности в `06-media-storage.md`.

`source` — происхождение изображения, от него зависит видимость:

| `source` | Что это | Кто видит |
|---|---|---|
| `user_upload` | фото пользователя | владелец (`owner_id`) |
| `nbu` | официальное каталожное фото НБУ | все |
| `ucoin` | взято с uCoin — своё или скачанное | только импортировавший пользователь |
| `manual` | добавлено администратором вручную | все |

Права на изображения uCoin нам не принадлежат, поэтому в публичных карточках вместо них
показывается плейсхолдер. Правила целиком — `06-media-storage.md`.

### exchange_rates

```
id             bigserial PK
currency_code  text NOT NULL FK currencies
rate_uah       numeric(14,6) NOT NULL CHECK (rate_uah > 0)
effective_date date NOT NULL
fetched_at     timestamptz NOT NULL
source         text NOT NULL DEFAULT 'NBU'
UNIQUE (currency_code, effective_date, source)
```

Общая таблица: курс НБУ не зависит от пользователя.

### expenses

```
id                 bigserial PK
owner_id           bigint NOT NULL FK users ON DELETE CASCADE
category           expense_category NOT NULL
amount             numeric(14,2) NOT NULL CHECK (amount >= 0)
currency_code      text NOT NULL FK currencies
rate_uah           numeric(14,6)
expense_date       date NOT NULL
catalog_item_id    bigint FK catalog_items ON DELETE SET NULL
collection_item_id bigint FK collection_items ON DELETE SET NULL
series_id          bigint FK coin_series ON DELETE SET NULL
vendor             text
description        text
created_at         timestamptz
```

В legacy покупка монеты автоматически создавала расход категории `coin_purchase` — все 620
записей именно такие. Поведение сохраняем: расход создаётся в той же транзакции, что и
`collection_items`.

**Удаление — в сервисном слое, не каскадом.** При удалении экземпляра сервис той же
транзакцией удаляет связанный расход категории `coin_purchase`. FK остаётся
`ON DELETE SET NULL` как страховка от висячей ссылки, если запись всё-таки удалят в обход
сервиса, — но полагаться на него нельзя: `SET NULL` оставит расход в базе и завысит сумму
трат. См. `04-business-rules.md`, п. 10.

### sales, purchase_offers, collection_goals

Переносим из legacy с добавлением `owner_id` и заменой типов. В MVP не используются —
DDL см. в `legacy/legacy-schema.sql`, адаптировать по тем же правилам.

### ucoin_catalog_sources

Сохранённые разделы каталога uCoin для повторного импорта.

```
id                bigserial PK
owner_id          bigint FK users ON DELETE CASCADE
title             text NOT NULL
url               text NOT NULL
country           text
collection_group  collection_group
last_import_at    timestamptz
last_scanned, last_inserted, last_updated, last_skipped  int NOT NULL DEFAULT 0
created_at, updated_at timestamptz
UNIQUE (owner_id, url)
```

В legacy `url` был глобально уникален — при многопользовательской работе это неверно,
уникальность должна быть в пределах пользователя.

### user_settings

Вместо legacy-таблицы `settings` с ключом-строкой:

```
user_id     bigint PK FK users ON DELETE CASCADE
locale      text NOT NULL DEFAULT 'uk'   -- 'uk' | 'en'
display_currency text NOT NULL DEFAULT 'UAH'
default_grade_commemorative text NOT NULL DEFAULT 'UNC'
default_grade_circulation   text NOT NULL DEFAULT 'VF'
updated_at  timestamptz
```

Значения по умолчанию — из ТЗ (раздел 6): памятные и коллекционные считаются в UNC,
обиходные в VF.

### auth_tokens

Одноразовые токены подтверждения email и восстановления пароля. Устроены по образцу
`refresh_tokens` (`07-auth.md`): в базе лежит хеш, а не сам токен.

```
id          bigserial PK
user_id     bigint NOT NULL FK users ON DELETE CASCADE
kind        auth_token_kind NOT NULL      -- 'email_verify' | 'password_reset'
token_hash  text NOT NULL UNIQUE          -- sha256 от токена
expires_at  timestamptz NOT NULL
used_at     timestamptz
created_at  timestamptz NOT NULL DEFAULT now()
```

```sql
CREATE TYPE auth_token_kind AS ENUM ('email_verify', 'password_reset');
CREATE INDEX ON auth_tokens (user_id, kind);
```

Токен считается годным, если `used_at IS NULL` и `expires_at > now()`. Срок жизни: 24 часа
для подтверждения email, 1 час для сброса пароля. Выдача нового токена того же типа гасит
предыдущие невыполненные. Регистрация и восстановление пароля — обязательная часть MVP,
см. `07-auth.md`.

### audit_log

```
id           bigserial PK
user_id      bigint FK users ON DELETE SET NULL
action       text NOT NULL
entity_type  text NOT NULL
entity_id    text
details      jsonb
created_at   timestamptz NOT NULL DEFAULT now()
```

Создаём сразу, заполнять начинаем на операциях удаления и массового импорта.

## Схема связей

```
users ──< collection_items >── catalog_items ──< market_price_snapshots
  │              │                   │       └─< price_source_links
  │              │                   │       └─< catalog_variants
  │              │                   │       └─< media_files (каталожные)
  │              └─< media_files (свои фото)
  │              └─< expenses
  ├──< catalog_items (личные позиции, created_by)
  ├──< market_price_snapshots (свои снимки цен, created_by)
  └─< user_settings
  └─< ucoin_catalog_sources
  └─< refresh_tokens, auth_tokens

countries ──< coin_series ──< catalog_items
    └─────< denominations ──< catalog_items

currencies ──< exchange_rates
```

## Что проверить при реализации

- Расширения: `citext`, `pg_trgm`
- `updated_at` обновлять триггером, а не в приложении
- Все `numeric` для денег, ни одного `float`
- Каскады: удаление пользователя чистит его коллекцию и личные позиции каталога,
  но не трогает общий каталог
- Фильтр видимости каталога (`created_by IS NULL OR created_by = :user_id`) и снимков цен —
  в репозиторийном слое, рядом с `owner_id`, а не в роутах
