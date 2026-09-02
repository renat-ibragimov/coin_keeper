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
      , source_key TEXT, metal_kind TEXT CHECK (metal_kind IN ('precious', 'base', 'unknown')));

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
      , is_for_sale INTEGER NOT NULL DEFAULT 0 CHECK (is_for_sale IN (0, 1)));

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

CREATE TABLE sales (
                      id INTEGER PRIMARY KEY,
                      collection_item_id INTEGER NOT NULL REFERENCES collection_items(id) ON DELETE RESTRICT,
                      catalog_item_id INTEGER NOT NULL REFERENCES catalog_items(id) ON DELETE RESTRICT,
                      quantity INTEGER NOT NULL CHECK (quantity > 0),
                      sale_date TEXT NOT NULL,
                      buyer TEXT,
                      sale_price REAL NOT NULL CHECK (sale_price >= 0),
                      sale_currency TEXT NOT NULL DEFAULT 'UAH' REFERENCES currencies(code),
                      sale_rate_uah REAL NOT NULL DEFAULT 1,
                      notes TEXT,
                      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );

CREATE TABLE schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value_json TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
      );

CREATE TABLE ucoin_catalog_sources (
                      id INTEGER PRIMARY KEY,
                      title TEXT NOT NULL,
                      url TEXT NOT NULL UNIQUE,
                      country TEXT,
                      collection_group TEXT,
                      last_import_at TEXT,
                      last_scanned INTEGER NOT NULL DEFAULT 0,
                      last_inserted INTEGER NOT NULL DEFAULT 0,
                      last_updated INTEGER NOT NULL DEFAULT 0,
                      last_skipped INTEGER NOT NULL DEFAULT 0,
                      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );

CREATE INDEX idx_catalog_items_catalog_numbers ON catalog_items(catalog_km, catalog_uc, catalog_numista);

CREATE INDEX idx_catalog_items_country_year ON catalog_items(country_id, issue_year);

CREATE INDEX idx_catalog_items_series ON catalog_items(series_id);

CREATE UNIQUE INDEX idx_catalog_items_source_key ON catalog_items(source_key) WHERE source_key IS NOT NULL;

CREATE INDEX idx_collection_items_catalog ON collection_items(catalog_item_id);

CREATE UNIQUE INDEX idx_countries_name_original ON countries(name_original);

CREATE INDEX idx_market_price_latest ON market_price_snapshots(catalog_item_id, observed_at DESC);

CREATE INDEX idx_purchase_offers_catalog_item
                      ON purchase_offers(catalog_item_id, found_at DESC, id DESC);

CREATE INDEX idx_sales_catalog_item ON sales(catalog_item_id, sale_date DESC, id DESC);

CREATE INDEX idx_sales_collection_item ON sales(collection_item_id, sale_date DESC, id DESC);

