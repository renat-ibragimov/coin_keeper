# 03. Контракт API

REST + JSON. Префикс `/api/v1`. Аутентификация — Bearer-токен в заголовке `Authorization`.

## Общие правила

- Ответы — camelCase (фронт на TypeScript), Pydantic-модели с `alias_generator = to_camel`.
- Списки — всегда постранично: `?page=1&pageSize=50`, ответ `{items, total, page, pageSize}`.
  3063 позиции каталога одним куском не отдаём никогда.
- Ошибки — RFC 7807 (`application/problem+json`): `{type, title, status, detail}`.
- Даты — ISO 8601. Дата без времени — `YYYY-MM-DD`, момент — с таймзоной.
- Деньги — строка, не число: `"1923.00"`. Иначе JS-фронт потеряет точность.
- Долгие операции (импорт каталога, массовое обновление цен) не выполняются в HTTP-запросе:
  возвращают `jobId`, статус читается отдельно. См. «Фоновые задачи».

## Маппинг старого IPC на REST

В десктопной версии интерфейс общался с бэкендом через 35 методов `window.coinKeeper.*`.
Полный список — `legacy/ui-strings.json`, ключ `api_methods`. Соответствие:

| Старый метод | REST |
|---|---|
| `getBootstrap` | `GET /bootstrap` |
| `listCatalog` | `GET /catalog` |
| `createCoin` | `POST /catalog` — создаёт **личную** позицию |
| `updateCoin` | `PATCH /catalog/{id}` — своя позиция; общая только для admin |
| `deleteCoin` | `DELETE /catalog/{id}` — своя позиция; общая только для admin |
| `refreshCoinPrice` | `POST /catalog/{id}/price-refresh` — только по **личным** позициям |
| `listPriceHistory` | `GET /catalog/{id}/prices` |
| `refreshCoinImage` | `POST /catalog/{id}/image-refresh` — только по **личным** позициям |
| `deleteCatalogImage` | `DELETE /catalog/{id}/images/{role}` |
| `addPurchase` | `POST /collection` |
| `updatePurchase` | `PATCH /collection/{id}` |
| `deletePurchase` | `DELETE /collection/{id}` |
| `listPurchases` | `GET /catalog/{id}/collection-items` |
| `listSeriesOptions` | `GET /series` |
| `createSeriesOption` | `POST /series` |
| `addSale`, `deleteSale`, `getSalesOverview` | `POST/DELETE /sales`, `GET /sales/overview` — отложено |
| `addOffer`, `deleteOffer`, `listOffers` | `/offers` — отложено |
| `selectExcelFiles` + `importExcel` | `POST /imports/excel` (multipart) |
| `previewUcoinCoin` | `POST /imports/ucoin/preview` |
| `importUcoinUrl` | `POST /imports/ucoin` |
| `listUcoinCatalogSources` | `GET /imports/ucoin/sources` |
| `saveUcoinCatalogSource` | `POST /imports/ucoin/sources` |
| `cancelUcoinPriceRefresh` | `POST /jobs/{jobId}/cancel` |
| `openUcoinSession`, `openUcoinUnblock`, `resetUcoinSession` | в MVP не переносим: ручное прохождение Cloudflare на сервере невозможно, см. `05-integrations.md` |
| `exportCatalog` | `POST /exports/excel` |
| `createBackup`, `listBackups` | не нужны — бэкапы на уровне сервера, см. `10-infra.md` |
| `openExternalUrl` | не нужен — в вебе это обычная ссылка |

`selectExcelFiles` и `openExternalUrl` были обёртками над диалогами Electron. В вебе исчезают.
`createBackup`/`listBackups` в вебе не пользовательская функция — переносим в инфраструктуру.

## Аутентификация

```
POST   /auth/register        {email, password, displayName?, website?}  → 202
POST   /auth/verify-email    {token}                          → {user, tokens}
POST   /auth/resend-verification {email}                      → 202
POST   /auth/login           {email, password}                → {user, tokens}
POST   /auth/refresh         —                                → {tokens}
POST   /auth/logout          —                                → 204
POST   /auth/forgot-password {email}                          → 202
POST   /auth/reset-password  {token, newPassword}             → 204
GET    /auth/me                                               → {user}
PATCH  /auth/me              {displayName?, locale?}          → {user}
POST   /auth/change-password {currentPassword, newPassword}   → 204
```

