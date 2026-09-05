import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { fetchCatalog, fetchCountries, fetchSeries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut, CatalogPage } from '@/shared/api/types';

import { MissingPage } from './MissingPage';

vi.mock('@/features/catalog/api', () => ({
  fetchCatalog: vi.fn(),
  fetchCountries: vi.fn(),
  fetchSeries: vi.fn(),
  PAGE_SIZE: 24,
}));
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
      catalogItems: 1316,
      collectionItems: 0,
      countries: 1,
      completedItems: 0,
      missingItems: 1316,
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

const EMPTY_PAGE: CatalogPage = { items: [], total: 0, page: 1, pageSize: 24 };

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <MissingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MissingPage', () => {
  it('hides the KPIs, filters and list for a user with no coins at all', async () => {
    vi.mocked(fetchCatalog).mockResolvedValue(EMPTY_PAGE);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(true));
    vi.mocked(fetchCountries).mockResolvedValue([]);
    vi.mocked(fetchSeries).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Додайте перші монети')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Знайти першу монету' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.queryByText('1 316')).toBeNull();
    expect(fetchCatalog).not.toHaveBeenCalled();
  });

  it('shows the KPIs and filters once the collection has coins', async () => {
    vi.mocked(fetchCatalog).mockResolvedValue(EMPTY_PAGE);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([]);
    vi.mocked(fetchSeries).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Усього не вистачає')).toBeInTheDocument();
    expect(screen.queryByText('Додайте перші монети')).toBeNull();
  });
});
