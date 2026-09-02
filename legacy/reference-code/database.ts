import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
import path from "node:path";
import type { CatalogCoin, CoinInput, DashboardSnapshot, ExchangeRateSummary, FinanceSummary, PriceHistoryRecord, PurchaseInput, PurchaseRecord } from "../domain/types";

const migrations = [
  {
    version: 1,
    name: "initial-domain-model",
    sql: `
      CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE countries (
        id INTEGER PRIMARY KEY,
        code TEXT UNIQUE,
        name_original TEXT NOT NULL,
        name_ru TEXT,
        name_en TEXT,
        collect_variants INTEGER NOT NULL DEFAULT 0 CHECK (collect_variants IN (0, 1)),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE currencies (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        symbol TEXT,
        decimal_places INTEGER NOT NULL DEFAULT 2
      );

      CREATE TABLE denominations (
        id INTEGER PRIMARY KEY,
        country_id INTEGER NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
        currency_code TEXT REFERENCES currencies(code),
        value_minor_units INTEGER,
        label_original TEXT NOT NULL,
        label_ru TEXT,
        label_en TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        UNIQUE(country_id, label_original)
      );

      CREATE TABLE coin_series (
        id INTEGER PRIMARY KEY,
        country_id INTEGER NOT NULL REFERENCES countries(id) ON DELETE CASCADE,
        name_original TEXT NOT NULL,
        name_ru TEXT,
        name_en TEXT,
        description TEXT,
        start_year INTEGER,
        end_year INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(country_id, name_original)
      );

      CREATE TABLE catalog_items (
        id INTEGER PRIMARY KEY,
        item_type TEXT NOT NULL DEFAULT 'coin',
        country_id INTEGER NOT NULL REFERENCES countries(id),
        series_id INTEGER REFERENCES coin_series(id) ON DELETE SET NULL,
        denomination_id INTEGER REFERENCES denominations(id) ON DELETE SET NULL,
        collection_group TEXT NOT NULL CHECK (collection_group IN ('circulation', 'commemorative', 'collector', 'other')),
        subtype TEXT,
        title_original TEXT NOT NULL,
        title_ru TEXT,
        title_en TEXT,
        issue_year INTEGER NOT NULL,
        issue_date TEXT,
        mintage_announced INTEGER,
        mintage_actual INTEGER,
        material TEXT,
        weight_grams REAL,
        diameter_mm REAL,
        thickness_mm REAL,
        shape TEXT,
        edge TEXT,
        orientation TEXT,
        catalog_km TEXT,
        catalog_uc TEXT,
        catalog_numista TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE INDEX idx_catalog_items_country_year ON catalog_items(country_id, issue_year);
      CREATE INDEX idx_catalog_items_series ON catalog_items(series_id);
      CREATE INDEX idx_catalog_items_catalog_numbers ON catalog_items(catalog_km, catalog_uc, catalog_numista);

      CREATE TABLE catalog_variants (
        id INTEGER PRIMARY KEY,
        catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        mint_name TEXT,
        mint_mark TEXT,
        variety_code TEXT,
        notes TEXT,
        UNIQUE(catalog_item_id, name, mint_mark)
      );

      CREATE TABLE collection_goals (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        country_id INTEGER REFERENCES countries(id) ON DELETE CASCADE,
        series_id INTEGER REFERENCES coin_series(id) ON DELETE CASCADE,
        collection_group TEXT,
        year_from INTEGER,
        year_to INTEGER,
        denomination_ids_json TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE collection_items (
        id INTEGER PRIMARY KEY,
        catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
        variant_id INTEGER REFERENCES catalog_variants(id) ON DELETE SET NULL,
        quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
        grade TEXT,
        condition_notes TEXT,
        acquisition_date TEXT,
        acquisition_place TEXT,
        seller TEXT,
        purchase_price REAL,
        purchase_currency TEXT REFERENCES currencies(code),
        purchase_rate_uah REAL,
        storage_location TEXT,
        grading_company TEXT,
        grading_number TEXT,
        grading_grade TEXT,
        is_for_swap INTEGER NOT NULL DEFAULT 0 CHECK (is_for_swap IN (0, 1)),
        needs_replacement INTEGER NOT NULL DEFAULT 0 CHECK (needs_replacement IN (0, 1)),
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE INDEX idx_collection_items_catalog ON collection_items(catalog_item_id);

      CREATE TABLE media_files (
        id INTEGER PRIMARY KEY,
        catalog_item_id INTEGER REFERENCES catalog_items(id) ON DELETE CASCADE,
        collection_item_id INTEGER REFERENCES collection_items(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('obverse', 'reverse', 'edge', 'additional')),
        original_path TEXT NOT NULL,
        thumbnail_path TEXT,
        mime_type TEXT,
        width INTEGER,
        height INTEGER,
        sha256 TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CHECK (catalog_item_id IS NOT NULL OR collection_item_id IS NOT NULL)
      );

      CREATE TABLE price_source_links (
        id INTEGER PRIMARY KEY,
        catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
        source TEXT NOT NULL,
        external_id TEXT NOT NULL,
        match_status TEXT NOT NULL DEFAULT 'confirmed' CHECK (match_status IN ('suggested', 'confirmed', 'rejected')),
        matched_at TEXT,
        UNIQUE(catalog_item_id, source)
      );

      CREATE TABLE market_price_snapshots (
        id INTEGER PRIMARY KEY,
        catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
        source TEXT NOT NULL,
        grade TEXT,
        price REAL NOT NULL CHECK (price >= 0),
        currency_code TEXT NOT NULL REFERENCES currencies(code),
        observed_at TEXT NOT NULL,
        source_url TEXT,
        raw_payload_json TEXT,
        UNIQUE(catalog_item_id, source, grade, observed_at)
      );

      CREATE INDEX idx_market_price_latest ON market_price_snapshots(catalog_item_id, observed_at DESC);

      CREATE TABLE purchase_offers (
        id INTEGER PRIMARY KEY,
        catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE CASCADE,
        price REAL NOT NULL CHECK (price >= 0),
        currency_code TEXT NOT NULL REFERENCES currencies(code),
        url TEXT,
        seller TEXT,
        found_at TEXT NOT NULL,
        expires_at TEXT,
        status TEXT NOT NULL DEFAULT 'considering' CHECK (status IN ('considering', 'ordered', 'purchased', 'rejected', 'unavailable')),
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE exchange_rates (
        id INTEGER PRIMARY KEY,
        currency_code TEXT NOT NULL REFERENCES currencies(code),
        rate_uah REAL NOT NULL CHECK (rate_uah > 0),
        effective_date TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'NBU',
        UNIQUE(currency_code, effective_date, source)
      );

      CREATE TABLE expenses (
        id INTEGER PRIMARY KEY,
        category TEXT NOT NULL CHECK (category IN ('coin_purchase', 'delivery', 'album', 'holder', 'storage', 'grading', 'literature', 'photo_equipment', 'other')),
        amount REAL NOT NULL CHECK (amount >= 0),
        currency_code TEXT NOT NULL REFERENCES currencies(code),
        rate_uah REAL,
        expense_date TEXT NOT NULL,
        catalog_item_id INTEGER REFERENCES catalog_items(id) ON DELETE SET NULL,
        collection_item_id INTEGER REFERENCES collection_items(id) ON DELETE SET NULL,
        series_id INTEGER REFERENCES coin_series(id) ON DELETE SET NULL,
        vendor TEXT,
        description TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE audit_log (
        id INTEGER PRIMARY KEY,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        details_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

      CREATE TABLE backup_runs (
        id INTEGER PRIMARY KEY,
        archive_path TEXT NOT NULL,
        sha256 TEXT,
        size_bytes INTEGER,
        status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
        details TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT
      );

      INSERT OR IGNORE INTO currencies(code, name, symbol, decimal_places) VALUES
        ('UAH', 'Ukrainian hryvnia', '₴', 2),
        ('USD', 'US dollar', '$', 2),
        ('EUR', 'Euro', '€', 2);

      INSERT OR IGNORE INTO settings(key, value_json) VALUES
        ('ui.language', '"ru"'),
        ('pricing.defaultGrade.commemorative', '"UNC"'),
        ('pricing.defaultGrade.circulation', '"VF"'),
        ('pricing.source.ukraine', '"UA-Coins"'),
        ('pricing.source.other', '"Numista"');
    `,
  },
  {
    version: 2,
    name: "catalog-import-identity",
    sql: `
      ALTER TABLE catalog_items ADD COLUMN source_key TEXT;
      CREATE UNIQUE INDEX idx_catalog_items_source_key ON catalog_items(source_key) WHERE source_key IS NOT NULL;
      CREATE UNIQUE INDEX idx_countries_name_original ON countries(name_original);
    `,
  },
];

