/** Thin fetch wrapper for the CoinKeeper API.
 *
 * - The access token lives in memory only (docs/07-auth.md); the refresh
 *   token never reaches this code — it travels in an httpOnly cookie.
 * - A 401 on an authorised request triggers one refresh attempt through the
 *   cookie endpoint, then the original request is retried.
 * - RFC 7807 problem responses are parsed into a typed ApiError.
 * - Every request carries the interface language: the API answers with names
 *   in that locale (docs/03-api-contract.md).
 */

const API_BASE: string = import.meta.env.VITE_API_BASE ?? '/api/v1';

let accessToken: string | null = null;
let sessionVersion = 0;
let apiLocale = 'uk';
const listeners = new Set<(token: string | null) => void>();

export function setAccessToken(token: string | null): void {
  if (token === null) sessionVersion += 1;
  accessToken = token;
  for (const listener of listeners) listener(token);
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Which language the API should answer in. Set from the i18n locale. */
export function setApiLocale(locale: string): void {
  apiLocale = locale;
}

export function onAccessTokenChange(listener: (token: string | null) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  errors?: { field: string; message: string }[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly problemType: string;
  readonly detail: string;
  readonly fieldErrors: { field: string; message: string }[];

  constructor(status: number, problem: ProblemDetails) {
    super(problem.detail ?? problem.title ?? `HTTP ${status}`);
    this.name = 'ApiError';
    this.status = status;
    // The backend uses full URIs (https://…/problems/<slug>): keep the slug.
    this.problemType = problem.type?.split('/').pop() ?? 'unknown';
    this.detail = problem.detail ?? '';
    this.fieldErrors = problem.errors ?? [];
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** A Blob is sent as raw bytes; anything else is serialised as JSON. */
  body?: unknown;
  /** Attach the Authorization header and refresh on 401. Default true. */
  auth?: boolean;
  signal?: AbortSignal;
}

async function parseProblem(response: Response): Promise<ApiError> {
  let problem: ProblemDetails = {};
  try {
    problem = (await response.json()) as ProblemDetails;
  } catch {
    /* non-JSON error body: keep the bare status */
  }
  return new ApiError(response.status, problem);
}

async function rawRequest(path: string, options: RequestOptions, token: string | null) {
  const headers: Record<string, string> = { 'Accept-Language': apiLocale };
  // An image goes up as itself. Wrapping bytes in JSON would base64 them for
  // no gain — the avatar endpoint takes one file and no fields beside it.
  const isBlob = options.body instanceof Blob;
  if (options.body !== undefined) {
    headers['Content-Type'] = isBlob ? (options.body as Blob).type : 'application/json';
  }
  if (options.auth !== false && token) headers['Authorization'] = `Bearer ${token}`;
  const init: RequestInit = {
    method: options.method ?? 'GET',
    headers,
    // The refresh cookie must travel with auth endpoints.
    credentials: 'include',
  };
  if (options.body !== undefined) {
    init.body = isBlob ? (options.body as Blob) : JSON.stringify(options.body);
  }
  if (options.signal) init.signal = options.signal;
  return fetch(`${API_BASE}${path}`, init);
}

/** Deduplicated refresh: concurrent 401s share one attempt. */
let refreshInFlight: Promise<boolean> | null = null;

export async function tryRefresh(): Promise<boolean> {
  const version = sessionVersion;
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (version !== sessionVersion) return false;
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) setAccessToken(null);
        return false;
      }
      const session = (await response.json()) as { tokens: { accessToken: string } };
      if (version !== sessionVersion) return false;
      setAccessToken(session.tokens.accessToken);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const version = sessionVersion;
  const requestToken = accessToken;
  let response: Response;
  try {
    response = await rawRequest(path, options, accessToken);
  } catch {
    throw new ApiError(0, { type: 'network-error' });
  }

  if (requestToken && options.auth !== false && version !== sessionVersion) {
    throw new ApiError(401, { type: 'session-ended' });
  }
  if (response.status === 401 && options.auth !== false && requestToken) {
    if (accessToken !== requestToken || (await tryRefresh())) {
      try {
        response = await rawRequest(path, options, accessToken);
      } catch {
        throw new ApiError(0, { type: 'network-error' });
      }
      if (version !== sessionVersion) throw new ApiError(401, { type: 'session-ended' });
      if (response.status === 401) setAccessToken(null);
    }
  }

  if (!response.ok) throw await parseProblem(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Serialise defined, non-empty values into a query string. */
export function toQuery(
  params: Record<string, string | number | boolean | undefined | (string | number)[]>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue;
    if (Array.isArray(value)) {
      // Repeated keys (?countryId=1&countryId=2) — the shape a multi-select
      // filter sends and the backend's list[int] query params read
      // (docs/03-api-contract.md, 2026-09-12).
      for (const item of value) search.append(key, String(item));
      continue;
    }
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}
