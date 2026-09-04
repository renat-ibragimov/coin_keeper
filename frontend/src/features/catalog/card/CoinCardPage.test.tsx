import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { ApiError } from '@/shared/api/client';
import type { CatalogCard, CatalogCollectionItem } from '@/shared/api/types';

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

  it('shows the title, specs and the owner purchases with the rate per unit', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    vi.mocked(fetchOwnInstances).mockResolvedValue(INSTANCES);
    renderPage();

    expect(await screen.findByRole('heading', { level: 1, name: 'Дельфін' })).toBeInTheDocument();
    expect(screen.getByText('2 гривні · Україна · 2017')).toBeInTheDocument();
    expect(screen.getByText('KM# 123')).toBeInTheDocument();
    expect(screen.getByText('Тираж (заявлений)')).toBeInTheDocument();
    expect(screen.getByText('31 мм')).toBeInTheDocument();
    expect(screen.queryByText('Товщина')).toBeNull();

    // owned twice: purchase total and the valuation = price × quantity
    expect(screen.getByText('640 ₴')).toBeInTheDocument();
    expect(screen.getByText('920 ₴')).toBeInTheDocument();

    expect(await screen.findAllByTestId('instance-row')).toHaveLength(2);
    expect(screen.getByText('Аукціон Violity')).toBeInTheDocument();
    expect(screen.getByText('35 ₴ за 1 $')).toBeInTheDocument();
    expect(screen.getByText('Цін ще немає.')).toBeInTheDocument();
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

  it('leaves the original line out when the name shown is the original', async () => {
    vi.mocked(fetchCard).mockResolvedValue(makeCard());
    renderPage();

    expect(await screen.findByRole('heading', { level: 1, name: 'Дельфін' })).toBeInTheDocument();
    expect(screen.queryByText(/Оригінал:/)).toBeNull();
  });

  it('hides the money block and says there is nothing yet without instances', async () => {
    vi.mocked(fetchCard).mockResolvedValue(
      makeCard({ quantityOwned: 0, purchaseTotalUah: '0.00' }),
    );
    renderPage();

    expect(await screen.findByText('Ще немає.')).toBeInTheDocument();
    expect(screen.queryByText('Куплено за')).toBeNull();
    expect(screen.getByText('✕ Не вистачає')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Додати покупку/ })).toHaveAttribute(
      'href',
      '/collection/new?catalogItemId=7',
    );
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
