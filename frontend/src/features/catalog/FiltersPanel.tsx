import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CountryOut, DenominationOut, SeriesOut } from '@/shared/api/types';
import { Button, Input, Select } from '@/shared/ui';

import type { CatalogFilters } from './useCatalogFilters';
import styles from './FiltersPanel.module.css';

export interface ActiveFilterChip {
  key: string;
  label: string;
  onRemove: () => void;
}

interface FiltersPanelProps {
  filters: CatalogFilters;
  update: (changes: Partial<CatalogFilters>) => void;
  reset: () => void;
  countries: CountryOut[];
  series: SeriesOut[];
  seriesLoading: boolean;
  denominations: DenominationOut[];
  activeFilters: ActiveFilterChip[];
}

export function FiltersPanel({
  filters,
  update,
  reset,
  countries,
  series,
  seriesLoading,
  denominations,
  activeFilters,
}: FiltersPanelProps) {
  const { t } = useTranslation();

  // The search box debounces before touching the URL.
  const [search, setSearch] = useState(filters.q);
  useEffect(() => setSearch(filters.q), [filters.q]);
  useEffect(() => {
    if (search === filters.q) return;
    const timer = setTimeout(() => update({ q: search }), 400);
    return () => clearTimeout(timer);
  }, [search, filters.q, update]);

  const numberOrUndefined = (raw: string) => {
    const value = Number.parseInt(raw, 10);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  };

  return (
    <div className={styles.panel}>
      <div className={styles.fields}>
        <div className={styles.search}>
          <Input
            type="search"
            placeholder={t('catalog.searchPlaceholder')}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label={t('catalog.searchPlaceholder')}
          />
        </div>

        <div className={styles.field}>
          <Select
            label={t('catalog.country')}
            centerLabel
            value={filters.countryId ?? ''}
            onChange={(event) => {
              const countryId = numberOrUndefined(event.target.value);
              // A new country invalidates the series and denomination chosen under the old one.
              update({ countryId, seriesId: undefined, denominationId: undefined });
            }}
          >
            <option value="">{t('catalog.allCountries')}</option>
            {countries.map((country) => (
              <option key={country.id} value={country.id}>
                {country.name}
              </option>
            ))}
          </Select>
        </div>

        <div className={styles.field}>
          <Select
            label={t('catalog.tableSeries')}
            centerLabel
            value={filters.seriesId ?? ''}
            disabled={seriesLoading}
            onChange={(event) => update({ seriesId: numberOrUndefined(event.target.value) })}
            searchable
            searchPlaceholder={t('catalog.seriesSearchPlaceholder')}
          >
            <option value="">{t('catalog.allSeries')}</option>
            {series.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </div>

        <div className={styles.yearField}>
          <div className={styles.groupTitle}>{t('catalog.years')}</div>
          <div className={styles.yearRow}>
            <Input
              type="number"
              inputMode="numeric"
              placeholder={t('catalog.yearFrom')}
              value={filters.yearFrom ?? ''}
              onChange={(event) => update({ yearFrom: numberOrUndefined(event.target.value) })}
              aria-label={t('catalog.yearFrom')}
            />
            <span className={styles.yearDash}>—</span>
            <Input
              type="number"
              inputMode="numeric"
              placeholder={t('catalog.yearTo')}
              value={filters.yearTo ?? ''}
              onChange={(event) => update({ yearTo: numberOrUndefined(event.target.value) })}
              aria-label={t('catalog.yearTo')}
            />
          </div>
        </div>

        <div className={styles.field}>
          <Select
            label={t('catalog.denomination')}
            centerLabel
            value={filters.denominationId ?? ''}
            onChange={(event) => update({ denominationId: numberOrUndefined(event.target.value) })}
          >
            <option value="">{t('catalog.anyDenomination')}</option>
            {denominations.map((denomination) => (
              <option key={denomination.id} value={denomination.id}>
                {denomination.label}
              </option>
            ))}
          </Select>
        </div>

        <div className={styles.field}>
          <Select
            label={t('catalog.type')}
            centerLabel
            value={filters.group ?? ''}
            onChange={(event) =>
              update({ group: (event.target.value || undefined) as CatalogFilters['group'] })
            }
          >
            <option value="">{t('catalog.all')}</option>
            <option value="circulation">{t('catalog.typeCirculation')}</option>
            <option value="commemorative">{t('catalog.typeCommemorative')}</option>
            <option value="collector">{t('catalog.typeCollector')}</option>
          </Select>
        </div>

        <div className={styles.field}>
          <Select
            label={t('catalog.metal')}
            centerLabel
            value={filters.metalKind ?? ''}
            onChange={(event) =>
              update({
                metalKind: (event.target.value || undefined) as CatalogFilters['metalKind'],
              })
            }
          >
            <option value="">{t('catalog.all')}</option>
            <option value="precious">{t('catalog.metalPrecious')}</option>
            <option value="base">{t('catalog.metalBase')}</option>
            <option value="unknown">{t('catalog.metalUnknown')}</option>
          </Select>
        </div>

        <div className={styles.field}>
          <Select
            label={t('catalog.availability')}
            centerLabel
            value={filters.owned === undefined ? '' : String(filters.owned)}
            onChange={(event) => {
              const raw = event.target.value;
              update({ owned: raw === '' ? undefined : raw === 'true' });
            }}
          >
            <option value="">{t('catalog.all')}</option>
            <option value="true">{t('catalog.availabilityOwned')}</option>
            <option value="false">{t('catalog.availabilityMissing')}</option>
          </Select>
        </div>
      </div>

      {activeFilters.length > 0 ? (
        <div className={styles.activeRow}>
          <span className={styles.activeLabel}>{t('catalog.activeFilters')}</span>
          <div className={styles.chips}>
            {activeFilters.map((chip) => (
              <button
                key={chip.key}
                type="button"
                className={styles.chip}
                onClick={chip.onRemove}
                aria-label={`${chip.label} — ${t('catalog.removeFilter')}`}
              >
                {chip.label}
                <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
          <Button variant="secondary" size="sm" onClick={reset} className={styles.resetButton}>
            ↺ {t('catalog.resetFilters')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
