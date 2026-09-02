export interface DashboardSnapshot {
  catalogItems: number;
  physicalItems: number;
  countries: number;
  countryBreakdown: Array<{ name: string; count: number; owned: number }>;
  seriesBreakdown: Array<{ name: string; country: string; count: number; owned: number }>;
  completedItems: number;
  missingItems: number;
  completionPercent: number;
  coinSpendUah: number;
  relatedSpendUah: number;
  totalSpendUah: number;
  marketValueUah: number;
  missingBudgetUah: number;
  unpricedMissingItems: number;
  isEmpty: boolean;
}

export interface ExchangeRateSummary {
  code: "USD" | "EUR";
  rate: number | null;
  effectiveDate: string | null;
}

export interface BootstrapPayload {
  appVersion: string;
  dataDirectory: string;
  schemaVersion: number;
  dashboard: DashboardSnapshot;
  exchangeRates: ExchangeRateSummary[];
  finance: FinanceSummary;
}

export interface FinanceSummary {
  coinSpendUah: number;
  coinSpendUsdAtPurchase: number | null;
  coinSpendEurAtPurchase: number | null;
  purchasesWithoutHistoricalUsdRate: number;
  purchasesWithoutHistoricalEurRate: number;
}

export interface BackupListItem {
  fileName: string;
  absolutePath: string;
  sizeBytes: number;
  createdAt: string;
}

export interface BackupResult extends BackupListItem {
  checksum: string;
}

export interface CatalogCoin {
  id: number;
  country: string;
  seriesName: string | null;
  denomination: string;
  year: number;
  title: string;
  variety: string | null;
  catalogNumber: string | null;
  collectionGroup: "circulation" | "commemorative" | "collector" | "other";
  material: string | null;
  marketPriceUah: number | null;
  priceSource: string | null;
  priceObservedAt: string | null;
  quantityOwned: number;
  purchaseTotalUah: number;
  thumbnailPath: string | null;
  obverseImagePath: string | null;
  reverseImagePath: string | null;
  sourceUrl: string | null;
}

export interface CoinInput {
  country: string;
  seriesName?: string | null;
  denomination: string;
  year: number;
  title: string;
  variety?: string | null;
  catalogNumber?: string | null;
  collectionGroup: CatalogCoin["collectionGroup"];
  marketPriceUah?: number | null;
  priceSource?: string | null;
  material?: string | null;
  sourceUrl?: string | null;
  obverseImageUrl?: string | null;
  reverseImageUrl?: string | null;
}

export interface PurchaseInput {
  catalogItemId: number;
  quantity: number;
  price: number;
  purchaseDate: string;
  seller?: string | null;
  notes?: string | null;
}

export interface PurchaseRecord {
  id: number;
  catalogItemId: number;
  quantity: number;
  purchaseDate: string | null;
  seller: string | null;
  priceUah: number;
  totalUah: number;
  usdAtPurchase: number | null;
  eurAtPurchase: number | null;
  notes: string | null;
}

export interface ImportSummary {
  fileName: string;
  scanned: number;
  inserted: number;
  updated: number;
  skipped: number;
  countries: number;
  warnings: string[];
}

export interface PriceHistoryRecord {
  id: number;
  catalogItemId: number;
  source: string;
  priceUah: number;
  observedAt: string;
  sourceUrl: string | null;
}

export interface RateRefreshResult {
  effectiveDate: string;
  rates: Array<{ code: "USD" | "EUR"; rate: number }>;
}

export interface RateSyncResult {
  startDate: string;
  endDate: string;
  checkedDates: number;
  fetchedDates: number;
  failedDates: Array<{ date: string; message: string }>;
}

export interface PriceRefreshResult {
  catalogItemId: number;
  source: "UA-Coins" | "Numista" | "uCoin";
  status: "updated" | "not-found" | "needs-api-key";
  previousPriceUah: number | null;
  priceUah: number | null;
  observedAt: string;
  sourceUrl?: string;
  message: string;
}

export interface UcoinImportResult {
  mode: "coin" | "catalog";
  sourceUrl: string;
  scanned: number;
  inserted: number;
  updated: number;
  skipped: number;
  warnings: string[];
}

export interface CoinKeeperApi {
  getBootstrap(): Promise<BootstrapPayload>;
  createBackup(): Promise<BackupResult>;
  listBackups(): Promise<BackupListItem[]>;
  selectExcelFiles(): Promise<string[]>;
  importExcel(filePaths: string[]): Promise<ImportSummary[]>;
  listCatalog(): Promise<CatalogCoin[]>;
  createCoin(input: CoinInput): Promise<CatalogCoin>;
  updateCoin(id: number, input: CoinInput): Promise<CatalogCoin>;
  deleteCoin(id: number): Promise<void>;
  addPurchase(input: PurchaseInput): Promise<CatalogCoin>;
  listPurchases(catalogItemId: number): Promise<PurchaseRecord[]>;
  listPriceHistory(catalogItemId: number): Promise<PriceHistoryRecord[]>;
  refreshRates(): Promise<RateRefreshResult>;
  syncMissingRates(): Promise<RateSyncResult>;
  refreshCoinPrice(id: number): Promise<PriceRefreshResult>;
  previewUcoinCoin(url: string): Promise<CoinInput>;
  importUcoinUrl(url: string): Promise<UcoinImportResult>;
}
