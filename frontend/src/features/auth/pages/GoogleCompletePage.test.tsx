import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { GOOGLE_POPUP_CHANNEL, GOOGLE_POPUP_FLOW_KEY } from '../googlePopup';
import { GoogleCompletePage } from './GoogleCompletePage';

const completeGoogleSession = vi.fn();
vi.mock('../useAuth', () => ({ useAuth: () => ({ completeGoogleSession }) }));

class FakeChannel {
  static latest: FakeChannel;
  postMessage = vi.fn();
  close = vi.fn();

  constructor(name: string) {
    expect(name).toBe(GOOGLE_POPUP_CHANNEL);
    FakeChannel.latest = this;
  }
}

describe('GoogleCompletePage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    completeGoogleSession.mockReset();
    vi.stubGlobal('BroadcastChannel', FakeChannel);
  });

  it('signals the original tab when OAuth finishes in the popup', async () => {
    sessionStorage.setItem(GOOGLE_POPUP_FLOW_KEY, 'flow-123');
    const view = render(
      <MemoryRouter initialEntries={['/google-complete']}>
        <GoogleCompletePage />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(FakeChannel.latest.postMessage).toHaveBeenCalledWith({
        type: 'complete',
        flowId: 'flow-123',
      }),
    );
    expect(completeGoogleSession).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(GOOGLE_POPUP_FLOW_KEY)).toBeNull();
    view.unmount();
  });
});