export interface ImportedCatalogRow extends CoinInput {
  sourceKey: string;
}

export class DatabaseService {
  private readonly database: DatabaseSync;

  constructor(readonly databasePath: string) {
    fs.mkdirSync(path.dirname(databasePath), { recursive: true });
    this.database = new DatabaseSync(databasePath);
    this.database.exec("PRAGMA foreign_keys = ON;");
    this.database.exec("PRAGMA journal_mode = WAL;");
    this.database.exec("PRAGMA synchronous = NORMAL;");
    this.runMigrations();
  }

  private runMigrations(): void {
    this.database.exec(`
      CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );
    `);

    const rows = this.database.prepare("SELECT version FROM schema_migrations").all() as Array<{ version: number }>;
    const applied = new Set(rows.map((row) => row.version));

    for (const migration of migrations) {
      if (applied.has(migration.version)) continue;

      this.database.exec("BEGIN IMMEDIATE;");
      try {
        this.database.exec(migration.sql);
        this.database
          .prepare("INSERT INTO schema_migrations(version, name) VALUES (?, ?)")
          .run(migration.version, migration.name);
        this.database.exec("COMMIT;");
      } catch (error) {
        this.database.exec("ROLLBACK;");
        throw error;
      }
    }
  }

  getSchemaVersion(): number {
    const row = this.database
      .prepare("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations")
      .get() as { version: number };
    return Number(row.version);
  }

