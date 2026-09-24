import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { AuthDialogContext } from '@/features/auth/authDialogContext';
import { CollectionRoot, RootRoute } from './App';
import { GuestCollectionPage } from '@/features/collection/guest/GuestCollectionPage';
import { ProtectedRoute } from './ProtectedRoute';

const auth = vi.hoisted(() => ({ user: null as null | { id: number; role: string }, ready: true }));
vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => auth }));
vi.mock('@/features/landing/LandingPage', () => ({
  default: () => <h1>Collection landing page</h1>,
}));
const openAuth = vi.fn();

describe('public routes', () => {
  it('shows the landing page to anonymous root visitors', async () => {
    auth.user = null;
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<RootRoute />} />
          <Route path="/catalog" element={<p>Public catalog</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole('heading', { name: 'Collection landing page' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Public catalog')).not.toBeInTheDocument();
  });

  it('shows the collection preview without account data', () => {
    auth.user = null;
    render(
      <MemoryRouter initialEntries={['/collection']}>
        <AuthDialogContext.Provider value={openAuth}>
          <Routes>
            <Route path="/collection" element={<CollectionRoot />} />
          </Routes>
        </AuthDialogContext.Provider>
      </MemoryRouter>,
    );
    expect(screen.getByText('Ваш огляд у цифрах')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Увійти' })).toBeInTheDocument();
  });
  it.each([
    ['coins', 'Ваші монети поруч'],
    ['completeness', 'Від першої до повної'],
    ['money', 'Усі витрати на місці'],
  ] as const)('shows the %s guest section with a login action', (section, title) => {
    auth.user = null;
    render(
      <MemoryRouter initialEntries={[`/collection/${section}`]}>
        <AuthDialogContext.Provider value={openAuth}>
          <GuestCollectionPage section={section} />
        </AuthDialogContext.Provider>
      </MemoryRouter>,
    );
    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Увійти' })).toBeInTheDocument();
  });
  it('keeps personal pages behind authentication', () => {
    auth.user = null;
    render(
      <MemoryRouter initialEntries={['/collection/add']}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/collection/add" element={<p>Personal form</p>} />
          </Route>
          <Route path="/login" element={<p>Login form</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText('Login form')).toBeInTheDocument();
    expect(screen.queryByText('Personal form')).not.toBeInTheDocument();
  });

  it('keeps the collection as the signed-in root destination', () => {
    auth.user = { id: 1, role: 'user' };
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<RootRoute />} />
          <Route path="/collection" element={<p>Personal collection</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText('Personal collection')).toBeInTheDocument();
  });
});
