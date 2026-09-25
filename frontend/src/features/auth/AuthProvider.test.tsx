import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { setAccessToken } from '@/shared/api/client';
import type { SessionOut } from '@/shared/api/types';

import { AuthProvider } from './AuthProvider';
import { GOOGLE_POPUP_FLOW_KEY } from './googlePopup';
import { useAuth } from './useAuth';

const SESSION: SessionOut = {
  user: {
    id: 7,
    email: 'owner@example.com',
    displayName: null,
    role: 'user',
    locale: 'uk',
    emailVerified: true,
    avatarUrl: null,
  },
  tokens: { accessToken: 'access-1', expiresIn: 900 },
};

function Probe() {
  const { ready, user, acceptSession } = useAuth();
  return (
    <>
      <span>{ready ? 'ready' : 'loading'}</span>
      <span>{user ? `user:${user.id}` : 'guest'}</span>
      <button type="button" onClick={() => acceptSession(SESSION, true)}>
        accept
      </button>
    </>
  );
}

describe('AuthProvider', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    localStorage.clear();
    sessionStorage.clear();
    setAccessToken(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('does not refresh inside the Google popup, leaving it to the opener', async () => {
    localStorage.setItem('ck-remember', '1');
    sessionStorage.setItem(GOOGLE_POPUP_FLOW_KEY, 'flow-1');

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(await screen.findByText('ready')).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('signs this tab out when another tab signs out', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await screen.findByText('ready');
    act(() => screen.getByRole('button', { name: 'accept' }).click());
    expect(screen.getByText('user:7')).toBeInTheDocument();

    const otherTab = new BroadcastChannel('ck-auth');
    otherTab.postMessage({ type: 'signed-out' });
    otherTab.close();

    await waitFor(() => expect(screen.getByText('guest')).toBeInTheDocument());
  });
});
