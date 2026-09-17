import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { AuthDialogContext } from '@/features/auth/authDialogContext';
import { ThemeContext } from '@/shared/theme/themeContext';
import { ToastProvider } from '@/shared/ui';
import { AppLayout } from './AppLayout';
import { DonationDialogContext } from './donationDialogContext';

const auth = vi.hoisted(() => ({
  user: null as null | { id: number; email: string; role: string },
}));
vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => ({ ...auth, signOut: vi.fn() }) }));
const openAuth = vi.fn();

function show(path = '/catalog') {
  return render(
    <ThemeContext.Provider value={{ theme: 'light', preference: 'light', setPreference: vi.fn() }}>
      <ToastProvider>
        <DonationDialogContext.Provider value={vi.fn()}>
          <MemoryRouter initialEntries={[path]}>
            <AuthDialogContext.Provider value={openAuth}>
              <Routes>
                <Route element={<AppLayout />}>
                  <Route path="/catalog" element={<p>Catalog content</p>} />
                  <Route path="/collection/coins" element={<p>Guest coins content</p>} />
                </Route>
              </Routes>
            </AuthDialogContext.Provider>
          </MemoryRouter>
        </DonationDialogContext.Provider>
      </ToastProvider>
    </ThemeContext.Provider>,
  );
}

describe('AppLayout account state', () => {
  it('keeps both destinations and opens login without leaving the catalog', async () => {
    auth.user = null;
    show();
    expect(screen.getAllByRole('link', { name: 'Каталог' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Моя колекція' }).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole('button', { name: 'Увійти' }));
    expect(openAuth).toHaveBeenCalledWith();
    expect(screen.queryByRole('link', { name: 'Створити акаунт' })).not.toBeInTheDocument();
    expect(screen.getByText('Catalog content')).toBeInTheDocument();
  });

  it('offers login and display controls in the guest menu', async () => {
    auth.user = null;
    show();
    await userEvent.click(screen.getByRole('button', { name: 'Меню акаунта' }));
    expect(screen.getByRole('menuitem', { name: 'Увійти' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Створити акаунт' })).not.toBeInTheDocument();
    expect(screen.getByText('Мова інтерфейсу')).toBeInTheDocument();
    expect(screen.getByText('Тема')).toBeInTheDocument();
  });

  it('shows collection sections in the guest navigation', () => {
    auth.user = null;
    show('/collection/coins');
    expect(screen.getByText('Guest coins content')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Монети' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Серії' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Гроші' }).length).toBeGreaterThan(0);
  });

  it('keeps the signed-in identity area', () => {
    auth.user = { id: 1, email: 'collector@example.com', role: 'user' };
    show();
    expect(screen.getByText('collector@example.com')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Створити акаунт' })).not.toBeInTheDocument();
  });
});
