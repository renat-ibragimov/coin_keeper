import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthDialogContext } from '@/features/auth/authDialogContext';
import i18n from '@/shared/i18n';

import { GuestCollectionPage } from '../guest/GuestCollectionPage';
import { CollectionOnboarding } from './CollectionOnboarding';

beforeEach(async () => {
  await i18n.changeLanguage('en');
});
const action = <a href="/catalog">Browse catalog</a>;

describe('collection onboarding', () => {
  it.each(['dashboard', 'coins', 'completeness', 'money'] as const)(
    'keeps guest login available throughout %s',
    async (section) => {
      const openAuth = vi.fn();
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <AuthDialogContext.Provider value={openAuth}>
            <GuestCollectionPage section={section} />
          </AuthDialogContext.Provider>
        </MemoryRouter>,
      );
      for (let index = 0; index < 3; index++) {
        expect(
          screen.getByRole('heading', {
            name: i18n.t(`onboarding.${section}.slides.${index}.title`),
          }),
        ).toBeVisible();
        await user.click(screen.getByRole('button', { name: i18n.t('guest.login') }));
        expect(openAuth).toHaveBeenCalledTimes(index + 1);
        await user.click(screen.getByRole('button', { name: 'Next example' }));
      }
      expect(
        screen.getByRole('heading', { name: i18n.t(`onboarding.${section}.slides.0.title`) }),
      ).toBeVisible();
    },
  );

  it('supports keyboard navigation and direct selection while keeping the action intact', async () => {
    const user = userEvent.setup();
    render(<CollectionOnboarding section="coins" actions={action} />);
    const next = screen.getByRole('button', { name: 'Next example' });
    next.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('heading', { name: 'Find the right coin' })).toBeVisible();
    expect(next).toHaveFocus();
    await user.keyboard('{End}');
    expect(screen.getByRole('button', { name: 'Show example 3' })).toHaveAttribute(
      'aria-current',
      'step',
    );
    expect(screen.queryByRole('heading', { name: 'Cards or a table' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Show example 1' }));
    expect(screen.getByRole('heading', { name: 'Cards or a table' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Browse catalog' })).toHaveAttribute(
      'href',
      '/catalog',
    );
  });

  it('resets the slide when a reused guest route changes section', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<CollectionOnboarding section="coins" actions={action} />);
    await user.click(screen.getByRole('button', { name: 'Show example 3' }));
    rerender(<CollectionOnboarding section="money" actions={action} />);
    expect(screen.getByRole('heading', { name: 'Coins and related expenses' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Show example 1' })).toHaveAttribute(
      'aria-current',
      'step',
    );
  });

  it('accepts horizontal swipes and leaves vertical scrolling alone', () => {
    render(<CollectionOnboarding section="coins" actions={action} />);
    const slides = document.getElementById(
      screen.getByRole('button', { name: 'Next example' }).getAttribute('aria-controls')!,
    )!;
    fireEvent.touchStart(slides, { touches: [{ clientX: 200, clientY: 100 }] });
    fireEvent.touchEnd(slides, { changedTouches: [{ clientX: 190, clientY: 230 }] });
    expect(screen.getByRole('heading', { name: 'Cards or a table' })).toBeVisible();
    fireEvent.touchStart(slides, { touches: [{ clientX: 250, clientY: 100 }] });
    fireEvent.touchEnd(slides, { changedTouches: [{ clientX: 100, clientY: 110 }] });
    expect(screen.getByRole('heading', { name: 'Find the right coin' })).toBeVisible();
  });
});
