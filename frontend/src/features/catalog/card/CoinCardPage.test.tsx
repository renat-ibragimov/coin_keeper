import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { AuthDialogContext } from '@/features/auth/authDialogContext';
const authState = vi.hoisted(() => ({
  user: { id: 1, role: 'user' } as { id: number; role: string } | null,
}));
const openAuth = vi.fn();
vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => authState }));
import { ApiError } from '@/shared/api/client';
import type {
  BootstrapOut,
  CatalogCard,
  CatalogCollectionItem,
  PriceHistoryItem,
} from '@/shared/api/types';
import type { CoinImageOut } from '@/shared/lib/coinImage';
import { ThemeContext } from '@/shared/theme/themeContext';

import { fetchBootstrap } from '@/features/dashboard/api';

import { fetchCard, fetchOwnInstances, fetchPrices } from '../api';
import { CoinCardPage } from './CoinCardPage';

vi.mock('../api', () => ({
  fetchCard: vi.fn(),
  fetchPrices: vi.fn(),
  fetchOwnInstances: vi.fn(),
}));

vi.mock('@/features/dashboard/api', () => ({ fetchBootstrap: vi.fn() }));

const lwcMocks = vi.hoisted(() => {
  const timeScale = { fitContent: vi.fn(), setVisibleRange: vi.fn() };
  const series = { setData: vi.fn() };
  const chart = {
    addSeries: vi.fn(() => series),
    timeScale: vi.fn(() => timeScale),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    remove: vi.fn(),
  };
  return {
    createChart: vi.fn(() => chart),
    createSeriesMarkers: vi.fn(() => ({ setMarkers: vi.fn() })),
  };
});

// PriceHistoryChart draws on a <canvas>, which jsdom does not implement; the
// page's own tests only need to know the chart was asked to render, not that
// it actually painted (that lives in PriceHistoryChart.test.tsx).
vi.mock('lightweight-charts', () => ({
  createChart: lwcMocks.createChart,
  createSeriesMarkers: lwcMocks.createSeriesMarkers,
  AreaSeries: 'Area',
  ColorType: { Solid: 'solid' },
  CrosshairMode: { Magnet: 1 },
  LineStyle: { Dotted: 2, Solid: 0 },
}));

function makeBootstrap(usdRate: string | null = '41.5000'): BootstrapOut {
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
      isEmpty: true,
    },
    exchangeRates: [
      { code: 'USD', rate: usdRate, effectiveDate: usdRate ? '2026-09-13' : null },
      { code: 'EUR', rate: null, effectiveDate: null },
    ],
    finance: {
      coinSpendUah: '0.00',
      coinSpendUsdAtPurchase: null,
      coinSpendEurAtPurchase: null,
      purchasesWithoutHistoricalUsdRate: 0,
      purchasesWithoutHistoricalEurRate: 0,
    },
  };
}

