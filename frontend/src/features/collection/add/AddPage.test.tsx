import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import {
  fetchAllMaterials,
  fetchCard,
  fetchCountries,
  fetchCurrencies,
  fetchDenominations,
  fetchEdgeTypes,
  fetchQualityTypes,
  fetchSeries,
  lookupCatalog,
} from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { createExpense } from '@/features/expenses/api';
import type { BootstrapOut, CatalogCard, CatalogListItem } from '@/shared/api/types';

import { createCollectionItem, fetchStorageLocations } from '../api';
import { AddPage } from './AddPage';

vi.mock('@/features/catalog/api', () => ({
  fetchCard: vi.fn(),
  fetchCountries: vi.fn(),
  fetchCurrencies: vi.fn(),
  fetchDenominations: vi.fn(),
  fetchAllMaterials: vi.fn(),
  fetchEdgeTypes: vi.fn(),
  fetchQualityTypes: vi.fn(),
  fetchSeries: vi.fn(),
  lookupCatalog: vi.fn(),
}));
vi.mock('@/features/dashboard/api', () => ({ fetchBootstrap: vi.fn() }));
vi.mock('../api', () => ({ createCollectionItem: vi.fn(), fetchStorageLocations: vi.fn() }));
vi.mock('@/features/expenses/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/expenses/api')>()),
  createExpense: vi.fn(),
}));

const UKRAINE = {
  id: 230,
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

function makeBootstrap(): BootstrapOut {
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
      isEmpty: false,
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

const SUGGESTION = {
  id: 7,
  country: 'Україна',
  seriesName: null,
  denomination: null,
  year: 2018,
  title: 'Дельфін',
  titleOriginal: 'Дельфін',
  originalLang: 'uk',
  titleUk: null,
  titleUkSource: null,
  titleEn: null,
  titleEnSource: null,
  variety: null,
  catalogNumber: null,
  collectionGroup: 'commemorative',
  metalKind: 'unknown',
  composition: null,
  material: null,
  marketPriceUah: null,
  priceSource: null,
  priceObservedAt: null,
  quantityOwned: 0,
  purchaseTotalUah: '0.00',
  obverseImage: null,
  reverseImage: null,
  thumbnailUrl: null,
  isOwn: false,
  isArchived: false,
  archiveReason: null,
  sourceUrl: null,
} as CatalogListItem;

const CARD = {
  ...SUGGESTION,
  countryId: 230,
  seriesId: null,
  denominationId: null,
  itemType: 'coin',
  subtype: null,
  issueDate: null,
  mintageAnnounced: null,
  mintageActual: null,
  weightGrams: null,
  diameterMm: null,
  thicknessMm: null,
  shape: null,
  edge: null,
  orientation: null,
  catalogKm: null,
  catalogUc: null,
  catalogNumista: null,
  notes: null,
  archivedAt: null,
  createdAt: '2024-01-01T00:00:00Z',
  updatedAt: '2024-01-01T00:00:00Z',
} as CatalogCard;

function renderPage(path = '/collection/add') {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={[path]}>
        <AddPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchBootstrap).mockResolvedValue(makeBootstrap());
  vi.mocked(fetchCountries).mockResolvedValue([UKRAINE]);
  vi.mocked(fetchCurrencies).mockResolvedValue([
    { code: 'UAH', name: 'Hryvnia', symbol: '₴', decimalPlaces: 2 },
  ]);
  vi.mocked(fetchAllMaterials).mockResolvedValue([{ id: 3, code: 'silver', name: 'Срібло' }]);
  vi.mocked(fetchEdgeTypes).mockResolvedValue([]);
  vi.mocked(fetchQualityTypes).mockResolvedValue([]);
  vi.mocked(fetchStorageLocations).mockResolvedValue([]);
  vi.mocked(fetchDenominations).mockResolvedValue([]);
  vi.mocked(fetchSeries).mockResolvedValue([]);
  vi.mocked(lookupCatalog).mockResolvedValue([]);
  vi.mocked(fetchCard).mockResolvedValue(CARD);
  vi.mocked(createCollectionItem).mockResolvedValue({ catalogItemId: 7 } as never);
  vi.mocked(createExpense).mockResolvedValue({ id: 1 } as never);
});

async function chooseCountry() {
  await userEvent.click(screen.getByLabelText('Країна'));
  await userEvent.click(await screen.findByRole('option', { name: 'Україна' }));
}

