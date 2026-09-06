/**
 * The HTTP client — 3/3 §8, §1 rule 7.
 *
 * Two properties are worth stating because both are easy to lose later.
 *
 * **The access token lives in memory only.** Not localStorage, not
 * sessionStorage — §8, and the reason is concrete rather than theoretical: a
 * dashboard left open on a shared OPD terminal is the exposure, and anything
 * persisted survives the tab being closed by the next person who sits down. The
 * refresh cookie is httpOnly and this code cannot read it, which is the point.
 *
 * **No clinical text ever reaches the console.** Errors carry a status, a
 * method and a path, and never a response body: a failed report fetch logged
 * with its payload is a patient's history in the browser console, which §1
 * rule 7 forbids and which every browser extension can read.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly method: string,
    readonly path: string,
  ) {
    // Deliberately not the server's message. A 422 from the backend can quote
    // the field it rejected, and the fields here are clinical.
    super(`${method} ${path} failed with ${status}`);
    this.name = 'ApiError';
  }

  /** Fail closed: an unauthenticated or under-privileged user sees a refusal. */
  get isAuthFailure() {
    return this.status === 401 || this.status === 403;
  }
}

let accessToken: string | null = null;
let principalHeaders: Record<string, string> = {};
let onAuthFailure: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

/**
 * The header principal — `X-User-Id` / `X-User-Role` / `X-Hospital-Id`.
 *
 * **A stand-in for the hospital's identity provider**, and the backend says so
 * itself: `app/api/auth.py` gates it on `ALLOW_HEADER_AUTH`, which is off in
 * any environment holding real data. It exists so this dashboard could be built
 * before the IdP integration was, and it is what the sign-in screen collects.
 *
 * Held in the same place as the access token and under the same rule: **memory
 * only**. When the IdP lands, `setAccessToken` is the path that survives and
 * this function is deleted along with the sign-in form.
 */
export function setPrincipalHeaders(headers: Record<string, string> | null) {
  principalHeaders = headers ?? {};
}

/** Called when the server refuses. The app clears its session and shows a refusal. */
export function setAuthFailureHandler(handler: () => void) {
  onAuthFailure = handler;
}

export const API_BASE = '/api/v1';

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    // The refresh cookie rides along; the access token is a header.
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...principalHeaders,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    ...(signal ? { signal } : {}),
  });

  if (!response.ok) {
    const error = new ApiError(response.status, method, path);
    if (error.isAuthFailure) onAuthFailure?.();
    throw error;
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>('GET', path, undefined, signal),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
};
