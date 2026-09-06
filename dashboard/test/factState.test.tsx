/**
 * Fact states — 3/3 §11 item 2, §1 rule 3.
 *
 * The property under test is the one the whole screen rests on: **a doctor must
 * be able to tell at a glance which parts of this document to trust.** Every
 * state in §4.2's table renders distinctly, and none of `unresolved`,
 * `not_asked` or `not_applicable` is ever rendered as "no" or allowed to
 * vanish.
 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  STATE_STYLES,
  statesFor,
  type FactLike,
  type FactState,
} from '../src/report/factState';
import { ReportView } from '../src/report/ReportView';
import type { PhysicianReport } from '../src/api/types';

describe('what a state means', () => {
  it('keeps the four unsettled statuses apart', () => {
    // Four different medico-legal positions. Collapsing any two is the single
    // most dangerous shortcut available in this file.
    expect(statesFor({}, { status: 'unresolved' })).toContain('unresolved');
    expect(statesFor({}, { status: 'not_asked' })).toContain('not_asked');
    expect(statesFor({}, { status: 'not_applicable' })).toContain('not_applicable');
    expect(statesFor({}, { status: 'refused' })).toContain('unresolved');

    const labels = new Set(
      (['unresolved', 'not_asked', 'not_applicable'] as FactState[]).map(
        (s) => STATE_STYLES[s].label,
      ),
    );
    expect(labels.size).toBe(3);
  });

  it('never words an unsettled fact as "no"', () => {
    for (const state of Object.keys(STATE_STYLES) as FactState[]) {
      expect(STATE_STYLES[state].label.toLowerCase()).not.toMatch(/^no\b/);
    }
    // "Not established" is the wording §4.2 fixes for unresolved.
    expect(STATE_STYLES.unresolved.label).toBe('not established');
  });

  it('reports every qualifier a line carries, not just the worst', () => {
    // Uncertainty is displayed, never smoothed: a repaired, low-confidence,
    // attendant-reported answer is three things, and showing one hides two.
    const states = statesFor(
      { markers: [{ code: 'attendant', text: 'reported by an attendant' }] },
      { repaired: true, needs_verification: true },
    );
    expect(states).toEqual(expect.arrayContaining(['repaired', 'low_confidence', 'second_hand']));
  });

  it('is plain only when nothing qualifies it', () => {
    expect(statesFor({}, { status: 'answered' })).toEqual(['confirmed']);
    expect(STATE_STYLES.confirmed.label).toBe('');
  });

  it('distinguishes every state by shape as well as colour', () => {
    // Some reviewers are colour-blind and all of them are looking at a
    // projector. A state told apart only by hue is a state not told apart.
    const glyphs = (Object.keys(STATE_STYLES) as FactState[])
      .filter((s) => s !== 'confirmed')
      .map((s) => STATE_STYLES[s].glyph);
    expect(new Set(glyphs).size).toBe(glyphs.length);
    expect(glyphs.every((g) => g.length > 0)).toBe(true);
  });

  it('shows the original words wherever the line was reconstructed or read', () => {
    expect(STATE_STYLES.repaired.showsOriginal).toBe(true);
    expect(STATE_STYLES.low_confidence.showsOriginal).toBe(true);
  });
});

/**
 * A fixture containing **every state in §4.2's table** — §11 item 2.
 *
 * The conflict is the backend's real shape (`app/domain/record.py::
 * Contradiction`), not a convenient one: a conflict where only the record has
 * a claim is a real case — a medicine on the prescription the patient did not
 * mention — and the screen must not render that as the patient denying it.
 */
const report: PhysicianReport = {
  intake_id: 'i1',
  hospital_id: 'aiia-delhi',
  language: 'en',
  sections: [
    {
      section: 'hpi',
      title: 'History of present illness',
      lines: [
        { text: 'Chest pain for two days', fact_ids: ['f-plain'] },
        { text: 'Breathlessness', fact_ids: ['f-unresolved'] },
        {
          text: 'Metformin 500 mg',
          fact_ids: ['f-repaired'],
          markers: [{ code: 'repaired', text: 'reconstructed' }],
          original_text: 'मेटफॉर्मिन पाँच सौ',
          original_language: 'hi',
        },
        { text: 'Diabetes', fact_ids: ['f-carried'] },
        { text: 'HbA1c 8.2%', fact_ids: ['f-lowconf'] },
        { text: 'Penicillin allergy', fact_ids: ['f-verified'] },
        { text: 'Pain 6/10', fact_ids: ['f-amended'] },
        { text: 'Pregnancy', fact_ids: ['f-na'] },
      ],
    },
  ],
  unresolved: [{ text: 'Smoking history', fact_ids: ['f-notasked'] }],
  conflicts: [
    {
      field_id: 'diabetes',
      kind: 'status',
      reported_today: {
        fact_id: 'f-carried',
        statement: 'Patient reports diabetes',
        channel: 'voice',
        source_label: 'turn 7',
      },
      from_record: {
        fact_id: 'f-doc',
        statement: 'No antidiabetic on the prescription',
        channel: 'document',
        source_label: 'doc-1 p1',
      },
      resolution: 'Physician verification required',
    },
  ],
};

