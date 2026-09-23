import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut } from '@/shared/api/types';

import { CatalogPage } from './CatalogPage';
import { fetchCatalog } from './api';

vi.mock('@/features/auth/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: 'user' } }),
}));
vi.mock('./api', () => ({
  fetchCatalog: vi.fn(),
  fetchCountries: vi.fn().mockResolvedValue([]),
  fetchDenominations: vi.fn().mockResolvedValue([]),
  fetchSeries: vi.fn().mockResolvedValue([]),
  fetchCatalogMaterials: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/features/dashboard/api', () => ({ fetchBootstrap: vi.fn() }));

function makeBootstrap(collectionItems: number): BootstrapOut {
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
      defaultGrade: 'UNC',
      showPackagingVariants: false,
      theme: 'system',
      catalogViewMode: 'cards',
      collectionViewMode: 'cards',
      secondaryCurrency: 'USD',
      defaultStorageLocation: null,
      includeSupportingExpenses: true,
    },
    dashboard: {
      catalogItems: 100,
      collectionItems,
      countries: 1,
      completedItems: collectionItems,
      missingItems: 100 - collectionItems,
      completionPercent: collectionItems,
      coinSpendUah: '0.00',
      relatedSpendUah: '0.00',
      totalSpendUah: '0.00',
      marketValueUah: '0.00',
      missingBudgetUah: '0.00',
      unpricedMissingItems: 0,
      countryBreakdown: [],
      seriesBreakdown: [],
      isEmpty: collectionItems === 0,
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

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/catalog']}>
        <Routes>
          <Route path="/catalog" element={<CatalogPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CatalogPage summary tiles', () => {
  it('stays hidden for a signed-in owner whose collection is still empty', async () => {
    vi.mocked(fetchCatalog).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 30 });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(0));
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Каталог монет' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Разом витрачено/ })).toBeNull();
  });

  it('shows the same four tiles as Огляд for an owner with at least one coin', async () => {
    vi.mocked(fetchCatalog).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 30 });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(5));
    renderPage();

    expect(await screen.findByRole('link', { name: /Монет у колекції/ })).toHaveAttribute(
      'href',
      '/collection/coins',
    );
    expect(screen.getByRole('link', { name: /Разом витрачено/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Поточна оцінка/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Різниця/ })).toBeInTheDocument();
  });
});
