import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { CompletenessGroup } from '@/shared/api/types';

import { fetchCountries } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import type { BootstrapOut, CountryOut } from '@/shared/api/types';

import { fetchCompletenessSummary } from './api';
import { CompletenessListPage } from './CompletenessListPage';
import { sortGroups } from './sort';

vi.mock('./api', () => ({ fetchCompletenessSummary: vi.fn() }));
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
  catalogConfirmed: true,
  sortOrder: 0,
  minYear: null,
  maxYear: null,
};

function group(
  value: number,
  label: string,
  owned: number,
  total: number,
  overrides: Partial<CompletenessGroup> = {},
): CompletenessGroup {
  return {
    groupBy: 'series',
    value,
    unassigned: false,
    label,
    countryId: 1,
    description: null,
    startYear: null,
    endYear: null,
    sortOrder: null,
    summary: {
      total,
      owned,
      missing: total - owned,
      completionPercent: total ? Math.round((owned / total) * 1000) / 10 : 0,
      purchaseTotalUah: '100.00',
      currentValueUah: '250.00',
      unpricedMissing: total - owned > 0 ? 1 : 0,
    },
    ...overrides,
  };
}

const ROWS = [
  group(1, 'Half', 5, 10),
  group(2, 'Almost', 19, 20),
  group(3, 'Done', 3, 3),
  group(4, 'Empty', 0, 0),
];

describe('sortGroups', () => {
  it('puts the most complete group first and can sort by value', () => {
    expect(sortGroups(ROWS, 'completion').map((row) => row.label)).toEqual([
      'Done',
      'Almost',
      'Half',
      'Empty',
    ]);
    // None of these rows carry a sortOrder, so 'value' falls back to the label.
    expect(sortGroups(ROWS, 'value').map((row) => row.label)).toEqual([
      'Almost',
      'Done',
      'Empty',
      'Half',
    ]);
  });

  it('sorts numerically by sortOrder when every row has one', () => {
    const rows = [
      group(2015, '2015', 1, 1, { sortOrder: 2015 }),
      group(1999, '1999', 1, 1, { sortOrder: 1999 }),
      group(2001, '2001', 1, 1, { sortOrder: 2001 }),
    ];
    expect(sortGroups(rows, 'value').map((row) => row.label)).toEqual(['1999', '2001', '2015']);
  });
});

function renderPage(initialEntries: string[] = ['/']) {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={initialEntries}>
        <CompletenessListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CompletenessListPage', () => {
  it('defaults to "Мої": started groups only, hiding the zeroed-out one', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    expect(await screen.findByRole('link', { name: 'Almost' })).toHaveAttribute(
      'href',
      '/collection/completeness/series/2',
    );
    expect(screen.getByText('19 з 20')).toBeInTheDocument();
    expect(screen.getAllByText('100 ₴')).toHaveLength(3);
    expect(screen.getAllByText('250 ₴')).toHaveLength(3);
    expect(screen.queryByText('Empty')).toBeNull();
  });

  it('switches to "Усі" and shows every group, including unstarted ones', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    await screen.findByText('Almost');
    expect(screen.queryByText('Empty')).toBeNull();

    await userEvent.click(screen.getByRole('tab', { name: 'Усі' }));
    expect(await screen.findByText('Empty')).toBeInTheDocument();
    expect(screen.getAllByText('100 ₴')).toHaveLength(4);
  });

  it('filters the visible rows by label as the user types', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    await screen.findByText('Almost');
    await userEvent.type(screen.getByPlaceholderText('Пошук…'), 'alm');

    await waitFor(() => expect(screen.queryByText('Half')).toBeNull());
    expect(screen.getByText('Almost')).toBeInTheDocument();
    expect(screen.queryByText('Done')).toBeNull();
  });

  it('shows a placeholder with a scope switch when nothing is started yet', async () => {
    const notStarted = [group(1, 'Half', 0, 10), group(2, 'Almost', 0, 20)];
    vi.mocked(fetchCompletenessSummary).mockResolvedValue(notStarted);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    expect(await screen.findByText('Ще нічого не почато')).toBeInTheDocument();
    expect(screen.queryByText('Half')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: 'Показати всі' }));
    expect(await screen.findByText('Half')).toBeInTheDocument();
    expect(screen.getByText('Almost')).toBeInTheDocument();
  });

  it('shows an onboarding empty state instead of a zeroed-out list', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(true));
    vi.mocked(fetchCountries).mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText('Тут поки порожньо')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute(
      'href',
      '/catalog',
    );
    expect(screen.getByRole('link', { name: 'Додати монету' })).toHaveAttribute(
      'href',
      '/collection/add',
    );
    expect(screen.queryByText('Almost')).toBeNull();
    expect(screen.queryByText('0 %')).toBeNull();
  });

  it('lets the viewer switch the grouping field', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    await screen.findByText('Almost');
    await userEvent.click(screen.getByRole('tab', { name: 'Рік' }));

    await waitFor(() =>
      expect(fetchCompletenessSummary).toHaveBeenLastCalledWith('year', undefined, undefined),
    );
  });

  it('narrows every dimension by metal kind, not only the "metal" tab', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue(ROWS);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage();

    await screen.findByText('Almost');
    await userEvent.click(screen.getByRole('button', { name: 'Цінність металу' }));
    await userEvent.click(screen.getByRole('option', { name: 'Дорогоцінні' }));

    await waitFor(() =>
      expect(fetchCompletenessSummary).toHaveBeenLastCalledWith('series', undefined, 'precious'),
    );
  });

  it('shows the "без значення" label for the unassigned bucket', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue([
      group(1, 'Мідь', 2, 5, { groupBy: 'material' }),
      {
        ...group(0, '', 1, 3, { groupBy: 'material' }),
        unassigned: true,
        value: null,
        label: null,
      },
    ]);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage(['/?groupBy=material']);

    expect(await screen.findByText('Без металу')).toBeInTheDocument();
  });

  it('shows the "без значення" label for edge/quality, same as denomination/material', async () => {
    vi.mocked(fetchCompletenessSummary).mockResolvedValue([
      group(1, 'Рифлений', 2, 5, { groupBy: 'edge' }),
      { ...group(0, '', 1, 3, { groupBy: 'edge' }), unassigned: true, value: null, label: null },
    ]);
    vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap(false));
    vi.mocked(fetchCountries).mockResolvedValue([COUNTRY]);
    renderPage(['/?groupBy=edge']);

    expect(await screen.findByText('Рифлений')).toBeInTheDocument();
    expect(screen.getByText('Без гурту')).toBeInTheDocument();
  });
});
