import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import i18n from '@/shared/i18n';

import { landingCopy } from './copy';
import LandingPage from './LandingPage';

vi.mock('@/features/auth/useAuth', () => ({ useAuth: () => ({ user: null }) }));
vi.mock('@/features/auth/authDialogContext', () => ({ useAuthDialog: () => vi.fn() }));
vi.mock('./ExpensesDemo', () => ({ ExpensesDemo: () => null }));

function renderLanding() {
  render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );
}

describe('landing collection preview', () => {
  it.each(['uk', 'en'] as const)('keeps the sample total when filtering in %s', async (locale) => {
    await i18n.changeLanguage(locale);
    const user = userEvent.setup();
    const c = landingCopy[locale];
    renderLanding();
    const collection = screen.getByRole('region', { name: c.collectionTitle });
    const preview = within(collection);
    expect(preview.getByText(c.coinsShown(3, 3))).toBeInTheDocument();
    const search = preview.getByRole('searchbox');
    await user.type(search, c.demoNames[0]!);
    expect(preview.getByText(c.coinsShown(1, 3))).toBeInTheDocument();
    await user.type(search, 'unmatched');
    expect(preview.getByText(c.coinsShown(0, 3))).toBeInTheDocument();
    expect(preview.getByText(i18n.t('catalog.emptyTitle'))).toBeInTheDocument();
    expect(preview.queryByRole('table')).not.toBeInTheDocument();
    await user.click(preview.getAllByRole('button', { name: i18n.t('catalog.resetFilters') })[0]!);
    expect(preview.getByText(c.coinsShown(3, 3))).toBeInTheDocument();
  });

  it('labels spending accurately and orders coins by descending purchase cost', async () => {
    await i18n.changeLanguage('en');
    const user = userEvent.setup();
    renderLanding();
    const preview = within(screen.getByRole('region', { name: /Your collection. Your rules./ }));
    await user.selectOptions(
      preview.getByRole('combobox', { name: i18n.t('catalog.sort') }),
      'cost',
    );
    expect(preview.getByRole('option', { name: 'By amount spent' })).toHaveProperty(
      'selected',
      true,
    );
    const rows = within(preview.getByRole('table')).getAllByRole('row').slice(1);
    expect(rows.map((row) => within(row).getAllByRole('cell')[0]?.textContent)).toEqual([
      expect.stringContaining(landingCopy.en.demoNames[0]!),
      expect.stringContaining(landingCopy.en.demoNames[2]!),
      expect.stringContaining(landingCopy.en.demoNames[1]!),
    ]);
    const notice = preview.getByText(landingCopy.en.interactiveDemo).parentElement!;
    expect(notice).toHaveTextContent(landingCopy.en.collectionDemoHint);
    expect(notice.closest('a, button')).toBeNull();
  });
});
