import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { fetchCountries, fetchSeries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { fetchSeriesProgress } from '@/features/series/api';
import type { BootstrapOut, CollectionPage as CollectionPageOut } from '@/shared/api/types';

import { fetchCollection } from './api';
import { CollectionPage } from './CollectionPage';

vi.mock('./api', () => ({ fetchCollection: vi.fn(), PAGE_SIZE: 24 }));
vi.mock('@/features/catalog/api', () => ({ fetchCountries: vi.fn(), fetchSeries: vi.fn() }));
vi.mock('@/features/dashboard/api', () => ({ fetchBootstrap: vi.fn() }));
vi.mock('@/features/series/api', () => ({ fetchSeriesProgress: vi.fn() }));

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

const EMPTY_PAGE: CollectionPageOut = { items: [], total: 0, page: 1, pageSize: 24 };

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <CollectionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CollectionPage', () => {
  it('shows an onboarding empty state for a user with no coins at all', async () => {
    vi.mocked(fetchCollection).mockResolvedValue(EMPTY_PAGE);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(true));
    vi.mocked(fetchSeriesProgress).mockResolvedValue([]);
    vi.mocked(fetchCountries).mockResolvedValue([]);
    vi.mocked(fetchSeries).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('У вашій колекції ще немає монет')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.queryByPlaceholderText('Пошук у колекції…')).toBeNull();
  });

  it('shows the normal toolbar once the collection has coins', async () => {
    vi.mocked(fetchCollection).mockResolvedValue(EMPTY_PAGE);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchSeriesProgress).mockResolvedValue([]);
    vi.mocked(fetchCountries).mockResolvedValue([]);
    vi.mocked(fetchSeries).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByPlaceholderText('Пошук у колекції…')).toBeInTheDocument();
    expect(screen.queryByText('У вашій колекції ще немає монет')).toBeNull();
  });
});