`tokens` — `{accessToken, expiresIn}`. **Refresh-токен в теле не передаётся ни в запросе,
ни в ответе**: он живёт только в httpOnly Secure SameSite=Lax cookie, которую сервер
выставляет сам и сам же читает в `/auth/refresh` и `/auth/logout`. Поэтому у этих двух
эндпоинтов тела запроса нет. Решение и обоснование — `07-auth.md`.

Регистрация возвращает `202`, а не токены: аккаунт неактивен до подтверждения адреса.
Токены выдаёт `/auth/verify-email`. `website` — honeypot-поле формы регистрации
(`07-auth.md`): заполнено — ответ тот же `202`, пользователь не создаётся.

`/auth/resend-verification` и `/auth/forgot-password` всегда отвечают `202`, существует
адрес или нет. Ограничения частоты по всем этим эндпоинтам — в `07-auth.md`.

`locale` в `PATCH /auth/me` — `'uk' | 'en'`, по умолчанию `'uk'`.

## Bootstrap

Один запрос при загрузке приложения — заменяет пачку мелких. Так было в legacy и это удобно.

```
GET /bootstrap
→ {
    user: {...},
    settings: {...},
    dashboard: {
      catalogItems, collectionItems, countries,
      completedItems, missingItems, completionPercent,
      coinSpendUah, relatedSpendUah, totalSpendUah,
      marketValueUah, missingBudgetUah, unpricedMissingItems,
      countryBreakdown: [{name, count, owned}],
      seriesBreakdown:  [{id, name, country, count, owned}],
      isEmpty
    },
    exchangeRates: [{code, rate, effectiveDate}],
    finance: {
      coinSpendUah, coinSpendUsdAtPurchase, coinSpendEurAtPurchase,
      purchasesWithoutHistoricalUsdRate, purchasesWithoutHistoricalEurRate
    }
  }
```

Структура взята из legacy `BootstrapPayload` (`legacy/reference-code/types.ts`) — она
проверена практикой и покрывает весь дашборд.

`seriesBreakdown[].id` — id серии (`coin_series.id`), аддитивное поле: фронт использует
его, чтобы сделать строку серии на Огляді ссылкой на `/collection/series/{id}` вместо
общего списка серій.

`isEmpty` в вебе означает «у пользователя ещё ничего нет»: ни экземпляров, ни личных
позиций. Общий каталог сам по себе дашборд не «наполняет» — новый пользователь видит
пустое состояние. В legacy флаг считался по каталогу, но там каталог и был коллекцией
владельца.

## Каталог

```
GET /catalog
  ?page, pageSize
  &q               — поиск по названию, стране, году, каталожному номеру
  &countryId
  &seriesId
  &year, yearFrom, yearTo
  &denominationId
  &group           — circulation | commemorative | collector | other
  &metalKind       — precious | base | unknown
  &owned           — true (есть в коллекции) | false (не хватает)
  &scope           — all (по умолчанию) | shared (только общий каталог) | own (только личные)
  &archived        — false (по умолчанию) | true (только архивные)
  &sort            — title | country | series | year | denomination | material
                     | owned | purchase | price
  &order           — asc | desc
```

`sort=material` — по тому, что показано в колонке «Матеріал»: название из справочника
`materials` на языке запроса, а где его нет — свободный текст `catalog_items.material`
(`08-ui-map.md`).

Выдача всегда ограничена видимыми позициями: общий каталог плюс личные позиции текущего
пользователя (`created_by IS NULL OR created_by = :userId`). Фильтр ставит репозиторий, а не
роут — `07-auth.md`.

**`archived`** по умолчанию `false` — витрина показывает только активные позиции
(`NOT is_archived` в запросе, `04-business-rules.md`, п. 10). При `archived=true`:

| Кто спрашивает | Что видит |
|---|---|
| admin | все архивные записи |
| обычный пользователь | только те архивные, где у него есть экземпляр |

Второе — не декорация: пользователь должен иметь возможность найти свою монету, даже если
позицию убрали из каталога. Архивных позиций, к которым он не имеет отношения, он не видит
вовсе.

