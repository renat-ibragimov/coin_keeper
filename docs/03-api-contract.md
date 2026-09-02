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
      seriesBreakdown:  [{name, country, count, owned}],
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
  &sort            — title | country | series | year | denomination | owned | purchase | price
  &order           — asc | desc
```

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
  "country": "Украина",
  "seriesName": "Флора и фауна",
  "denomination": "2 гривны",
  "year": 2018,
  "title": "Дельфін",
  "titleUk": "Дельфін",
  "titleRu": "Дельфин",
  "variety": null,
  "catalogNumber": "KM# 123",
  "collectionGroup": "commemorative",
  "metalKind": "base",
  "material": "нейзильбер",
  "marketPriceUah": "666.00",
  "priceSource": "UA-Coins",
  "priceObservedAt": "2026-08-06T12:20:27Z",
  "quantityOwned": 1,
  "purchaseTotalUah": "666.00",
  "obverseImageUrl": "https://cdn.../obverse.webp",
  "reverseImageUrl": "https://cdn.../reverse.webp",
  "thumbnailUrl": "https://cdn.../thumb.webp",
  "isOwn": false,
  "isArchived": false,
  "archiveReason": null,
  "sourceUrl": "https://ru.ucoin.net/coin/ua-2uah-2018-dolphin"
}
```

`title` — готовое к показу название по правилу
`title_uk → title_original → title_en → title_ru` (`02-data-model.md`). Отдельные поля
переводов отдаются как есть, для карточки редактирования.

`quantityOwned`, `purchaseTotalUah` и `marketPriceUah` считаются для текущего пользователя.
`isOwn` — `true` у личной позиции (`created_by` = текущий пользователь), `false` у общей;
фронт по нему решает, показывать ли кнопки правки.

`isArchived` и `archiveReason` есть и в элементе списка, и в карточке. По ним фронт рисует
плашку «Позиция архивирована: <причина>» (`08-ui-map.md`). У активной позиции
`archiveReason` — `null`.

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
GET    /collection?page&pageSize&countryId&seriesId&q&sort
POST   /collection    {catalogItemId, quantity, price, currency, purchaseDate, seller?, notes?, grade?}
PATCH  /collection/{id}
DELETE /collection/{id}
```

При создании: сервер подтягивает курс НБУ на `purchaseDate`, пишет `purchase_rate_uah`
и в той же транзакции создаёт расход категории `coin_purchase`. См. `04-business-rules.md`.

До этапа 5 курсы берутся только из таблицы `exchange_rates` (HTTP-клиента НБУ ещё нет):
покупка не в гривне с датой, на которую нет курса ≤ `purchaseDate`, отклоняется с `422`.

## Серии

```
GET  /series?countryId
POST /series  {countryId, name, description?, startYear?, endYear?}
GET  /series/{id}/summary
  → {total, owned, missing, completionPercent, purchaseTotalUah, currentValueUah, unpricedMissing}
```

## Расходы

```
GET    /expenses?category&dateFrom&dateTo&page&pageSize
POST   /expenses
PATCH  /expenses/{id}
DELETE /expenses/{id}
GET    /expenses/summary  → по категориям и итого
```

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

## Справочники

```
GET /countries
GET /denominations?countryId
GET /currencies
```
