import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CountryOut, DenominationOut, SeriesOut } from '@/shared/api/types';
import { buildYearGroups, clampYear, computeYearBounds } from '@/shared/lib/yearRange';
import type { ActiveFilterChip } from '@/shared/ui';
import { FiltersShell, Input, Select } from '@/shared/ui';

import { GRADES } from './grades';
import type { CollectionFilters } from './useCollectionFilters';
import styles from './CollectionFiltersPanel.module.css';

interface CollectionFiltersPanelProps {
  filters: CollectionFilters;
  update: (changes: Partial<CollectionFilters>) => void;
  reset: () => void;
  countries: CountryOut[];
  series: SeriesOut[];
  seriesLoading: boolean;
  denominations: DenominationOut[];
  activeFilters: ActiveFilterChip[];
}

export function CollectionFiltersPanel({
  filters,
  update,
  reset,
  countries,
  series,
  seriesLoading,
  denominations,
  activeFilters,
}: CollectionFiltersPanelProps) {
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

  // Bounds for the year dropdowns: the selected country's own range among
  // the owner's purchases, or the whole loaded list when none is selected
  // (docs/03). Each field additionally narrows against the other's current
  // value, so "до" never offers a year before "від" and vice versa.
  const yearBounds = computeYearBounds(countries, filters.countryId);
  const yearFromGroups = buildYearGroups({
    min: yearBounds.min,
    max: filters.yearTo ?? yearBounds.max,
  });
  const yearToGroups = buildYearGroups({
    min: filters.yearFrom ?? yearBounds.min,
    max: yearBounds.max,
  });

  return (
    <FiltersShell activeFilters={activeFilters} onReset={reset}>
      <div className={styles.search}>
        <Input
          type="search"
          placeholder={t('collection.searchPlaceholder')}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label={t('collection.searchPlaceholder')}
        />
      </div>

      <div className={styles.field}>
        <Select
          label={t('catalog.country')}
          centerLabel
          value={filters.countryId ?? ''}
          onChange={(event) => {
            const countryId = numberOrUndefined(event.target.value);
            const newBounds = computeYearBounds(countries, countryId);
            update({
              countryId,
              // A new country invalidates the series and denomination chosen under the old one.
              seriesId: undefined,
              denominationId: undefined,
              // Out-of-range years follow the country instead of silently clearing.
              yearFrom: clampYear(filters.yearFrom, newBounds),
              yearTo: clampYear(filters.yearTo, newBounds),
            });
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
          <option value="">{t('collection.allSeries')}</option>
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
          <Select
            className={styles.yearSelect}
            value={filters.yearFrom ?? ''}
            onChange={(event) => update({ yearFrom: numberOrUndefined(event.target.value) })}
            aria-label={t('catalog.yearFrom')}
          >
            <option value="">—</option>
            {yearFromGroups.map((group) => (
              <optgroup key={group.decade} label={t('catalog.decade', { decade: group.decade })}>
                {group.years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
          <span className={styles.yearDash}>—</span>
          <Select
            className={styles.yearSelect}
            value={filters.yearTo ?? ''}
            onChange={(event) => update({ yearTo: numberOrUndefined(event.target.value) })}
            aria-label={t('catalog.yearTo')}
          >
            <option value="">—</option>
            {yearToGroups.map((group) => (
              <optgroup key={group.decade} label={t('catalog.decade', { decade: group.decade })}>
                {group.years.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
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
            update({ group: (event.target.value || undefined) as CollectionFilters['group'] })
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
              metalKind: (event.target.value || undefined) as CollectionFilters['metalKind'],
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
          label={t('collection.grade')}
          centerLabel
          value={filters.grade ?? ''}
          onChange={(event) => update({ grade: event.target.value || undefined })}
        >
          <option value="">{t('catalog.all')}</option>
          {GRADES.map((grade) => (
            <option key={grade} value={grade}>
              {grade}
            </option>
          ))}
        </Select>
      </div>
    </FiltersShell>
  );
}
