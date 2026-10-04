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
import userEvent from '@testing-library/user-event';
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
    expect(await screen.findByRole('button', { name: /sign in to opd queue/i })).toBeVisible();
    expect(screen.queryByRole('list', { name: /opd queue/i })).toBeNull();
  });

  it('lets a physician through to the worklist', async () => {
    stubFetch({ 'GET /worklist*': () => ({ body: WORKLIST }) });
    signInAs('physician');
    renderWithProviders(<App />, { route: '/' });
    expect(await screen.findByRole('list', { name: /opd queue/i })).toBeVisible();
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
      expect(screen.getByRole('button', { name: /sign in to opd queue/i })).toBeVisible(),
    );
    expect(screen.getByText(/server refused/i)).toBeVisible();
  });
});

/**
 * The front desk and the pharmacy counter.
 *
 * Both belong on this dashboard and neither belongs in a patient's record, and
 * the whole phase turns on those being different questions. `canSeeClinicalContent`
 * used to mean "is the role in `DASHBOARD_ROLES`", so adding either role would
 * silently have granted it every clinical screen. These tests are what stops
 * that being reintroduced by somebody adding a sixth role to the union.
 */
describe('a receptionist', () => {
  it('reaches the front desk', async () => {
    stubFetch({ 'GET /worklist*': () => ({ body: WORKLIST }) });
    signInAs('receptionist');
    renderWithProviders(<App />, { route: '/reception' });

    expect(await screen.findByTestId('reception-queue')).toBeVisible();
    expect(screen.queryByTestId('refusal')).toBeNull();
  });

  it('is refused the report, and asks the backend for no part of it', async () => {
    const { calls } = stubFetch({
      'GET /intakes/i-1': () => ({ body: {} }),
      'GET /intakes/i-1/report*': () => ({ body: {} }),
      'GET /hospitals': () => ({ body: { hospitals: [] } }),
    });
    signInAs('receptionist');
    renderWithProviders(<App />, { route: '/intakes/i-1' });

    expect(await screen.findByTestId('refusal')).toBeVisible();

    // The refusal is a role decision, taken before anything clinical is
    // fetched. A screen that asks first has already put the record in a
    // response, whatever it then chooses to render.
    //
    // Scoped to clinical routes rather than asserting zero requests outright:
    // the shell around the refusal legitimately loads the facility directory
    // for the header, which names a hospital and never a patient. Asserting
    // "nothing at all" would make a chrome request look like a leak, and —
    // worse — a future chrome request could be "fixed" by relaxing this into
    // something that no longer checks the record at all.
    const clinical = calls.filter((call) => call.path.includes('/intakes/'));
    await waitFor(() => expect(clinical).toHaveLength(0));
  });

  it('is refused the worklist itself', async () => {
    stubFetch({ 'GET /worklist*': () => ({ body: WORKLIST }) });
    signInAs('receptionist');
    renderWithProviders(<App />, { route: '/' });

    expect(await screen.findByTestId('refusal')).toBeVisible();
  });

  it('shows no symptom text anywhere on its own screen', async () => {
    // The queue payload has no field that could carry one, and this asserts
    // the screen does not go looking for a name either.
    stubFetch({ 'GET /worklist*': () => ({ body: WORKLIST }) });
    signInAs('receptionist');
    renderWithProviders(<App />, { route: '/reception' });

    await screen.findByTestId('reception-queue');
    const rendered = document.body.textContent ?? '';
    for (const forbidden of ['पेट में दर्द', 'abdominal', 'fever', 'breathlessness']) {
      expect(rendered.toLowerCase()).not.toContain(forbidden.toLowerCase());
    }
  });
});

describe('a chemist', () => {
  it('reaches the pharmacy', async () => {
    stubFetch({
      'GET /pharmacy/alerts': () => ({ body: { generated_at: '2026-09-06T09:00:00Z', alerts: [] } }),
    });
    signInAs('chemist');
    renderWithProviders(<App />, { route: '/pharmacy' });

    expect(await screen.findByTestId('pharmacy-stock')).toBeVisible();
  });

  it('is refused the report and the worklist', async () => {
    for (const route of ['/intakes/i-1', '/']) {
      const { unmount } = renderWithProviders(<App />, { route });
      signInAs('chemist');
      expect(await screen.findByTestId('refusal')).toBeVisible();
      unmount();
    }
  });
});

describe('the nav', () => {
  it('offers each role only the screens it may open', async () => {
    stubFetch({
      'GET /pharmacy/alerts': () => ({ body: { generated_at: '2026-09-06T09:00:00Z', alerts: [] } }),
    });
    signInAs('chemist');
    renderWithProviders(<App />, { route: '/pharmacy' });

    await screen.findByTestId('pharmacy-stock');
    // A tab that leads to a refusal is a tab that should not be drawn.
    expect(screen.queryByRole('link', { name: /worklist/i })).toBeNull();
    expect(screen.queryByRole('link', { name: /alerts/i })).toBeNull();
  });
});

/**
 * Signing in lands you on a screen your role may open.
 *
 * Distinct from the refusals above, and the distinction is the point.
 * `RequireDashboardRole` refuses rather than redirects on purpose — a redirect
 * tells an account it merely needs to try again, which is false. But that is
 * the right answer for somebody who *navigated to* a screen, not for somebody
 * who just signed in: they asked for nothing in particular, and the URL is
 * whatever the previous person on a shared OPD terminal left behind.
 *
 * Before this, a pharmacist signing in behind a receptionist saw "Not available
 * to this role" for `/reception` — a screen they had never asked for — and had
 * to discover the nav tab to get anywhere.
 */
describe('signing in', () => {
  it('sends a chemist to the pharmacy even from the front desk URL', async () => {
    stubFetch({
      'GET /hospitals': () => ({ body: { hospitals: [] } }),
      'GET /pharmacy/alerts*': () => ({ body: { alerts: [], generated_at: null } }),
    });
    renderWithProviders(<App />, { route: '/reception' });

    await userEvent.click(await screen.findByRole('button', { name: /demo: pharmacy/i }));

    expect(await screen.findByTestId('pharmacy-stock')).toBeVisible();
    expect(screen.queryByTestId('refusal')).toBeNull();
  });

  it('sends a receptionist to the front desk even from a report URL', async () => {
    stubFetch({
      'GET /hospitals': () => ({ body: { hospitals: [] } }),
      'GET /worklist*': () => ({ body: WORKLIST }),
    });
    renderWithProviders(<App />, { route: '/intakes/i-1' });

    await userEvent.click(
      await screen.findByRole('button', { name: /demo: receptionist/i }),
    );

    expect(await screen.findByTestId('reception-queue')).toBeVisible();
    expect(screen.queryByTestId('refusal')).toBeNull();
  });
});
