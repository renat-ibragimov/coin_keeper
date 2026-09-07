import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { fetchCurrencies } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut, ExpenseOut, ExpensePage, ExpensesSummary } from '@/shared/api/types';
import { ThemeContext } from '@/shared/theme/themeContext';

import { fetchExpenses, fetchExpensesSummary } from './api';
import { ExpensesPage } from './ExpensesPage';

// recharts measures its container through ResizeObserver + getBoundingClientRect,
// neither of which jsdom implements; stub both so the charts actually render.
beforeEach(() => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: 600,
    height: 300,
    top: 0,
    left: 0,
    bottom: 300,
    right: 600,
    x: 0,
    y: 0,
    toJSON() {
      return {};
    },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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
  byMonth: [],
  byCategory: [],
  thisMonthUah: '0.00',
  prevMonthUah: '0.00',
};

function renderPage() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {/* jsdom has no matchMedia, so the theme is provided directly rather than via ThemeProvider. */}
      <ThemeContext.Provider value={{ theme: 'light', toggleTheme: () => {} }}>
        <MemoryRouter>
          <ExpensesPage />
        </MemoryRouter>
      </ThemeContext.Provider>
    </QueryClientProvider>,
  );
}

function monthKey(offsetFromToday: number): string {
  const date = new Date();
  date.setDate(1);
  date.setMonth(date.getMonth() + offsetFromToday);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function makeByMonth(thisMonthCoins: string, prevMonthSupporting: string) {
  return Array.from({ length: 12 }, (_, index) => {
    const offset = index - 11;
    return {
      month: monthKey(offset),
      coinsUah: offset === 0 ? thisMonthCoins : '0.00',
      supportingUah: offset === -1 ? prevMonthSupporting : '0.00',
    };
  });
}

function makeExpense(overrides: Partial<ExpenseOut>): ExpenseOut {
  return {
    id: 1,
    category: 'album',
    amount: '100.00',
    currencyCode: 'UAH',
    rateUah: '1',
    amountUah: '100.00',
    expenseDate: '2024-01-01',
    catalogItemId: null,
    collectionItemId: null,
    seriesId: null,
    vendor: null,
    description: null,
    coinTitle: null,
    ...overrides,
  };
}

describe('ExpensesPage', () => {
  it('points a user with no coins at all to the catalog instead of the add-expense form', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue(EMPTY_LIST);
    vi.mocked(fetchExpensesSummary).mockResolvedValue(EMPTY_SUMMARY);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(true));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Фінансової історії поки немає')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.getByRole('link', { name: 'Додати покупку' })).toHaveAttribute(
      'href',
      '/collection/coins/new',
    );
    // No header action, zero-value KPI tiles, charts or category chips above the empty state.
    expect(screen.queryByRole('button', { name: /Додати витрату/ })).toBeNull();
    expect(screen.queryByText('Разом на хобі')).toBeNull();
    expect(screen.queryByText('Витрати за місяцями')).toBeNull();
    expect(screen.queryByText('Усі категорії')).toBeNull();
  });

  it('offers to add an expense by hand once the collection has coins', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue(EMPTY_LIST);
    vi.mocked(fetchExpensesSummary).mockResolvedValue(EMPTY_SUMMARY);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Витрат ще немає')).toBeInTheDocument();
    expect(screen.queryByText('Фінансової історії поки немає')).toBeNull();
    // The header action stays (plus this empty state's own inline CTA),
    // since the collection itself isn't empty.
    expect(screen.getAllByRole('button', { name: /Додати витрату/ })).toHaveLength(2);
  });

  it('shows the "this month" tile with a delta against last month', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue({
      items: [makeExpense({ id: 1 })],
      total: 1,
      page: 1,
      pageSize: 24,
    });
    vi.mocked(fetchExpensesSummary).mockResolvedValue({
      categories: [{ category: 'album', count: 1, totalUah: '100.00' }],
      totalUah: '100.00',
      coinSpendUah: '0.00',
      relatedSpendUah: '100.00',
      byMonth: makeByMonth('0.00', '50.00'),
      byCategory: [{ category: 'album', count: 1, totalUah: '100.00' }],
      thisMonthUah: '300.00',
      prevMonthUah: '50.00',
    });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Цього місяця')).toBeInTheDocument();
    expect(screen.getByText('300 ₴')).toBeInTheDocument();
    expect(screen.getByText('+250 ₴ до минулого місяця')).toBeInTheDocument();
  });

  it('says there was no spending last month when the previous month is empty', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue({
      items: [makeExpense({ id: 1 })],
      total: 1,
      page: 1,
      pageSize: 24,
    });
    vi.mocked(fetchExpensesSummary).mockResolvedValue({
      categories: [{ category: 'album', count: 1, totalUah: '100.00' }],
      totalUah: '100.00',
      coinSpendUah: '0.00',
      relatedSpendUah: '100.00',
      byMonth: makeByMonth('80.00', '0.00'),
      byCategory: [{ category: 'album', count: 1, totalUah: '100.00' }],
      thisMonthUah: '80.00',
      prevMonthUah: '0.00',
    });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('минулого місяця витрат не було')).toBeInTheDocument();
  });

  it('links a coin_purchase row to the coin, falling back when there is no title', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue({
      items: [
        makeExpense({
          id: 1,
          category: 'coin_purchase',
          catalogItemId: 5,
          coinTitle: 'Дельфін',
          amountUah: '300.00',
        }),
        makeExpense({
          id: 2,
          category: 'coin_purchase',
          catalogItemId: 7,
          coinTitle: null,
          amountUah: '120.00',
        }),
        makeExpense({
          id: 3,
          category: 'album',
          description: 'Альбом для монет',
          vendor: 'Rozetka',
        }),
      ],
      total: 3,
      page: 1,
      pageSize: 24,
    });
    vi.mocked(fetchExpensesSummary).mockResolvedValue({
      categories: [
        { category: 'coin_purchase', count: 2, totalUah: '420.00' },
        { category: 'album', count: 1, totalUah: '100.00' },
      ],
      totalUah: '520.00',
      coinSpendUah: '420.00',
      relatedSpendUah: '100.00',
      byMonth: makeByMonth('300.00', '50.00'),
      byCategory: [
        { category: 'coin_purchase', count: 2, totalUah: '420.00' },
        { category: 'album', count: 1, totalUah: '100.00' },
      ],
      thisMonthUah: '300.00',
      prevMonthUah: '50.00',
    });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByRole('link', { name: 'Дельфін' })).toHaveAttribute(
      'href',
      '/catalog/5',
    );
    expect(screen.getByRole('link', { name: 'з покупки монети' })).toHaveAttribute(
      'href',
      '/catalog/7',
    );

    // The right-hand actions column no longer repeats "з покупки монети" for these rows.
    expect(screen.getAllByText('з покупки монети')).toHaveLength(1);
    expect(screen.getByText('Редагувати')).toBeInTheDocument();
    expect(screen.getByText('Видалити')).toBeInTheDocument();
  });

  it('renders the month and category charts once there is data', async () => {
    vi.mocked(fetchExpenses).mockResolvedValue({
      items: [
        makeExpense({
          id: 1,
          category: 'coin_purchase',
          catalogItemId: 5,
          coinTitle: 'Дельфін',
          amountUah: '300.00',
        }),
        makeExpense({ id: 2, category: 'album', amountUah: '100.00' }),
      ],
      total: 2,
      page: 1,
      pageSize: 24,
    });
    vi.mocked(fetchExpensesSummary).mockResolvedValue({
      categories: [
        { category: 'coin_purchase', count: 1, totalUah: '300.00' },
        { category: 'album', count: 1, totalUah: '100.00' },
      ],
      totalUah: '400.00',
      coinSpendUah: '300.00',
      relatedSpendUah: '100.00',
      byMonth: makeByMonth('300.00', '50.00'),
      byCategory: [
        { category: 'coin_purchase', count: 1, totalUah: '300.00' },
        { category: 'album', count: 1, totalUah: '100.00' },
      ],
      thisMonthUah: '300.00',
      prevMonthUah: '50.00',
    });
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCurrencies).mockResolvedValue([]);
    const { container } = renderPage();

    expect(await screen.findByText('Витрати за місяцями')).toBeInTheDocument();
    expect(screen.getByText('За категоріями')).toBeInTheDocument();
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-surface').length).toBeGreaterThanOrEqual(2);
    });
    // The category donut's legend is plain markup, independent of chart measurement.
    const categoryCard = container.querySelector('[aria-label="За категоріями"]');
    expect(categoryCard?.textContent).toContain('Покупка монети');
    expect(categoryCard?.textContent).toContain('Альбоми');
  });
});
