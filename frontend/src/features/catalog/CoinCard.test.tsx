import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import '@/shared/i18n';
import type { CatalogListItem } from '@/shared/api/types';

import { CoinCard } from './CoinCard';

function makeItem(overrides: Partial<CatalogListItem> = {}): CatalogListItem {
  return {
    id: 1,
    country: 'Ukraine',
    seriesName: null,
    denomination: '5 ₴',
    year: 2021,
    title: 'Sikorsky',
    titleOriginal: 'Ihor Sikorsky',
    titleUk: null,
    titleRu: null,
    titleEn: null,
    variety: null,
    catalogNumber: null,
    collectionGroup: 'commemorative',
    metalKind: 'base',
    material: null,
    marketPriceUah: null,
    priceSource: null,
    priceObservedAt: null,
    quantityOwned: 0,
    purchaseTotalUah: '0.00',
    obverseImageUrl: null,
    reverseImageUrl: null,
    thumbnailUrl: null,
    isOwn: false,
    isArchived: false,
    archiveReason: null,
    sourceUrl: null,
    ...overrides,
  };
}

describe('CoinCard images', () => {
  it('shows the placeholder when the item has no photo', () => {
    const { container } = render(<CoinCard item={makeItem()} />);

    expect(screen.getAllByTestId('coin-placeholder')).toHaveLength(1);
    expect(container.querySelector('img')).toBeNull();
  });

  it('replaces an unreachable photo with the same placeholder', () => {
    const { container } = render(
      <CoinCard item={makeItem({ obverseImageUrl: 'https://ucoin.net/coin/obverse.jpg' })} />,
    );

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
        item={makeItem({
          obverseImageUrl: 'https://ucoin.net/coin/obverse.jpg',
          reverseImageUrl: 'https://ucoin.net/coin/reverse.jpg',
        })}
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

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'https://ucoin.net/coin/ua-5uah-2021');
    expect(container.querySelector('img')).toBeNull();
  });
});
