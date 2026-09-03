import { api } from '@/shared/api/client';
import type { UserOut } from '@/shared/api/types';

export function updateProfile(body: {
  displayName?: string | null;
  locale?: 'uk' | 'en';
}): Promise<UserOut> {
  return api<UserOut>('/auth/me', { method: 'PATCH', body });
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return api<void>('/auth/change-password', {
    method: 'POST',
    body: { currentPassword, newPassword },
  });
}
