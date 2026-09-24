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
Соответствие:

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
| `openUcoinSession`, `openUcoinUnblock`, `resetUcoinSession` | в MVP не переносим: ручное прохождение Cloudflare на сервере невозможно, см. `integrations.md` |
| `exportCatalog` | `POST /exports/excel` |
| `createBackup`, `listBackups` | не нужны — бэкапы на уровне сервера, см. `infra.md` |
| `openExternalUrl` | не нужен — в вебе это обычная ссылка |

`selectExcelFiles` и `openExternalUrl` были обёртками над диалогами Electron. В вебе исчезают.
`createBackup`/`listBackups` в вебе не пользовательская функция — переносим в инфраструктуру.

## Аутентификация

```
POST   /auth/register        {email, displayName?, website?}   → 202
POST   /auth/verify-email    {token, newPassword?}             → {user, tokens}
POST   /auth/resend-verification {email}                      → 202
POST   /auth/login           {email, password}                → {user, tokens}
POST   /auth/refresh         —                                → {tokens}
POST   /auth/logout          —                                → 204
POST   /auth/forgot-password {email}                          → 202
POST   /auth/reset-password  {token, newPassword}             → 204
GET    /auth/me                                               → {user}
PATCH  /auth/me              {displayName?, locale?}          → {user}
PUT    /auth/me/avatar       <сырые байты изображения>        → {user}
DELETE /auth/me/avatar       —                                → {user}
POST   /auth/change-password {currentPassword, newPassword}   → 204
POST   /auth/set-password    {newPassword}                    → 204 (только без пароля)
GET    /auth/google/status   —                                → {enabled}
GET    /auth/google/start    —                                → 302 в Google
POST   /auth/google/link/start —                              → {url} (Bearer)
GET    /auth/google/callback {state, code}                    → 303 в приложение
```

`tokens` — `{accessToken, expiresIn}`. **Refresh-токен в теле не передаётся ни в запросе,
ни в ответе**: он живёт только в httpOnly Secure SameSite=Lax cookie, которую сервер
выставляет сам и сам же читает в `/auth/refresh` и `/auth/logout`. Поэтому у этих двух
эндпоинтов тела запроса нет. Решение и обоснование — `auth.md`.

Регистрация возвращает `202`, а не токены: аккаунт неактивен до подтверждения адреса.
Пароль задаётся при `/auth/verify-email` владельцем почты; только для аккаунта,
созданного через Google, `newPassword` можно опустить. Старое поле `password` в
`/auth/register` принимается для совместимости, но игнорируется.
Токены выдаёт `/auth/verify-email`. `website` — honeypot-поле формы регистрации
(`auth.md`): заполнено — ответ тот же `202`, пользователь не создаётся.

`/auth/resend-verification` и `/auth/forgot-password` всегда отвечают `202`, существует
адрес или нет. Ограничения частоты по всем этим эндпоинтам — в `auth.md`.

`locale` в `PATCH /auth/me` — `'uk' | 'en'`, по умолчанию `'uk'`.

`user` также содержит `hasPassword` и `googleLinked`. Google callback выставляет
обычную refresh-cookie и ведёт на `/google-complete`, где фронт вызывает `/auth/refresh`.
`link/start` доступен только вошедшему пользователю; при совпадении email привязка
сохраняет его `user.id` и коллекцию. При конфликте callback ведёт на страницу входа
с предложением сначала войти существующим способом.

`user` везде содержит `avatarUrl` — подписанная ссылка на час или `null`, не ключ в
бакете (`media.md`). Она собирается в одном месте на бэкенде, поэтому приходит
одинаково и здесь, и в `/bootstrap`.

`PUT /auth/me/avatar` принимает **тело-изображение целиком, без multipart**: один файл без
сопутствующих полей в конверте не нуждается. JPEG, PNG или WebP до 12 МБ и не шире 4000 px;
всё остальное — `422 invalid-image`. Операция идемпотентна: те же байты дают тот же ключ.
`DELETE` отвечает `200` с профилем, а не `204`, — вызывающему нужен уже пустой `avatarUrl`;
удаление отсутствующей аватарки ошибкой не считается.

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

Структура взята из legacy `BootstrapPayload` — она проверена практикой и покрывает
весь дашборд.

`seriesBreakdown[].id` — id серии (`coin_series.id`), аддитивное поле: фронт использует
его, чтобы сделать строку серии на Огляді ссылкой на `/collection/series/{id}` вместо
общего списка серій.

`isEmpty` в вебе означает «у пользователя ещё ничего нет»: ни экземпляров, ни личных
позиций. Общий каталог сам по себе дашборд не «наполняет» — новый пользователь видит
пустое состояние. В legacy флаг считался по каталогу, но там каталог и был коллекцией
владельца.

`PATCH /bootstrap/settings` — частичное обновление: тело присылает только те поля
`user_settings`, которые меняются, остальные не трогает (`SettingsUpdate.model_dump(exclude_unset=True)`
идёт прямиком в `UserRepository.update_settings(**fields)` — общий метод на все поля
настроек, а не отдельный сеттер под каждое). Все поля, кроме `locale` (тот меняется
`PATCH /auth/me`), проходят через этот эндпоинт:

- `showPackagingVariants` (по умолчанию `true`) — включает показ монет в сувенирной
  упаковке отдельной карточкой в `GET /catalog`, подробности — `business-rules.md`,
  BR-15;
