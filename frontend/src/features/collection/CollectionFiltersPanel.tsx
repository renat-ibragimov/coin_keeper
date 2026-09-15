import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CoinMaterial, CountryOut, DenominationOut, SeriesOut } from '@/shared/api/types';
import { buildYearList, clampYear, computeYearBounds } from '@/shared/lib/yearRange';
import type { ActiveFilterChip, MultiSelectOption } from '@/shared/ui';
import { Combobox, FiltersShell, Input, MultiSelect, Select } from '@/shared/ui';

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
  materials: CoinMaterial[];
  activeFilters: ActiveFilterChip[];
}

function idOptions(items: { id: number; name: string }[]): MultiSelectOption[] {
  return items.map((item) => ({ value: String(item.id), label: item.name }));
}

function intValues(raw: string[]): number[] {
  return raw.map((value) => Number.parseInt(value, 10)).filter((value) => Number.isFinite(value));
}

export function CollectionFiltersPanel({
  filters,
  update,
  reset,
  countries,
  series,
  seriesLoading,
  denominations,
  materials,
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

  // Bounds for the year fields' suggestion lists: the union of the selected
  // countries' own range among the owner's purchases, or the whole loaded
  // list when none is selected (docs/03). Each field additionally narrows
  // against the other's current value, so "до" never suggests a year before
  // "від" and vice versa. Both fields stay free-text inputs — the list is a
  // suggestion, not a constraint (docs/08-ui-map.md).
  const yearBounds = computeYearBounds(countries, filters.countryIds);
  const yearFromList = buildYearList({
    min: yearBounds.min,
    max: filters.yearTo ?? yearBounds.max,
  });
  const yearToList = buildYearList({
    min: filters.yearFrom ?? yearBounds.min,
    max: yearBounds.max,
  });

  const groupOptions: MultiSelectOption[] = [
    { value: 'circulation', label: t('catalog.typeCirculation') },
    { value: 'commemorative', label: t('catalog.typeCommemorative') },
    { value: 'collector', label: t('catalog.typeCollector') },
    { value: 'other', label: t('catalog.typeOther') },
  ];

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
        <MultiSelect
          label={t('catalog.country')}
          centerLabel
          placeholder={t('catalog.allCountries')}
          options={idOptions(countries)}
          value={filters.countryIds.map(String)}
          onChange={(raw) => {
            const countryIds = intValues(raw);
            const newBounds = computeYearBounds(countries, countryIds);
            update({
              countryIds,
              // A changed country selection invalidates the series,
              // denomination and material chosen under the old one.
              seriesIds: [],
              denominationIds: [],
              materialIds: [],
              // Out-of-range years follow the country instead of silently clearing.
              yearFrom: clampYear(filters.yearFrom, newBounds),
              yearTo: clampYear(filters.yearTo, newBounds),
            });
          }}
        />
      </div>

      <div className={styles.field}>
        <MultiSelect
          label={t('catalog.tableSeries')}
          centerLabel
          placeholder={t('collection.allSeries')}
          options={idOptions(series)}
          value={filters.seriesIds.map(String)}
          disabled={seriesLoading}
          onChange={(raw) => update({ seriesIds: intValues(raw) })}
          searchable
          searchPlaceholder={t('catalog.seriesSearchPlaceholder')}
        />
      </div>

      <div className={styles.yearField}>
        <div className={styles.groupTitle}>{t('catalog.years')}</div>
        <div className={styles.yearRow}>
          <Combobox
            inputMode="numeric"
            options={yearFromList.map(String)}
            placeholder={t('catalog.yearFrom')}
            value={filters.yearFrom !== undefined ? String(filters.yearFrom) : ''}
            onChange={(event) => update({ yearFrom: numberOrUndefined(event.target.value) })}
            aria-label={t('catalog.yearFrom')}
            className={styles.yearInput}
          />
          <span className={styles.yearDash}>—</span>
          <Combobox
            inputMode="numeric"
            options={yearToList.map(String)}
            placeholder={t('catalog.yearTo')}
            value={filters.yearTo !== undefined ? String(filters.yearTo) : ''}
            onChange={(event) => update({ yearTo: numberOrUndefined(event.target.value) })}
            aria-label={t('catalog.yearTo')}
            className={styles.yearInput}
          />
        </div>
      </div>

      <div className={styles.field}>
        <MultiSelect
          label={t('catalog.denomination')}
          centerLabel
          placeholder={t('catalog.anyDenomination')}
          options={denominations.map((d) => ({ value: String(d.id), label: d.label }))}
          value={filters.denominationIds.map(String)}
          onChange={(raw) => update({ denominationIds: intValues(raw) })}
        />
      </div>

      <div className={styles.field}>
        <MultiSelect
          label={t('catalog.type')}
          centerLabel
          placeholder={t('catalog.all')}
          options={groupOptions}
          value={filters.groups}
          onChange={(raw) => update({ groups: raw as CollectionFilters['groups'] })}
        />
      </div>

      <div className={styles.field}>
        <MultiSelect
          label={t('catalog.metal')}
          centerLabel
          placeholder={t('catalog.all')}
          options={materials.map((m) => ({ value: String(m.id), label: m.name }))}
          value={filters.materialIds.map(String)}
          onChange={(raw) => update({ materialIds: intValues(raw) })}
        />
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
