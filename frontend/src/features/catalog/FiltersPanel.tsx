import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CountryOut, DenominationOut, SeriesOut } from '@/shared/api/types';
import { Button, Input, Select, Toggle } from '@/shared/ui';

import type { CatalogFilters } from './useCatalogFilters';
import styles from './FiltersPanel.module.css';

interface FiltersPanelProps {
  filters: CatalogFilters;
  update: (changes: Partial<CatalogFilters>) => void;
  reset: () => void;
  countries: CountryOut[];
  series: SeriesOut[];
  seriesLoading: boolean;
  denominations: DenominationOut[];
}

function Chips<T>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className={styles.chips}>
      {options.map((option, index) => (
        <button
          key={index}
          type="button"
          className={[styles.chip, option.value === value ? styles.chipActive : ''].join(' ')}
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function FiltersPanel({
  filters,
  update,
  reset,
  countries,
  series,
  seriesLoading,
  denominations,
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

  // Second row starts open when a filter it holds is already active, so it is
  // never invisible right after a shared link or F5 restores the URL.
  const [expanded, setExpanded] = useState(
    () =>
      filters.denominationId !== undefined ||
      filters.metalKind !== undefined ||
      filters.scope !== 'all' ||
      filters.archived,
  );

  const numberOrUndefined = (raw: string) => {
    const value = Number.parseInt(raw, 10);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  };

  return (
    <div className={styles.panel}>
      <div className={styles.mainRow}>
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
            value={filters.seriesId ?? ''}
            disabled={seriesLoading}
            onChange={(event) => update({ seriesId: numberOrUndefined(event.target.value) })}
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
            label={t('catalog.type')}
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
            label={t('catalog.availability')}
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

        <Button variant="secondary" onClick={reset} className={styles.resetButton}>
          ↺ {t('catalog.resetFilters')}
        </Button>
      </div>

      <button
        type="button"
        className={styles.moreToggle}
        aria-expanded={expanded}
        onClick={() => setExpanded((current) => !current)}
      >
        {t('catalog.moreFilters')} {expanded ? '▲' : '▼'}
      </button>

      {expanded ? (
        <div className={styles.secondaryRow}>
          <div className={styles.group}>
            <div className={styles.groupTitle}>{t('catalog.denomination')}</div>
            <Select
              value={filters.denominationId ?? ''}
              onChange={(event) =>
                update({ denominationId: numberOrUndefined(event.target.value) })
              }
              aria-label={t('catalog.denomination')}
            >
              <option value="">{t('catalog.anyDenomination')}</option>
              {denominations.map((denomination) => (
                <option key={denomination.id} value={denomination.id}>
                  {denomination.label}
                </option>
              ))}
            </Select>
          </div>

          <div className={styles.group}>
            <div className={styles.groupTitle}>{t('catalog.metal')}</div>
            <Chips
              options={[
                {
                  value: 'precious' as CatalogFilters['metalKind'],
                  label: t('catalog.metalPrecious'),
                },
                { value: 'base' as CatalogFilters['metalKind'], label: t('catalog.metalBase') },
                {
                  value: 'unknown' as CatalogFilters['metalKind'],
                  label: t('catalog.metalUnknown'),
                },
                { value: undefined, label: t('catalog.all') },
              ]}
              value={filters.metalKind}
              onChange={(metalKind) => update({ metalKind })}
            />
          </div>

          <div className={styles.group}>
            <div className={styles.groupTitle}>{t('catalog.scope')}</div>
            <Chips
              options={[
                { value: 'all' as CatalogFilters['scope'], label: t('catalog.scopeAll') },
                { value: 'shared' as CatalogFilters['scope'], label: t('catalog.scopeShared') },
                { value: 'own' as CatalogFilters['scope'], label: t('catalog.scopeOwn') },
              ]}
              value={filters.scope}
              onChange={(scope) => update({ scope })}
            />
          </div>

          <div className={styles.group}>
            <Toggle
              checked={filters.archived}
              onChange={(archived) => update({ archived })}
              label={t('catalog.showArchived')}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
