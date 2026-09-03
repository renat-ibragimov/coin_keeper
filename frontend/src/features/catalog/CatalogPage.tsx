import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import { useDismissable } from '@/shared/lib/useDismissable';
import { Button, EmptyState, ErrorState, Pagination, Select, Skeleton, Tabs } from '@/shared/ui';

import { fetchCatalog, fetchCountries, fetchDenominations, PAGE_SIZE } from './api';
import { CatalogTable } from './CatalogTable';
import { CoinCard } from './CoinCard';
import { FiltersPanel } from './FiltersPanel';
import { SORT_FIELDS, useCatalogFilters } from './useCatalogFilters';
import type { CatalogView, SortField } from './useCatalogFilters';
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

export function CatalogPage() {
  const { t } = useTranslation();
  const { filters, update, reset } = useCatalogFilters();
  const [drawerOpen, setDrawerOpen] = useState(false);
  // The overlay handles the outside press itself; Escape and navigation come from the hook.
  useDismissable(drawerOpen, () => setDrawerOpen(false));

  const catalogQuery = useQuery({
    queryKey: ['catalog', filters],
    queryFn: () => fetchCatalog(filters),
    placeholderData: keepPreviousData,
  });
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: fetchCountries });
  const denominationsQuery = useQuery({
    queryKey: ['denominations', filters.countryId],
    queryFn: () => fetchDenominations(filters.countryId),
  });

  const page = catalogQuery.data;
  const total = page?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const shown = page ? page.items.length + (page.page - 1) * PAGE_SIZE : 0;

  const filtersPanel = (
    <FiltersPanel
      filters={filters}
      update={(changes) => {
        update(changes);
      }}
      reset={reset}
      countries={countriesQuery.data ?? []}
      denominations={denominationsQuery.data ?? []}
    />
  );

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.title}>{t('catalog.title')}</h1>
          <p className={styles.subtitle}>{t('catalog.subtitle')}</p>
        </div>
        <Link to="/catalog/new">
          <Button>+ {t('catalog.addOwn')}</Button>
        </Link>
      </header>

      <div className={styles.layout}>
        <aside className={styles.sidebar}>{filtersPanel}</aside>

        <section className={styles.content}>
          <div className={styles.toolbar}>
            <span className={`${styles.counter} tabular`}>
              {t('pagination.shown', { shown, total })}
            </span>
            <Button
              variant="secondary"
              size="sm"
              className={styles.filtersButton}
              onClick={() => setDrawerOpen(true)}
            >
              ☰ {t('catalog.filters')}
            </Button>
            <Tabs<CatalogView>
              aria-label={t('catalog.viewLabel')}
              options={[
                { value: 'cards', label: t('catalog.viewCards') },
                { value: 'table', label: t('catalog.viewTable') },
                { value: 'map', label: t('catalog.viewMap') },
              ]}
              value={filters.view}
              onChange={(view) => update({ view, page: filters.page })}
            />
            <span className={styles.sortControls}>
              <Select
                value={filters.sort}
                onChange={(event) => update({ sort: event.target.value as SortField })}
                aria-label={t('catalog.sort')}
              >
                {SORT_FIELDS.map((field) => (
                  <option key={field} value={field}>
                    {t(SORT_LABELS[field])}
                  </option>
                ))}
              </Select>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => update({ order: filters.order === 'asc' ? 'desc' : 'asc' })}
                aria-label={
                  filters.order === 'asc' ? t('catalog.orderAsc') : t('catalog.orderDesc')
                }
                title={filters.order === 'asc' ? t('catalog.orderAsc') : t('catalog.orderDesc')}
              >
                {filters.order === 'asc' ? '↑' : '↓'}
              </Button>
            </span>
          </div>

          <p className={styles.priceNote}>ⓘ {t('catalog.priceNote')}</p>

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
            <EmptyState title={t('catalog.emptyTitle')} description={t('catalog.emptyText')} />
          ) : null}

          {page && page.items.length > 0 ? (
            filters.view === 'cards' ? (
              <div className={styles.grid}>
                {page.items.map((item) => (
                  <CoinCard key={item.id} item={item} />
                ))}
              </div>
            ) : filters.view === 'table' ? (
              <CatalogTable items={page.items} filters={filters} update={update} />
            ) : (
              <EmptyState
                icon="🗺"
                title={t('catalog.viewMap')}
                description={t('catalog.mapComingSoon')}
              />
            )
          ) : null}

          <div className={styles.hint}>
            <div>
              <div className={styles.hintTitle}>{t('catalog.notFoundTitle')}</div>
              <div className={styles.hintText}>{t('catalog.notFoundText')}</div>
            </div>
            <div className={styles.hintActions}>
              <Link to="/import">
                <Button variant="secondary">{t('catalog.importUcoin')}</Button>
              </Link>
              <Link to="/catalog/new">
                <Button>+ {t('catalog.createOwn')}</Button>
              </Link>
            </div>
          </div>

          <Pagination
            page={filters.page}
            pageCount={pageCount}
            onChange={(next) => update({ page: next })}
          />
        </section>
      </div>

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
                ✕
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
