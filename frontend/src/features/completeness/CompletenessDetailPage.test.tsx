import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => ({ user: { id: 1, role: 'user' } }) }));
import type { CatalogListItem, CompletenessGroup, CountryOut, SeriesOut } from '@/shared/api/types';

import { fetchCountries, fetchSeries } from '../catalog/api';
import { fetchCompletenessGroup, fetchCompletenessItems } from './api';
import { CompletenessDetailPage } from './CompletenessDetailPage';

vi.mock('../catalog/api', async () => {
  const actual = await vi.importActual<typeof import('../catalog/api')>('../catalog/api');
  return { ...actual, fetchCountries: vi.fn(), fetchSeries: vi.fn() };
});
vi.mock('./api', () => ({ fetchCompletenessGroup: vi.fn(), fetchCompletenessItems: vi.fn() }));

function makeSeries(overrides: Partial<SeriesOut> = {}): SeriesOut {
  return {
    id: 5,
    countryId: 1,
    name: '50 State Quarters',
    nameOriginal: '50 State Quarters',
    originalLang: 'en',
    nameUk: null,
    nameUkSource: null,
    nameEn: '50 State Quarters',
    nameEnSource: 'official',
    description: null,
    startYear: 1999,
    endYear: 2008,
    ...overrides,
  };
}

function makeCountry(overrides: Partial<CountryOut> = {}): CountryOut {
  return {
    id: 1,
    code: 'US',
    name: 'США',
    nameOriginal: 'United States',
    originalLang: 'en',
    nameUk: 'США',
    nameEn: 'United States',
    collectVariants: false,
    isActive: true,
    catalogConfirmed: true,
    sortOrder: 100,
    minYear: null,
    maxYear: null,
    ...overrides,
  };
}

function makeGroup(overrides: Partial<CompletenessGroup> = {}): CompletenessGroup {
  return {
    groupBy: 'series',
    value: 5,
    unassigned: false,
    label: '50 State Quarters',
    countryId: 1,
    description: null,
    startYear: 1999,
    endYear: 2008,
    sortOrder: null,
    summary: {
      total: 56,
      owned: 56,
      missing: 0,
      completionPercent: 100,
      purchaseTotalUah: '604.64',
      currentValueUah: '1837.00',
      unpricedMissing: 0,
    },
    ...overrides,
  };
}

function makeItem(overrides: Partial<CatalogListItem> = {}): CatalogListItem {
  return {
    id: 1,
    country: 'США',
    seriesName: '50 State Quarters',
    denomination: {
      id: 1,
      value: '0.250',
      unit: 'cent',
      currencyCode: 'USD',
      label: '25 центів',
    },
    denominationText: null,
    year: 1999,
    title: 'Delaware',
    titleOriginal: 'Delaware',
    originalLang: 'en',
    titleUk: null,
    titleUkSource: null,
    titleEn: null,
    titleEnSource: null,
    variety: null,
    catalogNumber: null,
    collectionGroup: 'commemorative',
    metalKind: 'base',
    composition: null,
    material: null,
    marketPriceUah: null,
    priceSource: null,
    priceObservedAt: null,
    quantityOwned: 1,
    purchaseTotalUah: '250.00',
    purchaseTotalUsd: null,
    purchaseTotalEur: null,
    supportingExpensesUah: null,
    obverseImage: null,
    reverseImage: null,
    thumbnailUrl: null,
    isOwn: true,
    isArchived: false,
    archiveReason: null,
    sourceUrl: null,
    ...overrides,
  };
}

function renderPage(initialEntries: string[] = ['/collection/completeness/series/5']) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route
            path="/collection/completeness/:groupBy/:value"
            element={<CompletenessDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CompletenessDetailPage', () => {
  beforeEach(() => {
    vi.mocked(fetchSeries).mockReset().mockResolvedValue([makeSeries()]);
    vi.mocked(fetchCompletenessGroup).mockReset().mockResolvedValue(makeGroup());
    vi.mocked(fetchCompletenessItems)
      .mockReset()
      .mockResolvedValue({
        items: [makeItem()],
        total: 1,
        page: 1,
        pageSize: 24,
      });
    vi.mocked(fetchCountries).mockReset().mockResolvedValue([makeCountry()]);
  });

  it('offers to open the catalog when the country is confirmed, and shows no notice', async () => {
    renderPage();
    expect(await screen.findByRole('link', { name: 'Відкрити в каталозі' })).toHaveAttribute(
      'href',
      '/catalog?seriesId=5',
    );
    expect(screen.queryByText(/загального каталогу/)).not.toBeInTheDocument();
    // The tiles still render regardless -- this is not what the notice branches on.
    expect(await screen.findByText('Delaware')).toBeInTheDocument();
  });

  it('shows the personal-collection notice instead of the catalog link when the country is not confirmed', async () => {
    vi.mocked(fetchCountries).mockResolvedValue([makeCountry({ catalogConfirmed: false })]);
    renderPage();

    expect(
      await screen.findByText(
        'Цю країну ще не додано до загального каталогу, тому тут показані лише монети з вашої особистої колекції.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Відкрити в каталозі' })).not.toBeInTheDocument();
    // The owner-reported bug: the personal item must still render as a tile.
    expect(await screen.findByText('Delaware')).toBeInTheDocument();
  });

  it('fetches this group only from the ungated completeness-items endpoint, never GET /catalog', async () => {
    renderPage();
    await screen.findByText('Delaware');
    expect(fetchCompletenessItems).toHaveBeenCalledWith('series', { value: 5 }, undefined, 1, 24);
  });

  it('renders a generic header and no series-only chrome for a non-series grouping', async () => {
    vi.mocked(fetchCompletenessGroup).mockResolvedValue(
      makeGroup({
        groupBy: 'year',
        value: 2015,
        label: '2015',
        countryId: null,
        description: null,
        startYear: null,
        endYear: null,
      }),
    );
    renderPage(['/collection/completeness/year/2015']);

    expect(await screen.findByRole('heading', { name: '2015' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Відкрити в каталозі' })).not.toBeInTheDocument();
    expect(screen.queryByText(/загального каталогу/)).not.toBeInTheDocument();
    expect(fetchCompletenessItems).toHaveBeenCalledWith('year', { value: 2015 }, undefined, 1, 24);
  });

  it('resolves the "none" route segment to the unassigned bucket', async () => {
    vi.mocked(fetchCompletenessGroup).mockResolvedValue(
      makeGroup({
        groupBy: 'material',
        value: null,
        unassigned: true,
        label: null,
        countryId: null,
        startYear: null,
        endYear: null,
      }),
    );
    renderPage(['/collection/completeness/material/none']);

    await screen.findByText('Delaware');
    expect(fetchCompletenessItems).toHaveBeenCalledWith(
      'material',
      { unassigned: true },
      undefined,
      1,
      24,
    );
  });
});
