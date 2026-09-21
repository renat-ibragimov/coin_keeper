/** Convenient aliases over the generated OpenAPI types (npm run gen:api). */

import type { components } from './generated/openapi';

// avatarUrl is on the server's UserOut already; the checked-in OpenAPI
// snapshot predates it. Drop the intersection after `npm run gen:api` runs
// against a backend carrying migration 0020.
export type UserOut = components['schemas']['UserOut'] & {
  avatarUrl?: string | null;
  hasPassword?: boolean;
  googleLinked?: boolean;
};
export type SessionOut = components['schemas']['SessionOut'];
export type TokensOut = components['schemas']['TokensOut'];

export type CatalogListItem = components['schemas']['CatalogListItem'];
export type CatalogCard = components['schemas']['CatalogCard'];
export type CatalogPage = components['schemas']['Page_CatalogListItem_'];
export type CoinMaterial = components['schemas']['CoinMaterial'];
export type CoinEdgeType = components['schemas']['CoinEdgeType'];
export type CoinQualityType = components['schemas']['CoinQualityType'];
export type CoinDescriptions = components['schemas']['CoinDescriptions'];

export type CountryOut = components['schemas']['CountryOut'];
export type DenominationOut = components['schemas']['DenominationOut'];
export type CurrencyOut = components['schemas']['CurrencyOut'];
export type SeriesOut = components['schemas']['SeriesOut'];

export type CollectionGroup = components['schemas']['CollectionGroup'];
export type MetalKind = components['schemas']['MetalKind'];

export type BootstrapOut = components['schemas']['BootstrapOut'];
export type SettingsOut = components['schemas']['SettingsOut'];
export type SettingsUpdate = components['schemas']['SettingsUpdate'];
export type DashboardOut = components['schemas']['DashboardOut'];
export type BreakdownEntry = components['schemas']['BreakdownEntry'];
export type SeriesBreakdownEntry = components['schemas']['SeriesBreakdownEntry'];
export type ExchangeRateOut = components['schemas']['ExchangeRateOut'];

export type PriceHistoryItem = components['schemas']['PriceHistoryItem'];
export type CatalogCollectionItem = components['schemas']['CatalogCollectionItemOut'];

// obverseImage/reverseImage and the photos endpoints are on the server
// already; the checked-in OpenAPI snapshot predates them. Drop the
// intersection and add CollectionItemPhotosOut after `npm run gen:api` runs
// against a backend carrying the collection-photos endpoints.
type CoinImage = components['schemas']['CoinImageOut'];
export type CollectionItem = components['schemas']['CollectionItemOut'] & {
  obverseImage?: CoinImage | null;
  reverseImage?: CoinImage | null;
  obversePhotoIsOwn?: boolean;
  reversePhotoIsOwn?: boolean;
};
export type CollectionItemPhotos = { obverse: CoinImage | null; reverse: CoinImage | null };
export type CollectionItemCreate = components['schemas']['CollectionItemCreate'];
export type CollectionItemUpdate = components['schemas']['CollectionItemUpdate'];
export type CollectionPosition = components['schemas']['CollectionPositionOut'];
export type CollectionPage = components['schemas']['Page_CollectionPositionOut_'];
export type StorageLocation = components['schemas']['StorageLocationOut'];

export type CatalogItemCreate = components['schemas']['CatalogItemCreate'];
export type CatalogItemUpdate = components['schemas']['CatalogItemUpdate'] & {
  description?: string | null;
  descriptionObverse?: string | null;
  descriptionReverse?: string | null;
};
export type NewCatalogItem = components['schemas']['NewCatalogItemIn'];

export type SeriesProgress = components['schemas']['SeriesProgressOut'];
export type SeriesSummary = components['schemas']['SeriesSummaryOut'];

export type ExpenseOut = components['schemas']['ExpenseOut'];
export type ExpenseCreate = components['schemas']['ExpenseCreate'];
export type ExpenseUpdate = components['schemas']['ExpenseUpdate'];
export type ExpenseCategory = components['schemas']['ExpenseCategory'];
export type ExpensePage = components['schemas']['Page_ExpenseOut_'];
export type ExpensesSummary = components['schemas']['ExpensesSummaryOut'];
export type ExpenseCategorySummary = components['schemas']['ExpenseCategorySummary'];
export type ExpenseMonthTotal = components['schemas']['ExpenseMonthTotal'];

export type JobRunOut = components['schemas']['JobRunOut'];
export type JobRunsPage = components['schemas']['JobRunsOut'];
export type TelegramStatus = components['schemas']['TelegramStatusOut'];
export type TelegramLink = components['schemas']['TelegramLinkOut'];
export type AdminUser = components['schemas']['AdminUserOut'];
export type AdminUsersPage = components['schemas']['AdminUsersOut'];
export type AdminProposal = { status: string; card: CatalogCard };
export type AdminProposalsPage = {
  items: AdminProposal[];
  total: number;
  page: number;
  pageSize: number;
};
export type ExpensePeriodTotal = components['schemas']['ExpensePeriodTotal'];
export type ExpensesChart = components['schemas']['ExpensesChartOut'];
