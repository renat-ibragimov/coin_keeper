import { api } from '@/shared/api/client';
import type { SettingsOut, UserOut } from '@/shared/api/types';

export function updateProfile(body: {
  displayName?: string | null;
  locale?: 'uk' | 'en';
}): Promise<UserOut> {
  return api<UserOut>('/auth/me', { method: 'PATCH', body });
}

export function updateSettings(body: { showPackagingVariants: boolean }): Promise<SettingsOut> {
  return api<SettingsOut>('/bootstrap/settings', { method: 'PATCH', body });
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return api<void>('/auth/change-password', {
    method: 'POST',
    body: { currentPassword, newPassword },
  });
}
