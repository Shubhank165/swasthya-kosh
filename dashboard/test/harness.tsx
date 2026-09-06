/**
 * Test scaffolding.
 *
 * `renderWithProviders` gives a component the three things the real app gives
 * it — a query client, a router and a session — and nothing else. Notably it
 * does **not** stub the API client: tests stub `fetch`, so the request the
 * component actually makes is the thing under test. A mocked query layer would
 * pass whatever shape the test invented.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { vi } from 'vitest';

import { useSession, type DashboardRole, type Session } from '../src/auth/session';

export function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function signInAs(role: DashboardRole | 'patient' | 'kiosk', overrides: Partial<Session> = {}) {
  useSession.getState().signIn({
    userId: `test-${role}`,
    // Cast because the store's type excludes `patient` and `kiosk` by design —
    // and a test that proves they are refused has to be able to smuggle one in.
    role: role as DashboardRole,
    hospitalId: 'aiia-delhi',
    departmentCode: null,
    ...overrides,
  });
}

export function signOut() {
  useSession.getState().signOut();
}

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', ...options }: { route?: string } & RenderOptions = {},
) {
  const client = makeClient();
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { client, ...render(ui, { wrapper: Wrapper, ...options }) };
}

/**
 * A `fetch` that answers from a routing table.
 *
 * Keyed by `METHOD /path` with the `/api/v1` prefix stripped, so the assertion
 * a test makes about a URL is about the URL the client built.
 */
export type Route = (request: { body: unknown; url: string }) =>
  | { status?: number; body?: unknown }
  | Promise<{ status?: number; body?: unknown }>;

export function stubFetch(routes: Record<string, Route>) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  const impl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? 'GET').toUpperCase();
    const path = url.replace(/^\/api\/v1/, '');
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body });

    const exact = routes[`${method} ${path}`];
    const prefix = Object.entries(routes).find(([key]) => {
      const [routeMethod, routePath] = key.split(' ');
      return routeMethod === method && routePath?.endsWith('*') &&
        path.startsWith(routePath.slice(0, -1));
    })?.[1];
    const handler = exact ?? prefix;
    if (!handler) {
      return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } });
    }
    const result = await handler({ body, url });
    return new Response(JSON.stringify(result.body ?? {}), {
      status: result.status ?? 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  vi.stubGlobal('fetch', impl);
  return { calls, impl };
}
