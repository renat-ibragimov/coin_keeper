import { fireEvent, render as renderBare, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
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

describe('CoinCard collection state (same footer everywhere: catalog, series)', () => {
  it('offers to add the coin to the collection when it is missing, with no negative badge', () => {
    render(<CoinCard item={makeItem({ quantityOwned: 0 })} />);
    expect(screen.queryByText(/Не вистачає/)).not.toBeInTheDocument();
    const link = screen.getByRole('link', { name: /Додати до колекції/ });
    expect(link).toHaveAttribute('href', '/collection/coins/new?catalogItemId=1');
  });

  it('shows a status row with a "+1" action when already owned, and no missing badge', () => {
    render(<CoinCard item={makeItem({ quantityOwned: 2 })} />);
    expect(screen.getAllByText(/У моїй колекції/).length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: /Додати до колекції/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Не вистачає/)).not.toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'Додати ще один екземпляр' });
    expect(link).toHaveTextContent('+1');
    expect(link).toHaveAttribute('href', '/collection/coins/new?catalogItemId=1');
  });

  it('tints the card when the coin is owned, plain otherwise', () => {
    const { container: missing } = render(<CoinCard item={makeItem({ quantityOwned: 0 })} />);
    expect(missing.querySelector('article')?.className ?? '').not.toMatch(/_owned_/);

    const { container: owned } = render(<CoinCard item={makeItem({ quantityOwned: 1 })} />);
    expect(owned.querySelector('article')?.className ?? '').toMatch(/_owned_/);
  });

  it('carries backTo through as router state, so the purchase form can return to it', () => {
    function LocationState() {
      const location = useLocation();
      return <output>{(location.state as { from?: string } | null)?.from ?? 'none'}</output>;
    }
    renderBare(
      <MemoryRouter initialEntries={['/missing']}>
        <Routes>
          <Route
            path="/missing"
            element={
              <CoinCard item={makeItem({ quantityOwned: 0 })} backTo="/collection/missing" />
            }
          />
          <Route path="/collection/coins/new" element={<LocationState />} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('link', { name: /Додати до колекції/ }));
    expect(screen.getByText('/collection/missing')).toBeInTheDocument();
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
});

describe('CoinCard series link', () => {
  it('links the series name to its page when a matching id is passed in', () => {
    render(
      <CoinCard
        item={makeItem({ seriesName: 'Видатні особистості України' })}
        seriesIdByName={{ 'Видатні особистості України': 7 }}
      />,
    );
    const link = screen.getByRole('link', { name: 'Видатні особистості України' });
    expect(link).toHaveAttribute('href', '/collection/series/7');
  });

  it('falls back to plain text when there is no matching series id', () => {
    render(<CoinCard item={makeItem({ seriesName: 'Видатні особистості України' })} />);
    expect(
      screen.queryByRole('link', { name: 'Видатні особистості України' }),
    ).not.toBeInTheDocument();
    expect(screen.getByText('Видатні особистості України')).toBeInTheDocument();
  });

  it('shows a circulation stand-in label when a circulation coin has no series', () => {
    render(<CoinCard item={makeItem({ seriesName: null, collectionGroup: 'circulation' })} />);
    expect(screen.getByText('Обігові монети')).toBeInTheDocument();
  });

  it('shows nothing for a non-circulation coin with no series', () => {
    render(<CoinCard item={makeItem({ seriesName: null, collectionGroup: 'commemorative' })} />);
    expect(screen.queryByText('Обігові монети')).not.toBeInTheDocument();
  });
});

describe('CoinCard price source', () => {
  it('shows the source name as a link to sourceUrl in the footer, next to the price', () => {
    render(
      <CoinCard
        item={makeItem({
          priceSource: 'ucoin',
          sourceUrl: 'https://ucoin.net/coin/ua-5uah-2021',
        })}
      />,
    );
    const link = screen.getByRole('link', { name: /uCoin/ });
    expect(link).toHaveAttribute('href', 'https://ucoin.net/coin/ua-5uah-2021');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('shows the source name as plain muted text when there is no sourceUrl', () => {
    render(<CoinCard item={makeItem({ priceSource: 'ucoin', sourceUrl: null })} />);
    expect(screen.queryByRole('link', { name: /uCoin/ })).not.toBeInTheDocument();
    expect(screen.getByText('uCoin')).toBeInTheDocument();
  });
});
