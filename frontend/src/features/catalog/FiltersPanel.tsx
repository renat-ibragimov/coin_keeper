import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CountryOut, DenominationOut } from '@/shared/api/types';
import { Button, Input, Select, Toggle } from '@/shared/ui';

import type { CatalogFilters } from './useCatalogFilters';
import styles from './FiltersPanel.module.css';

interface FiltersPanelProps {
  filters: CatalogFilters;
  update: (changes: Partial<CatalogFilters>) => void;
  reset: () => void;
  countries: CountryOut[];
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

  const numberOrUndefined = (raw: string) => {
    const value = Number.parseInt(raw, 10);
    return Number.isFinite(value) && value > 0 ? value : undefined;
  };

  return (
    <div className={styles.panel}>
      <h2 className={styles.heading}>{t('catalog.filters')}</h2>

      <Input
        type="search"
        placeholder={t('catalog.searchPlaceholder')}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        aria-label={t('catalog.searchPlaceholder')}
      />

      <div className={styles.group}>
        <div className={styles.groupTitle}>{t('catalog.country')}</div>
        <Chips
          options={[
            { value: undefined as number | undefined, label: t('catalog.allCountries') },
            ...countries.map((country) => ({
              value: country.id as number | undefined,
              label: country.name,
            })),
          ]}
          value={filters.countryId}
          onChange={(countryId) => update({ countryId, denominationId: undefined })}
        />
      </div>

      <div className={styles.group}>
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

      <div className={styles.group}>
        <div className={styles.groupTitle}>{t('catalog.denomination')}</div>
        <Select
          value={filters.denominationId ?? ''}
          onChange={(event) => update({ denominationId: numberOrUndefined(event.target.value) })}
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
        <div className={styles.groupTitle}>{t('catalog.type')}</div>
        <Chips
          options={[
            {
              value: 'circulation' as CatalogFilters['group'],
              label: t('catalog.typeCirculation'),
            },
            {
              value: 'commemorative' as CatalogFilters['group'],
              label: t('catalog.typeCommemorative'),
            },
            { value: 'collector' as CatalogFilters['group'], label: t('catalog.typeCollector') },
            { value: undefined, label: t('catalog.all') },
          ]}
          value={filters.group}
          onChange={(group) => update({ group })}
        />
      </div>

      <div className={styles.group}>
        <div className={styles.groupTitle}>{t('catalog.metal')}</div>
        <Chips
          options={[
            { value: 'precious' as CatalogFilters['metalKind'], label: t('catalog.metalPrecious') },
            { value: 'base' as CatalogFilters['metalKind'], label: t('catalog.metalBase') },
            { value: 'unknown' as CatalogFilters['metalKind'], label: t('catalog.metalUnknown') },
            { value: undefined, label: t('catalog.all') },
          ]}
          value={filters.metalKind}
          onChange={(metalKind) => update({ metalKind })}
        />
      </div>

      <div className={styles.group}>
        <div className={styles.groupTitle}>{t('catalog.availability')}</div>
        <Chips
          options={[
            { value: true as boolean | undefined, label: t('catalog.availabilityOwned') },
            { value: false as boolean | undefined, label: t('catalog.availabilityMissing') },
            { value: undefined, label: t('catalog.all') },
          ]}
          value={filters.owned}
          onChange={(owned) => update({ owned })}
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

      <Button variant="secondary" block onClick={reset}>
        ↺ {t('catalog.resetFilters')}
      </Button>
    </div>
  );
}