- `defaultGrade` (по умолчанию `UNC`) — состояние, которым предзаполняется форма покупки
  для любой монеты; свободная строка, как и `grade` самого экземпляра, без валидации по
  списку — фронт предлагает фиксированный `GRADES`, но сервер его не навязывает;
- `theme` (`'light' | 'dark' | 'system'`, по умолчанию `'system'`), `catalogViewMode` и
  `collectionViewMode` (`'cards' | 'table'`, по умолчанию `'cards'`) — кросс-девайсные
  версии того, что раньше жило только в localStorage; сервер валидирует по `Literal`.
  Фронт держит localStorage-копию как быстрый кэш до ответа `GET /bootstrap`, не как
  источник истины;
- `secondaryCurrency` (`'USD' | 'EUR'`, по умолчанию `'USD'`) — какая валюта показывается
  вторым числом («≈ …») рядом с гривневой суммой в карточке монеты, «Мої монети» и «Гроші».
  Гривна остаётся основной осью расчётов — вторичная валюта только выбирает, какое из уже
  посчитанных полей (`purchaseTotalUsd`/`purchaseTotalEur` и аналоги) показать.
- `defaultStorageLocation` (по умолчанию `null`) — имя, не id: сервер резолвит его через
  тот же get-or-create, что и `storageLocation` покупки (`business-rules.md`, BR-16).
  Пустая строка/`null` очищает дефолт;
- `includeSupportingExpenses` (по умолчанию `true`, 2026-09-22) — считать ли сопутствующие
  расходы частью `purchaseTotalUah`/«Зміни вартості» на карточке монеты (`supportingExpensesUah`
  тогда сложен с `purchaseTotalUah` на фронте) или показывать их отдельной информационной
  строкой без слияния. Само число `supportingExpensesUah` в ответе `GET /catalog/{id}` не
  зависит от этой настройки — она только про то, как фронт две уже готовые суммы показывает
  и что берёт за базу для расчёта изменения стоимости (`business-rules.md`, BR-4).

## Каталог

```
GET /catalog
  ?page, pageSize
  &q               — поиск по названию, стране, году, каталожному номеру
  &countryId
  &seriesId
  &year, yearFrom, yearTo
  &dateFrom, dateTo — диапазон issue_date (ISO-дата); монета без issue_date всё равно
                      попадает в выдачу, если её issue_year — в границах лет dateFrom..dateTo
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

```
GET /catalog/lookup
  ?q          — обязателен, 1…200 символов
  &countryId
  &limit      — 1…20, по умолчанию 8
  → [CatalogListItem]   — без пагинации, это не листинг
```

Поиск для живых подсказок в форме «Додати» (`ui.md`). Отдаёт те же элементы, что
`GET /catalog`, и с той же видимостью слоёв (общие + личные текущего пользователя,
неархивные), но **вообще без витринного правила** — ни `is_active`, ни `catalog_confirmed`
(`business-rules.md`, BR-13 and BR-13а). Причина: выпадашка стран в форме предлагает всех
эмитентов, какие были, а каталог показывает только подтверждённые страны — если не видеть
дальше каталога, пользователь заведёт личный дубль монеты, которая в общем каталоге уже
есть (решение владельца 2026-09-14). Сам `GET /catalog` при этом не меняется. Маршрут
зарегистрирован до `/catalog/{id}`.

`sort=material` — по тому, что показано в колонке «Матеріал»: название из справочника
`materials` на языке запроса, а где его нет — свободный текст `catalog_items.material`
(`ui.md`).

```
GET /catalog/summary
  — те же query-параметры, что у GET /catalog (без page/pageSize/sort/order)
  → CatalogSummaryOut = {total, owned, missing, purchaseTotalUah, missingBudgetUah,
                          unpricedMissing}