  getDashboardSnapshot(): DashboardSnapshot {
    const counts = this.database.prepare(`
      SELECT
        (SELECT COUNT(*) FROM catalog_items) AS catalog_items,
        (SELECT COALESCE(SUM(quantity), 0) FROM collection_items) AS physical_items,
        (SELECT COUNT(DISTINCT country_id) FROM catalog_items) AS countries,
        (SELECT COUNT(DISTINCT catalog_item_id) FROM collection_items) AS completed_items,
        (SELECT COALESCE(SUM(CASE WHEN category = 'coin_purchase' THEN amount * COALESCE(rate_uah, 1) ELSE 0 END), 0) FROM expenses) AS coin_spend,
        (SELECT COALESCE(SUM(CASE WHEN category <> 'coin_purchase' THEN amount * COALESCE(rate_uah, 1) ELSE 0 END), 0) FROM expenses) AS related_spend,
        (SELECT COALESCE(SUM(
          ci.quantity * COALESCE((
            SELECT CASE WHEN ps.currency_code = 'UAH' THEN ps.price ELSE ps.price * COALESCE((
              SELECT er.rate_uah FROM exchange_rates er WHERE er.currency_code = ps.currency_code ORDER BY er.effective_date DESC LIMIT 1
            ), 0) END
            FROM market_price_snapshots ps WHERE ps.catalog_item_id = ci.catalog_item_id ORDER BY ps.observed_at DESC LIMIT 1
          ), 0)
        ), 0) FROM collection_items ci) AS market_value,
        (SELECT COALESCE(SUM(COALESCE((
          SELECT CASE WHEN ps.currency_code = 'UAH' THEN ps.price ELSE ps.price * COALESCE((
            SELECT er.rate_uah FROM exchange_rates er WHERE er.currency_code = ps.currency_code ORDER BY er.effective_date DESC LIMIT 1
          ), 0) END
          FROM market_price_snapshots ps WHERE ps.catalog_item_id = c.id ORDER BY ps.observed_at DESC LIMIT 1
        ), 0)), 0) FROM catalog_items c WHERE NOT EXISTS (
          SELECT 1 FROM collection_items ci WHERE ci.catalog_item_id = c.id
        )) AS missing_budget,
        (SELECT COUNT(*) FROM catalog_items c WHERE NOT EXISTS (
          SELECT 1 FROM collection_items ci WHERE ci.catalog_item_id = c.id
        ) AND NOT EXISTS (
          SELECT 1 FROM market_price_snapshots ps WHERE ps.catalog_item_id = c.id
        )) AS unpriced_missing
    `).get() as Record<string, number>;

    const catalogItems = Number(counts.catalog_items);
    const completedItems = Number(counts.completed_items);
    const coinSpendUah = Number(counts.coin_spend);
    const relatedSpendUah = Number(counts.related_spend);
    const countryBreakdown = this.database.prepare(`
      SELECT
        co.name_original AS name,
        COUNT(c.id) AS count,
        COUNT(DISTINCT ci.catalog_item_id) AS owned
      FROM catalog_items c
      JOIN countries co ON co.id = c.country_id
      LEFT JOIN collection_items ci ON ci.catalog_item_id = c.id
      GROUP BY co.id, co.name_original
      ORDER BY count DESC, co.name_original ASC
      LIMIT 6
    `).all() as Array<{ name: string; count: number; owned: number }>;
    const seriesBreakdown = this.database.prepare(`
      SELECT
        s.name_original AS name,
        co.name_original AS country,
        COUNT(c.id) AS count,
        COUNT(DISTINCT ci.catalog_item_id) AS owned
      FROM catalog_items c
      JOIN countries co ON co.id = c.country_id
      JOIN coin_series s ON s.id = c.series_id
      LEFT JOIN collection_items ci ON ci.catalog_item_id = c.id
      GROUP BY s.id, s.name_original, co.name_original
      ORDER BY count DESC, s.name_original ASC
      LIMIT 6
    `).all() as Array<{ name: string; country: string; count: number; owned: number }>;

    return {
      catalogItems,
      physicalItems: Number(counts.physical_items),
      countries: Number(counts.countries),
      countryBreakdown: countryBreakdown.map((row) => ({ name: row.name, count: Number(row.count), owned: Number(row.owned) })),
      seriesBreakdown: seriesBreakdown.map((row) => ({ name: row.name, country: row.country, count: Number(row.count), owned: Number(row.owned) })),
      completedItems,
      missingItems: Math.max(0, catalogItems - completedItems),
      completionPercent: catalogItems === 0 ? 0 : Math.round((completedItems / catalogItems) * 1000) / 10,
      coinSpendUah,
      relatedSpendUah,
      totalSpendUah: coinSpendUah + relatedSpendUah,
      marketValueUah: Number(counts.market_value),
      missingBudgetUah: Number(counts.missing_budget),
      unpricedMissingItems: Number(counts.unpriced_missing),
      isEmpty: catalogItems === 0,
    };
  }

