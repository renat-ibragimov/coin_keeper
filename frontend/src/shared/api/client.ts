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
let apiLocale = 'uk';
const listeners = new Set<(token: string | null) => void>();

export function setAccessToken(token: string | null): void {
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
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
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
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (options.auth !== false && token) headers['Authorization'] = `Bearer ${token}`;
  const init: RequestInit = {
    method: options.method ?? 'GET',
    headers,
    // The refresh cookie must travel with auth endpoints.
    credentials: 'include',
  };
  if (options.body !== undefined) init.body = JSON.stringify(options.body);
  if (options.signal) init.signal = options.signal;
  return fetch(`${API_BASE}${path}`, init);
}

/** Deduplicated refresh: concurrent 401s share one attempt. */
let refreshInFlight: Promise<boolean> | null = null;

export async function tryRefresh(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        setAccessToken(null);
        return false;
      }
      const session = (await response.json()) as { tokens: { accessToken: string } };
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
  let response: Response;
  try {
    response = await rawRequest(path, options, accessToken);
  } catch {
    throw new ApiError(0, { type: 'network-error' });
  }

  if (response.status === 401 && options.auth !== false && (await tryRefresh())) {
    response = await rawRequest(path, options, accessToken);
  }

  if (!response.ok) throw await parseProblem(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Serialise defined, non-empty values into a query string. */
export function toQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue;
    search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}
