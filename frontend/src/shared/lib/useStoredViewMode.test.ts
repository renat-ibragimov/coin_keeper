import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchBootstrap } from '@/features/dashboard/api';
import { updateSettings } from '@/features/settings/api';

import { useStoredViewMode } from './useStoredViewMode';

vi.mock('@/features/dashboard/api', () => ({ fetchBootstrap: vi.fn() }));
vi.mock('@/features/settings/api', () => ({ updateSettings: vi.fn() }));

function renderStoredViewMode(key: string, field: 'catalogViewMode' | 'collectionViewMode') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderHook(() => useStoredViewMode(key, field), {
    wrapper: ({ children }) => createElement(QueryClientProvider, { client }, children),
  });
}

describe('useStoredViewMode', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(fetchBootstrap)
      .mockReset()
      .mockReturnValue(new Promise(() => {}));
    vi.mocked(updateSettings).mockReset().mockResolvedValue({
      locale: 'uk',
      displayCurrency: 'UAH',
      defaultGrade: 'UNC',
      showPackagingVariants: true,
      theme: 'system',
      catalogViewMode: 'cards',
      collectionViewMode: 'cards',
      secondaryCurrency: 'USD',
      defaultStorageLocation: null,
    });
  });

  it('prefers an explicit URL value over anything stored', () => {
    localStorage.setItem('ck.viewMode.test', 'table');
    const { result } = renderStoredViewMode('ck.viewMode.test', 'catalogViewMode');
    expect(result.current.resolve('cards')).toBe('cards');
  });

  it('falls back to the stored value when the URL says nothing and the server has not answered yet', () => {
    localStorage.setItem('ck.viewMode.test', 'table');
    const { result } = renderStoredViewMode('ck.viewMode.test', 'catalogViewMode');
    expect(result.current.resolve(undefined)).toBe('table');
  });

  it('defaults to cards when the URL, storage and server all say nothing', () => {
    const { result } = renderStoredViewMode('ck.viewMode.test', 'catalogViewMode');
    expect(result.current.resolve(undefined)).toBe('cards');
  });

  it('ignores a garbage stored value', () => {
    localStorage.setItem('ck.viewMode.test', 'map');
    const { result } = renderStoredViewMode('ck.viewMode.test', 'catalogViewMode');
    expect(result.current.resolve(undefined)).toBe('cards');
  });

  it('remembers an explicit choice under its own key and persists it to the server', async () => {
    const { result } = renderStoredViewMode('ck.viewMode.catalog', 'catalogViewMode');
    act(() => result.current.remember('table'));
    expect(localStorage.getItem('ck.viewMode.catalog')).toBe('table');
    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ catalogViewMode: 'table' }));

    const other = renderStoredViewMode('ck.viewMode.collection', 'collectionViewMode');
    expect(other.result.current.resolve(undefined)).toBe('cards');
  });
});
