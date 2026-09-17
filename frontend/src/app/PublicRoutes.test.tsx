import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { CollectionRoot, RootRoute } from './App';
import { ProtectedRoute } from './ProtectedRoute';

const auth = vi.hoisted(() => ({ user: null as null | { id: number; role: string }, ready: true }));
vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => auth }));

describe('public routes', () => {
  it('sends anonymous root visitors to the catalog', () => {
    auth.user = null;
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<RootRoute />} />
          <Route path="/catalog" element={<p>Public catalog</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText('Public catalog')).toBeInTheDocument();
  });

  it('shows the collection preview without account data', () => {
    auth.user = null;
    render(
      <MemoryRouter initialEntries={['/collection']}>
        <Routes>
          <Route path="/collection" element={<CollectionRoot />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText('Тут з’явиться ваша колекція.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Створити колекцію' })).toHaveAttribute(
      'href',
      '/register',
    );
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