**Сортировки `owned`, `purchase`, `price` — это агрегаты per-user**, а не колонки
`catalog_items`: количество экземпляров пользователя, сумма его покупок, последняя видимая ему
цена. Запрос проектируется под них сразу — `LATERAL`-подзапросы или предагрегированные CTE,
подключаемые к основному запросу, а не постобработка страницы в Python. Иначе сортировка
будет верна в пределах страницы и неверна по всей выборке. Видимость цен при этом та же:
`created_by IS NULL OR created_by = :userId`.

Элемент списка:

```json
{
  "id": 1,
  "country": "Україна",
  "seriesName": "Флора і фауна України",
  "denomination": {
    "id": 4,
    "value": "2.000",
    "unit": "hryvnia",
    "currencyCode": "UAH",
    "label": "2 гривні"
  },
  "year": 2018,
  "title": "Дельфін",
  "titleOriginal": "Дельфін",
  "originalLang": "uk",
  "titleUk": "Дельфін",
  "titleUkSource": "official",
  "titleEn": "Dolphin",
  "titleEnSource": "official",
  "variety": null,
  "catalogNumber": "KM# 123",
  "collectionGroup": "commemorative",
  "metalKind": "base",
  "composition": { "id": 13, "code": "nickel_silver", "name": "Нейзильбер" },
  "material": null,
  "marketPriceUah": "666.00",
  "priceSource": "UA-Coins",
  "priceObservedAt": "2026-08-06T12:20:27Z",
  "quantityOwned": 1,
  "purchaseTotalUah": "666.00",
  "obverseImage": {
    "preview": "https://cdn.../obverse_300.webp",
    "medium": "https://cdn.../obverse_600.webp",
    "large": "https://cdn.../obverse_1200.webp",
    "attribution": "Національний банк України"
  },
  "reverseImage": { "...": "то же для реверса" },
  "thumbnailUrl": "https://cdn.../obverse_300.webp",
  "isOwn": false,
  "isArchived": false,
  "archiveReason": null,
  "sourceUrl": "https://www.ua-coins.info/ua/list/512-delfin"
}
```

`title` — готовое к показу название по правилу `title_{локаль} → title_original`
(`02-data-model.md`). Локаль ответа: `?locale=uk|en`, иначе `Accept-Language`, иначе `uk`.
По той же локали приходят `country`, `seriesName`, `denomination.label` и
`composition.name`. Слоты отдаются как есть — для формы редактирования и для строки
«Оригінал: …» в карточке.

`denomination` — структура плюс готовая подпись; `composition` — ряд справочника
материалов, а `material` остаётся заполненным только там, где исходную строку разобрать
не удалось.

`obverseImage` / `reverseImage` — три хранимых размера одного снимка и подпись
первоисточника. Страница берёт `preview` в списке, `medium` в карточке, `large` в
лайтбоксе и предлагает следующий размер на 2x. У снимка, которого нет в большем размере,
поля повторяют наибольший имеющийся (`06-media-storage.md`).

`quantityOwned`, `purchaseTotalUah` и `marketPriceUah` считаются для текущего пользователя.
`isOwn` — `true` у личной позиции (`created_by` = текущий пользователь), `false` у общей;
фронт по нему решает, показывать ли кнопки правки.

`isArchived` и `archiveReason` есть и в элементе списка, и в карточке. По ним фронт рисует
плашку «Позиция архивирована: <причина>» (`08-ui-map.md`). У активной позиции
`archiveReason` — `null`.

`sourceUrl` — ссылка «джерело» на странице монеты. Берётся из `price_source_links` с
приоритетом UA-Coins → НБУ → прочее. Кликабельный адрес отдаёт только UA-Coins: у неё в
`external_id` лежит URL страницы монеты. У НБУ там id карточки, URL из него не строится, и
строка НБУ намеренно отдаёт `null` — она стоит выше прочих только чтобы перебить
унаследованные строки uCoin, половина которых помечена не тем источником. Лучше без
ссылки, чем ссылка на uCoin. Позиция без подходящей ссылки отдаёт `null`, и фронт прячет
блок «Джерело».

```
GET    /catalog/{id}                    → карточка с полными характеристиками
POST   /catalog                         → создать личную позицию (created_by = текущий)
PATCH  /catalog/{id}
POST   /catalog/{id}/archive    {reason} → архивировать общую позицию (admin)
POST   /catalog/{id}/unarchive           → вернуть в витрину (admin)
DELETE /catalog/{id}                     → см. таблицу ниже
GET    /catalog/{id}/prices             → история цен, видимая пользователю
GET    /catalog/{id}/collection-items   → экземпляры текущего пользователя
```

