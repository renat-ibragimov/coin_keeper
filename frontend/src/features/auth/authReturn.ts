const RETURN_KEY = 'ck-auth-return';

export function safeAuthReturn(value: string | null | undefined): string | null {
  return value?.startsWith('/') && !value.startsWith('//') ? value : null;
}

export function saveAuthReturn(value: string | null | undefined): void {
  const path = safeAuthReturn(value);
  if (path) sessionStorage.setItem(RETURN_KEY, path);
  else sessionStorage.removeItem(RETURN_KEY);
}

export function readAuthReturn(): string | null {
  return safeAuthReturn(sessionStorage.getItem(RETURN_KEY));
}

export function takeAuthReturn(): string | null {
  const path = readAuthReturn();
  sessionStorage.removeItem(RETURN_KEY);
  return path;
}
