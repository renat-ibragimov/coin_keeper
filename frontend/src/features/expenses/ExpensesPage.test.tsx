import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { fetchCurrencies } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut, ExpensePage, ExpensesSummary } from '@/shared/api/types';

import { fetchExpenses, fetchExpensesSummary } from './api';
import { ExpensesPage } from './ExpensesPage';

vi.mock('./api', () => ({
  fetchExpenses: vi.fn(),
  fetchExpensesSummary: vi.fn(),
  createExpense: vi.fn(),
  updateExpense: vi.fn(),
  deleteExpense: vi.fn(),
  PAGE_SIZE: 24,
  ALL_CATEGORIES: ['coin_purchase', 'delivery', 'album', 'holder', 'storage', 'grading'],
}));
vi.mock('@/features/catalog/api', () => ({ fetchCurrencies: vi.fn() }));
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

const EMPTY_LIST: ExpensePage = { items: [], total: 0, page: 1, pageSize: 24 };
const EMPTY_SUMMARY: ExpensesSummary = {
  categories: [],
  totalUah: '0.00',
  coinSpendUah: '0.00',
  relatedSpendUah: '0.00',
};

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <ExpensesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ExpensesPage', () => {
  it('points a user with no coins at all to the catalog instead of the add-expense form', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue(EMPTY_LIST);
    vi.mocked(fetchExpensesSummary).mockResolvedValue(EMPTY_SUMMARY);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(true));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Фінансової історії поки немає')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Додати першу монету' })).toHaveAttribute(
      'href',
      '/catalog',
    );
  });

  it('offers to add an expense by hand once the collection has coins', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue(EMPTY_LIST);
    vi.mocked(fetchExpensesSummary).mockResolvedValue(EMPTY_SUMMARY);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Витрат ще немає')).toBeInTheDocument();
    expect(screen.queryByText('Фінансової історії поки немає')).toBeNull();
  });
});
