const RETURN_KEY = 'ck-auth-return';
const AUTH_PATHS = new Set([
  '/login',
  '/register',
  '/forgot-password',
  '/check-email',
  '/verify-email',
  '/reset-password',
  '/google-complete',
]);

export function safeAuthReturn(value: string | null | undefined): string | null {
  if (
    !value?.startsWith('/') ||
    value.startsWith('//') ||
    value.includes('\\') ||
    [...value].some((char) => char.charCodeAt(0) <= 32)
  )
    return null;
  const url = new URL(value, 'https://bakost.invalid');
  if (url.origin !== 'https://bakost.invalid' || AUTH_PATHS.has(url.pathname.replace(/\/+$/, '')))
    return null;
  return url.pathname + url.search + url.hash;
}

/** The nearest public screen for a private destination. */
export function guestDestination(value: string): string {
  const path = safeAuthReturn(value) ?? '/';
  const pathname = path.split(/[?#]/)[0]!.replace(/\/+$/, '') || '/';
  if (pathname === '/settings' || pathname === '/admin') return '/';
  if (pathname.startsWith('/collection/completeness/')) return '/collection/completeness';
  if (
    pathname.startsWith('/collection/') &&
    !['/collection/coins', '/collection/completeness', '/collection/money'].includes(pathname)
  )
    return '/collection/coins';
  return path;
}

export function saveAuthReturn(value: string | null | undefined): void {
  try {
    const path = safeAuthReturn(value);
    if (path) sessionStorage.setItem(RETURN_KEY, path);
    else sessionStorage.removeItem(RETURN_KEY);
  } catch {
    /* Navigation still works when storage is unavailable. */
  }
}

export function readAuthReturn(): string | null {
  try {
    return safeAuthReturn(sessionStorage.getItem(RETURN_KEY));
  } catch {
    return null;
  }
}

export function takeAuthReturn(): string | null {
  const path = readAuthReturn();
  saveAuthReturn(null);
  return path;
}
