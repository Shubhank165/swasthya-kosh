/**
 * The report screen end to end — 3/3 §11 items 3 and 7, §5, §6.
 *
 * Against a stubbed backend rather than a stubbed query layer, so what is under
 * test is the request the page actually makes and the shape it actually
 * expects. The two things asserted hardest are the two the demo rests on:
 * **one click from a line to its evidence**, and **an amendment that sends the
 * typed value in the shape the record holds**.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';

import { ReportPage } from '../src/report/ReportPage';
import { renderWithProviders, signInAs, signOut, stubFetch } from './harness';

/** The row a line lives in, so a per-line control is not ambiguous. */
function lineFor(text: string) {
  const row = screen.getByText(text).closest('li');
  if (row === null) throw new Error(`no report line for ${text}`);
  return within(row);
}

afterEach(() => {
  signOut();
  vi.unstubAllGlobals();
});

const INTAKE = {
  intake_id: 'i-1',
  hospital_id: 'aiia-delhi',
  status: 'complete',
  language: 'hi',
  department_code: 'kayachikitsa',
  patient_ref: { type: 'hospital_id', value: 'UHID-1' },
  red_flags: [],
  documents: [],
  contradictions: [],
  unresolved_fields: ['severity'],
  needs_review: false,
  provenance: {},
  received_at: '2026-09-06T08:55:00Z',
  demo: false,
  facts: [
    {
      fact_id: 'f-duration',
      field_id: 'duration',
      label: 'Duration',
      status: 'answered',
      value: { kind: 'duration', magnitude: 3, unit: 'day' },
      rendered: '3 days',
      original_text: 'तीन दिन से',
      language: 'hi',
      certainty: 'reported',
      channel: 'voice',
      section: 'hpi',
      confidence: 0.91,
      physician_verified: false,
      physician_action: null,
      repaired: false,
      needs_verification: false,
      carried_forward: null,
      source: { kind: 'turn', turn_id: 3, question_id: 'ask_duration', transcript_excerpt: 'तीन दिन से' },
      recorded_at: '2026-09-06T08:55:00Z',
    },
    {
      fact_id: 'f-hba1c',
      field_id: 'hba1c',
      label: 'HbA1c',
      status: 'answered',
      value: { kind: 'quantity', magnitude: 8.2, unit: '%' },
      rendered: '8.2 %',
      original_text: 'HbA1c 8.2',
      language: 'en',
      certainty: 'reported',
      channel: 'document',
      section: 'investigations',
      confidence: 0.71,
      physician_verified: false,
      physician_action: null,
      repaired: false,
      needs_verification: true,
      carried_forward: null,
      source: { kind: 'document', document_id: 'doc-1', page: 1, bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.05 } },
      recorded_at: '2026-09-06T08:56:00Z',
    },
  ],
};

const REPORT = {
  intake_id: 'i-1',
  language: 'hi',
  template_version: '1.0',
  text: 'Chief complaint: abdominal pain\n',
  physician_verified_by: null,
  demo: false,
  report: {
    intake_id: 'i-1',
    hospital_id: 'aiia-delhi',
    language: 'hi',
    sections: [
      {
        section: 'hpi',
        title: 'History of present illness',
        lines: [
          { text: 'Abdominal pain for 3 days', fact_ids: ['f-duration'], original_text: 'तीन दिन से', original_language: 'hi' },
        ],
      },
      {
        section: 'investigations',
        title: 'Prior investigations',
        lines: [
          {
            text: 'HbA1c 8.2%, 12 June',
            fact_ids: ['f-hba1c'],
            markers: [{ code: 'verify', text: 'check against the scan' }],
          },
        ],
      },
    ],
    unresolved: [{ text: 'Severity — not established', fact_ids: [] }],
    conflicts: [],
  },
};

const EVIDENCE: Record<string, unknown> = {
  'f-duration': {
    fact_id: 'f-duration',
    field_id: 'duration',
    status: 'answered',
    value: { kind: 'duration', magnitude: 3, unit: 'day' },
    original_text: 'तीन दिन से',
    language: 'hi',
    certainty: 'reported',
    channel: 'voice',
    confidence: 0.91,
    source: { kind: 'turn', turn_id: 3, question_id: 'ask_duration', transcript_excerpt: 'तीन दिन से' },
    recorded_at: '2026-09-06T08:55:00Z',
  },
  'f-hba1c': {
    fact_id: 'f-hba1c',
    field_id: 'hba1c',
    status: 'answered',
    value: { kind: 'quantity', magnitude: 8.2, unit: '%' },
    original_text: 'HbA1c 8.2',
    language: 'en',
    certainty: 'reported',
    channel: 'document',
    confidence: 0.71,
    source: { kind: 'document', document_id: 'doc-1', page: 1, bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.05 } },
    recorded_at: '2026-09-06T08:56:00Z',
  },
};

