/**
 * No clinical text in the console or in an error — 3/3 §11 item 9, §1 rule 7.
 *
 * Not a style preference. The browser console is readable by every extension
 * the physician has installed, and an error payload is what a front-end error
 * reporter would ship to a third party. A failed report fetch logged with its
 * body is a patient's history leaving the hospital.
 *
 * The assertion is made against a response that is *nothing but* clinical text,
 * so a leak anywhere in the transport shows up here.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { ApiError } from '../src/api/client';
import { AlertsPage } from '../src/alerts/AlertsPage';
import { ReportPage } from '../src/report/ReportPage';
import { renderWithProviders, signInAs, signOut, stubFetch } from './harness';

const PHI = 'पेट में दर्द तीन दिन से, मेटफॉर्मिन पाँच सौ';

afterEach(() => {
  signOut();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function captureConsole() {
  const written: string[] = [];
  for (const level of ['log', 'info', 'warn', 'error', 'debug'] as const) {
    vi.spyOn(console, level).mockImplementation((...args: unknown[]) => {
      written.push(args.map((arg) => String(arg)).join(' '));
    });
  }
  return written;
}

describe('what reaches the console', () => {
  it('carries no response body on an API error', () => {
    const error = new ApiError(422, 'GET', '/intakes/i-1/report');
    // Status, method and path, and those three only. A 422 from the backend
    // can quote the field it rejected, and the fields here are clinical — so
    // the body is never read, never attached, and never reachable from this
    // object however it is serialised.
    expect(error.message).toBe('GET /intakes/i-1/report failed with 422');
    expect(Object.keys({ ...error })).toEqual(['status', 'method', 'path', 'name']);
    expect(JSON.stringify(error)).not.toContain(PHI);
  });

  it('logs nothing clinical when a report fetch fails', async () => {
    const written = captureConsole();
    stubFetch({
      'GET /intakes/i-1': () => ({ status: 500, body: { detail: PHI } }),
      'GET /intakes/i-1/report': () => ({ status: 500, body: { detail: PHI } }),
      'GET /intakes/i-1/documents': () => ({ body: [] }),
    });
    signInAs('physician');
    renderWithProviders(
      <Routes>
        <Route path="/intakes/:intakeId" element={<ReportPage />} />
      </Routes>,
      { route: '/intakes/i-1' },
    );

    await waitFor(() => expect(screen.getByRole('alert')).toBeVisible());
    expect(written.join('\n')).not.toContain(PHI);
    // And the screen itself does not print the server's message either.
    expect(document.body.textContent).not.toContain(PHI);
  });

  it('logs nothing clinical when an acknowledgement is refused', async () => {
    const written = captureConsole();
    stubFetch({
      'GET /alerts*': () => ({
        body: {
          alerts: [
            {
              alert_id: 'a-1',
              intake_id: 'i-1',
              rule_id: 'gi_bleeding_suspected',
              severity: 'critical',
              label: 'Urgent clinical review criterion triggered',
              criteria_met: ['haematemesis'],
              received_at: '2026-09-06T09:00:00Z',
              arrived_at: '2026-09-06T08:55:00Z',
              intake_status: 'aborted_red_flag',
              language: 'hi',
              acknowledged_by: null,
            },
          ],
          unacknowledged: 1,
        },
      }),
      'POST /alerts/i-1/acknowledge': () => ({ status: 409, body: { message: PHI } }),
    });
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    await userEvent.click(await screen.findByTestId('acknowledge'));
    await screen.findByRole('alert');
    expect(written.join('\n')).not.toContain(PHI);
  });
});