  private upsertCountry(name: string): number {
    const normalized = name.trim() || "Без страны";
    const existing = this.database.prepare("SELECT id FROM countries WHERE name_original = ?").get(normalized) as { id: number } | undefined;
    if (existing) return Number(existing.id);
    const result = this.database.prepare("INSERT INTO countries(name_original, name_ru, name_en) VALUES (?, ?, ?)").run(normalized, normalized, normalized);
    return Number(result.lastInsertRowid);
  }

  private upsertDenomination(countryId: number, label: string): number {
    const normalized = label.trim() || "Без номинала";
    const existing = this.database
      .prepare("SELECT id FROM denominations WHERE country_id = ? AND label_original = ?")
      .get(countryId, normalized) as { id: number } | undefined;
    if (existing) return Number(existing.id);
    const result = this.database
      .prepare("INSERT INTO denominations(country_id, label_original, label_ru, label_en) VALUES (?, ?, ?, ?)")
      .run(countryId, normalized, normalized, normalized);
    return Number(result.lastInsertRowid);
  }

  private upsertSeries(countryId: number, name?: string | null): number | null {
    const normalized = name?.trim();
    if (!normalized) return null;
    const existing = this.database
      .prepare("SELECT id FROM coin_series WHERE country_id = ? AND name_original = ?")
      .get(countryId, normalized) as { id: number } | undefined;
    if (existing) return Number(existing.id);
    const yearMatch = normalized.match(/(\d{4})\s*[-–]\s*(\d{4})/);
    const result = this.database
      .prepare("INSERT INTO coin_series(country_id, name_original, name_ru, name_en, start_year, end_year) VALUES (?, ?, ?, ?, ?, ?)")
      .run(countryId, normalized, normalized, normalized, yearMatch ? Number(yearMatch[1]) : null, yearMatch ? Number(yearMatch[2]) : null);
    return Number(result.lastInsertRowid);
  }

  private addPriceSnapshot(catalogItemId: number, price: number, source: string, observedAt = new Date().toISOString(), sourceUrl?: string): void {
    const observedDay = observedAt.slice(0, 10);
    const existingToday = this.database.prepare(`
      SELECT id FROM market_price_snapshots
      WHERE catalog_item_id = ? AND source = ? AND grade IS NULL AND substr(observed_at, 1, 10) = ?
      ORDER BY observed_at DESC
      LIMIT 1
    `).get(catalogItemId, source, observedDay) as { id: number } | undefined;

    if (existingToday) {
      this.database.prepare(`
        UPDATE market_price_snapshots
        SET price = ?, currency_code = 'UAH', observed_at = ?, source_url = ?
        WHERE id = ?
      `).run(price, observedAt, sourceUrl ?? null, existingToday.id);
      if (sourceUrl) this.saveSourceLink(catalogItemId, source, sourceUrl);
      return;
    }

    this.database.prepare(`
      INSERT OR IGNORE INTO market_price_snapshots(catalog_item_id, source, price, currency_code, observed_at, source_url)
      VALUES (?, ?, ?, 'UAH', ?, ?)
    `).run(catalogItemId, source, price, observedAt, sourceUrl ?? null);
    if (sourceUrl) this.saveSourceLink(catalogItemId, source, sourceUrl);
  }

  private saveSourceLink(catalogItemId: number, source: string, sourceUrl?: string | null): void {
    const normalized = sourceUrl?.trim();
    if (!normalized) return;
    this.database.prepare(`
      INSERT INTO price_source_links(catalog_item_id, source, external_id, match_status, matched_at)
      VALUES (?, ?, ?, 'confirmed', CURRENT_TIMESTAMP)
      ON CONFLICT(catalog_item_id, source) DO UPDATE SET
        external_id = excluded.external_id,
        match_status = 'confirmed',
        matched_at = CURRENT_TIMESTAMP
    `).run(catalogItemId, source, normalized);
  }

  private saveCatalogImage(catalogItemId: number, role: "obverse" | "reverse", originalPath?: string | null): void {
    const normalized = originalPath?.trim();
    if (!normalized) return;
    this.database.prepare("DELETE FROM media_files WHERE catalog_item_id = ? AND role = ?").run(catalogItemId, role);
    this.database.prepare(`
      INSERT INTO media_files(catalog_item_id, role, original_path, thumbnail_path)
      VALUES (?, ?, ?, ?)
    `).run(catalogItemId, role, normalized, normalized);
  }

  private applyCatalogExtras(catalogItemId: number, input: CoinInput): void {
    if (input.sourceUrl) {
      const source = input.sourceUrl.includes("ua-coins.info") ? "UA-Coins" : input.sourceUrl.includes("ucoin.net") ? "uCoin" : "Manual";
      this.saveSourceLink(catalogItemId, source, input.sourceUrl);
    }
    this.saveCatalogImage(catalogItemId, "obverse", input.obverseImageUrl);
    this.saveCatalogImage(catalogItemId, "reverse", input.reverseImageUrl);
  }

