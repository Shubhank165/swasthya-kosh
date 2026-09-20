/// Talking to the backend.
///
/// Requests go to a *relative* path and Vite proxies them, which is how the
/// production build works too: the dashboard is served from the same origin as
/// the API, so there is no base URL baked into the bundle and no CORS. A
/// second host in the client would be one more thing to get wrong per
/// deployment.
///
/// **Identity is a header, not a token, and that is temporary.** The deployment
/// this talks to runs with `ALLOW_HEADER_AUTH=true` for the demo, which means
/// these headers are the whole of the authentication. That is a deliberate,
/// dated downgrade recorded on the backend side; when it is turned off, the
/// only thing that changes here is where `identity()` gets its values.

import type { ApiHospital, ApiIntake, ApiWorklist } from './types';

export interface Identity {
  userId: string;
  role: 'physician' | 'nurse' | 'receptionist';
  hospitalId: string;
}

/** Who the dashboard is acting as. One place, so a real session can replace it. */
export const DEFAULT_IDENTITY: Identity = {
  userId: 'dr.sharma',
  role: 'physician',
  hospitalId: 'aiia-delhi',
};

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

function headers(identity: Identity): HeadersInit {
  return {
    'X-User-Id': identity.userId,
    'X-User-Role': identity.role,
    'X-Hospital-Id': identity.hospitalId,
    Accept: 'application/json',
  };
}

async function get<T>(path: string, identity: Identity, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { headers: headers(identity), signal });
  if (!response.ok) {
    // The body is not shown to a physician — it can carry a stack trace — but it
    // is worth carrying to whoever is reading the console.
    throw new ApiError(response.status, `${path} -> ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  worklist: (identity: Identity, signal?: AbortSignal) =>
    get<ApiWorklist>('/worklist', identity, signal),

  intake: (intakeId: string, identity: Identity, signal?: AbortSignal) =>
    get<ApiIntake>(`/intakes/${encodeURIComponent(intakeId)}`, identity, signal),

  hospitals: (identity: Identity, signal?: AbortSignal) =>
    get<{ hospitals: ApiHospital[] }>('/hospitals', identity, signal),
};
