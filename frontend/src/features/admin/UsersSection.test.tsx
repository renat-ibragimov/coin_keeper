import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';

import { fetchAdminUsers, setAdminUserRole } from './api';
import { UsersSection } from './UsersSection';

vi.mock('@/features/auth/useAuth', () => ({
  useAuth: () => ({ user: { id: 1 } }),
}));

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return { ...actual, fetchAdminUsers: vi.fn(), setAdminUserRole: vi.fn() };
});

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UsersSection page={1} onPageChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

const page = {
  items: [
    {
      id: 1,
      email: 'owner@example.com',
      displayName: 'Owner',
      role: 'admin',
      isActive: true,
      emailVerified: true,
      createdAt: '2026-09-01T10:00:00Z',
      coinCount: 0,
    },
    {
      id: 2,
      email: 'collector@example.com',
      displayName: null,
      role: 'user',
      isActive: true,
      emailVerified: true,
      createdAt: '2026-09-02T10:00:00Z',
      coinCount: 12,
    },
  ],
  total: 2,
  page: 1,
  pageSize: 20,
  summary: { totalUsers: 2, collectors: 1 },
};

describe('UsersSection', () => {
  beforeEach(() => {
    vi.mocked(fetchAdminUsers).mockResolvedValue(page);
    vi.mocked(setAdminUserRole).mockReset();
  });

  it('shows live user analytics and collection size', async () => {
    renderSection();
    expect(await screen.findByText('Усього користувачів')).toBeInTheDocument();
    expect(screen.getByText('Почали колекцію')).toBeInTheDocument();
    expect(screen.getByText('collector@example.com')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('changes a role by user id while self-demotion stays unavailable', async () => {
    vi.mocked(setAdminUserRole).mockResolvedValue({ ...page.items[1]!, role: 'admin' });
    renderSection();
    const removeSelf = await screen.findByRole('button', { name: 'Зняти роль' });
    expect(removeSelf).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Зробити адміном' }));
    await waitFor(() => expect(setAdminUserRole).toHaveBeenCalledWith(2, 'admin'));
  });
});
