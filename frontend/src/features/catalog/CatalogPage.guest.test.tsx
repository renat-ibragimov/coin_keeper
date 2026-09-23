import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { fetchBootstrap } from '@/features/dashboard/api';

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
  beforeEach(() => localStorage.clear());

  it('starts in card view despite a saved signed-in table preference', async () => {
    localStorage.setItem('ck.viewMode.catalog', 'table');
    vi.mocked(fetchCatalog).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 30 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/catalog']}>
          <Routes>
            <Route path="/catalog" element={<CatalogPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('tab', { name: 'Картки' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await userEvent.click(screen.getByRole('tab', { name: 'Таблиця' }));
    expect(localStorage.getItem('ck.viewMode.catalog.guest')).toBe('table');
    expect(localStorage.getItem('ck.viewMode.catalog')).toBe('table');
  });

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
    expect(filters.sort).toBe('year');
    expect(screen.queryByText('Наявність')).not.toBeInTheDocument();
  });

  it('never fetches or shows the summary tiles for a guest', async () => {
    vi.mocked(fetchCatalog).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 30 });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/catalog']}>
          <Routes>
            <Route path="/catalog" element={<CatalogPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('heading', { name: 'Каталог монет' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Разом витрачено/ })).toBeNull();
    expect(fetchBootstrap).not.toHaveBeenCalled();
  });
});
