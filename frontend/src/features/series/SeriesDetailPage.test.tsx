import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CatalogListItem, CountryOut, SeriesOut } from '@/shared/api/types';

import { fetchCountries, fetchSeries } from '../catalog/api';
import { fetchSeriesItems, fetchSeriesSummary } from './api';
import { SeriesDetailPage } from './SeriesDetailPage';

vi.mock('../catalog/api', async () => {
  const actual = await vi.importActual<typeof import('../catalog/api')>('../catalog/api');
  return { ...actual, fetchCountries: vi.fn(), fetchSeries: vi.fn() };
});
vi.mock('./api', () => ({ fetchSeriesItems: vi.fn(), fetchSeriesSummary: vi.fn() }));

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

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/collection/series/5']}>
        <Routes>
          <Route path="/collection/series/:id" element={<SeriesDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SeriesDetailPage', () => {
  beforeEach(() => {
    vi.mocked(fetchSeries).mockReset().mockResolvedValue([makeSeries()]);
    vi.mocked(fetchSeriesSummary).mockReset().mockResolvedValue({
      total: 56,
      owned: 56,
      missing: 0,
      completionPercent: 100,
      purchaseTotalUah: '604.64',
      currentValueUah: '1837.00',
      unpricedMissing: 0,
    });
    vi.mocked(fetchSeriesItems)
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

  it('fetches this series only from the ungated series-items endpoint, never GET /catalog', async () => {
    renderPage();
    await screen.findByText('Delaware');
    expect(fetchSeriesItems).toHaveBeenCalledWith(5, 1, 24);
  });
});
