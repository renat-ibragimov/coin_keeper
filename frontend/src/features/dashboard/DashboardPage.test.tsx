import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { BootstrapOut } from '@/shared/api/types';

import { fetchBootstrap } from './api';
import { DashboardPage } from './DashboardPage';

vi.mock('./api', () => ({ fetchBootstrap: vi.fn() }));

function makeBootstrap(overrides: Partial<BootstrapOut['dashboard']> = {}): BootstrapOut {
  return {
    user: {
      id: 1,
      email: 'owner@example.com',
      displayName: 'Renat',
      role: 'admin',
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
      catalogItems: 3063,
      collectionItems: 620,
      countries: 12,
      completedItems: 590,
      missingItems: 2473,
      completionPercent: 19.3,
      coinSpendUah: '42000.00',
      relatedSpendUah: '765.66',
      totalSpendUah: '42765.66',
      marketValueUah: '50000.00',
      missingBudgetUah: '120000.00',
      unpricedMissingItems: 41,
      countryBreakdown: [{ name: 'Україна', count: 1200, owned: 590 }],
      seriesBreakdown: [
        { id: 11, name: 'Флора і фауна', country: 'Україна', count: 20, owned: 19 },
        { id: 12, name: 'Готово', country: 'Україна', count: 3, owned: 3 },
      ],
      isEmpty: false,
      ...overrides,
    },
    exchangeRates: [
      { code: 'USD', rate: '41.2500', effectiveDate: '2026-09-03' },
      { code: 'EUR', rate: null, effectiveDate: null },
    ],
    finance: {
      coinSpendUah: '42000.00',
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
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.mocked(fetchBootstrap).mockReset();
  });

  it('shows the empty state with a way into the catalog', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap({ isEmpty: true }));
    renderPage();

    expect(await screen.findByText('Колекція поки порожня')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.getByRole('link', { name: 'Додати покупку' })).toHaveAttribute(
      'href',
      '/collection/coins/new',
    );
    expect(screen.getByRole('link', { name: 'Імпортувати з uCoin' })).toHaveAttribute(
      'href',
      '/import',
    );
    expect(screen.queryByText('Фінанси')).toBeNull();
  });

  it('links every KPI tile to its own section', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap());
    renderPage();

    await screen.findByText('Усі важливі цифри та прогрес моєї колекції в одному місці.');
    expect(screen.getByRole('link', { name: /Монет у колекції/ })).toHaveAttribute(
      'href',
      '/collection/coins',
    );
    expect(screen.getByRole('link', { name: /Не вистачає/ })).toHaveAttribute(
      'href',
      '/catalog?owned=false',
    );
    expect(screen.getByRole('link', { name: /Комплектність/ })).toHaveAttribute(
      'href',
      '/collection/series',
    );
    expect(screen.getByRole('link', { name: /Поточна оцінка/ })).toHaveAttribute(
      'href',
      '/collection/money',
    );
  });

  it('opens the series page from the nearest-series row', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap());
    renderPage();

    expect(await screen.findByRole('link', { name: 'Флора і фауна' })).toHaveAttribute(
      'href',
      '/collection/series/11',
    );
    expect(screen.queryByRole('link', { name: 'Переглянути відсутні' })).toBeNull();
  });

  it('renders the totals and the delta between valuation and spend', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap());
    renderPage();

    expect(await screen.findByText('42 765,66 ₴')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-delta')).toHaveTextContent('+7 234,34 ₴');
    expect(screen.getByTestId('dashboard-delta')).toHaveTextContent('+16,9 %');
    expect(screen.getByText('без ціни: 41')).toBeInTheDocument();
  });

  it('lists every started series, closest to completion first and finished ones last', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap());
    renderPage();

    expect(await screen.findByText('Флора і фауна')).toBeInTheDocument();
    expect(screen.getByText('19 з 20')).toBeInTheDocument();
    const names = screen
      .getAllByRole('link', { name: /Флора і фауна|Готово/ })
      .map((link) => link.textContent);
    expect(names).toEqual(['Флора і фауна', 'Готово']);
  });

  it('drops a series the owner has not started at all', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(
      makeBootstrap({
        seriesBreakdown: [
          { id: 11, name: 'Флора і фауна', country: 'Україна', count: 20, owned: 19 },
          { id: 13, name: 'Ще не почато', country: 'Україна', count: 5, owned: 0 },
        ],
      }),
    );
    renderPage();

    expect(await screen.findByText('Флора і фауна')).toBeInTheDocument();
    expect(screen.queryByText('Ще не почато')).toBeNull();
  });

  it('shows the empty-series message when nothing has been started yet', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap({ seriesBreakdown: [] }));
    renderPage();

    expect(await screen.findByText('Ще не почато жодної серії.')).toBeInTheDocument();
  });

  it('shows the rate with its date and a placeholder for a missing one', async () => {
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap());
    renderPage();

    expect(await screen.findByText('41,25 ₴')).toBeInTheDocument();
    expect(screen.getByText('на 03.09.2026')).toBeInTheDocument();
    expect(screen.getByText('немає даних')).toBeInTheDocument();
  });
});
