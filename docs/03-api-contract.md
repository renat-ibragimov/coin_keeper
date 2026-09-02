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
| `createCoin` | `POST /catalog` |
| `updateCoin` | `PATCH /catalog/{id}` |
| `deleteCoin` | `DELETE /catalog/{id}` |
| `refreshCoinPrice` | `POST /catalog/{id}/price-refresh` |
| `listPriceHistory` | `GET /catalog/{id}/prices` |
| `refreshCoinImage` | `POST /catalog/{id}/image-refresh` |
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
| `openUcoinSession`, `openUcoinUnblock`, `resetUcoinSession` | `/imports/ucoin/session` — см. `05-integrations.md` |
| `exportCatalog` | `POST /exports/excel` |
| `createBackup`, `listBackups` | не нужны — бэкапы на уровне сервера, см. `10-infra.md` |
| `openExternalUrl` | не нужен — в вебе это обычная ссылка |

`selectExcelFiles` и `openExternalUrl` были обёртками над диалогами Electron. В вебе исчезают.
`createBackup`/`listBackups` в вебе не пользовательская функция — переносим в инфраструктуру.

## Аутентификация

```
POST   /auth/register        {email, password, displayName?}  → {user, tokens}
POST   /auth/login           {email, password}                → {user, tokens}
POST   /auth/refresh         {refreshToken}                   → {tokens}
POST   /auth/logout          {refreshToken}                   → 204
GET    /auth/me                                               → {user}
PATCH  /auth/me              {displayName?, locale?}          → {user}
POST   /auth/change-password {currentPassword, newPassword}   → 204
```

`tokens` — `{accessToken, refreshToken, expiresIn}`. Подробности в `07-auth.md`.

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
  &sort            — title | country | series | year | denomination | owned | purchase | price
  &order           — asc | desc
```

Элемент списка:

```json
{
  "id": 1,
  "country": "Украина",
  "seriesName": "Флора и фауна",
  "denomination": "2 гривны",
  "year": 2018,
  "title": "Дельфин",
  "titleRu": "Дельфин",
  "variety": null,
  "catalogNumber": "KM# 123",
  "collectionGroup": "commemorative",
  "metalKind": "base",
  "material": "нейзильбер",
  "marketPriceUah": "666.00",
  "priceSource": "uCoin",
  "priceObservedAt": "2026-08-06T12:20:27Z",
  "quantityOwned": 1,
  "purchaseTotalUah": "666.00",
  "obverseImageUrl": "https://cdn.../obverse.webp",
  "reverseImageUrl": "https://cdn.../reverse.webp",
  "thumbnailUrl": "https://cdn.../thumb.webp",
  "sourceUrl": "https://ru.ucoin.net/coin/ua-2uah-2018-dolphin"
}
```

`quantityOwned` и `purchaseTotalUah` считаются для текущего пользователя.

```
GET    /catalog/{id}                    → карточка с полными характеристиками
POST   /catalog                         → создать позицию вручную
PATCH  /catalog/{id}
DELETE /catalog/{id}                    → 409, если есть экземпляры у любого пользователя
GET    /catalog/{id}/prices             → история цен
GET    /catalog/{id}/collection-items   → экземпляры текущего пользователя
```

## Коллекция

```
GET    /collection?page&pageSize&countryId&seriesId&q&sort
POST   /collection    {catalogItemId, quantity, price, currency, purchaseDate, seller?, notes?, grade?}
PATCH  /collection/{id}
DELETE /collection/{id}
```

При создании: сервер подтягивает курс НБУ на `purchaseDate`, пишет `purchase_rate_uah`
и в той же транзакции создаёт расход категории `coin_purchase`. См. `04-business-rules.md`.

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

```
POST /catalog/{id}/price-refresh  → {source, status, previousPriceUah, priceUah, observedAt, message}
     status: updated | not-found | rejected | needs-api-key

POST /prices/refresh-batch  {filter: {...те же параметры, что у GET /catalog}}
     → {jobId}

GET  /rates                → текущие курсы
GET  /rates?date=2018-03-24 → курс на дату
POST /rates/refresh        → принудительное обновление (только admin)
```

`status: rejected` — новое по сравнению с legacy: цена получена, но не прошла валидацию.
Обязательно логируем в `raw_payload`. См. `05-integrations.md`.

## Импорт

```
POST /imports/excel            multipart, файл .xlsx
     → {jobId}
GET  /imports/excel/{jobId}    → {status, scanned, inserted, updated, skipped, countries, warnings[]}

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
POST   /catalog/{id}/images       multipart: file, role  → {mediaId, url, thumbnailUrl}
DELETE /catalog/{id}/images/{role}
POST   /collection/{id}/images    multipart: file, role
DELETE /collection/{id}/images/{role}
```

Ограничения и обработка — `06-media-storage.md`.

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