  private catalogSelect(where = ""): string {
    return `
      SELECT
        c.id,
        co.name_original AS country,
        s.name_original AS seriesName,
        d.label_original AS denomination,
        c.issue_year AS year,
        c.title_original AS title,
        c.subtype AS variety,
        COALESCE(c.catalog_km, c.catalog_uc, c.catalog_numista) AS catalogNumber,
        c.collection_group AS collectionGroup,
        c.material AS material,
        (SELECT ps.price FROM market_price_snapshots ps WHERE ps.catalog_item_id = c.id ORDER BY ps.observed_at DESC LIMIT 1) AS marketPriceUah,
        (SELECT ps.source FROM market_price_snapshots ps WHERE ps.catalog_item_id = c.id ORDER BY ps.observed_at DESC LIMIT 1) AS priceSource,
        (SELECT ps.observed_at FROM market_price_snapshots ps WHERE ps.catalog_item_id = c.id ORDER BY ps.observed_at DESC LIMIT 1) AS priceObservedAt,
        COALESCE((SELECT SUM(ci.quantity) FROM collection_items ci WHERE ci.catalog_item_id = c.id), 0) AS quantityOwned,
        COALESCE((SELECT SUM(ci.quantity * COALESCE(ci.purchase_price, 0) * COALESCE(ci.purchase_rate_uah, 1)) FROM collection_items ci WHERE ci.catalog_item_id = c.id), 0) AS purchaseTotalUah,
        (SELECT COALESCE(m.thumbnail_path, m.original_path) FROM media_files m WHERE m.catalog_item_id = c.id ORDER BY CASE m.role WHEN 'obverse' THEN 0 WHEN 'reverse' THEN 1 ELSE 2 END, m.id DESC LIMIT 1) AS thumbnailPath,
        (SELECT m.original_path FROM media_files m WHERE m.catalog_item_id = c.id AND m.role = 'obverse' ORDER BY m.id DESC LIMIT 1) AS obverseImagePath,
        (SELECT m.original_path FROM media_files m WHERE m.catalog_item_id = c.id AND m.role = 'reverse' ORDER BY m.id DESC LIMIT 1) AS reverseImagePath,
        (SELECT psl.external_id FROM price_source_links psl WHERE psl.catalog_item_id = c.id ORDER BY CASE psl.source WHEN 'uCoin' THEN 0 WHEN 'UA-Coins' THEN 1 ELSE 2 END, psl.id DESC LIMIT 1) AS sourceUrl
      FROM catalog_items c
      JOIN countries co ON co.id = c.country_id
      LEFT JOIN coin_series s ON s.id = c.series_id
      LEFT JOIN denominations d ON d.id = c.denomination_id
      ${where}
    `;
  }

  listCatalog(): CatalogCoin[] {
    return this.database.prepare(`${this.catalogSelect()} ORDER BY co.name_original, c.issue_year DESC, c.title_original`).all() as unknown as CatalogCoin[];
  }

  getCatalogCoin(id: number): CatalogCoin {
    const row = this.database.prepare(this.catalogSelect("WHERE c.id = ?")).get(id) as unknown as CatalogCoin | undefined;
    if (!row) throw new Error("Монета не найдена");
    return row;
  }