function makeCard(overrides: Partial<CatalogCard> = {}): CatalogCard {
  return {
    id: 7,
    country: 'Україна',
    seriesName: 'Флора і фауна України',
    denomination: {
      id: 4,
      value: '2.000',
      unit: 'hryvnia',
      currencyCode: 'UAH',
      label: '2 гривні',
    },
    denominationText: null,
    year: 2017,
    title: 'Дельфін',
    titleOriginal: 'Дельфін',
    originalLang: 'uk',
    titleUk: 'Дельфін',
    titleUkSource: 'official',
    titleEn: 'Dolphin',
    titleEnSource: 'official',
    variety: null,
    catalogNumber: null,
    collectionGroup: 'commemorative',
    metalKind: 'base',
    composition: { id: 13, code: 'nickel_silver', name: 'Нейзильбер' },
    material: null,
    marketPriceUah: '460.00',
    priceSource: 'ua-coins',
    priceObservedAt: '2024-05-18T00:00:00Z',
    quantityOwned: 2,
    purchaseTotalUah: '640.00',
    purchaseTotalUsd: '15.42',
    purchaseTotalEur: '14.00',
    supportingExpensesUah: null,
    obverseImage: null,
    reverseImage: null,
    thumbnailUrl: null,
    isOwn: false,
    isArchived: false,
    archiveReason: null,
    sourceUrl: null,
    countryId: 1,
    seriesId: 3,
    denominationId: 2,
    itemType: 'coin',
    subtype: null,
    issueDate: null,
    mintageAnnounced: 40000,
    mintageActual: null,
    weightGrams: '12.800',
    diameterMm: '31.000',
    thicknessMm: null,
    shape: null,
    edgeType: null,
    edge: 'рифлений',
    orientation: null,
    qualityType: null,
    quality: null,
    catalogKm: '123',
    catalogUc: null,
    catalogNumista: null,
    notes: null,
    description: null,
    designers: [],
    sculptors: [],
    archivedAt: null,
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

const INSTANCES: CatalogCollectionItem[] = [
  {
    id: 1,
    catalogItemId: 7,
    quantity: 1,
    grade: 'UNC',
    acquisitionDate: '2025-04-02',
    seller: 'Аукціон Violity',
    purchasePrice: '10.00',
    purchaseCurrency: 'USD',
    purchaseRateUah: '35.0000',
    totalUah: '350.00',
    totalUsd: '10.00',
    totalEur: '9.20',
    supportingExpensesUah: null,
    storageLocation: null,
    notes: 'Без капсули',
  },
  {
    id: 2,
    catalogItemId: 7,
    quantity: 1,
    grade: 'XF',
    acquisitionDate: '2023-11-15',
    seller: null,
    purchasePrice: '290.00',
    purchaseCurrency: 'UAH',
    purchaseRateUah: null,
    totalUah: '290.00',
    totalUsd: '7.25',
    totalEur: '6.70',
    supportingExpensesUah: null,
    storageLocation: null,
    notes: null,
  },
];

function priceSnapshot(overrides: Partial<PriceHistoryItem> = {}): PriceHistoryItem {
  return {
    id: 1,
    source: 'ua-coins',
    grade: null,
    price: '460.00',
    currencyCode: 'UAH',
    priceUah: '460.00',
    observedAt: '2024-05-18T00:00:00Z',
    sourceUrl: null,
    isOwn: false,
    isSuspect: false,
    ...overrides,
  };
}

function renderPage(path = '/catalog/7') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      {/* jsdom has no matchMedia, so the theme is provided directly rather than via ThemeProvider. */}
      <ThemeContext.Provider
        value={{ theme: 'light', preference: 'light', setPreference: () => {} }}
      >
        <MemoryRouter initialEntries={[path]}>
          <AuthDialogContext.Provider value={openAuth}>
            <Routes>
              <Route path="/catalog/:id" element={<CoinCardPage />} />
            </Routes>
          </AuthDialogContext.Provider>
        </MemoryRouter>
      </ThemeContext.Provider>
    </QueryClientProvider>,
  );
}