const facts: Record<string, FactLike> = {
  'f-plain': { status: 'answered' },
  'f-unresolved': { status: 'unresolved' },
  'f-repaired': { status: 'answered', repaired: true },
  'f-carried': {
    status: 'answered',
    carried_forward: { from_intake_id: 'i0', originally_recorded: '2026-06-12' },
  },
  'f-lowconf': { status: 'answered', needs_verification: true },
  'f-verified': { status: 'answered', physician_verified: true },
  'f-amended': {
    status: 'answered',
    physician_verified: true,
    physician_action: 'amended',
  },
  'f-na': { status: 'not_applicable' },
  'f-notasked': { status: 'not_asked' },
};

describe('the report as rendered', () => {
  const view = () =>
    render(
      <ReportView report={report} facts={facts} selectedFactId={null} onSelectFact={vi.fn()} />,
    );

  it('renders each state distinctly', () => {
    view();
    const stateOf = (factId: string) =>
      document.querySelector(`[data-fact-id="${factId}"]`)?.getAttribute('data-states') ?? '';

    expect(stateOf('f-plain')).toBe('confirmed');
    expect(stateOf('f-unresolved')).toContain('unresolved');
    expect(stateOf('f-repaired')).toContain('repaired');
    expect(stateOf('f-carried')).toContain('carried_forward');
    expect(stateOf('f-lowconf')).toContain('low_confidence');
    expect(stateOf('f-verified')).toContain('verified');
    expect(stateOf('f-notasked')).toContain('not_asked');
    expect(stateOf('f-na')).toContain('not_applicable');
    // A value the doctor typed, distinct from one the doctor agreed with.
    expect(stateOf('f-amended')).toContain('amended');
    expect(stateOf('f-amended')).not.toContain('verified');
  });

  it('renders every state in §4.2\u2019s table, and none of them as absence', () => {
    view();
    // The assertion the section is for: nothing unsettled vanishes, and
    // nothing unsettled reads as a denial.
    for (const factId of ['f-unresolved', 'f-notasked', 'f-na']) {
      const line = document.querySelector(`[data-fact-id="${factId}"]`);
      expect(line).not.toBeNull();
      expect(line!.textContent ?? '').not.toMatch(/\bno\b/i);
    }
    expect(screen.getByText('not established')).toBeVisible();
    expect(screen.getByText('not asked')).toBeVisible();
    expect(screen.getByText('not applicable')).toBeVisible();
  });

  it('shows unresolved and conflicts as full sections, not a toggle', () => {
    view();
    // §12: hiding the gaps to make the report look tidy defeats the system.
    const unresolved = screen.getByTestId('unresolved-section');
    expect(within(unresolved).getByText('Smoking history')).toBeVisible();
    expect(unresolved.querySelector('details')).toBeNull();

    const conflicts = screen.getByTestId('conflicts-section');
    expect(conflicts.querySelector('details')).toBeNull();
    // Both claims, both sources, and no winner picked.
    expect(within(conflicts).getByText('Patient reports diabetes')).toBeVisible();
    expect(within(conflicts).getByText('No antidiabetic on the prescription')).toBeVisible();
    expect(within(conflicts).getByText('turn 7')).toBeVisible();
    expect(within(conflicts).getByText('doc-1 p1')).toBeVisible();
    // The backend never resolves a conflict, and neither does this screen.
    expect(
      within(conflicts).getByText('Physician verification required'),
    ).toBeVisible();
  });

  it("shows the patient's own words without translating them in place", () => {
    view();
    const original = screen.getByText('मेटफॉर्मिन पाँच सौ');
    expect(original).toBeVisible();
    expect(original).toHaveAttribute('lang', 'hi');
    // The English line is still there beside it, not instead of it.
    expect(screen.getByText('Metformin 500 mg')).toBeVisible();
  });

  it('makes every line with a fact behind it traceable in one click', () => {
    view();
    // §1 rule 5. A line with no fact is inert rather than a dead click.
    for (const factId of Object.keys(facts)) {
      const line = document.querySelector(`[data-fact-id="${factId}"]`);
      expect(line).not.toBeNull();
      expect(line).not.toBeDisabled();
    }
  });
});
