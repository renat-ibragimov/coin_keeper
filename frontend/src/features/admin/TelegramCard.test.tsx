import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { createTelegramLink, fetchTelegramStatus, unlinkTelegram } from './api';
import { TelegramCard } from './TelegramCard';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    fetchTelegramStatus: vi.fn(),
    createTelegramLink: vi.fn(),
    unlinkTelegram: vi.fn(),
  };
});

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TelegramCard />
    </QueryClientProvider>,
  );
}

describe('TelegramCard', () => {
  beforeEach(() => {
    vi.mocked(fetchTelegramStatus).mockReset();
    vi.mocked(createTelegramLink).mockReset();
    vi.mocked(unlinkTelegram).mockReset();
  });

  it('offers to connect while no chat is linked', async () => {
    vi.mocked(fetchTelegramStatus).mockResolvedValue({ connected: false, chats: 0 });
    renderCard();

    expect(await screen.findByRole('button', { name: 'Підключити Telegram' })).toBeInTheDocument();
    expect(screen.getByText('Не підключено')).toBeInTheDocument();
  });

  it('opens the bot link and then waits for Start to be pressed', async () => {
    vi.mocked(fetchTelegramStatus).mockResolvedValue({ connected: false, chats: 0 });
    vi.mocked(createTelegramLink).mockResolvedValue({
      url: 'https://t.me/bakost_test_bot?start=code',
      expiresAt: '2026-09-10T12:15:00Z',
    });
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'Підключити Telegram' }));

    await waitFor(() =>
      expect(open).toHaveBeenCalledWith(
        'https://t.me/bakost_test_bot?start=code',
        '_blank',
        'noopener',
      ),
    );
    expect(await screen.findByText(/Натисніть у ньому Start/)).toBeInTheDocument();
  });

  it('offers to disconnect once a chat is linked', async () => {
    vi.mocked(fetchTelegramStatus).mockResolvedValue({ connected: true, chats: 1 });
    vi.mocked(unlinkTelegram).mockResolvedValue(undefined);
    renderCard();

    await userEvent.click(await screen.findByRole('button', { name: 'Відключити' }));

    await waitFor(() => expect(unlinkTelegram).toHaveBeenCalled());
  });
});