Права (`07-auth.md`):

| Запрос | Общая позиция | Своя личная | Чужая личная |
|---|---|---|---|
| `GET` | 200 | 200 | 404 |
| `POST /catalog` | всегда создаёт личную; общую — только admin | — | — |
| `PATCH` | 403 (admin — 200) | 200 | 404 |
| `POST .../archive`, `.../unarchive` | 403 (admin — 200) | 400 — к личным неприменимо | 404 |
| `DELETE` | 403 (admin — см. ниже) | 200 | 404 |

`POST /catalog` создаёт запись с `created_by` = текущий пользователь. Общую запись
(`created_by = NULL`) может создать только администратор — тем же эндпоинтом, передав
`shared: true` в теле. Флаг обязателен, потому что администратор — тоже коллекционер:
без явного флага и его записи создаются как личные. У обычного пользователя
`shared: true` даёт `403`.

### Правка названий (`titleOriginal` / `titleUk` / `titleEn`)

Отдельного эндпоинта нет — это обычный `PATCH /catalog/{id}` с теми же правами: своя
личная позиция правится автором, общая — только admin (`docs/05-integrations.md`,
раздел 11). Особое поведение только у `titleUk`/`titleEn`:

- значение непустое — пустая строка (`""`) отклоняется как `422`, слот либо не трогают
  (поле отсутствует в теле), либо заменяют настоящим текстом;
- переданное значение всегда помечает `titleUk_source`/`titleEn_source` как `manual` —
  ручная правка перекрывает и `official`, и `llm`, кем бы её ни делали.

`titleOriginal` правится тем же PATCH без пометки источника — у оригинала его нет
(`docs/02-data-model.md`).

```json
PATCH /catalog/{id}   { "titleUk": "Різдво Христове" }
→ 200, titleUk = "Різдво Христове", titleUkSource = "manual"

PATCH /catalog/{id}   { "titleUk": "" }
→ 422 — пустая строка
```

Фронт: правка трёх названий в admin-режиме карточки записи (по образцу существующих
admin-форм каталога) в `docs/BACKLOG.md` — контракт готов, экрана ещё нет.

### Архивация

```
POST /catalog/{id}/archive    {reason}   → 200, {isArchived: true, archivedAt, archiveReason}
     400 — reason пустой
     400 — позиция личная: архивация только для общих записей
     403 — не admin
     409 — уже архивирована

POST /catalog/{id}/unarchive             → 200, {isArchived: false}
     403 — не admin
     409 — не была архивирована
```

`reason` обязателен и непустой — иначе через полгода никто не вспомнит, почему позиции нет
в каталоге. Эндпоинты переключают `is_archived` и заполняют либо обнуляют `archived_at`
и `archive_reason` (`02-data-model.md`). Обе операции пишутся в `audit_log`. Экземпляры, покупки, расходы, фотографии и
история цен при архивации **не трогаются** — семантика в `04-business-rules.md`, п. 10.

### Удаление

```
DELETE /catalog/{id}
```

**Личная позиция:** удаляется автором физически, вместе с его экземплярами на ней и их
расходами `coin_purchase` — сервисным слоем, одной транзакцией. Позиция видна только
автору, поэтому каскад не может задеть чужие данные; правило удаления расхода вместе с
экземпляром — `04-business-rules.md`, п. 10.

**Общая позиция:** только admin и только «прибраться за опечаткой». `409` с указанием
причины, если не выполнено хотя бы одно условие:

- позиция **не архивирована** — сначала `POST /catalog/{id}/archive`;
- на неё есть ссылки из `collection_items` или `expenses` у любого пользователя.

`media_files` и `market_price_snapshots` удалению не мешают — уходят каскадом.
Штатный способ убрать позицию из каталога — архивация, а не это.

`GET /catalog/{id}/prices` отдаёт снимки с `created_by IS NULL OR created_by = :userId`;
у каждого снимка в ответе есть `isOwn`, чтобы в графике было видно, где своя цена, а где
общая.

## Коллекция