```

KPI-плитки экрана «Каталог» (є / не вистачає / витрачено на монети / треба докупити),
посчитанные с теми же фильтрами, что применены к списку — чтобы числа на плитках всегда
совпадали с тем, что показано под ними (`ui.md`, §«Каталог»). Параметр `owned`
принимается для симметрии сигнатуры с `GET /catalog`, но намеренно игнорируется: иначе выбор
«не вистачає» обнулил бы саму плитку, которая должна показать обе стороны этого соотношения.
Маршрут зарегистрирован до `/catalog/{id}`.

Выдача всегда ограничена видимыми позициями: общий каталог плюс личные позиции текущего
пользователя (`created_by IS NULL OR created_by = :userId`). Фильтр ставит репозиторий, а не
роут — `auth.md`.

**`archived`** по умолчанию `false` — витрина показывает только активные позиции
(`NOT is_archived` в запросе, `business-rules.md`, BR-10). При `archived=true`:

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
  "supportingExpensesUah": "60.00",
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
(`data-model.md`). Локаль ответа: `?locale=uk|en`, иначе `Accept-Language`, иначе `uk`.
По той же локали приходят `country`, `seriesName`, `denomination.label` и
`composition.name`. Слоты отдаются как есть — для формы редактирования и для строки
«Оригінал: …» в карточке.

`denomination` — структура плюс готовая подпись; `composition` — ряд справочника
материалов, а `material` остаётся заполненным только там, где исходную строку разобрать
не удалось.

`obverseImage` / `reverseImage` — три хранимых размера одного снимка и подпись
первоисточника. Страница берёт `preview` в списке, `medium` в карточке, `large` в
лайтбоксе и предлагает следующий размер на 2x. У снимка, которого нет в большем размере,
поля повторяют наибольший имеющийся (`media.md`).

`quantityOwned`, `purchaseTotalUah` и `marketPriceUah` считаются для текущего пользователя.
`isOwn` — `true` у личной позиции (`created_by` = текущий пользователь), `false` у общей;
фронт по нему решает, показывать ли кнопки правки.

`supportingExpensesUah` (2026-09-22) — сумма всех расходов пользователя по этой каталожной
позиции с категорией, отличной от `coin_purchase` (доставка, холдер, грейдинг и т. п.),
сконвертированная в гривню по курсу на дату каждого расхода; `null`, если таких расходов
нет. Считается по `catalog_item_id`, не по `collection_item_id` — это сумма **за всю
позицию**, а не за конкретную покупку, поэтому не зависит от того, проставлен ли
`collection_item_id` у старых расходов (см. бэкфилл, `business-rules.md`, BR-4). В
основную сумму `purchaseTotalUah` не входит и в «Зміна вартості» не участвует — карточка
показывает её отдельной приглушённой строкой, без слияния с ценой покупки.

`purchaseTotalUsd` / `purchaseTotalEur` — тот же куплено-итог, конвертированный курсом НБУ
на дату КАЖДОЙ покупки (не сегодняшним), `null` там, где курса на ту дату ещё нет. Оба
считаются всегда, независимо от `user_settings.secondary_currency` — какой из двух
показать, решает фронт. То же самое для `CatalogCollectionItemOut.totalUsd/totalEur` (по
экземплярам) и `ExpenseOut.amountUsd/amountEur` (по строкам «Гроші»).

`isArchived` и `archiveReason` есть и в элементе списка, и в карточке. По ним фронт рисует
плашку «Позиция архивирована: <причина>» (`ui.md`). У активной позиции
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

Права (`auth.md`):

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
личная позиция правится автором, общая — только admin (`docs/integrations.md`,
раздел 11). Особое поведение только у `titleUk`/`titleEn`:

- значение непустое — пустая строка (`""`) отклоняется как `422`, слот либо не трогают
  (поле отсутствует в теле), либо заменяют настоящим текстом;
- переданное значение всегда помечает `titleUk_source`/`titleEn_source` как `manual` —
  ручная правка перекрывает и `official`, и `llm`, кем бы её ни делали.

`titleOriginal` правится тем же PATCH без пометки источника — у оригинала его нет
(`docs/data-model.md`).

```json
PATCH /catalog/{id}   { "titleUk": "Різдво Христове" }
→ 200, titleUk = "Різдво Христове", titleUkSource = "manual"

PATCH /catalog/{id}   { "titleUk": "" }
→ 422 — пустая строка
```

Фронт: правка трёх названий в admin-режиме карточки записи (по образцу существующих
admin-форм каталога) в `docs/backlog.md` — контракт готов, экрана ещё нет.

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
и `archive_reason` (`data-model.md`). Обе операции пишутся в `audit_log`. Экземпляры, покупки, расходы, фотографии и
история цен при архивации **не трогаются** — семантика в `business-rules.md`, BR-10.

### Удаление

```
DELETE /catalog/{id}
```

**Личная позиция:** удаляется автором физически, вместе с его экземплярами на ней и их
расходами `coin_purchase` — сервисным слоем, одной транзакцией. Позиция видна только
автору, поэтому каскад не может задеть чужие данные; правило удаления расхода вместе с
экземпляром — `business-rules.md`, BR-10.

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
GET    /collection?page&pageSize&countryId&seriesId&year&yearFrom&yearTo&dateFrom&dateTo
                   &denominationId&group&metalKind&grade&q&sort&order
GET    /collection/{id}
POST   /collection    {catalogItemId, quantity, price, currency, purchaseDate, seller?, notes?, grade?}
PATCH  /collection/{id}
DELETE /collection/{id}
```

`sort` — `date` (по умолчанию) | `title` | `country` | `series` | `quantity` | `total` |
`valuation` | `grade`, `order` — `asc` | `desc`. По колонке таблицы «Мої монети»
(`ui.md`); `valuation` — по произведению «цена монеты × количество», то есть по тому
же числу, что показано в колонке, `grade` — по массиву состояний позиции.

`GET /collection` — список позиций: одна строка на каталожную монету,
все покупки этой монеты пользователем схлопнуты в одну позицию. Детали отдельных покупок —
только через `GET/PATCH/DELETE /collection/{id}` (id покупки, `CollectionItem`) и
`GET /catalog/{id}/collection-items` («Мої екземпляри» на карточке монеты).

Фильтры `countryId`, `seriesId`, `year`, `yearFrom`, `yearTo`, `dateFrom`, `dateTo`,
`denominationId`, `group`, `metalKind`, `q` — зеркально `GET /catalog`, работают по
атрибутам каталожной монеты. `dateFrom`/`dateTo` фильтруют по `issue_date`, а не по
`acquisition_date` покупки (у последней своего фильтра пока нет) — с тем же фолбэком
на `issue_year`, что у `GET /catalog`, когда точная дата выпуска не указана.
`grade` — свой для коллекции: позиция попадает в выдачу, если **хотя бы одна** её покупка
имеет такой стан; агрегаты при этом считаются по **всем** покупкам позиции, не только по
совпавшей — грейд-фильтр показывает позицию целиком, а не отфильтрованный кусок.

```
GET /collection/summary
  — те же фильтры, что у GET /collection (без page/pageSize/sort/order)
  → CollectionSummaryOut = {collectionItems, completedItems, coinSpendUah, relatedSpendUah,
                             totalSpendUah, marketValueUah}
```

