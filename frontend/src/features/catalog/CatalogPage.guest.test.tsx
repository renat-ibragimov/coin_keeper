import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { CatalogPage } from './CatalogPage';
import { fetchCatalog } from './api';

vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => ({ user: null }) }));
vi.mock('./api', () => ({
  fetchCatalog: vi.fn(),
  fetchCountries: vi.fn().mockResolvedValue([]),
  fetchDenominations: vi.fn().mockResolvedValue([]),
  fetchSeries: vi.fn().mockResolvedValue([]),
  fetchCatalogMaterials: vi.fn().mockResolvedValue([]),
}));
vi.mock('@/features/dashboard/api', () => ({ fetchBootstrap: vi.fn() }));

describe('public CatalogPage', () => {
  it('loads the real catalog endpoint and keeps personal filters out', async () => {
    vi.mocked(fetchCatalog).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 30 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/catalog?owned=true&sort=price']}>
          <Routes>
            <Route path="/catalog" element={<CatalogPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('heading', { name: 'Каталог монет' })).toBeInTheDocument();
    expect(fetchCatalog).toHaveBeenCalled();
    const filters = vi.mocked(fetchCatalog).mock.calls[0]![0];
    expect(filters.owned).toBeUndefined();
    expect(filters.sort).toBe('title');
    expect(screen.queryByText('Наявність')).not.toBeInTheDocument();
  });
});
