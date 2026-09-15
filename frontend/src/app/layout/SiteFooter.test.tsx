import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import i18n from '@/shared/i18n';

import { SiteFooter } from './SiteFooter';

describe('SiteFooter', () => {
  afterEach(async () => {
    await act(() => i18n.changeLanguage('uk'));
  });

  it('shows the Ukrainian copy, flag and current year', () => {
    render(<SiteFooter />);

    expect(screen.getByText('З України з любов’ю')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Прапор України' })).toHaveTextContent('🇺🇦');
    expect(
      screen.getByText(`© ${new Date().getFullYear()} Bakost Numismatics`),
    ).toBeInTheDocument();
    expect(screen.getByText('Підтримка')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText('Підтримати розвиток сайту')).toHaveAttribute('aria-disabled', 'true');
  });

  it('switches its copy to English', async () => {
    await act(() => i18n.changeLanguage('en'));
    render(<SiteFooter />);

    expect(screen.getByText('From Ukraine with love')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Flag of Ukraine' })).toBeInTheDocument();
    expect(screen.getByText('Support')).toBeInTheDocument();
    expect(screen.getByText('Support the project')).toBeInTheDocument();
  });
});
