import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { api, ApiError, setAccessToken, toQuery } from './client';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('api client', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    setAccessToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('attaches the bearer token to authorised requests', async () => {
    setAccessToken('token-1');
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await api('/catalog');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/catalog');
    expect((init.headers as Record<string, string>)['Authorization']).toBe('Bearer token-1');
  });

  it('parses RFC 7807 problems into a typed error', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, {
        type: 'https://coinkeeper.app/problems/shared-catalog-read-only',
        title: 'Forbidden',
        status: 403,
        detail: 'The shared catalog is read-only.',
      }),
    );

    const failure = await api('/catalog/1', { method: 'PATCH', body: {} }).catch((e: unknown) => e);

    expect(failure).toBeInstanceOf(ApiError);
    const apiError = failure as ApiError;
    expect(apiError.status).toBe(403);
    expect(apiError.problemType).toBe('shared-catalog-read-only');
    expect(apiError.detail).toBe('The shared catalog is read-only.');
  });

  it('refreshes once on 401 and retries the original request', async () => {
    setAccessToken('stale');
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(200, { tokens: { accessToken: 'fresh' } }))
      .mockResolvedValueOnce(jsonResponse(200, { items: [] }));

    const result = await api<{ items: unknown[] }>('/catalog');

    expect(result.items).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const refreshCall = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(refreshCall[0]).toBe('/api/v1/auth/refresh');
    const retryCall = fetchMock.mock.calls[2] as [string, RequestInit];
    expect((retryCall[1].headers as Record<string, string>)['Authorization']).toBe('Bearer fresh');
  });

  it('gives up when the refresh also fails', async () => {
    setAccessToken('stale');
    fetchMock
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired' }))
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'no cookie' }));

    const failure = await api('/catalog').catch((e: unknown) => e);

    expect((failure as ApiError).status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('toQuery', () => {
  it('skips undefined and empty values', () => {
    expect(toQuery({ a: 1, b: undefined, c: '', d: 'x', e: false })).toBe('?a=1&d=x&e=false');
  });

  it('returns an empty string with no values', () => {
    expect(toQuery({})).toBe('');
  });
});