function stub(extra: Record<string, () => { status?: number; body?: unknown }> = {}) {
  return stubFetch({
    'GET /intakes/i-1': () => ({ body: INTAKE }),
    // Trailing `*`: the screen now asks for the report in the reader's language,
    // so the path carries `?language=`. Matching on the prefix keeps the stub
    // honest about the route without pinning the query string.
    'GET /intakes/i-1/report*': () => ({ body: REPORT }),
    'GET /intakes/i-1/documents': () => ({
      body: [{ document_id: 'doc-1', kind: 'lab_report', status: 'processed', page_count: 1, url: 'https://signed.example/doc-1.png' }],
    }),
    'GET /intakes/i-1/facts/f-duration/evidence': () => ({ body: EVIDENCE['f-duration'] }),
    'GET /intakes/i-1/facts/f-hba1c/evidence': () => ({ body: EVIDENCE['f-hba1c'] }),
    ...extra,
  });
}

function open(role: 'physician' | 'staff' = 'physician') {
  signInAs(role);
  return renderWithProviders(
    <Routes>
      <Route path="/intakes/:intakeId" element={<ReportPage />} />
    </Routes>,
    { route: '/intakes/i-1' },
  );
}

describe('the report screen', () => {
  it('states the coverage as a count, not a percentage', async () => {
    stub();
    open();
    // "2 of 2 answered" — 92% invites rounding to "basically complete".
    expect(await screen.findByTestId('coverage')).toHaveTextContent('2 of 2 answered');
  });

  it('opens the transcript turn when a voice-sourced line is clicked', async () => {
    stub();
    open();
    await userEvent.click(await screen.findByText('Abdominal pain for 3 days'));
    const panel = await screen.findByTestId('evidence-voice');
    // The patient's own words, in their own script.
    const spoken = within(panel).getByText('तीन दिन से');
    expect(spoken).toHaveAttribute('lang', 'hi');
    expect(within(panel).getByText(/91%/)).toBeVisible();
  });

  it('opens the page image with the region boxed for a document-sourced line', async () => {
    // The demo moment: "HbA1c 8.2%, 12 June" -> click -> the lab report, boxed.
    stub();
    open();
    await userEvent.click(await screen.findByText('HbA1c 8.2%, 12 June'));

    const panel = await screen.findByTestId('evidence-document');
    expect(within(panel).getByRole('img')).toHaveAttribute(
      'src',
      'https://signed.example/doc-1.png',
    );
    const box = within(panel).getByTestId('evidence-bounding-box');
    expect(box).toHaveStyle({ left: '10%', top: '20%' });
    // The raw text beside the extraction, always.
    expect(within(panel).getByText('HbA1c 8.2')).toBeVisible();
  });

  it('sends an amendment as a typed value, not as free text', async () => {
    const { calls } = stub({
      'POST /intakes/i-1/facts/f-duration/verify': () => ({
        body: { ...INTAKE.facts[0], fact_id: 'f-duration-2', physician_action: 'amended' },
      }),
    });
    open();

    await screen.findByText('Abdominal pain for 3 days');
    const line = lineFor('Abdominal pain for 3 days');
    await userEvent.click(line.getByTestId('amend'));
    const editor = screen.getByTestId('amend-editor');
    const value = within(editor).getByLabelText('Corrected value');
    await userEvent.clear(value);
    await userEvent.type(value, '5');
    await userEvent.type(within(editor).getByLabelText('Reason'), 'patient corrected');
    await userEvent.click(within(editor).getByTestId('amend-save'));

    await waitFor(() =>
      expect(calls.some((call) => call.method === 'POST')).toBe(true),
    );
    const post = calls.find((call) => call.method === 'POST')!;
    // The shape the record holds. A `Duration`, not the string "5 days".
    expect(post.body).toEqual({
      action: 'amended',
      value: { kind: 'duration', magnitude: 5, unit: 'day' },
      reason: 'patient corrected',
    });
  });

  it('says what rejecting means before it does it', async () => {
    const { calls } = stub({
      'POST /intakes/i-1/facts/f-duration/verify': () => ({
        body: { ...INTAKE.facts[0], status: 'unresolved', physician_action: 'rejected' },
      }),
    });
    open();

    await screen.findByText('Abdominal pain for 3 days');
    await userEvent.click(lineFor('Abdominal pain for 3 days').getByTestId('reject'));
    // The distinction the record model exists to protect, said in the UI so a
    // physician is not surprised by it.
    expect(screen.getByText(/never established/i)).toBeVisible();
    expect(calls.filter((call) => call.method === 'POST')).toHaveLength(0);

    await userEvent.click(screen.getByTestId('reject-confirm'));
    await waitFor(() =>
      expect(calls.some((call) => call.method === 'POST')).toBe(true),
    );
    expect(calls.find((call) => call.method === 'POST')!.body).toEqual({
      action: 'rejected',
    });
  });

  it('offers no verification controls to staff', async () => {
    // Verification is the act that changes the clinical weight of the record.
    // The backend refuses it for staff; this screen does not offer it either.
    stub();
    open('staff');
    await screen.findByText('Abdominal pain for 3 days');
    expect(screen.queryByTestId('accept')).toBeNull();
    expect(screen.queryByTestId('verify-all')).toBeNull();
  });

  it('shows unresolved as a full section rather than hiding it', async () => {
    stub();
    open();
    const unresolved = await screen.findByTestId('unresolved-section');
    expect(within(unresolved).getByText(/Severity/)).toBeVisible();
    expect(unresolved.querySelector('details')).toBeNull();
  });

  it('calls the draft a draft', async () => {
    stub();
    open();
    expect(
      await screen.findByText(/draft report — requires physician verification/i),
    ).toBeVisible();
  });
});