describe('CoinCardPage', () => {
  beforeEach(() => {
    authState.user = { id: 1, role: 'user' };
    vi.mocked(fetchCard).mockReset();
    vi.mocked(fetchPrices).mockReset().mockResolvedValue([]);
    vi.mocked(fetchOwnInstances).mockReset().mockResolvedValue([]);
    vi.mocked(fetchBootstrap).mockReset().mockResolvedValue(makeBootstrap());
  });

  it('keeps public coin details and locks prices without requesting private endpoints', async () => {
    authState.user = null;
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ quantityOwned: 0 }));
    renderPage();
    expect(await screen.findByRole('heading', { level: 1, name: 'Дельфін' })).toBeInTheDocument();
    expect(screen.getByText('Доступно після реєстрації', { exact: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Увійти' })).toBeInTheDocument();
    expect(screen.queryByText('460 ₴')).not.toBeInTheDocument();
    expect(screen.queryByText('UA-Coins')).not.toBeInTheDocument();
    expect(vi.mocked(fetchPrices)).not.toHaveBeenCalled();
    expect(vi.mocked(fetchOwnInstances)).not.toHaveBeenCalled();
    expect(vi.mocked(fetchBootstrap)).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /Додати до колекції/ }));
    expect(openAuth).toHaveBeenCalledWith('register', {
      from: '/collection/add?catalogItemId=7',
      returnState: { from: '/catalog/7' },
      purpose: 'collection',
    });
  });
  it('shows the title and the identity fields in the specs table', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    expect(await screen.findByRole('heading', { level: 1, name: 'Дельфін' })).toBeInTheDocument();
    expect(screen.getByText('Країна')).toBeInTheDocument();
    expect(screen.getByText('Україна')).toBeInTheDocument();
    expect(screen.getByText('Серія')).toBeInTheDocument();
    expect(screen.getByText('Флора і фауна України')).toBeInTheDocument();
    expect(screen.getByText('Категорія')).toBeInTheDocument();
    expect(screen.getByText("Пам'ятна монета")).toBeInTheDocument();
    expect(screen.getByText('Рік')).toBeInTheDocument();
    expect(screen.getByText('2017')).toBeInTheDocument();
    expect(screen.getByText('Номінал')).toBeInTheDocument();
    expect(screen.getByText('2 гривні')).toBeInTheDocument();
  });

  it('shows the general, obverse and reverse descriptions when the parser found them', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({
        description: {
          general: 'Присвячена дельфінам Чорного моря.',
          obverse: 'На аверсі — малий герб України.',
          reverse: 'На реверсі — зображення дельфіна.',
        },
      }),
    );
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Опис' })).toBeInTheDocument();
    expect(screen.getByText('Присвячена дельфінам Чорного моря.')).toBeInTheDocument();
    expect(screen.getByText('На аверсі — малий герб України.')).toBeInTheDocument();
    expect(screen.getByText('На реверсі — зображення дельфіна.')).toBeInTheDocument();
  });

  it('omits the description section entirely when the parser has not touched the coin', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ description: null }));
    renderPage();

    await screen.findByRole('heading', { level: 1, name: 'Дельфін' });
    expect(screen.queryByRole('heading', { name: 'Опис' })).toBeNull();
  });

  it('shows designers and sculptors in the issue spec group', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({
        designers: ['Таран Володимир', 'Харук Олександр'],
        sculptors: ['Чайковський Роман'],
      }),
    );
    renderPage();

    expect(await screen.findByText('Художники')).toBeInTheDocument();
    expect(screen.getByText('Таран Володимир, Харук Олександр')).toBeInTheDocument();
    expect(screen.getByText('Скульптори')).toBeInTheDocument();
    expect(screen.getByText('Чайковський Роман')).toBeInTheDocument();
  });

  it('shows the edge/quality dictionary name over the raw text, and the raw text when there is no dictionary row', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({
        edgeType: { id: 1, code: 'reeded', name: 'Рифлений' },
        edge: 'reeded',
        qualityType: { id: 1, code: 'proof', name: 'Пруф' },
        quality: 'proof',
      }),
    );
    renderPage();

    expect(await screen.findByText('Гурт')).toBeInTheDocument();
    expect(screen.getByText('Рифлений')).toBeInTheDocument();
    expect(screen.queryByText('reeded')).not.toBeInTheDocument();
    expect(screen.getByText('Категорія якості карбування')).toBeInTheDocument();
    expect(screen.getByText('Пруф')).toBeInTheDocument();
  });

  it('falls back to the raw edge text when there is no dictionary row for it', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ edgeType: null, edge: 'Незвичайний гурт' }));
    renderPage();

    expect(await screen.findByText('Гурт')).toBeInTheDocument();
    expect(screen.getByText('Незвичайний гурт')).toBeInTheDocument();
  });

  it('shows the status, quantity and current price in the sidebar when owned', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    expect(await screen.findByRole('heading', { name: 'У моїй колекції' })).toBeInTheDocument();
    expect(screen.getByText('2 екземпляри')).toBeInTheDocument();
    expect(screen.getByText('460 ₴')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Додати ще екземпляр' })).toHaveAttribute(
      'href',
      '/collection/add?catalogItemId=7',
    );
    // The visitor's own purchase price, valuation and profit live on "Мої екземпляри" instead.
    expect(screen.queryByText('Куплено загалом')).toBeNull();
    expect(screen.queryByText('Поточна вартість колекції')).toBeNull();
  });

  it('shows a compact empty state with a call to action when not owned', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({ quantityOwned: 0, purchaseTotalUah: '0.00' }),
    );
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Немає у колекції' })).toBeInTheDocument();
    expect(screen.queryByText(/Кількість/)).toBeNull();
    expect(screen.getByRole('link', { name: /Додати до колекції/ })).toHaveAttribute(
      'href',
      '/collection/add?catalogItemId=7',
    );
    // Nothing to show on "Мої екземпляри" for a coin the visitor doesn't own.
    expect(screen.queryByRole('heading', { name: 'Мої екземпляри' })).toBeNull();
  });

  it('shows a calm empty state for the current price when there is none', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ marketPriceUah: null }));
    renderPage();

    expect(await screen.findByText('Актуальна ціна поки відсутня')).toBeInTheDocument();
  });

  it('links to the source for the current price', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ sourceUrl: 'https://ua-coins.info/coin/7' }));
    renderPage();

    expect(await screen.findByRole('link', { name: /Відкрити на/ })).toHaveAttribute(
      'href',
      'https://ua-coins.info/coin/7',
    );
  });

  it('shows a compact summary instead of a chart for a single price point', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    vi.mocked(fetchPrices).mockResolvedValue([priceSnapshot()]);
    renderPage();

    await screen.findByRole('heading', { name: 'Історія цін' });

    expect(screen.queryByRole('img', { name: /Графік цін/ })).toBeNull();
    expect(screen.getAllByText('460 ₴').length).toBeGreaterThan(0);
  });

  it('renders the chart for two or more price points', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    vi.mocked(fetchPrices).mockResolvedValue([
      priceSnapshot({ id: 1, observedAt: '2024-01-10T00:00:00Z', priceUah: '400.00' }),
      priceSnapshot({ id: 2, observedAt: '2024-05-18T00:00:00Z', priceUah: '460.00' }),
    ]);
    renderPage();

    await screen.findByRole('heading', { name: 'Історія цін' });
    expect(await screen.findByRole('img', { name: /Графік цін/ })).toBeInTheDocument();
  });

  it('shows the empty state when there is no price history', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    expect(await screen.findByText('Цін ще немає.')).toBeInTheDocument();
  });

  it('shows the purchase/valuation summary above the instances table', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    renderPage();

    await screen.findByRole('heading', { name: 'Мої екземпляри' });

    expect(await screen.findByText('640 ₴')).toBeInTheDocument();
    // current value = 460 × 2 = 920
    expect(screen.getByText('920 ₴')).toBeInTheDocument();
    // change = 920 − 640 = +280, +43,8 %
    expect(screen.getByText('+280 ₴')).toBeInTheDocument();
    expect(screen.getByText('(+43,8 %)')).toBeInTheDocument();

    const rows = await screen.findAllByTestId('instance-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('35 ₴ за 1 $')).toBeInTheDocument();

    const [firstRow, secondRow] = rows;
    expect(within(firstRow!).getByText('02.04.2025')).toBeInTheDocument();
    expect(within(secondRow!).getByText('15.11.2023')).toBeInTheDocument();
  });

  it('folds supporting expenses into "Куплено загалом" and the value change by default', async () => {
    // settings.includeSupportingExpenses defaults to true (makeBootstrap).
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({ purchaseTotalUah: '640.00', supportingExpensesUah: '60.00' }),
    );
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    renderPage();

    await screen.findByRole('heading', { name: 'Мої екземпляри' });
    // 640 (coin) + 60 (supporting) = 700, merged into the headline by default.
    expect(await screen.findByText('700 ₴')).toBeInTheDocument();
    expect(screen.getByText('у т.ч. 60 ₴ супутні витрати')).toBeInTheDocument();
    // change = 920 (current) − 700 (merged) = +220
    expect(screen.getByText('+220 ₴')).toBeInTheDocument();
  });

  it('keeps supporting expenses out of "Куплено загалом" when the viewer turned that off', async () => {
    const bootstrap = makeBootstrap();
    vi.mocked(fetchBootstrap).mockResolvedValue({
      ...bootstrap,
      settings: { ...bootstrap.settings, includeSupportingExpenses: false },
    });
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({ purchaseTotalUah: '640.00', supportingExpensesUah: '60.00' }),
    );
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    renderPage();

    await screen.findByRole('heading', { name: 'Мої екземпляри' });
    expect(await screen.findByText('640 ₴')).toBeInTheDocument();
    expect(screen.getByText('+ 60 ₴ супутні витрати')).toBeInTheDocument();
    // change = 920 (current) − 640 (coin only) = +280
    expect(screen.getByText('+280 ₴')).toBeInTheDocument();
  });

  it('skips the value-change percent when nothing was paid for the coin', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ purchaseTotalUah: '0.00' }));
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    renderPage();

    const changeValue = await screen.findByText('+920 ₴');
    // The value-change box has no percent when nothing was paid; the
    // per-row percent in "Мої екземпляри" is unaffected — it is computed
    // from each purchase's own price, not the card's aggregate total.
    expect(changeValue.closest('div')?.textContent).not.toMatch(/%/);
  });

  it('shows a compact empty state with a call to action on the instances tab when empty', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    expect(await screen.findByText('У вас ще немає екземплярів цієї монети.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Додати до колекції' })).toHaveAttribute(
      'href',
      '/collection/add?catalogItemId=7',
    );
    // No purchase/valuation summary without any instances.
    expect(screen.queryByText('Куплено загалом')).toBeNull();
  });

  it('hides a spec group entirely when none of its fields are present', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ catalogKm: null }));
    renderPage();

    await screen.findByRole('heading', { level: 1, name: 'Дельфін' });
    expect(screen.getByText('Технічні характеристики')).toBeInTheDocument();
    expect(screen.queryByText('Каталожна інформація')).toBeNull();
    expect(screen.queryByText('Товщина')).toBeNull();
  });

  it('puts the archive banner with its reason above an archived item', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({ isArchived: true, archiveReason: 'знято з випуску НБУ' }),
    );
    renderPage();

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Позицію архівовано: знято з випуску НБУ',
    );
  });

  it('opens the lightbox with the enlarged image', async () => {
    const image: CoinImageOut = {
      preview: 'https://cdn.example/dolphin-preview.jpg',
      medium: 'https://cdn.example/dolphin-medium.jpg',
      large: 'https://cdn.example/dolphin-large.jpg',
      attribution: 'uCoin',
    };
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ obverseImage: image }));
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /Збільшити — Аверс/ }));

    const lightbox = await screen.findByTestId('lightbox');
    expect(lightbox).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /Аверс — Дельфін/ })).toHaveAttribute(
      'src',
      image.large,
    );
  });

  it('credits the photo source in specs as one row when both sides share it', async () => {
    const image: CoinImageOut = {
      preview: null,
      medium: null,
      large: null,
      attribution: 'Національний банк України',
    };
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ obverseImage: image, reverseImage: image }));
    renderPage();

    await screen.findByRole('heading', { level: 1, name: 'Дельфін' });
    expect(screen.getByText('Джерело зображень')).toBeInTheDocument();
    expect(screen.getByText('Національний банк України')).toBeInTheDocument();
    expect(screen.queryByText('Джерело зображення аверсу')).toBeNull();
  });

  it('credits each side separately when their photo sources differ', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({
        obverseImage: { preview: null, medium: null, large: null, attribution: 'НБУ' },
        reverseImage: { preview: null, medium: null, large: null, attribution: 'uCoin' },
      }),
    );
    renderPage();

    await screen.findByRole('heading', { level: 1, name: 'Дельфін' });
    expect(screen.getByText('Джерело зображення аверсу')).toBeInTheDocument();
    expect(screen.getByText('НБУ')).toBeInTheDocument();
    expect(screen.getByText('Джерело зображення реверсу')).toBeInTheDocument();
    expect(screen.getByText('uCoin')).toBeInTheDocument();
    expect(screen.queryByText('Джерело зображень')).toBeNull();
  });

  it('shows what the issuer calls the coin when the reader sees a translation', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({
        title: 'Карбованець',
        titleOriginal: 'Рубль',
        originalLang: 'ru',
        titleUk: 'Карбованець',
      }),
    );
    renderPage();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Карбованець' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Оригінал: Рубль/)).toBeInTheDocument();
  });

  it('shows "not found" for a foreign personal item or a missing id', async () => {
    vi.mocked(fetchCard).mockRejectedValue(new ApiError(404, { detail: 'Item not found' }));
    renderPage('/catalog/999');

    expect(await screen.findByText('Позицію не знайдено')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Перейти до каталогу' })).toHaveAttribute(
      'href',
      '/catalog',
    );
  });
});
