/**
 * Triage alerts — 3/3 §11 item 4, §1 rule 2, §4.3.
 *
 * One rule dominates this file: **acknowledging is not escalating, and the two
 * are never one control.** Acknowledgement records that a human looked. It
 * authorises nothing. A single button that did both would mean every clinician
 * who glanced at an alert had, on the record, escalated it.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AlertsPage } from '../src/alerts/AlertsPage';
import { renderWithProviders, signInAs, signOut, stubFetch } from './harness';

afterEach(() => {
  signOut();
  vi.unstubAllGlobals();
});

const ALERT = {
  alert_id: 'a-1',
  intake_id: 'i-1',
  department_code: 'kayachikitsa',
  rule_id: 'gi_bleeding_suspected',
  severity: 'critical',
  label: 'Urgent clinical review criterion triggered',
  criteria_met: ['haematemesis'],
  fired_at_turn: 4,
  engine_version: 'rules-1.2',
  received_at: '2026-09-06T09:00:00Z',
  arrived_at: '2026-09-06T08:55:00Z',
  intake_status: 'aborted_red_flag',
  language: 'hi',
  acknowledged_by: null,
  acknowledged_at: null,
  acknowledgement_note: null,
};

function stub(overrides: Record<string, unknown> = {}) {
  return stubFetch({
    'GET /alerts*': () => ({
      body: { alerts: [{ ...ALERT, ...overrides }], unacknowledged: 1 },
    }),
    'POST /alerts/i-1/acknowledge': () => ({
      body: {
        intake_id: 'i-1',
        rule_id: 'gi_bleeding_suspected',
        acknowledged_by: 'test-physician',
        acknowledged_at: '2026-09-06T09:05:00Z',
      },
    }),
  });
}

describe('the alerts view', () => {
  it('keeps acknowledge and escalate as two separate controls', async () => {
    stub();
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    const card = await screen.findByTestId('alert-card');
    const acknowledge = within(card).getByTestId('acknowledge');
    const escalate = within(card).getByTestId('escalate');
    expect(acknowledge).not.toBe(escalate);
    // And escalation takes a second, explicit confirmation on top of that.
    expect(within(card).queryByTestId('escalate-confirm')).toBeNull();
  });

  it('acknowledging records the acting user and escalates nothing', async () => {
    const { calls } = stub();
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    await userEvent.click(await screen.findByTestId('acknowledge'));
    await waitFor(() =>
      expect(calls.some((call) => call.method === 'POST')).toBe(true),
    );

    const post = calls.find((call) => call.method === 'POST')!;
    expect(post.path).toBe('/alerts/i-1/acknowledge');
    // The acting user comes from the credential, not from the body — the
    // backend takes it from the principal, and this must not be sending one.
    expect(post.body).toEqual({ rule_id: 'gi_bleeding_suspected' });
    // Nothing in this request says "escalate".
    expect(JSON.stringify(post.body)).not.toMatch(/escalat/i);
  });

  it('records an escalation only after a second, explicit confirmation', async () => {
    const { calls } = stub();
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    await userEvent.click(await screen.findByTestId('escalate'));
    // Still nothing sent: the first click only reveals the confirmation.
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);

    await userEvent.click(screen.getByTestId('escalate-confirm'));
    await waitFor(() =>
      expect(calls.some((call) => call.method === 'POST')).toBe(true),
    );
    const post = calls.find((call) => call.method === 'POST')!;
    expect(String((post.body as { note: string }).note)).toMatch(/escalated to triage/i);
  });

  it('never names a condition', async () => {
    stub();
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    const card = await screen.findByTestId('alert-card');
    // The rule's own fixed wording, and the criteria that met it. Nothing that
    // reads as a diagnosis the device is not in a position to make.
    expect(
      within(card).getByText('Urgent clinical review criterion triggered'),
    ).toBeVisible();
    expect(within(card).getByText('haematemesis')).toBeVisible();
    expect(card.textContent).not.toMatch(/diagnos/i);
  });

  it('keeps an acknowledged alert on screen rather than making it vanish', async () => {
    stub({
      acknowledged_by: 'dr-sharma',
      acknowledged_at: '2026-09-06T09:05:00Z',
      acknowledgement_note: 'seen, patient stable',
    });
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    const card = await screen.findByTestId('alert-card');
    expect(card).toHaveAttribute('data-acknowledged', 'true');
    expect(within(card).getByText(/dr-sharma/)).toBeVisible();
    expect(within(card).queryByTestId('acknowledge')).toBeNull();
    expect(within(card).queryByTestId('escalate')).toBeNull();
  });

  it('says so when the acknowledgement is refused rather than looking successful', async () => {
    stubFetch({
      'GET /alerts*': () => ({ body: { alerts: [ALERT], unacknowledged: 1 } }),
      'POST /alerts/i-1/acknowledge': () => ({
        status: 409,
        body: { code: 'conflict' },
      }),
    });
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    await userEvent.click(await screen.findByTestId('acknowledge'));
    // Two people each assuming the other has seen it is the failure worth
    // being noisy about — the backend returns 409 and the screen must say so.
    expect(await screen.findByRole('alert')).toHaveTextContent(/already have been acknowledged/i);
  });
});
