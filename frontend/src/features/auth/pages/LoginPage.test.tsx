import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { LoginForm } from './LoginPage';

vi.mock('../useAuth', () => ({ useAuth: () => ({ signIn: vi.fn() }) }));
vi.mock('../api', () => ({ googleStatus: vi.fn().mockResolvedValue({ enabled: false }) }));

describe('LoginForm', () => {
  it('explains how to sign up when Google does not vouch for the address', () => {
    render(
      <MemoryRouter>
        <LoginForm from="/collection" onSuccess={vi.fn()} google="email-unconfirmed" />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(
        "Google не підтверджує цю адресу. Зареєструйтеся з email і паролем, а потім прив'яжіть Google у налаштуваннях.",
      ),
    ).toBeInTheDocument();
  });
});
