/** Convenient aliases over the generated OpenAPI types (npm run gen:api). */

import type { components } from './generated/openapi';

export type UserOut = components['schemas']['UserOut'];
export type SessionOut = components['schemas']['SessionOut'];
export type TokensOut = components['schemas']['TokensOut'];

export type CatalogListItem = components['schemas']['CatalogListItem'];
export type CatalogCard = components['schemas']['CatalogCard'];
export type CatalogPage = components['schemas']['Page_CatalogListItem_'];

export type CountryOut = components['schemas']['CountryOut'];
export type DenominationOut = components['schemas']['DenominationOut'];
export type CurrencyOut = components['schemas']['CurrencyOut'];
export type SeriesOut = components['schemas']['SeriesOut'];

export type CollectionGroup = components['schemas']['CollectionGroup'];
export type MetalKind = components['schemas']['MetalKind'];

export type BootstrapOut = components['schemas']['BootstrapOut'];
export type DashboardOut = components['schemas']['DashboardOut'];
export type BreakdownEntry = components['schemas']['BreakdownEntry'];
export type SeriesBreakdownEntry = components['schemas']['SeriesBreakdownEntry'];
export type ExchangeRateOut = components['schemas']['ExchangeRateOut'];

export type PriceHistoryItem = components['schemas']['PriceHistoryItem'];
export type CatalogCollectionItem = components['schemas']['CatalogCollectionItemOut'];