KPI-плитки экрана «Мої монети», посчитанные с активными фильтрами страницы — та же форма,
что у дашбордного снимка без фильтров (`11-roadmap.md`), но суженная под то, что сейчас видит
пользователь; без фильтров числа совпадают с бутстрапом (`ui.md`, §«Мої монети»).

Форма позиции — контекст каталожной монеты (как сейчас) плюс агрегаты по покупкам:

- `totalQuantity` — сумма `quantity` всех покупок;
- `totalSpendUah` — сумма покупок в гривне (по курсу на дату каждой), только цена монет —
  сопутствующі витрати сюди не входят независимо от настройки `includeSupportingExpenses`;
- `supportingExpensesUah` (2026-09-22) — сумма расходов позиции (доставка, холдер,
  грейдинг), по `catalogItemId`, как на карточке монеты; `null`, если их нет. Фронт сам
  решает, сливать ли это с `totalSpendUah`, по той же настройке, что и карточка монеты
  (`includeSupportingExpenses`);
- `marketValueUah` — последняя видимая пользователю неподозрительная цена монеты ×
  `totalQuantity` (`null`, если цены нет);
- `lastAcquisitionDate` — максимальная дата покупки (`null`, если ни у одной нет даты);
- `grades` — отсортированный список различных станов покупок, без `null`;
- `thumbnailUrl` — как раньше, по тем же правилам видимости, что в каталоге.

Каждая покупка в списке (`CatalogCollectionItemOut`, одна строка = одна покупка, не
экземпляр) несёт `supportingExpensesUah` (2026-09-22) — сумму расходов, привязанных именно к
этой покупке через `collection_item_id` (не ко всей каталожной позиции), `null` при их
отсутствии. У покупок, сделанных до правила о `collection_item_id` (п. 4) и не покрытых
бэкфиллом, поле `null`, даже если у позиции в целом есть сопутствующие расходы, — они видны
только в общем `supportingExpensesUah` карточки, а не в конкретной строке.

Сортировки: `date` — по `lastAcquisitionDate`, `title` — по названию, `total` — по
`totalSpendUah`. Пагинация — по позициям, не по покупкам.

При создании покупки (`POST /collection`): сервер подтягивает курс НБУ на `purchaseDate`,
пишет `purchase_rate_uah` и в той же транзакции создаёт расход категории `coin_purchase`.
См. `business-rules.md`. `GET/PATCH/DELETE /collection/{id}` и ответ `POST /collection`
остаются в форме одной покупки (`CollectionItemOut`) — не позиции.

До этапа 5 курсы берутся только из таблицы `exchange_rates` (HTTP-клиента НБУ ещё нет):
покупка не в гривне с датой, на которую нет курса ≤ `purchaseDate`, отклоняется с `422`.

### Покупка монеты, которой ещё нет в каталоге

Решение владельца 2026-09-14. В теле `POST /collection` вместо `catalogItemId` может прийти
вложенный объект `newCatalogItem` — описание монеты, которую пользователь заводит сам.
**Ровно одно** из двух полей должно присутствовать: и пустое тело, и оба сразу — `422`.

```json
POST /collection
{
  "newCatalogItem": {
    "countryId": 230,
    "titleOriginal": "Львівський оперний театр",
    "issueYear": 2021,
    "collectionGroup": "commemorative",
    "material": "Нейзильбер",
    "seriesId": null, "denominationId": null, "compositionId": null,
    "metalKind": "unknown", "issueDate": null, "mintageAnnounced": null,
    "weightGrams": null, "diameterMm": null, "thicknessMm": null,
    "shape": null, "edgeTypeId": null, "qualityTypeId": null,
    "catalogNumber": null,
    "description": null, "descriptionObverse": null, "descriptionReverse": null
  },
  "quantity": 1, "price": "120.00", "currency": "UAH", "purchaseDate": "2026-09-14"
}
→ 201, CollectionItemOut
```

`newCatalogItem` — подмножество `CatalogItemCreate` с тремя отличиями:

- **нет `shared`.** Запись всегда личная (`created_by` = текущий пользователь). Общий
  каталог остаётся read-only, через эту дверь в него не попасть;
- **нет `originalLang`, `titleUk`, `titleEn`.** Оба переводных слота при создании держат
  введённый текст с пометкой `manual` — ровно как у нового места хранения, — а фоновая
  задача заменяет тот из них, который является переводом, и помечает его `llm` (см. ниже).
  Клиент не может выдать свой текст за `official`;
- **материал обязателен** в одном из двух видов: `compositionId` из словаря `GET /materials`
  **или** свободный текст `material`. Ни того ни другого — `422`. Словарь заполнен тем, что
  реально есть в каталоге, и для большинства эмитентов пуст, поэтому свободный текст — не
  запасной, а равноправный путь. Так же устроены **номинал** (`denominationId` или
  `denominationText`) и **серия** (`seriesId` или `seriesText`), только они необязательны;
  гурт и якість, наоборот, форма шлёт только словарными половинами (`edgeTypeId`,
  `qualityTypeId`). Подробности — `business-rules.md`, BR-14.

Ещё три отличия от `CatalogItemCreate`, добавленные 2026-09-14 по скриншоту владельца:

- **один `catalogNumber` вместо `catalogKm`/`catalogUc`/`catalogNumista`.** Те три колонки
  никуда не делись — их заполняет конвейер из источника, который знает систему нумерации, —
  но у человека номер один, и спрашивать, чей он, бессмысленно. Пишется в новую колонку
  `catalog_items.catalog_number` (миграция `0019`) и стоит последним в цепочке, которую
  `CatalogListItem.catalogNumber` и так читал;