```
GET    /collection?page&pageSize&countryId&seriesId&year&yearFrom&yearTo&denominationId
                   &group&metalKind&grade&q&sort&order
GET    /collection/{id}
POST   /collection    {catalogItemId, quantity, price, currency, purchaseDate, seller?, notes?, grade?}
PATCH  /collection/{id}
DELETE /collection/{id}
```

`sort` — `date` (по умолчанию) | `title` | `country` | `series` | `quantity` | `total` |
`valuation` | `grade`, `order` — `asc` | `desc`. По колонке таблицы «Мої монети»
(`08-ui-map.md`); `valuation` — по произведению «цена монеты × количество», то есть по тому
же числу, что показано в колонке, `grade` — по массиву состояний позиции.

`GET /collection` — список позиций: одна строка на каталожную монету,
все покупки этой монеты пользователем схлопнуты в одну позицию. Детали отдельных покупок —
только через `GET/PATCH/DELETE /collection/{id}` (id покупки, `CollectionItem`) и
`GET /catalog/{id}/collection-items` («Мої екземпляри» на карточке монеты).

Фильтры `countryId`, `seriesId`, `year`, `yearFrom`, `yearTo`, `denominationId`, `group`,
`metalKind`, `q` — зеркально `GET /catalog`, работают по атрибутам каталожной монеты.
`grade` — свой для коллекции: позиция попадает в выдачу, если **хотя бы одна** её покупка
имеет такой стан; агрегаты при этом считаются по **всем** покупкам позиции, не только по
совпавшей — грейд-фильтр показывает позицию целиком, а не отфильтрованный кусок.

Форма позиции — контекст каталожной монеты (как сейчас) плюс агрегаты по покупкам:

- `totalQuantity` — сумма `quantity` всех покупок;
- `totalSpendUah` — сумма покупок в гривне (по курсу на дату каждой);
- `marketValueUah` — последняя видимая пользователю неподозрительная цена монеты ×
  `totalQuantity` (`null`, если цены нет);
- `lastAcquisitionDate` — максимальная дата покупки (`null`, если ни у одной нет даты);
- `grades` — отсортированный список различных станов покупок, без `null`;
- `thumbnailUrl` — как раньше, по тем же правилам видимости, что в каталоге.

Сортировки: `date` — по `lastAcquisitionDate`, `title` — по названию, `total` — по
`totalSpendUah`. Пагинация — по позициям, не по покупкам.

При создании покупки (`POST /collection`): сервер подтягивает курс НБУ на `purchaseDate`,
пишет `purchase_rate_uah` и в той же транзакции создаёт расход категории `coin_purchase`.
См. `04-business-rules.md`. `GET/PATCH/DELETE /collection/{id}` и ответ `POST /collection`
остаются в форме одной покупки (`CollectionItemOut`) — не позиции.

До этапа 5 курсы берутся только из таблицы `exchange_rates` (HTTP-клиента НБУ ещё нет):
покупка не в гривне с датой, на которую нет курса ≤ `purchaseDate`, отклоняется с `422`.

### Справочники, отфильтрованные по своей коллекции

```
GET /collection/countries
GET /collection/series?countryId
GET /collection/denominations?countryId
```

Те же схемы, что у общих `GET /countries` / `GET /series` / `GET /denominations`
(`CountryOut` / `SeriesOut` / `DenominationOut`), но список — только те страны/серії/
номінали, по которым у пользователя есть хотя бы одна покупка. Панель фільтрів
«Мої монети» использует именно их (не общий каталожный список): не имеет смысла
предлагать выбрать страну, монет которой у пользователя нет. Каталог продолжает
дёргать общие `/countries`, `/series`, `/denominations` — эти ручки его не касаются.
`CountryOut.minYear`/`maxYear` здесь — границы по монетам ПОЗИЦИЙ самого пользователя в этой
стране (не по общему каталогу): своя пара границ для «Рік від/до» на этой панели.
Порядок регистрации маршрутов важен: `/collection/countries` и соседние объявлены
раньше `/collection/{id}`, иначе FastAPI пытается распарсить `"countries"` как id.

## Серии

```
GET  /series?countryId
POST /series  {countryId, name, description?, startYear?, endYear?}
GET  /series/{id}/summary
  → {total, owned, missing, completionPercent, purchaseTotalUah, currentValueUah, unpricedMissing}
GET  /series/summary?countryId
  → [{series: {...}, summary: {...}}]   — все серии (страны) со сводкой одним запросом
```

