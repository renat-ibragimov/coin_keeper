import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { ApiError } from '@/shared/api/client';
import type { CatalogCard, CatalogCollectionItem, PriceHistoryItem } from '@/shared/api/types';
import type { CoinImageOut } from '@/shared/lib/coinImage';

import { fetchCard, fetchOwnInstances, fetchPrices } from '../api';
import { CoinCardPage } from './CoinCardPage';

vi.mock('../api', () => ({
  fetchCard: vi.fn(),
  fetchPrices: vi.fn(),
  fetchOwnInstances: vi.fn(),
}));

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
    edge: 'рифлений',
    orientation: null,
    catalogKm: '123',
    catalogUc: null,
    catalogNumista: null,
    notes: null,
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
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/catalog/:id" element={<CoinCardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CoinCardPage', () => {
  beforeEach(() => {
    vi.mocked(fetchCard).mockReset();
    vi.mocked(fetchPrices).mockReset().mockResolvedValue([]);
    vi.mocked(fetchOwnInstances).mockReset().mockResolvedValue([]);
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

  it('shows the status, quantity and current price in the sidebar when owned', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    expect(await screen.findByRole('heading', { name: 'У моїй колекції' })).toBeInTheDocument();
    expect(screen.getByText('2 екземпляри')).toBeInTheDocument();
    expect(screen.getByText('460 ₴')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Додати ще екземпляр' })).toHaveAttribute(
      'href',
      '/collection/coins/new?catalogItemId=7',
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
      '/collection/coins/new?catalogItemId=7',
    );
    // Nothing to show on "Мої екземпляри" for a coin the visitor doesn't own.
    expect(screen.queryByRole('tab', { name: 'Мої екземпляри' })).toBeNull();
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

    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: 'Історія цін' }));

    expect(screen.queryByTestId('trend-line')).toBeNull();
    expect(screen.getAllByText('460 ₴').length).toBeGreaterThan(0);
  });

  it('renders the trend line for two or more price points', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    vi.mocked(fetchPrices).mockResolvedValue([
      priceSnapshot({ id: 1, observedAt: '2024-01-10T00:00:00Z', priceUah: '400.00' }),
      priceSnapshot({ id: 2, observedAt: '2024-05-18T00:00:00Z', priceUah: '460.00' }),
    ]);
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: 'Історія цін' }));

    expect(await screen.findByTestId('trend-line')).toBeInTheDocument();
  });

  it('shows the empty state when there is no price history', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: 'Історія цін' }));

    expect(await screen.findByText('Цін ще немає.')).toBeInTheDocument();
  });

  it('shows the purchase/valuation summary and reveals the instances behind the disclosure', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: 'Мої екземпляри' }));

    expect(await screen.findByText('640 ₴')).toBeInTheDocument();
    // current value = 460 × 2 = 920
    expect(screen.getByText('920 ₴')).toBeInTheDocument();
    // change = 920 − 640 = +280, +43,8 %
    expect(screen.getByText('+280 ₴')).toBeInTheDocument();
    expect(screen.getByText('(+43,8 %)')).toBeInTheDocument();

    await user.click(await screen.findByText('Показати всі екземпляри (2)'));

    const rows = await screen.findAllByTestId('instance-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('Аукціон Violity')).toBeInTheDocument();
    expect(screen.getByText('35 ₴ за 1 $')).toBeInTheDocument();

    // The purchase date is the primary value of the first cell, quantity a
    // secondary line under it — shown even though every instance here owns 1.
    const [firstRow, secondRow] = rows;
    expect(within(firstRow!).getByText('Дата покупки')).toBeInTheDocument();
    expect(within(firstRow!).queryByText('Кількість')).toBeNull();
    expect(within(firstRow!).getByText('02.04.2025')).toBeInTheDocument();
    expect(within(firstRow!).getByText('1 екземпляр')).toBeInTheDocument();
    expect(within(secondRow!).getByText('15.11.2023')).toBeInTheDocument();
    expect(within(secondRow!).getByText('1 екземпляр')).toBeInTheDocument();
  });

  it('scrolls the newly revealed instances into view when the disclosure opens', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: 'Мої екземпляри' }));
    await user.click(await screen.findByText('Показати всі екземпляри (2)'));

    await waitFor(() =>
      expect(scrollIntoView).toHaveBeenCalledWith(
        expect.objectContaining({ behavior: 'smooth', block: 'end' }),
      ),
    );
  });

  it('skips the value-change percent when nothing was paid for the coin', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard({ purchaseTotalUah: '0.00' }));
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: 'Мої екземпляри' }));

    expect(await screen.findByText('+920 ₴')).toBeInTheDocument();
    expect(screen.queryByText(/%/)).toBeNull();
  });

  it('shows a compact empty state with a call to action on the instances tab when empty', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: 'Мої екземпляри' }));

    expect(await screen.findByText('У вас ще немає екземплярів цієї монети.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Додати до колекції' })).toHaveAttribute(
      'href',
      '/collection/coins/new?catalogItemId=7',
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