describe('AddPage', () => {
  it('opens on a coin purchase and switches to an expense without losing what was typed', async () => {
    renderPage();
    expect(await screen.findByLabelText('Тип')).toHaveTextContent('Покупка монети');

    await userEvent.type(await screen.findByLabelText(/Ціна за шт/), '250');
    await userEvent.type(screen.getByLabelText('Продавець'), 'Violity');

    await userEvent.click(screen.getByLabelText('Тип'));
    await userEvent.click(screen.getByRole('option', { name: 'Доставка' }));

    // The sum, the seller and the date mean the same thing on both sides of
    // the selector, so they carry over rather than being retyped.
    expect(await screen.findByLabelText(/Сума/)).toHaveValue('250');
    expect(screen.getByLabelText('Продавець')).toHaveValue('Violity');
    expect(screen.queryByLabelText('Кількість')).toBeNull();
  });

  it('collapses into the plain purchase form when a suggestion is picked', async () => {
    vi.mocked(lookupCatalog).mockResolvedValue([SUGGESTION]);
    renderPage();

    await chooseCountry();
    await userEvent.type(screen.getByLabelText('Назва монети'), 'Дельфін');

    const suggestion = await screen.findByRole('option', { name: /Дельфін/ });
    await userEvent.click(suggestion);

    // The coin is settled: its card replaces the search, and "Про монету"
    // has nothing left to ask.
    expect(await screen.findByRole('link', { name: 'Дельфін' })).toBeInTheDocument();
    expect(screen.queryByText('Про монету')).toBeNull();
    expect(screen.getByRole('button', { name: 'Обрати іншу монету' })).toBeInTheDocument();
  });

  it('sends the coin itself when the name is not in the catalog', async () => {
    renderPage();
    await chooseCountry();
    await userEvent.type(screen.getByLabelText('Назва монети'), 'Моя монета');

    expect(await screen.findByText('Про монету')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Рік випуску'), '2021');
    await userEvent.type(screen.getByLabelText('Матеріал'), 'Нейзильбер');
    await userEvent.type(screen.getByLabelText(/Ціна за шт/), '120');
    await userEvent.click(screen.getByRole('button', { name: 'Додати покупку' }));

    await waitFor(() => expect(createCollectionItem).toHaveBeenCalled());
    expect(vi.mocked(createCollectionItem).mock.calls[0]![0]).toMatchObject({
      price: '120',
      newCatalogItem: {
        countryId: 230,
        titleOriginal: 'Моя монета',
        issueYear: 2021,
        collectionGroup: 'commemorative',
        material: 'Нейзильбер',
        compositionId: null,
      },
    });
  });

  it('sends a dictionary material as an id rather than as text', async () => {
    renderPage();
    await chooseCountry();
    await userEvent.type(screen.getByLabelText('Назва монети'), 'Моя монета');
    await userEvent.type(await screen.findByLabelText('Рік випуску'), '2021');
    await userEvent.type(screen.getByLabelText('Матеріал'), 'Срібло');
    await userEvent.type(screen.getByLabelText(/Ціна за шт/), '120');
    await userEvent.click(screen.getByRole('button', { name: 'Додати покупку' }));

    await waitFor(() => expect(createCollectionItem).toHaveBeenCalled());
    expect(vi.mocked(createCollectionItem).mock.calls[0]![0]).toMatchObject({
      newCatalogItem: { compositionId: 3, material: null },
    });
  });

  it('refuses a new coin with no country, year or material', async () => {
    renderPage();
    await userEvent.type(await screen.findByLabelText('Назва монети'), 'Моя монета');
    await userEvent.type(screen.getByLabelText(/Ціна за шт/), '120');
    await userEvent.click(screen.getByRole('button', { name: 'Додати покупку' }));

    expect(createCollectionItem).not.toHaveBeenCalled();
    expect(screen.getByText('Вкажіть рік числом, від 1 до 2200.')).toBeInTheDocument();
    // The country and the material report the shared "required" message.
    expect(screen.getAllByText("Обов'язкове поле").length).toBeGreaterThan(1);
  });

  it('skips the search when a coin arrives in the address', async () => {
    renderPage('/collection/add?catalogItemId=7');

    expect(await screen.findByRole('link', { name: 'Дельфін' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Назва монети')).toBeNull();
    expect(fetchCard).toHaveBeenCalledWith(7);
  });

  it('attaches the chosen coin to an expense', async () => {
    vi.mocked(lookupCatalog).mockResolvedValue([SUGGESTION]);
    renderPage('/collection/add?type=grading');

    expect(await screen.findByLabelText('Тип')).toHaveTextContent('Грейдинг');
    await userEvent.type(screen.getByLabelText(/Сума/), '900');

    await userEvent.click(screen.getByLabelText('Країна'));
    await userEvent.click(await screen.findByRole('option', { name: 'Україна' }));
    await userEvent.type(screen.getByLabelText('Назва монети'), 'Дельфін');
    await userEvent.click(await screen.findByRole('option', { name: /Дельфін/ }));

    await userEvent.click(screen.getByRole('button', { name: 'Додати витрату' }));

    await waitFor(() => expect(createExpense).toHaveBeenCalled());
    expect(vi.mocked(createExpense).mock.calls[0]![0]).toMatchObject({
      category: 'grading',
      amount: '900',
      catalogItemId: 7,
    });
  });
});