  createCoin(input: CoinInput): CatalogCoin {
    this.database.exec("BEGIN IMMEDIATE;");
    try {
      const countryId = this.upsertCountry(input.country);
      const denominationId = this.upsertDenomination(countryId, input.denomination);
      const seriesId = this.upsertSeries(countryId, input.seriesName);
      const catalogNumber = input.catalogNumber?.trim() || null;
      const result = this.database.prepare(`
        INSERT INTO catalog_items(country_id, series_id, denomination_id, collection_group, subtype, title_original, title_ru, title_en, issue_year, catalog_km, material)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        countryId,
        seriesId,
        denominationId,
        input.collectionGroup,
        input.variety?.trim() || null,
        input.title.trim(),
        input.title.trim(),
        input.title.trim(),
        input.year,
        catalogNumber,
        input.material?.trim() || null,
      );
      const id = Number(result.lastInsertRowid);
      this.applyCatalogExtras(id, input);
      if (input.marketPriceUah !== null && input.marketPriceUah !== undefined) {
        this.addPriceSnapshot(id, input.marketPriceUah, input.priceSource || "Manual");
      }
      this.database.exec("COMMIT;");
      return this.getCatalogCoin(id);
    } catch (error) {
      this.database.exec("ROLLBACK;");
      throw error;
    }
  }

  updateCoin(id: number, input: CoinInput): CatalogCoin {
    this.database.exec("BEGIN IMMEDIATE;");
    try {
      this.getCatalogCoin(id);
      const countryId = this.upsertCountry(input.country);
      const denominationId = this.upsertDenomination(countryId, input.denomination);
      const seriesId = this.upsertSeries(countryId, input.seriesName);
      this.database.prepare(`
        UPDATE catalog_items SET country_id = ?, series_id = ?, denomination_id = ?, collection_group = ?, subtype = ?,
          title_original = ?, title_ru = ?, title_en = ?, issue_year = ?, catalog_km = ?, material = COALESCE(?, material), updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
      `).run(
        countryId,
        seriesId,
        denominationId,
        input.collectionGroup,
        input.variety?.trim() || null,
        input.title.trim(),
        input.title.trim(),
        input.title.trim(),
        input.year,
        input.catalogNumber?.trim() || null,
        input.material?.trim() || null,
        id,
      );
      this.applyCatalogExtras(id, input);
      if (input.marketPriceUah !== null && input.marketPriceUah !== undefined) {
        this.addPriceSnapshot(id, input.marketPriceUah, input.priceSource || "Manual");
      }
      this.database.exec("COMMIT;");
      return this.getCatalogCoin(id);
    } catch (error) {
      this.database.exec("ROLLBACK;");
      throw error;
    }
  }

  deleteCoin(id: number): void {
    const owned = this.database.prepare("SELECT COUNT(*) AS count FROM collection_items WHERE catalog_item_id = ?").get(id) as { count: number };
    if (Number(owned.count) > 0) throw new Error("Нельзя удалить монету с покупками. Сначала удалите экземпляры коллекции.");
    const result = this.database.prepare("DELETE FROM catalog_items WHERE id = ?").run(id);
    if (Number(result.changes) === 0) throw new Error("Монета не найдена");
  }

  addPurchase(input: PurchaseInput): CatalogCoin {
    this.getCatalogCoin(input.catalogItemId);
    this.database.exec("BEGIN IMMEDIATE;");
    try {
      const collectionResult = this.database.prepare(`
        INSERT INTO collection_items(catalog_item_id, quantity, acquisition_date, seller, purchase_price, purchase_currency, purchase_rate_uah, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `).run(input.catalogItemId, input.quantity, input.purchaseDate, input.seller ?? null, input.price, "UAH", 1, input.notes ?? null);
      this.database.prepare(`
        INSERT INTO expenses(category, amount, currency_code, rate_uah, expense_date, catalog_item_id, collection_item_id, vendor, description)
        VALUES ('coin_purchase', ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        input.price * input.quantity,
        "UAH",
        1,
        input.purchaseDate,
        input.catalogItemId,
        Number(collectionResult.lastInsertRowid),
        input.seller ?? null,
        input.notes ?? "Покупка монеты",
      );
      this.database.exec("COMMIT;");
      return this.getCatalogCoin(input.catalogItemId);
    } catch (error) {
      this.database.exec("ROLLBACK;");
      throw error;
    }
  }

  listPurchases(catalogItemId: number): PurchaseRecord[] {
    this.getCatalogCoin(catalogItemId);
    return this.database.prepare(`
      SELECT
        ci.id,
        ci.catalog_item_id AS catalogItemId,
        ci.quantity,
        ci.acquisition_date AS purchaseDate,
        ci.seller,
        COALESCE(ci.purchase_price, 0) AS priceUah,
        ci.quantity * COALESCE(ci.purchase_price, 0) * COALESCE(ci.purchase_rate_uah, 1) AS totalUah,
        CASE WHEN (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'USD' AND er.effective_date <= ci.acquisition_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) IS NOT NULL THEN ci.quantity * COALESCE(ci.purchase_price, 0) * COALESCE(ci.purchase_rate_uah, 1) / (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'USD' AND er.effective_date <= ci.acquisition_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) END AS usdAtPurchase,
        CASE WHEN (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'EUR' AND er.effective_date <= ci.acquisition_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) IS NOT NULL THEN ci.quantity * COALESCE(ci.purchase_price, 0) * COALESCE(ci.purchase_rate_uah, 1) / (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'EUR' AND er.effective_date <= ci.acquisition_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) END AS eurAtPurchase,
        ci.notes
      FROM collection_items ci
      WHERE ci.catalog_item_id = ?
      ORDER BY ci.acquisition_date DESC, ci.id DESC
    `).all(catalogItemId) as unknown as PurchaseRecord[];
  }

  listPriceHistory(catalogItemId: number): PriceHistoryRecord[] {
    this.getCatalogCoin(catalogItemId);
    return this.database.prepare(`
      SELECT
        id,
        catalog_item_id AS catalogItemId,
        source,
        price AS priceUah,
        observed_at AS observedAt,
        source_url AS sourceUrl
      FROM market_price_snapshots
      WHERE catalog_item_id = ?
      ORDER BY observed_at DESC, id DESC
    `).all(catalogItemId) as unknown as PriceHistoryRecord[];
  }

  getFinanceSummary(): FinanceSummary {
    const row = this.database.prepare(`
      SELECT
        COALESCE(SUM(amount * COALESCE(rate_uah, 1)), 0) AS coinSpendUah,
        SUM(CASE WHEN (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'USD' AND er.effective_date <= expenses.expense_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) IS NOT NULL THEN amount * COALESCE(rate_uah, 1) / (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'USD' AND er.effective_date <= expenses.expense_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) END) AS coinSpendUsdAtPurchase,
        SUM(CASE WHEN (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'EUR' AND er.effective_date <= expenses.expense_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) IS NOT NULL THEN amount * COALESCE(rate_uah, 1) / (
          SELECT er.rate_uah FROM exchange_rates er
          WHERE er.currency_code = 'EUR' AND er.effective_date <= expenses.expense_date
          ORDER BY er.effective_date DESC LIMIT 1
        ) END) AS coinSpendEurAtPurchase,
        SUM(CASE WHEN NOT EXISTS (
          SELECT 1 FROM exchange_rates er WHERE er.currency_code = 'USD' AND er.effective_date <= expenses.expense_date
        ) THEN 1 ELSE 0 END) AS missingUsd,
        SUM(CASE WHEN NOT EXISTS (
          SELECT 1 FROM exchange_rates er WHERE er.currency_code = 'EUR' AND er.effective_date <= expenses.expense_date
        ) THEN 1 ELSE 0 END) AS missingEur
      FROM expenses
      WHERE category = 'coin_purchase'
    `).get() as Record<string, number | null>;
    const spend = Number(row.coinSpendUah ?? 0);
    return {
      coinSpendUah: spend,
      coinSpendUsdAtPurchase: spend === 0 ? 0 : row.coinSpendUsdAtPurchase === null ? null : Number(row.coinSpendUsdAtPurchase),
      coinSpendEurAtPurchase: spend === 0 ? 0 : row.coinSpendEurAtPurchase === null ? null : Number(row.coinSpendEurAtPurchase),
      purchasesWithoutHistoricalUsdRate: Number(row.missingUsd ?? 0),
      purchasesWithoutHistoricalEurRate: Number(row.missingEur ?? 0),
    };
  }

  private findExistingCatalogItem(country: string, denomination: string, year: number, title: string, catalogNumber?: string | null, sourceKey?: string | null): number | null {
    if (sourceKey) {
      const bySource = this.database.prepare("SELECT id FROM catalog_items WHERE source_key = ?").get(sourceKey) as { id: number } | undefined;
      if (bySource) return Number(bySource.id);
    }
    const byNatural = this.database.prepare(`
      SELECT c.id
      FROM catalog_items c
      JOIN countries co ON co.id = c.country_id
      LEFT JOIN denominations d ON d.id = c.denomination_id
      WHERE co.name_original = ?
        AND d.label_original = ?
        AND c.issue_year = ?
        AND lower(c.title_original) = lower(?)
        AND (? IS NULL OR COALESCE(c.catalog_km, c.catalog_uc, c.catalog_numista) = ?)
      ORDER BY CASE WHEN COALESCE(c.catalog_km, c.catalog_uc, c.catalog_numista) = ? THEN 0 ELSE 1 END, c.id
      LIMIT 1
    `).get(country, denomination, year, title, catalogNumber ?? null, catalogNumber ?? null, catalogNumber ?? null) as { id: number } | undefined;
    return byNatural ? Number(byNatural.id) : null;
  }

  importCatalogRows(rows: ImportedCatalogRow[]): { inserted: number; updated: number; skipped: number } {
    let inserted = 0;
    let updated = 0;
    let skipped = 0;
    this.database.exec("BEGIN IMMEDIATE;");
    try {
      for (const input of rows) {
        const countryId = this.upsertCountry(input.country);
        const denominationId = this.upsertDenomination(countryId, input.denomination);
        const seriesId = this.upsertSeries(countryId, input.seriesName);
        const title = input.title.trim() || `${input.denomination} · ${input.year}`;
        const catalogNumber = input.catalogNumber?.trim() || null;
        const existingId = this.findExistingCatalogItem(input.country, input.denomination, input.year, title, catalogNumber, input.sourceKey);
        if (existingId) {
          this.database.prepare(`
            UPDATE catalog_items SET
              country_id = ?,
              series_id = COALESCE(?, series_id),
              denomination_id = ?,
              collection_group = ?,
              subtype = COALESCE(?, subtype),
              title_original = ?,
              title_ru = ?,
              title_en = ?,
              issue_year = ?,
              catalog_km = COALESCE(?, catalog_km),
              material = COALESCE(?, material),
              source_key = COALESCE(source_key, ?),
              updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
          `).run(
            countryId,
            seriesId,
            denominationId,
            input.collectionGroup,
            input.variety?.trim() || null,
            title,
            title,
            title,
            input.year,
            catalogNumber,
            input.material?.trim() || null,
            input.sourceKey,
            existingId,
          );
          this.applyCatalogExtras(existingId, input);
          if (input.marketPriceUah !== null && input.marketPriceUah !== undefined) {
            this.addPriceSnapshot(existingId, input.marketPriceUah, input.priceSource || "Catalog import", new Date().toISOString(), input.sourceUrl ?? undefined);
          }
          updated += 1;
          continue;
        }
        const result = this.database.prepare(`
          INSERT OR IGNORE INTO catalog_items(
            country_id, series_id, denomination_id, collection_group, subtype, title_original, title_ru, title_en,
            issue_year, catalog_km, source_key, material
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `).run(
          countryId,
          seriesId,
          denominationId,
          input.collectionGroup,
          input.variety?.trim() || null,
          title,
          title,
          title,
          input.year,
          catalogNumber,
          input.sourceKey,
          input.material?.trim() || null,
        );
        if (Number(result.changes) === 0) {
          const existing = this.database.prepare("SELECT id FROM catalog_items WHERE source_key = ?").get(input.sourceKey) as { id: number } | undefined;
          if (existing && seriesId !== null) {
            this.database.prepare("UPDATE catalog_items SET series_id = COALESCE(series_id, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?").run(seriesId, existing.id);
          }
          skipped += 1;
          continue;
        }
        inserted += 1;
        const id = Number(result.lastInsertRowid);
        this.applyCatalogExtras(id, input);
        if (input.marketPriceUah !== null && input.marketPriceUah !== undefined) {
          this.addPriceSnapshot(id, input.marketPriceUah, input.priceSource || "Excel import", new Date().toISOString(), input.sourceUrl ?? undefined);
        }
      }
      this.database.exec("COMMIT;");
      return { inserted, updated, skipped };
    } catch (error) {
      this.database.exec("ROLLBACK;");
      throw error;
    }
  }

  saveExchangeRate(code: "USD" | "EUR", rate: number, effectiveDate: string): void {
    this.database.prepare(`
      INSERT INTO exchange_rates(currency_code, rate_uah, effective_date, fetched_at, source)
      VALUES (?, ?, ?, ?, 'NBU')
      ON CONFLICT(currency_code, effective_date, source) DO UPDATE SET rate_uah = excluded.rate_uah, fetched_at = excluded.fetched_at
    `).run(code, rate, effectiveDate, new Date().toISOString());
  }

  saveMarketPrice(id: number, price: number, source: string, observedAt: string, sourceUrl?: string): CatalogCoin {
    this.getCatalogCoin(id);
    this.addPriceSnapshot(id, price, source, observedAt, sourceUrl);
    return this.getCatalogCoin(id);
  }

  getLatestExchangeRates(): ExchangeRateSummary[] {
    const statement = this.database.prepare(`
      SELECT currency_code AS code, rate_uah AS rate, effective_date AS effectiveDate
      FROM exchange_rates
      WHERE currency_code = ?
      ORDER BY effective_date DESC
      LIMIT 1
    `);

    return (["USD", "EUR"] as const).map((code) => {
      const row = statement.get(code) as { code: "USD" | "EUR"; rate: number; effectiveDate: string } | undefined;
      return row ?? { code, rate: null, effectiveDate: null };
    });
  }

  listMissingExchangeRateDates(startDate: string, endDate: string): string[] {
    const rows = this.database.prepare(`
      WITH required_dates(date_value) AS (
        SELECT ? AS date_value
        UNION
        SELECT substr(acquisition_date, 1, 10) FROM collection_items WHERE acquisition_date IS NOT NULL
        UNION
        SELECT substr(expense_date, 1, 10) FROM expenses WHERE expense_date IS NOT NULL
      )
      SELECT date_value AS date
      FROM required_dates
      WHERE date_value BETWEEN ? AND ?
        AND (
          NOT EXISTS (
            SELECT 1 FROM exchange_rates er
            WHERE er.currency_code = 'USD' AND er.effective_date = date_value AND er.source = 'NBU'
          )
          OR NOT EXISTS (
            SELECT 1 FROM exchange_rates er
            WHERE er.currency_code = 'EUR' AND er.effective_date = date_value AND er.source = 'NBU'
          )
        )
      ORDER BY date_value ASC
    `).all(endDate, startDate, endDate) as Array<{ date: string }>;
    return rows.map((row) => row.date);
  }

  checkpoint(): void {
    this.database.exec("PRAGMA wal_checkpoint(TRUNCATE);");
  }

  createSnapshot(targetPath: string): void {
    this.checkpoint();
    const escapedPath = targetPath.replaceAll("'", "''");
    this.database.exec(`VACUUM INTO '${escapedPath}';`);
  }

  recordBackupStart(archivePath: string): number {
    const result = this.database
      .prepare("INSERT INTO backup_runs(archive_path, status) VALUES (?, 'running')")
      .run(archivePath);
    return Number(result.lastInsertRowid);
  }

  recordBackupComplete(id: number, checksum: string, sizeBytes: number): void {
    this.database
      .prepare("UPDATE backup_runs SET sha256 = ?, size_bytes = ?, status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?")
      .run(checksum, sizeBytes, id);
  }

  recordBackupFailure(id: number, details: string): void {
    this.database
      .prepare("UPDATE backup_runs SET status = 'failed', details = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ?")
      .run(details, id);
  }

  close(): void {
    this.database.close();
  }
}
