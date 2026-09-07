import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useStoredViewMode } from './useStoredViewMode';

describe('useStoredViewMode', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('prefers an explicit URL value over anything stored', () => {
    localStorage.setItem('ck.viewMode.test', 'table');
    const { result } = renderHook(() => useStoredViewMode('ck.viewMode.test'));
    expect(result.current.resolve('cards')).toBe('cards');
  });

  it('falls back to the stored value when the URL says nothing', () => {
    localStorage.setItem('ck.viewMode.test', 'table');
    const { result } = renderHook(() => useStoredViewMode('ck.viewMode.test'));
    expect(result.current.resolve(undefined)).toBe('table');
  });

  it('defaults to cards when neither the URL nor storage has a value', () => {
    const { result } = renderHook(() => useStoredViewMode('ck.viewMode.test'));
    expect(result.current.resolve(undefined)).toBe('cards');
  });

  it('ignores a garbage stored value', () => {
    localStorage.setItem('ck.viewMode.test', 'map');
    const { result } = renderHook(() => useStoredViewMode('ck.viewMode.test'));
    expect(result.current.resolve(undefined)).toBe('cards');
  });

  it('remembers an explicit choice under its own key', () => {
    const { result } = renderHook(() => useStoredViewMode('ck.viewMode.catalog'));
    result.current.remember('table');
    expect(localStorage.getItem('ck.viewMode.catalog')).toBe('table');

    const other = renderHook(() => useStoredViewMode('ck.viewMode.collection'));
    expect(other.result.current.resolve(undefined)).toBe('cards');
  });
});