Серии — общий справочник, личных серий нет: серия описывает выпуск, а не коллекцию.
`POST /series` доступен только администратору (`403` обычному пользователю), дубль имени
в пределах страны — `409`. В `summary` обе части дроби комплектности считаются по активным
видимым пользователю позициям; деньги (`purchaseTotalUah`, `currentValueUah`) — по его
экземплярам, включая экземпляры архивных позиций (`04-business-rules.md`, пп. 5 и 10).

## Расходы

```
GET    /expenses?category&dateFrom&dateTo&page&pageSize&sort&order
POST   /expenses
PATCH  /expenses/{id}
DELETE /expenses/{id}
GET    /expenses/summary
```

`sort` — `date` (по умолчанию) | `category` | `description` | `vendor` | `amount`,
`order` — `asc` | `desc` (по умолчанию). Сортировка по колонкам журнала (`08-ui-map.md`):
`description` — по тому, что показано в колонке «Опис» (название монеты для покупки, свой
текст для остального), `amount` — по сумме в гривне, `category` — в порядке объявления
таксономии, а не по алфавиту: смысл этой сортировки — сгруппировать журнал по видам.

В `ExpenseOut` для `category=coin_purchase` `coinTitle` — локализованная (`?locale`/
`Accept-Language`) название монеты, джойном через `catalogItemId`; для остальных категорий
— всегда `null`.

`GET /expenses/summary` (`ExpensesSummaryOut`):

- `categories` / `total_uah` / `coin_spend_uah` / `related_spend_uah` — как раньше;
- `byCategory` — тот же список, что `categories` (по каждой категории с ненулевой суммой:
  `category`, `count`, `totalUah`);
- `byMonth` — последние 12 календарных месяцев по дате сервера, от самого старого к
  текущему, каждый — `{month: "YYYY-MM", coinsUah, supportingUah}`; месяцы без трат идут
  нулями, а не пропускаются, чтобы ось графика была сплошной;
- `thisMonthUah` / `prevMonthUah` — сумма (монеты + сопутствующие) за текущий и
  предыдущий календарный месяц; равны последним двум точкам `byMonth`.

## Цены и курсы

Цены общего каталога обновляет системная суточная задача — пользовательского запуска для них
нет (`04-business-rules.md`, п. 7). Эндпоинты ниже работают **только по личным позициям**.

```
POST /catalog/{id}/price-refresh  → {source, status, previousPriceUah, priceUah, observedAt, message}
     status: updated | not-found | rejected | needs-api-key
     403 — позиция общая: её цены обновляет системная задача
     404 — позиция чужая

POST /prices/refresh-batch  {filter: {...те же параметры, что у GET /catalog}}
     → {jobId}
     обходит только личные позиции пользователя: к фильтру принудительно
     добавляется created_by = :userId, независимо от переданного scope

POST /prices/manual  {catalogItemId, price, currency, grade?, observedAt?}
     → снимок с created_by = текущий пользователь; работает и по общей позиции

GET  /rates                → текущие курсы
GET  /rates?date=2018-03-24 → курс на дату
POST /rates/refresh        → принудительное обновление (только admin)
```

Снимки, созданные этими эндпоинтами, пишутся с `created_by` = текущий пользователь и видны
только ему. Ручной ввод (`/prices/manual`) — единственный способ поставить свою цену общей
позиции: сама общая запись при этом не меняется.

`status: rejected` — новое по сравнению с legacy: цена получена, но не прошла валидацию.
Валидация одинакова для всех путей, включая ручной ввод. Обязательно логируем в
`raw_payload`. См. `05-integrations.md`.

## Импорт

Импорт **создаёт только личные позиции** (`created_by` = текущий пользователь). Если
совпадение нашлось в общем каталоге, новая запись не создаётся — экземпляры привязываются
к общей. Правила дедупликации — `04-business-rules.md`, п. 3.

```
POST /imports/excel            multipart, файл .xlsx
     → {jobId}
GET  /imports/excel/{jobId}    → {status, scanned, matchedShared, inserted, updated,
                                  skipped, countries, warnings[]}
     matchedShared — сколько строк совпало с общим каталогом и не создало личной позиции

POST /imports/ucoin/preview    {url}   → черновик позиции, без записи в БД
POST /imports/ucoin            {url}   → {jobId}   (одна монета или раздел каталога)

GET    /imports/ucoin/sources
POST   /imports/ucoin/sources  {title, url, country, collectionGroup}
DELETE /imports/ucoin/sources/{id}
```

