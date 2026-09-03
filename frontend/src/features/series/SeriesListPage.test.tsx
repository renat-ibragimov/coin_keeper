import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { SeriesProgress } from '@/shared/api/types';

import { fetchCountries } from '@/features/catalog/api';

import { fetchSeriesProgress } from './api';
import { SeriesListPage } from './SeriesListPage';
import { sortSeries } from './sort';

vi.mock('./api', () => ({ fetchSeriesProgress: vi.fn(), fetchSeriesSummary: vi.fn() }));
vi.mock('@/features/catalog/api', () => ({ fetchCountries: vi.fn() }));

function progress(id: number, name: string, owned: number, total: number): SeriesProgress {
  return {
    series: {
      id,
      countryId: 1,
      name,
      nameRu: null,
      nameEn: null,
      description: null,
      startYear: null,
      endYear: null,
    },
    summary: {
      total,
      owned,
      missing: total - owned,
      completionPercent: total ? Math.round((owned / total) * 1000) / 10 : 0,
      purchaseTotalUah: '100.00',
      currentValueUah: '250.00',
      unpricedMissing: total - owned > 0 ? 1 : 0,
    },
  };
}

const ROWS = [
  progress(1, 'Half', 5, 10),
  progress(2, 'Almost', 19, 20),
  progress(3, 'Done', 3, 3),
  progress(4, 'Empty', 0, 0),
];

describe('sortSeries', () => {
  it('puts the most complete series first and can sort by name', () => {
    expect(sortSeries(ROWS, 'completion').map((row) => row.series.name)).toEqual([
      'Done',
      'Almost',
      'Half',
      'Empty',
    ]);
    expect(sortSeries(ROWS, 'name').map((row) => row.series.name)).toEqual([
      'Almost',
      'Done',
      'Empty',
      'Half',
    ]);
  });
});

describe('SeriesListPage', () => {
  it('renders every series with its progress, spend and valuation', async () => {
    vi.mocked(fetchSeriesProgress).mockResolvedValue(ROWS);
    vi.mocked(fetchCountries).mockResolvedValue([
      { id: 1, code: 'UA', name: 'Україна', nameRu: null, nameEn: null, collectVariants: false },
    ]);
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <SeriesListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('link', { name: 'Almost' })).toHaveAttribute(
      'href',
      '/series/2',
    );
    expect(screen.getByText('19 з 20')).toBeInTheDocument();
    expect(screen.getAllByText('100 ₴')).toHaveLength(4);
    expect(screen.getAllByText('250 ₴')).toHaveLength(4);
    expect(screen.getAllByText('Україна').length).toBeGreaterThan(0);
  });
});