- **`description`, `descriptionObverse`, `descriptionReverse` вместо `notes`.** Складываются
  в `descriptions` под локаль запроса, в форму, зафиксированную `data-model.md` (обе
  локали, три ключа, `null` где текста нет); пусто во всех трёх — колонка остаётся `NULL`.
  `notes` этот эндпоинт не пишет вовсе: это заметка о записи, а не описание монеты.

Обязательны, кроме материала: `countryId`, `titleOriginal`, `issueYear`, `collectionGroup`.
Год обязателен, потому что `catalog_items.issue_year` — `NOT NULL`, и на нём держатся
комплектность серий и фильтры по годам (решение владельца 2026-09-14). Остальное —
опционально.

**Одна транзакция.** Позиция каталога, экземпляр и расход `coin_purchase` создаются вместе
(`business-rules.md`, BR-4). Курс, валюта и место хранения разрешаются **до** первой
записи, поэтому покупка, отклонённая с `exchange-rate-missing` или `unknown-currency`, не
оставляет за собой осиротевшую позицию каталога. Плохие
`countryId`/`seriesId`/`denominationId`/`compositionId`/`edgeTypeId`/`qualityTypeId` дают
`422 invalid-reference` — тоже до записи. Транзакция коммитится **явно, внутри
запроса**: FastAPI выполняет `BackgroundTasks` раньше, чем закрывающий коммит сессии
запроса (доказано на местах хранения 2026-09-13), а фоновая задача перевода открывает свою
сессию — она бы не увидела монету. Атомарность при этом не страдает: это по-прежнему один
коммит на все три строки.

### Сопутствующие расходы одной покупкой

Решение владельца 2026-09-14, обратная сторона «Пов'язаної монети» в ветке расходов. В теле
`POST /collection` может прийти массив `extraExpenses` — доставка, холдер, грейдинг: деньги,
потраченные на эту монету в момент покупки. Работает с обеими формами тела, и с
`catalogItemId`, и с `newCatalogItem`.

```json
POST /collection
{
  "catalogItemId": 812,
  "quantity": 1, "price": "250.00", "currency": "UAH", "purchaseDate": "2026-09-14",
  "seller": "Violity",
  "extraExpenses": [
    {"category": "delivery", "amount": "60.00", "currency": "UAH"},
    {"category": "holder",   "amount": "25.00", "currency": "UAH"}
  ]
}
→ 201, CollectionItemOut
```

- поля ровно три: `category`, `amount`, `currency`. **Дата и продавец не спрашиваются
  второй раз** — расход берёт `purchaseDate` и `seller` покупки, ради чего всё и затевалось;
- `amount` строго больше нуля (`gt=0`), как и в `POST /expenses`. Монета может честно
  достаться даром, доставка — нет: ноль здесь означает незаполненное поле;
- `category` — любая ручная категория, кроме `coin_purchase`: эту строку пишет сама покупка,
  вторая такая удвоила бы расходы на монеты во всех сводках. Попытка — `422`;
- не больше 10 элементов в массиве; отсутствие поля и пустой массив равнозначны.

**`collection_item_id` (уточнено 2026-09-22).** Каждая строка `extraExpenses` пишется с
`catalog_item_id` **и** `collection_item_id` только что созданной покупки — так же, как
`coin_purchase`. `amount` кладётся как пришло, без домножения на `quantity`: это сумма за
покупку целиком, а не за экземпляр (`business-rules.md`, BR-4). Подробности удаления —
там же, п. 10.

**Курсы всех валют разрешаются до первой записи.** Доставка в валюте, на дату которой нет
курса НБУ, отклоняет запрос целиком: ни монеты, ни экземпляра, ни расхода `coin_purchase`.
Это то же правило, что и для самой покупки, распространённое на весь запрос.

**Что получается на выходе — обычный ручной расход**, привязанный к монете через
`catalog_item_id`; `collection_item_id` остаётся пустым. Это не оговорка: `collection_item_id`
во всём остальном приложении значит «эта строка *и есть* покупка» — на неё смотрят иконки в
журнале «Гроші», её удаляет удаление экземпляра (`business-rules.md`, BR-4). Доставка
покупкой не является, поэтому:

- **удаление доставки монету не трогает** — это просто удаление расхода;
- **удаление монеты из коллекции доставку не удаляет** — деньги были потрачены независимо
  от того, осталась ли монета в коллекции.

**Фоновый перевод названия.** Ответ ничего не ждёт. Задача просит Haiku перевести название,
определяет язык оригинала и заменяет только тот слот, который является переводом; слот на
языке оригинала остаётся посимвольной копией введённого текста с пометкой `manual`. Промпт
свой, не общий с местами хранения (`app/services/translation.py`). При любой ошибке
остаётся оригинал. Без `ANTHROPIC_API_KEY` задача — no-op с предупреждением в лог.

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

### Місце зберігання

```
GET    /collection/storage-locations              → [{name, custom}]
POST   /collection/storage-locations  {name}       → {name, custom}
DELETE /collection/storage-locations?name=
```

