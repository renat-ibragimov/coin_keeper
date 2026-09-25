import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import * as authApi from '../api';
import { GOOGLE_POPUP_CHANNEL, GOOGLE_POPUP_FLOW_KEY } from '../googlePopup';
import { GoogleSignIn } from './GoogleSignIn';

const completeGoogleSession = vi.fn();
vi.mock('../useAuth', () => ({ useAuth: () => ({ completeGoogleSession }) }));
vi.mock('../api', () => ({ googleStatus: vi.fn() }));

class FakeChannel {
  static latest: FakeChannel;
  onmessage:
    | ((
        message: MessageEvent<{ type: string; flowId: string; mode?: string; google?: string }>,
      ) => void)
    | null = null;
  close = vi.fn();

  constructor(name: string) {
    expect(name).toBe(GOOGLE_POPUP_CHANNEL);
    FakeChannel.latest = this;
  }
}

describe('GoogleSignIn', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal('BroadcastChannel', FakeChannel);
    vi.mocked(authApi.googleStatus).mockReset().mockResolvedValue({ enabled: true });
    completeGoogleSession.mockReset().mockResolvedValue(undefined);
  });

  it('completes OAuth in a popup and leaves the catalog tab in place', async () => {
    const popupStorage = new Map<string, string>();
    const popup = {
      closed: false,
      close: vi.fn(),
      location: { replace: vi.fn() },
      sessionStorage: {
        setItem: vi.fn((key: string, value: string) => popupStorage.set(key, value)),
      },
      opener: window,
    };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
    const onSuccess = vi.fn();
    render(<GoogleSignIn returnTo="/catalog/7" onSuccess={onSuccess} />);

    await userEvent.click(await screen.findByRole('link', { name: 'Продовжити з Google' }));
    expect(popup.location.replace).toHaveBeenCalledWith(
      new URL('/api/v1/auth/google/start', window.location.origin).href,
    );
    expect(popup.opener).toBeNull();
    expect(sessionStorage.getItem('ck-auth-return')).toBe('/catalog/7');
    expect(completeGoogleSession).not.toHaveBeenCalled();

    FakeChannel.latest.onmessage?.({
      data: { type: 'complete', flowId: popupStorage.get(GOOGLE_POPUP_FLOW_KEY) },
    } as MessageEvent<{ type: string; flowId: string; mode?: string; google?: string }>);
    await waitFor(() => expect(onSuccess).toHaveBeenCalledOnce());
    expect(completeGoogleSession).toHaveBeenCalledWith(true);
    expect(popup.close).toHaveBeenCalled();
    expect(sessionStorage.getItem('ck-auth-return')).toBeNull();
  });
  it.each([
    ['login', 'link-required'],
    ['login', 'email-unconfirmed'],
  ])('returns OAuth %s results to the original dialog', async (mode, google) => {
    const popupStorage = new Map<string, string>();
    const popup = {
      closed: false,
      close: vi.fn(),
      location: { replace: vi.fn() },
      sessionStorage: { setItem: (key: string, value: string) => popupStorage.set(key, value) },
      opener: window,
    };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
    const onResult = vi.fn();
    render(<GoogleSignIn returnTo="/catalog/7" onResult={onResult} />);
    await userEvent.click(await screen.findByRole('link', { name: 'Продовжити з Google' }));
    FakeChannel.latest.onmessage?.({
      data: { type: 'result', flowId: popupStorage.get(GOOGLE_POPUP_FLOW_KEY), mode, google },
    } as MessageEvent<{ type: string; flowId: string; mode: string; google: string }>);
    expect(onResult).toHaveBeenCalledWith(mode, google);
    expect(completeGoogleSession).not.toHaveBeenCalled();
    expect(popup.close).toHaveBeenCalled();
  });
});
