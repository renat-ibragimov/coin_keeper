import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import { ApiError } from '@/shared/api/client';

import { PasswordForm } from './PasswordForm';

describe('PasswordForm', () => {
  it('rejects a short or mismatched password before calling the API', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PasswordForm busy={false} submitError={null} onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText('Поточний пароль'), 'old-password');
    await userEvent.type(screen.getByLabelText('Новий пароль'), 'short');
    await userEvent.type(screen.getByLabelText('Повторіть пароль'), 'different');
    await userEvent.click(screen.getByRole('button', { name: 'Змінити пароль' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(
      screen.getByText('Пароль закороткий: потрібно щонайменше 10 символів.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Паролі не збігаються.')).toBeInTheDocument();
  });

  it('submits a valid pair and clears the fields afterwards', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<PasswordForm busy={false} submitError={null} onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText('Поточний пароль'), 'old-password');
    await userEvent.type(screen.getByLabelText('Новий пароль'), 'new-password-1');
    await userEvent.type(screen.getByLabelText('Повторіть пароль'), 'new-password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Змінити пароль' }));

    expect(onSubmit).toHaveBeenCalledWith('old-password', 'new-password-1');
    expect(screen.getByLabelText('Новий пароль')).toHaveValue('');
  });

  it('names a wrong current password', () => {
    render(
      <PasswordForm
        busy={false}
        submitError={new ApiError(401, { type: 'https://x/problems/invalid-credentials' })}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Поточний пароль невірний.');
  });
});