Ресурс адресуется по имени, не по id — сервер резолвит имя в `storage_locations.id`
прозрачно (`business-rules.md`, BR-16). `custom` — `true`, если запись принадлежит
текущему владельцу (можно удалить), `false` — системный пресет («Вдома», единственный).
`storageLocation` в `CollectionItemCreate`/`CollectionItemUpdate`/`CollectionItemOut` и
`defaultStorageLocation` в `SettingsOut`/`SettingsUpdate` — тем же именем: набирая текст
в форме покупки или в настройках, отдельно создавать место через `POST` не обязательно,
первое же использование текста заводит личную запись сама.

`DELETE` — `204` при успехе, `403` при попытке удалить пресет, `404`, если имя не видно
этому владельцу вовсе (включая чужую личную запись — не подтверждаем её существование).

## Серии

```
GET  /series?countryId
POST /series  {countryId, name, description?, startYear?, endYear?}
GET  /series/summary?countryId
  → [{series: {...}, summary: {...}}]   — все серии (страны) со сводкой одним запросом
```

Серии — общий справочник, личных серий нет: серия описывает выпуск, а не коллекцию.
`POST /series` доступен только администратору (`403` обычному пользователю), дубль имени
в пределах страны — `409`. `GET /series/summary` — источник дашбордного KPI «почато/завершено
серій» (`features/collection/CollectionPage.tsx`); экран «Комплектність» на нём не завязан,
он использует `/completeness/*` ниже.

## Комплектность

```
GET /completeness/summary?groupBy&countryId&metalKind
  → [CompletenessGroupOut]
GET /completeness/group?groupBy&value|unassigned&countryId&metalKind
  → CompletenessGroupOut
GET /completeness/items?groupBy&value|unassigned&countryId&metalKind&owned&page&pageSize
  → Page<CatalogListItem>               — та же схема, что и у GET /catalog

groupBy = series | year | denomination | material | edge | quality
CompletenessGroupOut = {
  groupBy, value, unassigned, label, countryId, description, startYear, endYear,
  sortOrder, summary: {total, owned, missing, completionPercent, purchaseTotalUah,
  currentValueUah, unpricedMissing}
}
```

Комплектность по произвольному полю каталога — обобщение того, что раньше было только для
серии (`GET /series/{id}/summary`/`GET /series/{id}/items`, оба эндпоинта удалены, заменены
`/completeness/group`/`/completeness/items` с `groupBy=series`). `value`/`unassigned` —
взаимоисключающие, ровно один обязателен: `value=<id>` адресует конкретную серию/номинал/
материал/гурт/якість карбування (или конкретный год — число само является значением),
`unassigned=true` — бакет «без значения» (`series_id`/`denomination_id`/`composition_id`/
`edge_type_id`/`quality_type_id IS NULL`); `groupBy=year` не принимает `unassigned`
(`issue_year` NOT NULL) — `422`. Обе части дроби комплектности считаются по активным видимым
пользователю позициям; деньги (`purchaseTotalUah`, `currentValueUah`) — по его экземплярам,
включая экземпляры архивных позиций (`business-rules.md`, BR-5 and BR-10) — то же правило, что
раньше проверялось только для серий, теперь общее для всех измерений.

`metalKind` (`precious`/`base`, необязательный) — фильтр по `catalog_items.metal_kind`,
независимый от `groupBy`: применяется одинаково к любому измерению («тільки дорогоцінні по
роках», «тільки недорогоцінні по серіях»), а не только к выбору конкретного значения. Без
него — все монеты, вне зависимости от цінності металу (UI-контрол — `ui.md`, тулбар
«Комплектність»). Изначально был только на `/summary`; с 2026-09-24 (карточка группы получила
свой тулбар) — также на `/group` и `/items`, чтобы клик по строке списка переносил активный
фильтр в детальный экран, а не сбрасывал его.

`owned` (bool, необязательный) — только на `/completeness/items`: сужает плитки до
«тільки наявні»/«тільки відсутні» в детальном экране группы, независимо от `groupBy` и
`metalKind`.

`/completeness/items` — плитки монет для экрана деталей группы, **не** `GET /catalog?...=`
(правило унаследовано от `/series/{id}/items`, добавлено 2026-09-13, `business-rules.md`
§13a). Разница принципиальная: `storefront_visible(require_confirmed=False)` вместо жёсткого
гейта `GET /catalog` — экран комплектности про личную коллекцию пользователя, а не про витрину
каталога, поэтому не прячет позиции страны без `catalog_confirmed`, даже если это единственный
способ увидеть свои же монеты (найдено на живых данных: серия США «50 State Quarters», 56
личных позиций, каталог США не подтверждён — до фикса плитки были пустыми несмотря на 100%
комплектности в `summary`). `CountryOut.catalogConfirmed` — сигнал для фронта, актуален только
при `groupBy=series` (только у серии есть естественная привязка к одной стране): `true` →
показываем «Відкрити в каталозі», `false` → вместо кнопки поясняющий текст, что показана только
особиста колекція.

## Расходы

```
GET    /expenses?category&dateFrom&dateTo&page&pageSize&sort&order
POST   /expenses
PATCH  /expenses/{id}
DELETE /expenses/{id}
GET    /expenses/summary
GET    /expenses/chart-summary?dateFrom&dateTo
```

`sort` — `date` (по умолчанию) | `category` | `description` | `vendor` | `amount`,
`order` — `asc` | `desc` (по умолчанию). Сортировка по колонкам журнала (`ui.md`):
`description` — по тому, что показано в колонке «Опис» (название монеты для покупки, свой
текст для остального), `amount` — по сумме в гривне, `category` — в порядке объявления
таксономии, а не по алфавиту: смысл этой сортировки — сгруппировать журнал по видам.

