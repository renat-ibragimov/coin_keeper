import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import * as authApi from '../api';
import { VerifyEmailPage } from './VerifyEmailPage';

vi.mock('../useAuth', () => ({ useAuth: () => ({ acceptSession: vi.fn() }) }));
vi.mock('../api', () => ({ verifyEmail: vi.fn() }));

describe('VerifyEmailPage', () => {
  it('always asks for a password, whatever the link carries', () => {
    window.history.replaceState(null, '', '/verify-email?token=abc&google=1');
    render(
      <MemoryRouter>
        <VerifyEmailPage />
      </MemoryRouter>,
    );
    expect(screen.getAllByLabelText(/пароль/i).length).toBeGreaterThan(0);
    expect(authApi.verifyEmail).not.toHaveBeenCalled();
  });
});
