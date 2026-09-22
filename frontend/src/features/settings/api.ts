import { api } from '@/shared/api/client';
import type { SettingsOut, UserOut } from '@/shared/api/types';

export function updateProfile(body: {
  displayName?: string | null;
  locale?: 'uk' | 'en';
}): Promise<UserOut> {
  return api<UserOut>('/auth/me', { method: 'PATCH', body });
}

export function updateSettings(body: {
  showPackagingVariants?: boolean;
  defaultGrade?: string;
  theme?: 'light' | 'dark' | 'system';
  catalogViewMode?: 'cards' | 'table';
  collectionViewMode?: 'cards' | 'table';
  secondaryCurrency?: 'USD' | 'EUR';
  defaultStorageLocation?: string;
  includeSupportingExpenses?: boolean;
}): Promise<SettingsOut> {
  return api<SettingsOut>('/bootstrap/settings', { method: 'PATCH', body });
}

/** Raw bytes, not multipart: one file with no fields beside it. */
export function uploadAvatar(image: Blob): Promise<UserOut> {
  return api<UserOut>('/auth/me/avatar', { method: 'PUT', body: image });
}

export function deleteAvatar(): Promise<UserOut> {
  return api<UserOut>('/auth/me/avatar', { method: 'DELETE' });
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return api<void>('/auth/change-password', {
    method: 'POST',
    body: { currentPassword, newPassword },
  });
}

export function setPassword(newPassword: string): Promise<void> {
  return api<void>('/auth/set-password', { method: 'POST', body: { newPassword } });
}
