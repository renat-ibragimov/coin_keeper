import { fireEvent, render as renderBare, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';
import type { CatalogListItem } from '@/shared/api/types';

import { CoinCard } from './CoinCard';

function render(ui: ReactElement) {
  return renderBare(<MemoryRouter>{ui}</MemoryRouter>);
}

function photo(side: string): CatalogListItem['obverseImage'] {
  return {
    preview: `https://storage.test/${side}_300.webp`,
    medium: `https://storage.test/${side}_600.webp`,
    large: `https://storage.test/${side}_1200.webp`,
    attribution: 'Національний банк України',
  };
}

function makeItem(overrides: Partial<CatalogListItem> = {}): CatalogListItem {
  return {
    id: 1,
    country: 'Ukraine',
    seriesName: null,
    denomination: {
      id: 1,
      value: '5.000',
      unit: 'hryvnia',
      currencyCode: 'UAH',
      label: '5 гривень',
    },
    year: 2021,
    title: 'Sikorsky',
    titleOriginal: 'Ihor Sikorsky',
    originalLang: 'uk',
    titleUk: null,
    titleUkSource: null,
    titleEn: null,
    titleEnSource: null,
    variety: null,
    catalogNumber: null,
    collectionGroup: 'commemorative',
    metalKind: 'base',
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
    ...overrides,
  };
}

describe('CoinCard', () => {
  it('links the title to the coin page and applies the title rule', () => {
    render(<CoinCard item={makeItem({ titleUk: 'Сікорський', title: 'Sikorsky' })} />);
    const heading = screen.getByRole('heading', { name: 'Сікорський' });
    expect(within(heading).getByRole('link')).toHaveAttribute('href', '/catalog/1');
  });
});

describe('CoinCard images', () => {
  it('shows the placeholder when the item has no photo', () => {
    const { container } = render(<CoinCard item={makeItem()} />);

    expect(screen.getAllByTestId('coin-placeholder')).toHaveLength(1);
    expect(container.querySelector('img')).toBeNull();
  });

  it('replaces an unreachable photo with the same placeholder', () => {
    const { container } = render(<CoinCard item={makeItem({ obverseImage: photo('obverse') })} />);

    const image = container.querySelector('img');
    expect(image).not.toBeNull();
    expect(screen.queryByTestId('coin-placeholder')).toBeNull();

    fireEvent.error(image!);

    expect(screen.getAllByTestId('coin-placeholder')).toHaveLength(1);
    expect(container.querySelector('img')).toBeNull();
  });

  it('keeps a failed side out while the other side still loads', () => {
    const { container } = render(
      <CoinCard
        item={makeItem({ obverseImage: photo('obverse'), reverseImage: photo('reverse') })}
      />,
    );
    expect(container.querySelectorAll('img')).toHaveLength(2);

    fireEvent.error(container.querySelectorAll('img')[0]!);

    expect(container.querySelectorAll('img')).toHaveLength(1);
    expect(screen.getAllByTestId('coin-placeholder')).toHaveLength(1);
  });

  it('renders sourceUrl as a link, never as an image', () => {
    const { container } = render(
      <CoinCard item={makeItem({ sourceUrl: 'https://ucoin.net/coin/ua-5uah-2021' })} />,
    );

    const link = screen.getByRole('link', { name: /Джерело/ });
    expect(link).toHaveAttribute('href', 'https://ucoin.net/coin/ua-5uah-2021');
    expect(container.querySelector('img')).toBeNull();
  });
});