`amount` в `POST`/`PATCH /expenses` — строго больше нуля (`422` на ноль и на минус,
приведено к фронту 2026-09-14). Это отличие от цены покупки, где `0` законен — подарок или
неизвестная цена; доставка или альбом за ноль — опечатка. `CHECK` в самой таблице остаётся
`amount >= 0`: он сторожит и строки `coin_purchase`, которые эти эндпоинты не пишут.

`catalogItemId` в теле — необязательная привязка сопутствующей траты к монете (грейдинг,
холдер для конкретного экземпляра). Ссылается на **существующую** позицию, видимую
пользователю, — общую или свою личную; ничего не создаёт. Неизвестный id — `422`.

`CatalogListItem.denominationText` и `CatalogCard.denominationText` — номинал словами у
записи, для страны которой справочника нет; показывается вместо `denomination`, когда тот
`null` (`data-model.md`). `seriesName` отдельного текстового поля не получил: он и так
строка, и подставляет `series_text`, когда `series_id` пуст. В `CollectionPositionOut` /
`CollectionItemOut` то же самое делает уже готовая строка `denomination`.

`coinTitle` в `ExpenseOut` — локализованное (`?locale`/`Accept-Language`) название монеты,
джойном через `catalogItemId`, для **любой** траты, у которой этот id задан, а не только
для покупок (расширено 2026-09-14: иначе прив'язку, которую человек сделал в форме, негде
увидеть). У траты без монеты — `null`.

`GET /expenses/summary` (`ExpensesSummaryOut`):

- `categories` / `total_uah` / `coin_spend_uah` / `related_spend_uah` — как раньше;
- `byCategory` — тот же список, что `categories` (по каждой категории с ненулевой суммой:
  `category`, `count`, `totalUah`);
- `byMonth` — последние 12 календарных месяцев по дате сервера, от самого старого к
  текущему, каждый — `{month: "YYYY-MM", coinsUah, supportingUah}`; месяцы без трат идут
  нулями, а не пропускаются, чтобы ось графика была сплошной;
- `thisMonthUah` / `prevMonthUah` — сумма (монеты + сопутствующие) за текущий и
  предыдущий календарный месяц; равны последним двум точкам `byMonth`.

`GET /expenses/chart-summary?dateFrom&dateTo` (`ExpensesChartOut`, оба параметра обязательны,
`dateFrom > dateTo` — `422`) — те же два виджета графика на странице «Гроші», но за диапазон,
который выбирает сам пользователь (плашки «1М/3М/6М/1Р» и произвольные даты на фронте), в
отличие от фиксированных окон `ExpensesSummaryOut`:

- `granularity` — `day`, если диапазон не длиннее 31 дня, иначе `month`;
- `byPeriod` — точки графика, от старой к новой, нулями там, где трат не было; `period` —
  `"YYYY-MM-DD"` при дневной группировке, `"YYYY-MM"` при месячной;
- `byCategory` — разбивка по категориям **только за этот диапазон** (не тот же список, что
  `categories`/`byCategory` в `ExpensesSummaryOut`, которые всегда за всё время).

## Цены и курсы

Цены общего каталога обновляет системная суточная задача — пользовательского запуска для них
нет (`business-rules.md`, BR-7). Эндпоинты ниже работают **только по личным позициям**.

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
`raw_payload`. См. `integrations.md`.

## Импорт

Импорт **создаёт только личные позиции** (`created_by` = текущий пользователь). Если
совпадение нашлось в общем каталоге, новая запись не создаётся — экземпляры привязываются
к общей. Правила дедупликации — `business-rules.md`, BR-3.

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
PUT    /collection/{id}/photos/{role}     сырые байты (image/jpeg|png|webp) → CollectionItemPhotosOut
DELETE /collection/{id}/photos/{role}                                      → CollectionItemPhotosOut
```

`role` — `obverse` или `reverse`, в пути; что-то ещё — `422`. Как `PUT/DELETE /auth/me/avatar`
(`ui.md`, часть 8): один файл без multipart-конверта, `Content-Length` сверх лимита
отбивается `422` до чтения тела. Ответ — уже подписанные `CoinImageOut` на обе стороны этого
**экземпляра** (`{obverse, reverse}`), чтобы страница перерисовалась без второго запроса.
Всегда пишет новую строку `media_files` с `collectionItemId` (не `catalogItemId`) и
`source = 'user_upload'`; своя позиция чужого пользователя — `404`.

`GET /collection/{id}` и списки коллекции/каталога подмешивают этот же приоритет на чтение —
подробности выбора и происхождения см. `media.md`.

Загрузка фото для **каталожных** записей (`/catalog/{id}/images`, редактирование общей
позиции администратором) в MVP не реализована — отложено за пределы этого этапа.

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
запускается снаружи, своим контейнером, и отчитывается о себе сама (`admin.md`).

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

Чтение — под ролью admin, обычный `403` всем остальным:

```
GET /admin/jobs?job=&page=&pageSize=
  → {
      items: [{id, job, status, startedAt, finishedAt, runDate,
               summary, stats, details, exitCode}],
      total, page, pageSize,
      jobs: ["update-prices", ...]   // имена задач, которые уже отчитывались
    }
