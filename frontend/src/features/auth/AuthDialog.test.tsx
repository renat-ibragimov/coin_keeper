import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { AuthDialogProvider } from './AuthDialog';
import { useAuthDialog } from './authDialogContext';
import * as authApi from './api';

const signIn = vi.fn();
vi.mock('./useAuth', () => ({ useAuth: () => ({ signIn }) }));
vi.mock('./api', () => ({
  register: vi.fn(),
  googleStatus: vi.fn().mockResolvedValue({ enabled: false }),
  resendVerification: vi.fn(),
}));

function Trigger() {
  const openAuth = useAuthDialog();
  const location = useLocation();
  return (
    <>
      <span data-testid="path">{location.pathname + location.search}</span>
      <button type="button" onClick={() => openAuth()}>
        Open login
      </button>
      <button type="button" onClick={() => openAuth('register')}>
        Open registration
      </button>
    </>
  );
}

function show() {
  return render(
    <MemoryRouter initialEntries={['/catalog/7?view=cards']}>
      <AuthDialogProvider>
        <Trigger />
      </AuthDialogProvider>
    </MemoryRouter>,
  );
}

describe('AuthDialog', () => {
  beforeEach(() => {
    sessionStorage.clear();
    signIn.mockReset().mockResolvedValue(undefined);
    vi.mocked(authApi.register).mockReset().mockResolvedValue(undefined);
  });

  it('signs in on the current page and closes the dialog', async () => {
    show();
    await userEvent.click(screen.getByRole('button', { name: 'Open login' }));
    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Email' }),
      'guest@example.test',
    );
    await userEvent.type(screen.getByLabelText('Пароль'), 'password1234');
    await userEvent.click(screen.getByRole('button', { name: 'Увійти' }));
    await waitFor(() =>
      expect(signIn).toHaveBeenCalledWith('guest@example.test', 'password1234', true),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('path')).toHaveTextContent('/catalog/7?view=cards');
  });

  it('keeps the page visible after registration and remembers it for email verification', async () => {
    show();
    await userEvent.click(screen.getByRole('button', { name: 'Open registration' }));
    await userEvent.type(await screen.findByRole('textbox', { name: 'Email' }), 'new@example.test');
    await userEvent.click(screen.getByRole('button', { name: 'Зареєструватися' }));
    await waitFor(() => expect(authApi.register).toHaveBeenCalled());
    expect(screen.getByRole('dialog', { name: 'Перевірте пошту' })).toBeInTheDocument();
    expect(screen.getByTestId('path')).toHaveTextContent('/catalog/7?view=cards');
    expect(sessionStorage.getItem('ck-auth-return')).toBe('/catalog/7?view=cards');
  });
});
