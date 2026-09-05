import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { SeriesProgress } from '@/shared/api/types';

import { fetchCountries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut } from '@/shared/api/types';

import { fetchSeriesProgress } from './api';
import { SeriesListPage } from './SeriesListPage';
import { sortSeries } from './sort';

vi.mock('./api', () => ({ fetchSeriesProgress: vi.fn(), fetchSeriesSummary: vi.fn() }));
vi.mock('@/features/catalog/api', () => ({ fetchCountries: vi.fn() }));
vi.mock('@/features/dashboard/api', () => ({ fetchBootstrap: vi.fn() }));

function makeBootstrap(isEmpty: boolean): BootstrapOut {
  return {
    user: {
      id: 1,
      email: 'owner@example.com',
      displayName: null,
      role: 'user',
      locale: 'uk',
      emailVerified: true,
    },
    settings: {
      locale: 'uk',
      displayCurrency: 'UAH',
      defaultGradeCommemorative: 'UNC',
      defaultGradeCirculation: 'VF',
    },
    dashboard: {
      catalogItems: 0,
      collectionItems: 0,
      countries: 0,
      completedItems: 0,
      missingItems: 0,
      completionPercent: 0,
      coinSpendUah: '0.00',
      relatedSpendUah: '0.00',
      totalSpendUah: '0.00',
      marketValueUah: '0.00',
      missingBudgetUah: '0.00',
      unpricedMissingItems: 0,
      countryBreakdown: [],
      seriesBreakdown: [],
      isEmpty,
    },
    exchangeRates: [],
    finance: {
      coinSpendUah: '0.00',
      coinSpendUsdAtPurchase: null,
      coinSpendEurAtPurchase: null,
      purchasesWithoutHistoricalUsdRate: 0,
      purchasesWithoutHistoricalEurRate: 0,
    },
  };
}

function progress(id: number, name: string, owned: number, total: number): SeriesProgress {
  return {
    series: {
      id,
      countryId: 1,
      name,
      nameOriginal: name,
      originalLang: 'uk',
      nameUk: null,
      nameUkSource: null,
      nameEn: null,
      nameEnSource: null,
      description: null,
      startYear: null,
      endYear: null,
    },
    summary: {
      total,
      owned,
      missing: total - owned,
      completionPercent: total ? Math.round((owned / total) * 1000) / 10 : 0,
      purchaseTotalUah: '100.00',
      currentValueUah: '250.00',
      unpricedMissing: total - owned > 0 ? 1 : 0,
    },
  };
}

const ROWS = [
  progress(1, 'Half', 5, 10),
  progress(2, 'Almost', 19, 20),
  progress(3, 'Done', 3, 3),
  progress(4, 'Empty', 0, 0),
];

describe('sortSeries', () => {
  it('puts the most complete series first and can sort by name', () => {
    expect(sortSeries(ROWS, 'completion').map((row) => row.series.name)).toEqual([
      'Done',
      'Almost',
      'Half',
      'Empty',
    ]);
    expect(sortSeries(ROWS, 'name').map((row) => row.series.name)).toEqual([
      'Almost',
      'Done',
      'Empty',
      'Half',
    ]);
  });
});

describe('SeriesListPage', () => {
  it('renders every series with its progress, spend and valuation', async () => {
    vi.mocked(fetchSeriesProgress).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([
      {
        id: 1,
        code: 'UA',
        name: 'Україна',
        nameOriginal: 'Україна',
        originalLang: 'uk',
        nameUk: 'Україна',
        nameEn: 'Ukraine',
        collectVariants: false,
        isActive: true,
        sortOrder: 0,
      },
    ]);
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <SeriesListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('link', { name: 'Almost' })).toHaveAttribute(
      'href',
      '/collection/series/2',
    );
    expect(screen.getByText('19 з 20')).toBeInTheDocument();
    expect(screen.getAllByText('100 ₴')).toHaveLength(4);
    expect(screen.getAllByText('250 ₴')).toHaveLength(4);
    expect(screen.getAllByText('Україна').length).toBeGreaterThan(0);
  });

  it('shows an onboarding empty state instead of a zeroed-out list', async () => {
    vi.mocked(fetchSeriesProgress).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(true));
    vi.mocked(fetchCountries).mockResolvedValue([]);
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <SeriesListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Серій ще немає')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.queryByText('Almost')).toBeNull();
    expect(screen.queryByText('0 %')).toBeNull();
  });
});
