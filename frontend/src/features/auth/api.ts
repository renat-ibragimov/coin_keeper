import { api } from '@/shared/api/client';
import type { SessionOut, UserOut } from '@/shared/api/types';

export function login(email: string, password: string): Promise<SessionOut> {
  return api<SessionOut>('/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: false,
  });
}

export function register(input: {
  email: string;
  password: string;
  displayName?: string;
  website?: string;
}): Promise<void> {
  return api<void>('/auth/register', { method: 'POST', body: input, auth: false });
}

export function resendVerification(email: string): Promise<void> {
  return api<void>('/auth/resend-verification', { method: 'POST', body: { email }, auth: false });
}

export function verifyEmail(token: string): Promise<SessionOut> {
  return api<SessionOut>('/auth/verify-email', { method: 'POST', body: { token }, auth: false });
}

export function forgotPassword(email: string): Promise<void> {
  return api<void>('/auth/forgot-password', { method: 'POST', body: { email }, auth: false });
}

export function resetPassword(token: string, newPassword: string): Promise<void> {
  return api<void>('/auth/reset-password', {
    method: 'POST',
    body: { token, newPassword },
    auth: false,
  });
}

export function logout(): Promise<void> {
  return api<void>('/auth/logout', { method: 'POST', auth: false });
}

export function me(): Promise<UserOut> {
  return api<UserOut>('/auth/me');
}
