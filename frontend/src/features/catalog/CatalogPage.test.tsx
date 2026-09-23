import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut, CatalogSummary } from '@/shared/api/types';

import { CatalogPage } from './CatalogPage';
import { fetchCatalog, fetchCatalogSummary } from './api';

vi.mock('@/features/auth/useAuth', () => ({
  useAuth: () => ({ user: { id: 1, role: 'user' } }),
}));
vi.mock('./api', () => ({
  fetchCatalog: vi.fn(),
  fetchCatalogSummary: vi.fn(),
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

function makeSummary(overrides: Partial<CatalogSummary> = {}): CatalogSummary {
  return {
    total: 100,
    owned: 5,
    missing: 95,
    purchaseTotalUah: '1200.00',
    missingBudgetUah: '45000.00',
    unpricedMissing: 3,
    ...overrides,
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
    expect(screen.queryByText('Є в колекції')).toBeNull();
    expect(fetchCatalogSummary).not.toHaveBeenCalled();
  });

  it("shows the catalog's own four tiles for an owner with at least one coin", async () => {
    vi.mocked(fetchCatalog).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 30 });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(5));
    vi.mocked(fetchCatalogSummary).mockResolvedValue(makeSummary());
    renderPage();

    expect(await screen.findByText('Є в колекції')).toBeInTheDocument();
    expect(screen.getByText('Не вистачає')).toBeInTheDocument();
    expect(screen.getByText('Витрачено на монети')).toBeInTheDocument();
    expect(screen.getByText('Треба докупити')).toBeInTheDocument();
  });

  it('requests the summary scoped to whatever filters are already in the URL', async () => {
    vi.mocked(fetchCatalog).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 30 });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(5));
    vi.mocked(fetchCatalogSummary).mockResolvedValue(makeSummary());

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/catalog?countryId=7']}>
          <Routes>
            <Route path="/catalog" element={<CatalogPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText('Є в колекції');
    expect(fetchCatalogSummary).toHaveBeenCalledWith(expect.objectContaining({ countryIds: [7] }));
  });
});
