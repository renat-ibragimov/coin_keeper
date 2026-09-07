import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { SeriesProgress } from '@/shared/api/types';

import { fetchCountries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut, CountryOut } from '@/shared/api/types';

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

const COUNTRY: CountryOut = {
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
};

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

function renderPage(initialEntries: string[] = ['/']) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={initialEntries}>
        <SeriesListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SeriesListPage', () => {
  it('defaults to "Мої": started series only, hiding the zeroed-out one', async () => {
    vi.mocked(fetchSeriesProgress).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    expect(await screen.findByRole('link', { name: 'Almost' })).toHaveAttribute(
      'href',
      '/collection/series/2',
    );
    expect(screen.getByText('19 з 20')).toBeInTheDocument();
    expect(screen.getAllByText('100 ₴')).toHaveLength(3);
    expect(screen.getAllByText('250 ₴')).toHaveLength(3);
    expect(screen.queryByText('Empty')).toBeNull();
  });

  it('switches to "Усі" and shows every series, including unstarted ones', async () => {
    vi.mocked(fetchSeriesProgress).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    await screen.findByText('Almost');
    expect(screen.queryByText('Empty')).toBeNull();

    await userEvent.click(screen.getByRole('tab', { name: 'Усі' }));
    expect(await screen.findByText('Empty')).toBeInTheDocument();
    expect(screen.getAllByText('100 ₴')).toHaveLength(4);
  });

  it('filters the visible series by name as the user types', async () => {
    vi.mocked(fetchSeriesProgress).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    await screen.findByText('Almost');
    await userEvent.type(screen.getByPlaceholderText('Пошук серії…'), 'alm');

    await waitFor(() => expect(screen.queryByText('Half')).toBeNull());
    expect(screen.getByText('Almost')).toBeInTheDocument();
    expect(screen.queryByText('Done')).toBeNull();
  });

  it('shows a placeholder with a scope switch when nothing is started yet', async () => {
    const notStarted = [progress(1, 'Half', 0, 10), progress(2, 'Almost', 0, 20)];
    vi.mocked(fetchSeriesProgress).mockResolvedValue(notStarted);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    expect(await screen.findByText('Ще не почато жодної серії')).toBeInTheDocument();
    expect(screen.queryByText('Half')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: 'Показати всі серії' }));
    expect(await screen.findByText('Half')).toBeInTheDocument();
    expect(screen.getByText('Almost')).toBeInTheDocument();
  });

  it('shows an onboarding empty state instead of a zeroed-out list', async () => {
    vi.mocked(fetchSeriesProgress).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(true));
    vi.mocked(fetchCountries).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Серій ще немає')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.getByRole('link', { name: 'Додати покупку' })).toHaveAttribute(
      'href',
      '/collection/coins/new',
    );
    expect(screen.queryByText('Almost')).toBeNull();
    expect(screen.queryByText('0 %')).toBeNull();
  });
});
