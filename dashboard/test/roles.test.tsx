/**
 * Fail closed — 3/3 §11 item 5, §1 rule 6.
 *
 * The assertion is not "a patient sees an error". It is that a patient or kiosk
 * credential sees **a refusal and no clinical content at all** — no header
 * strip with the sections it may not read quietly missing, no worklist with
 * rows filtered out, and no request fired at the backend on its behalf. A
 * partially rendered clinical screen is indistinguishable from a short one, and
 * a physician glancing at it cannot tell which they are looking at.
 */
import { screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { App } from '../src/App';
import { renderWithProviders, signInAs, signOut, stubFetch } from './harness';

afterEach(() => {
  signOut();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const WORKLIST = {
  entries: [{ intake_id: 'i-1', state: 'ready', intake_status: 'complete', arrived_at: '2026-09-06T09:00:00Z', language: 'hi', patient_ref_type: 'guest', unacknowledged_alerts: 0, unresolved_count: 0, contradiction_count: 0 }],
  pending_alerts: [],
  total: 1,
};

describe('who may open this dashboard', () => {
  it('refuses a patient credential outright', async () => {
    const { calls } = stubFetch({ 'GET /worklist*': () => ({ body: WORKLIST }) });
    signInAs('patient');
    renderWithProviders(<App />);

    expect(await screen.findByTestId('refusal')).toBeVisible();
    expect(screen.queryByRole('table')).toBeNull();
    // Nothing was even asked for. A refusal that fires the request first has
    // already put the record in a response the browser can read.
    await waitFor(() => expect(calls).toHaveLength(0));
  });

  it('refuses a kiosk credential outright', async () => {
    stubFetch({ 'GET /worklist*': () => ({ body: WORKLIST }) });
    signInAs('kiosk');
    renderWithProviders(<App />);

    const refusal = await screen.findByTestId('refusal');
    expect(refusal).toBeVisible();
    expect(refusal.textContent).toMatch(/corridor/i);
  });

  it('shows the sign-in screen when there is no session at all', async () => {
    stubFetch({});
    renderWithProviders(<App />);
    expect(await screen.findByRole('button', { name: /open the worklist/i })).toBeVisible();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('lets a physician through to the worklist', async () => {
    stubFetch({ 'GET /worklist*': () => ({ body: WORKLIST }) });
    signInAs('physician');
    renderWithProviders(<App />, { route: '/' });
    expect(await screen.findByRole('table')).toBeVisible();
  });

  it('refuses a physician the admin-only quality view without hiding half of it', async () => {
    stubFetch({
      'GET /worklist*': () => ({ body: WORKLIST }),
      'GET /metrics/correction-rate': () => ({ body: { facts_reviewed: 9, correction_rate: 0.2 } }),
    });
    signInAs('physician');
    renderWithProviders(<App />, { route: '/metrics' });

    expect(await screen.findByTestId('refusal')).toBeVisible();
    expect(screen.queryByText(/correction rate/i)).toBeNull();
  });

  it('clears the session when the server refuses a request', async () => {
    // §1 rule 6, enforced in the transport rather than remembered per screen.
    const { setAuthFailureHandler } = await import('../src/api/client');
    const { useSession } = await import('../src/auth/session');
    setAuthFailureHandler(() => useSession.getState().signOut('refused'));

    stubFetch({ 'GET /worklist*': () => ({ status: 403, body: { code: 'forbidden' } }) });
    signInAs('staff');
    renderWithProviders(<App />);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /open the worklist/i })).toBeVisible(),
    );
    expect(screen.getByText(/server refused/i)).toBeVisible();
  });
});
