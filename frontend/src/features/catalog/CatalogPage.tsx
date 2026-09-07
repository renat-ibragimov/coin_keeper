import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { SearchX, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/shared/api/client';
import { useDismissable } from '@/shared/lib/useDismissable';
import type { ActiveFilterChip } from '@/shared/ui';
import {
  Button,
  EmptyState,
  ErrorState,
  FiltersToolbar,
  GridIcon,
  PageHeader,
  Pagination,
  Skeleton,
  TableIcon,
} from '@/shared/ui';

import { fetchCatalog, fetchCountries, fetchDenominations, fetchSeries } from './api';
import { CatalogTable } from './CatalogTable';
import { CoinCard } from './CoinCard';
import { FiltersPanel } from './FiltersPanel';
import { SORT_FIELDS, useCatalogFilters } from './useCatalogFilters';
import type { CatalogFilters, CatalogView, SortField } from './useCatalogFilters';
import styles from './CatalogPage.module.css';

const SORT_LABELS: Record<SortField, string> = {
  country: 'catalog.sortCountry',
  title: 'catalog.sortTitle',
  series: 'catalog.sortSeries',
  year: 'catalog.sortYear',
  denomination: 'catalog.sortDenomination',
  owned: 'catalog.sortOwned',
  purchase: 'catalog.sortPurchase',
  price: 'catalog.sortPrice',
};

const GROUP_LABELS: Record<NonNullable<CatalogFilters['group']>, string> = {
  circulation: 'catalog.typeCirculation',
  commemorative: 'catalog.typeCommemorative',
  collector: 'catalog.typeCollector',
  other: 'catalog.typeOther',
};

const METAL_LABELS: Record<NonNullable<CatalogFilters['metalKind']>, string> = {
  precious: 'catalog.metalPrecious',
  base: 'catalog.metalBase',
  unknown: 'catalog.metalUnknown',
};

// A multiple of every column count the grid uses (1/2/3/5, see
// CatalogPage.module.css), so a full page always fills complete rows instead
// of stranding a short one before the pager.
const GRID_PAGE_SIZE = 30;

export function CatalogPage() {
  const { t } = useTranslation();
  const { filters, update, reset } = useCatalogFilters();
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The overlay handles the outside press itself; Escape and navigation come from the hook.
  useDismissable(drawerOpen, () => setDrawerOpen(false));

  const catalogQuery = useQuery({
    queryKey: ['catalog', filters, GRID_PAGE_SIZE],
    queryFn: () => fetchCatalog(filters, GRID_PAGE_SIZE),
    placeholderData: keepPreviousData,
  });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: () => fetchCountries() });
  const denominationsQuery = useQuery({
    queryKey: ['denominations', filters.countryId],
    queryFn: () => fetchDenominations(filters.countryId),
  });
  const seriesQuery = useQuery({
    queryKey: ['series', 'catalog', filters.countryId],
    queryFn: () => fetchSeries(filters.countryId),
  });

  // The same series list already fetched for the "Серія" filter, keyed by
  // its display name so the card's series line can link to it without a
  // seriesId field on CatalogListItem or an extra request per card.
  const seriesIdByName = useMemo(
    () => Object.fromEntries((seriesQuery.data ?? []).map((series) => [series.name, series.id])),
    [seriesQuery.data],
  );

  const page = catalogQuery.data;
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / GRID_PAGE_SIZE));
  const shown = page ? page.items.length + (page.page - 1) * GRID_PAGE_SIZE : 0;

  const activeChips = useMemo(() => {
    const chips: ActiveFilterChip[] = [];
    if (filters.q) {
      chips.push({ key: 'q', label: filters.q, onRemove: () => update({ q: '' }) });
    }
    if (filters.countryId !== undefined) {
      const country = (countriesQuery.data ?? []).find((c) => c.id === filters.countryId);
      if (country) {
        chips.push({
          key: 'country',
          label: country.name,
          onRemove: () =>
            update({ countryId: undefined, seriesId: undefined, denominationId: undefined }),
        });
      }
    }
    if (filters.seriesId !== undefined) {
      const series = (seriesQuery.data ?? []).find((s) => s.id === filters.seriesId);
      if (series) {
        chips.push({
          key: 'series',
          label: series.name,
          onRemove: () => update({ seriesId: undefined }),
        });
      }
    }
    if (filters.yearFrom !== undefined || filters.yearTo !== undefined) {
      chips.push({
        key: 'years',
        label: `${t('catalog.years')}: ${filters.yearFrom ?? '…'}–${filters.yearTo ?? '…'}`,
        onRemove: () => update({ yearFrom: undefined, yearTo: undefined }),
      });
    }
    if (filters.denominationId !== undefined) {
      const denomination = (denominationsQuery.data ?? []).find(
        (d) => d.id === filters.denominationId,
      );
      if (denomination) {
        chips.push({
          key: 'denomination',
          label: denomination.label,
          onRemove: () => update({ denominationId: undefined }),
        });
      }
    }
    if (filters.group) {
      chips.push({
        key: 'group',
        label: t(GROUP_LABELS[filters.group]),
        onRemove: () => update({ group: undefined }),
      });
    }
    if (filters.metalKind) {
      chips.push({
        key: 'metal',
        label: t(METAL_LABELS[filters.metalKind]),
        onRemove: () => update({ metalKind: undefined }),
      });
    }
    if (filters.owned !== undefined) {
      chips.push({
        key: 'owned',
        label: t(filters.owned ? 'catalog.availabilityOwned' : 'catalog.availabilityMissing'),
        onRemove: () => update({ owned: undefined }),
      });
    }
    return chips;
  }, [filters, countriesQuery.data, seriesQuery.data, denominationsQuery.data, update, t]);

  const filtersPanel = (
    <FiltersPanel
      filters={filters}
      update={(changes) => {
        update(changes);
      }}
      reset={reset}
      countries={countriesQuery.data ?? []}
      series={seriesQuery.data ?? []}
      seriesLoading={seriesQuery.isLoading}
      denominations={denominationsQuery.data ?? []}
      activeFilters={activeChips}
    />
  );

  return (
    <div className={styles.page}>
      <PageHeader align="center" title={t('catalog.title')} subtitle={t('catalog.subtitle')} />

      <div className={styles.filtersBar}>{filtersPanel}</div>

      <section className={styles.content}>
        <FiltersToolbar<CatalogView>
          shown={shown}
          total={total}
          view={filters.view}
          viewOptions={[
            {
              value: 'cards',
              label: (
                <>
                  <GridIcon />
                  {t('catalog.viewCards')}
                </>
              ),
            },
            {
              value: 'table',
              label: (
                <>
                  <TableIcon />
                  {t('catalog.viewTable')}
                </>
              ),
            },
          ]}
          onViewChange={(view) => update({ view, page: filters.page })}
          sort={filters.sort}
          sortOptions={SORT_FIELDS.map((field) => ({ value: field, label: t(SORT_LABELS[field]) }))}
          onSortChange={(sort) => update({ sort: sort as SortField })}
          order={filters.order}
          onOrderChange={() => update({ order: filters.order === 'asc' ? 'desc' : 'asc' })}
          onOpenFilters={() => setDrawerOpen(true)}
        />

        {catalogQuery.isError ? (
          <ErrorState
            detail={
              catalogQuery.error instanceof ApiError && catalogQuery.error.status === 0
                ? t('errors.network')
                : undefined
            }
            onRetry={() => void catalogQuery.refetch()}
          />
        ) : null}

        {catalogQuery.isPending ? (
          <div className={styles.grid}>
            {Array.from({ length: 8 }, (_, index) => (
              <Skeleton key={index} height={280} />
            ))}
          </div>
        ) : null}

        {page && page.items.length === 0 ? (
          <EmptyState
            icon={<SearchX strokeWidth={1.75} />}
            title={t('catalog.emptyTitle')}
            description={t('catalog.emptyText')}
          />
        ) : null}

        {page && page.items.length > 0 ? (
          filters.view === 'cards' ? (
            <div className={styles.grid}>
              {page.items.map((item) => (
                <CoinCard key={item.id} item={item} seriesIdByName={seriesIdByName} />
              ))}
            </div>
          ) : (
            <CatalogTable items={page.items} filters={filters} update={update} />
          )
        ) : null}

        <Pagination
          page={filters.page}
          pageCount={pageCount}
          onChange={(next) => update({ page: next })}
        />
      </section>

      {drawerOpen ? (
        <div className={styles.drawerOverlay} onClick={() => setDrawerOpen(false)}>
          <div
            className={styles.drawer}
            role="dialog"
            aria-label={t('catalog.filters')}
            onClick={(event) => event.stopPropagation()}
          >
            <div className={styles.drawerHeader}>
              <button
                type="button"
                className={styles.drawerClose}
                onClick={() => setDrawerOpen(false)}
                aria-label={t('catalog.closeFilters')}
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>
            {filtersPanel}
            <Button block onClick={() => setDrawerOpen(false)}>
              {t('catalog.applyFilters')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
