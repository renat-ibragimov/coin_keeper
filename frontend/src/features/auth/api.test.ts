import { afterEach, describe, expect, it, vi } from 'vitest';

import { logout } from './api';

describe('auth api', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('signs out under the same cross-tab lock as refresh', async () => {
    const request = vi.fn((_name: string, work: () => Promise<unknown>) => work());
    vi.stubGlobal('navigator', { ...navigator, locks: { request } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await logout();

    expect(request).toHaveBeenCalledWith('ck-refresh', expect.any(Function));
  });
});
