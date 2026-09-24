import { StrictMode } from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import '@/shared/i18n';
import type { SessionOut } from '@/shared/api/types';
import { getAccessToken, setAccessToken } from '@/shared/api/client';
import { ProtectedRoute } from '@/app/ProtectedRoute';
import { AuthProvider } from './AuthProvider';
import { AuthDialogProvider } from './AuthDialog';
import { AuthEntry } from './AuthEntry';
import { useAuth } from './useAuth';
import { useAuthDialog } from './authDialogContext';
import { useSessionDraft } from './useSessionDraft';
import { setDraftOwner } from './sessionDrafts';
import * as authApi from './api';

vi.mock('./api', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
  googleStatus: vi.fn(),
  forgotPassword: vi.fn(),
}));
const session = (id = 7) =>
  ({
    user: { id, email: 'member@example.test', role: 'user' },
    tokens: { accessToken: `token-${id}` },
  }) as SessionOut;
function Controls() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const open = useAuthDialog();
  if (!auth.ready) return <p>Restoring</p>;
  return (
    <>
      <output data-testid="path">{location.pathname + location.search + location.hash}</output>
      <output data-testid="member">{auth.user?.id ?? 'guest'}</output>
      <button onClick={() => auth.acceptSession(session(), false)}>Start session</button>
      <button onClick={() => void auth.signOut()}>Sign out</button>
      <button onClick={() => open()}>Open sign in</button>
      <button onClick={() => open('login', { from: '/collection/add?catalogItemId=42' })}>
        Add selected coin
      </button>
      <button onClick={() => navigate(-1)}>Go back</button>
    </>
  );
}
function Form() {
  const [value, setValue] = useSessionDraft('test:note', '');
  return (
    <input
      aria-label="Purchase note"
      value={value}
      onChange={(event) => setValue(event.target.value)}
    />
  );
}
function show(path = '/catalog?q=silver#coins', history?: string[]) {
  return render(
    <StrictMode>
      <AuthProvider>
        <MemoryRouter initialEntries={history ?? [path]}>
          <AuthDialogProvider>
            <Controls />
            <Routes>
              <Route path="/login" element={<AuthEntry mode="login" />} />
              <Route path="/register" element={<AuthEntry mode="register" />} />
              <Route path="/forgot-password" element={<AuthEntry mode="forgot-password" />} />
              <Route path="/check-email" element={<AuthEntry mode="check-email" />} />
              <Route element={<ProtectedRoute />}>
                <Route path="/collection/add" element={<Form />} />
                <Route path="/settings" element={<p>Account settings</p>} />
              </Route>
              <Route path="*" element={<p>Public site</p>} />
            </Routes>
          </AuthDialogProvider>
        </MemoryRouter>
      </AuthProvider>
    </StrictMode>,
  );
}
async function signIn() {
  const dialog = await screen.findByRole('dialog');
  await userEvent.type(
    await within(dialog).findByRole('textbox', { name: 'Email' }),
    'member@example.test',
  );
  await userEvent.type(within(dialog).getByLabelText('Пароль'), 'password1234');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Увійти' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
}
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  setAccessToken(null);
  setDraftOwner(null);
  vi.mocked(authApi.login).mockReset().mockResolvedValue(session());
  vi.mocked(authApi.logout).mockReset().mockResolvedValue(undefined);
  vi.mocked(authApi.googleStatus).mockResolvedValue({ enabled: false });
  vi.mocked(authApi.forgotPassword).mockResolvedValue(undefined);
});
describe('auth navigation', () => {
  it('resumes the exact private URL after login on a public background', async () => {
    show('/collection/add?catalogItemId=42#purchase');
    await screen.findByRole('dialog');
    expect(screen.getByTestId('path')).toHaveTextContent('/collection/coins');
    expect(screen.queryByLabelText('Purchase note')).not.toBeInTheDocument();
    await signIn();
    expect(screen.getByTestId('path')).toHaveTextContent(
      '/collection/add?catalogItemId=42#purchase',
    );
    expect(screen.getByLabelText('Purchase note')).toBeInTheDocument();
  });
  it('does not reopen a dismissed request on Back', async () => {
    show('', ['/catalog', '/collection/add']);
    await screen.findByRole('dialog');
    await userEvent.keyboard('{Escape}');
    await userEvent.click(screen.getByText('Go back'));
    expect(screen.getByTestId('path')).toHaveTextContent('/catalog');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it.each(['/login', '/register', '/forgot-password', '/check-email'])(
    'keeps %s on the public site',
    async (path) => {
      show(path);
      await screen.findByRole('dialog');
      expect(screen.getByTestId('path')).toHaveTextContent('/collection');
      await userEvent.keyboard('{Escape}');
      expect(screen.getByText('Public site')).toBeInTheDocument();
    },
  );
  it('continues a selected action after login', async () => {
    show();
    await userEvent.click(await screen.findByText('Add selected coin'));
    await signIn();
    expect(screen.getByTestId('path')).toHaveTextContent('/collection/add?catalogItemId=42');
  });
  it('keeps password recovery inside the dialog', async () => {
    show();
    await userEvent.click(await screen.findByText('Open sign in'));
    await userEvent.click(await screen.findByRole('button', { name: 'Забули пароль?' }));
    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Email' }),
      'member@example.test',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Надіслати посилання' }));
    await waitFor(() => expect(authApi.forgotPassword).toHaveBeenCalledWith('member@example.test'));
    expect(screen.getByTestId('path')).toHaveTextContent('/catalog?q=silver#coins');
    await userEvent.keyboard('{Escape}');
    expect(sessionStorage.getItem('ck-auth-return')).toBe('/catalog?q=silver#coins');
  });
  it('signs out in place without reopening login', async () => {
    show();
    await userEvent.click(await screen.findByText('Start session'));
    await userEvent.click(screen.getByText('Sign out'));
    expect(screen.getByTestId('member')).toHaveTextContent('guest');
    expect(screen.getByTestId('path')).toHaveTextContent('/catalog?q=silver#coins');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
  });
  it('leaves settings for the homepage on voluntary sign out', async () => {
    show('/settings');
    await signIn();
    await userEvent.click(screen.getByText('Sign out'));
    await waitFor(() => expect(screen.getByTestId('path').textContent).toBe('/'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('restores a form after expiry and same-account reauthentication', async () => {
    show('/collection/add');
    await signIn();
    await userEvent.type(screen.getByLabelText('Purchase note'), 'Keep this note');
    act(() => setAccessToken(null));
    expect(
      await screen.findByText('Сеанс завершився. Увійдіть знову, щоб продовжити.'),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Purchase note')).not.toBeInTheDocument();
    await signIn();
    expect(screen.getByLabelText('Purchase note')).toHaveValue('Keep this note');
  });
  it('does not restore another account’s draft', async () => {
    show('/collection/add');
    await signIn();
    await userEvent.type(screen.getByLabelText('Purchase note'), 'Private note');
    act(() => setAccessToken(null));
    await screen.findByRole('dialog');
    vi.mocked(authApi.login).mockResolvedValue(session(8));
    await signIn();
    expect(screen.getByLabelText('Purchase note')).toHaveValue('');
  });
  it('remembers a temporary session only in this tab', async () => {
    show();
    await userEvent.click(await screen.findByText('Start session'));
    expect(localStorage.getItem('ck-remember')).toBeNull();
    expect(sessionStorage.getItem('ck-remember')).toBe('1');
    await userEvent.click(screen.getByText('Sign out'));
    expect(sessionStorage.getItem('ck-remember')).toBeNull();
  });
  it('restores a temporary session after reloading the tab', async () => {
    sessionStorage.setItem('ck-remember', '1');
    vi.mocked(authApi.me).mockResolvedValue(session().user);
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify({ tokens: { accessToken: 'restored' } }), { status: 200 }),
      );
    try {
      show();
      await waitFor(() => expect(screen.getByTestId('member')).toHaveTextContent('7'));
      expect(authApi.me).toHaveBeenCalled();
      expect(localStorage.getItem('ck-remember')).toBeNull();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it('clears an unsaved form on a voluntary logout', async () => {
    show('/collection/add');
    await signIn();
    await userEvent.type(screen.getByLabelText('Purchase note'), 'Discard on logout');
    await userEvent.click(screen.getByText('Sign out'));
    await userEvent.click(screen.getByText('Add selected coin'));
    await signIn();
    expect(screen.getByLabelText('Purchase note')).toHaveValue('');
  });
  it('does not continue navigation when a submitted login dialog was dismissed', async () => {
    let finish!: (session: SessionOut) => void;
    vi.mocked(authApi.login).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    show();
    await userEvent.click(await screen.findByText('Add selected coin'));
    await userEvent.type(
      await screen.findByRole('textbox', { name: 'Email' }),
      'member@example.test',
    );
    await userEvent.type(screen.getByLabelText('Пароль'), 'password1234');
    await userEvent.click(screen.getByRole('button', { name: 'Увійти' }));
    await userEvent.keyboard('{Escape}');
    await act(async () => {
      finish(session());
    });
    expect(screen.getByTestId('path')).toHaveTextContent('/catalog?q=silver#coins');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
