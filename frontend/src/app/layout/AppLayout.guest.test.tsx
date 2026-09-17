import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { ThemeContext } from '@/shared/theme/themeContext';
import { ToastProvider } from '@/shared/ui';
import { AppLayout } from './AppLayout';
import { DonationDialogContext } from './donationDialogContext';

const auth = vi.hoisted(() => ({
  user: null as null | { id: number; email: string; role: string },
}));
vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => ({ ...auth, signOut: vi.fn() }) }));

function show() {
  return render(
    <ThemeContext.Provider value={{ theme: 'light', preference: 'light', setPreference: vi.fn() }}>
      <ToastProvider>
        <DonationDialogContext.Provider value={vi.fn()}>
          <MemoryRouter initialEntries={['/catalog']}>
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="/catalog" element={<p>Catalog content</p>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </DonationDialogContext.Provider>
      </ToastProvider>
    </ThemeContext.Provider>,
  );
}

describe('AppLayout account state', () => {
  it('keeps both destinations and gives guests login and registration', () => {
    auth.user = null;
    show();
    expect(screen.getAllByRole('link', { name: 'Каталог' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('link', { name: 'Моя колекція' }).length).toBeGreaterThan(0);
    expect(screen.getByRole('link', { name: 'Увійти' })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: 'Створити акаунт' })).toHaveAttribute(
      'href',
      '/register',
    );
    expect(screen.getByText('Catalog content')).toBeInTheDocument();
  });

  it('offers account and display controls in the guest menu', async () => {
    auth.user = null;
    show();
    await userEvent.click(screen.getByRole('button', { name: 'Меню акаунта' }));
    expect(screen.getByRole('menuitem', { name: 'Увійти' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Створити акаунт' })).toBeInTheDocument();
    expect(screen.getByText('Мова інтерфейсу')).toBeInTheDocument();
    expect(screen.getByText('Тема')).toBeInTheDocument();
  });

  it('keeps the signed-in identity area', () => {
    auth.user = { id: 1, email: 'collector@example.com', role: 'user' };
    show();
    expect(screen.getByText('collector@example.com')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Створити акаунт' })).not.toBeInTheDocument();
  });
});