GET /admin/jobs/{id}  → одна такая запись, 404 если нет
```

`jobs` в ответе списка — чтобы экран показал фильтр по задачам, не делая второго запроса.
Сортировка всегда «сначала свежие»: список отвечает на вопрос «как прошла эта ночь».

### Админский бот

```
GET    /admin/telegram        → {connected, chats}          // роль admin
POST   /admin/telegram/link   → {url, expiresAt}            // t.me/<бот>?start=<код>
DELETE /admin/telegram        → 204
POST   /telegram/webhook      → 200 всегда
```

Код привязки — обычный одноразовый токен `auth_tokens` (вид `telegram_link`, 15 минут),
выдача нового гасит предыдущий. `503`, если бот на сервере не настроен.

Вебхук — единственный публичный маршрут без аутентификации пользователя. Секрет
проверяется из заголовка `X-Telegram-Bot-Api-Secret-Token` **до** разбора тела; чужой
секрет — `403`, незаданный на сервере — `404`, как будто маршрута нет. Ответ всегда `200`:
любой другой код заставляет телеграм часами повторять тот же апдейт. Обрабатываются
только `/start <код>` и `/last`, остальное молча игнорируется — ответ подтвердил бы
постороннему, что бот жив.

### Бот підтримки (публічний, `/support/telegram`)

Окремий бот від адмінського: тут — саппорт-чат для будь-якого користувача (ідеї, питання,
зв'язок з адмінами), а не сповіщення адмінів про прогони. Посилання на нього — у футері
(`ui.md`).

```
GET  /support/telegram         → {url}                       // публічний, без входу
POST /support/telegram/link    {sourcePath?} → {url}          // за логіном
POST /support/telegram/webhook → 200 завжди
```

`GET` — статична публічна ланка для гостя. `POST` (авторизований) підмішує в ланку контекст
користувача, `sourcePath` — необов'язкова позначка, зі скількох екрана прийшов запит.
`503`, якщо бот не налаштований на сервері (`SUPPORT_TELEGRAM_*` відсутні). Вебхук — та сама
схема секрету й завжди-200, що й у адмінського бота вище, окремий токен
(`support_telegram_webhook_secret`), окремий обробник (`services/support.py`).

### Користувачі (`/admin/users`)

```
GET   /admin/users?page&pageSize
  → { items: [{id, email, displayName, role, isActive, emailVerified, createdAt, coinCount}],
      total, page, pageSize,
      summary: {totalUsers, collectors} }        // collectors — з хоча б однією монетою
PATCH /admin/users/{id}/role  {role: "user" | "admin"}
  → AdminUserOut (той самий один рядок, coinCount тут завжди 0 — не перераховується на PATCH)
```

Обидва — тільки роль admin, `403` іншим. `PATCH` — зі стандартними запобіжниками
(`business-rules.md`): `409 cannot-demote-self` — собі роль не знімають, `409 last-admin`
— останнього адміна в системі не знімають, `409 admin-user-ineligible` — підвищити можна
тільки активного користувача з підтвердженим email.

### Ревью чернеток каталогу (`/admin/proposals`)

```
GET    /admin/proposals?page&pageSize
  → { items: [{status, card: CatalogCard}], total, page, pageSize }
GET    /admin/proposals/{id}    → {status, card}         // 404, якщо не draft
PUT    /admin/proposals/{id}/photos/{role}    (raw image body, ≤12 МБ)  → CatalogCard
DELETE /admin/proposals/{id}/photos/{role}    → CatalogCard
POST   /admin/proposals/{id}/approve          → CatalogCard        // draft → active
POST   /admin/proposals/{id}/reject   {reason} → ArchiveStateOut   // draft → archived
```

Тільки роль admin. Список і картка бачать записи виключно зі `status = draft`
(`repositories/catalog.py`, той самий фільтр, що ховає чернетки від публічної вітрини й
пошуку — `business-rules.md`). `role` у шляху фото — `obverse`/`reverse`, той самий
формат, що у звичайного завантаження фото каталогу. `approve`/`reject` — `409
proposal-not-draft`, якщо запис уже не чернетка (повторний клік, паралельна дія іншого
адміна); `reject` без непорожньої причини — `400`. Джерело чернеток — щоденний
`nbu-catalog-sync` у coin-parser: нові випуски й оновлені офіційні дані потрапляють сюди
`status = draft`, а не одразу у вітрину (`11-roadmap.md`, `admin.md`).

## Справочники

```
GET /countries?scope=active|all|confirmed
GET /denominations?countryId
GET /materials
GET /edge-types
GET /quality-types
GET /currencies
```

`GET /countries` — `scope=active` (по умолчанию) отдаёт витрину: только активные страны,
`scope=all` — весь справочник, для формы личной позиции, куда можно вписать монету любого
когда-либо существовавшего эмитента.

`GET /materials`, `GET /edge-types`, `GET /quality-types` — **полные** словари состава,
гурта и качества чеканки (`CoinMaterial` / `CoinEdgeType` / `CoinQualityType`: `id`, `code`,
`name` на языке запроса, по алфавиту). Их читает форма «Додати», где монета ещё не
существует. Не путать с `GET /catalog/materials`: тот отдаёт только материалы, которые
реально встречаются у подтверждённых записей, — он сужает фильтр до того, что можно найти.

`CountryOut.minYear`/`maxYear` — границы `issue_year` по каталожным монетам страны, видимым
текущему пользователю (тот же скоуп видимости, что у `GET /catalog`: общий каталог плюс личные
позиции, без архивных). `null`/`null` у страны без ни одной видимой монеты. Используются
фронтом как границы выпадашек «Рік від/до» (`ui.md`) — отдельной ручки для глобальных
границ нет, фронт берёт min/max по уже загруженному списку стран.