## Экспорт

```
POST /exports/excel  {filter: {...}}  → {jobId}
GET  /exports/{jobId}                 → {status, downloadUrl}
```

Ссылка — presigned URL на S3 со сроком жизни, файл не отдаём потоком из приложения.

## Фото

```
POST   /catalog/{id}/images       multipart: file, role  → {mediaId, url, thumbnailUrl, source}
DELETE /catalog/{id}/images/{role}
POST   /collection/{id}/images    multipart: file, role
DELETE /collection/{id}/images/{role}
```

`/catalog/{id}/images` работает только по **личным** позициям пользователя (403 на общую,
404 на чужую); фото общего каталога загружает администратор или задача по каталогу НБУ.
Загруженное пользователем получает `source = 'user_upload'`.

Ограничения, обработка и правила видимости по происхождению — `06-media-storage.md`.

## Фоновые задачи

Любая операция, которая может идти дольше нескольких секунд, ставится в очередь.

```
GET  /jobs/{jobId}
  → {
      jobId, type, status,          // queued | running | done | failed | cancelled
      progress: {current, total},
      result: {...},                 // при done
      error: {...}                   // при failed
    }
POST /jobs/{jobId}/cancel  → 202
```

Типы задач: `excel-import`, `ucoin-import`, `price-refresh-batch`, `excel-export`,
`rates-sync`.

Системные задачи — `prices-daily-sync` (суточное обновление цен общего каталога по UA-Coins)
и `nbu-catalog-sync` (еженедельная пересборка украинской части каталога) — запускаются по
расписанию, а не из API. Их статус виден администратору тем же `GET /jobs/{jobId}`.

Отмена нужна обязательно: в legacy массовое обновление цен было длинным и имело кнопку
«Остановить» — соответствующие строки интерфейса сохранились
(`Останавливаем обновление цен…`, `Обновление цен остановлено.`).

Прогресс на фронт — обычным polling каждые 1–2 секунды. WebSocket на этом этапе избыточен.

### Отчёты о прогонах задач по расписанию

Всё выше — про очередь внутри приложения (этап 5). Задача по расписанию живёт иначе: она
запускается снаружи, своим контейнером, и отчитывается о себе сама (`13-admin.md`).

```
POST  /internal/job-runs         → 201 {id, job, status, startedAt, ...}
PATCH /internal/job-runs/{id}    → 200 {…, status, finishedAt, summary, stats, exitCode}
```

Заголовок `X-Job-Token` с общим секретом (`JOB_REPORT_TOKEN`); ни пользователя, ни сессии
здесь нет — вызывает контейнер внутри docker-сети. Сравнение постоянное по времени, пустой
секрет в конфигурации **выключает** эндпоинт (`503`), а не открывает его.

`POST` открывает прогон перед работой, `PATCH` закрывает исходом. Два послабления сделаны
намеренно, потому что вызывающий — cron, а не человек: `POST` принимает и сразу
завершённый прогон (если открыть не удалось, но работа прошла — отчёт не должен пропасть),
а повторный `PATCH` по тому же прогону разрешён (повтор после сетевой ошибки).

Чтение — `GET /admin/jobs` и `GET /admin/jobs/{id}` под ролью admin.

## Справочники

```
GET /countries?scope=active|all
GET /denominations?countryId
GET /currencies
```

`GET /countries` — `scope=active` (по умолчанию) отдаёт витрину: только активные страны,
`scope=all` — весь справочник, для формы личной позиции, куда можно вписать монету любого
когда-либо существовавшего эмитента.

`CountryOut.minYear`/`maxYear` — границы `issue_year` по каталожным монетам страны, видимым
текущему пользователю (тот же скоуп видимости, что у `GET /catalog`: общий каталог плюс личные
позиции, без архивных). `null`/`null` у страны без ни одной видимой монеты. Используются
фронтом как границы выпадашек «Рік від/до» (`08-ui-map.md`) — отдельной ручки для глобальных
границ нет, фронт берёт min/max по уже загруженному списку стран.
