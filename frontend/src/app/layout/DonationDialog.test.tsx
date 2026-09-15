import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DONATION_URL } from '@/shared/config/donation';
import i18n from '@/shared/i18n';

import { DonationDialog } from './DonationDialog';

vi.mock('qrcode.react', () => ({
  QRCodeSVG: ({ value, title }: { value: string; title: string }) => (
    <svg data-value={value}>
      <title>{title}</title>
    </svg>
  ),
}));

function renderDialog(onClose = vi.fn()) {
  render(
    <MemoryRouter>
      <DonationDialog open onClose={onClose} />
    </MemoryRouter>,
  );
  return onClose;
}

describe('DonationDialog', () => {
  afterEach(async () => {
    await act(() => i18n.changeLanguage('uk'));
  });

  it('shows the Ukrainian donation options using the shared URL', () => {
    renderDialog();

    expect(screen.getByRole('heading', { name: 'Підтримати проєкт' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Відкрити банку monobank/ })).toHaveAttribute(
      'href',
      DONATION_URL,
    );
    expect(screen.getByTitle('QR-код банки monobank').closest('svg')).toHaveAttribute(
      'data-value',
      DONATION_URL,
    );
    expect(screen.getByText('Відскануйте QR-код з іншого пристрою')).toBeInTheDocument();
  });

  it('shows the English copy', async () => {
    await act(() => i18n.changeLanguage('en'));
    renderDialog();

    expect(screen.getByRole('heading', { name: 'Support the project' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open monobank Jar/ })).toHaveAttribute(
      'href',
      DONATION_URL,
    );
    expect(screen.getByText('Scan the QR code with another device')).toBeInTheDocument();
  });

  it('closes from the close button and Escape', () => {
    const onClose = renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'Закрити' }));
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
