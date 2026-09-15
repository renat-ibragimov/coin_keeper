import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/shared/i18n';

import { SiteFooter } from './SiteFooter';

vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => ({ user: null }) }));
vi.mock('@/shared/ui', () => ({ useToast: () => ({ show: vi.fn() }) }));

function renderFooter() {
  return render(
    <MemoryRouter>
      <SiteFooter />
    </MemoryRouter>,
  );
}

describe('SiteFooter', () => {
  afterEach(async () => {
    await act(() => i18n.changeLanguage('uk'));
  });

  it('shows the Ukrainian copy, flag and current year', () => {
    renderFooter();

    expect(screen.getByText('З України з любов’ю')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Прапор України' })).toHaveTextContent('🇺🇦');
    expect(
      screen.getByText(`© ${new Date().getFullYear()} Bakost Numismatics`),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Допомога' })).toBeEnabled();
    expect(screen.getByText('Підтримати проєкт')).toHaveAttribute('aria-disabled', 'true');
  });

  it('switches its copy to English', async () => {
    await act(() => i18n.changeLanguage('en'));
    renderFooter();

    expect(screen.getByText('From Ukraine with love')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Flag of Ukraine' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Help' })).toBeInTheDocument();
    expect(screen.getByText('Support the project')).toBeInTheDocument();
  });
});
