/**
 * The parts of the report the backend computes and this screen used to discard.
 *
 * `PhysicianReport` has always carried `alerts`, `interactions`,
 * `document_timeline` and `document_notes`. Three were typed and none were
 * rendered, so drug interactions were computed on every report build and thrown
 * away, and the document timeline — which is the problem statement's timeline
 * requirement — never reached a physician at all. These tests exist so that
 * cannot quietly happen again.
 *
 * Against `ReportView` directly rather than the page, because what is under
 * test is rendering and not fetching.
 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ReportView } from '../src/report/ReportView';
import type { PhysicianReport } from '../src/api/types';

function show(report: Partial<PhysicianReport>) {
  const full = {
    intake_id: 'i-1',
    hospital_id: 'aiia-delhi',
    language: 'en',
    sections: [],
    unresolved: [],
    conflicts: [],
    ...report,
  } as PhysicianReport;
  return render(
    <ReportView
      report={full}
      facts={{}}
      selectedFactId={null}
      onSelectFact={() => {}}
    />,
  );
}

describe('sections the backend decided and the screen must show', () => {
  it('renders drug interactions, with the source that raised them', () => {
    // Computed by `interactions.py` on every build and, until now, dropped on
    // the floor by the one screen a physician reads.
    show({
      interactions: [
        {
          text: 'Warfarin + Ibuprofen — increased bleeding risk. Please review together.',
          severity: 'major',
          source: 'CDSCO',
        },
      ],
    });
    const block = screen.getByTestId('report-interactions');
    expect(within(block).getByText(/Warfarin \+ Ibuprofen/)).toBeInTheDocument();
    expect(within(block).getByText(/CDSCO/)).toBeInTheDocument();
  });

  it('renders the document timeline, and says when a document could not be dated', () => {
    show({
      document_timeline: [
        {
          document_id: 'd-1',
          document_date: '2026-08-03',
          days_before_intake: 40,
          dated: true,
          text: 'Prescription, 40 days before this visit',
        },
        {
          document_id: 'd-2',
          dated: false,
          text: 'A page with no legible date',
        },
      ],
    });
    const block = screen.getByTestId('document-timeline');
    expect(within(block).getByText(/40 days before this visit/)).toBeInTheDocument();
    // An undated document states the problem rather than showing a blank cell:
    // it cannot be placed on the timeline at all, which is the finding.
    expect(within(block).getByText('No legible date')).toBeInTheDocument();
  });

  it('renders red-flag criteria above everything else', () => {
    show({
      alerts: [
        {
          rule_id: 'RF_SEVERE_BREATHLESSNESS',
          severity: 'critical',
          label: 'Severe breathlessness with high pain score',
          criteria_met: ['breathlessness=true', 'severity>=8'],
          acknowledged_by: null,
        },
      ],
      sections: [
        { section: 'hpi', title: 'History', lines: [{ text: 'Something else' }] },
      ],
    });
    const article = screen.getByLabelText('Patient report');
    const alerts = screen.getByTestId('report-alerts');
    // First child of the article: a criterion that stopped an interview is not
    // something to scroll to.
    expect(article.firstElementChild).toBe(alerts);
    expect(within(alerts).getByText(/Severe breathlessness/)).toBeInTheDocument();
    expect(within(alerts).getByText(/Not yet acknowledged/)).toBeInTheDocument();
  });

  it('says nothing at all when there is nothing to say', () => {
    // An empty interactions list is not "no interactions found" — the report
    // never claims a check was run. Unresolved and Conflicts are the deliberate
    // exceptions and stay full sections either way (§12).
    show({});
    expect(screen.queryByTestId('report-interactions')).toBeNull();
    expect(screen.queryByTestId('document-timeline')).toBeNull();
    expect(screen.queryByTestId('report-alerts')).toBeNull();
    expect(screen.getByTestId('unresolved-section')).toBeInTheDocument();
    expect(screen.getByTestId('conflicts-section')).toBeInTheDocument();
  });
});

describe('a line is a label and a value, not a key-value string', () => {
  it('renders the halves the builder stated', () => {
    show({
      sections: [
        {
          section: 'hpi',
          title: 'History',
          lines: [
            {
              text: 'Duration: 3 days',
              label: 'Duration',
              value: '3 days',
              fact_ids: ['f-1'],
            },
          ],
        },
      ],
    });
    expect(screen.getByText('Duration')).toBeInTheDocument();
    expect(screen.getByText('3 days')).toBeInTheDocument();
    // And not the joined string, which is what made the page read as a dict.
    expect(screen.queryByText('Duration: 3 days')).toBeNull();
  });

  it('falls back to the whole sentence when there are no halves', () => {
    // An unresolved line is a sentence — "Severity — not established" — and
    // splitting one into a pair would invent a structure it does not have.
    show({ unresolved: [{ text: 'Severity — not established' }] });
    expect(screen.getByText('Severity — not established')).toBeInTheDocument();
  });
});

describe('identifiers a physician should never be shown', () => {
  it('uses the backend label for a conflicting field, not the field id', () => {
    show({
      field_labels: { chief_complaint: 'Chief complaint' },
      conflicts: [
        {
          field_id: 'chief_complaint',
          kind: 'value',
          from_record: {
            fact_id: 'f-old',
            statement: 'Joint pain',
            channel: 'voice',
            source_label: 'Visit of 12 June',
          },
          resolution: 'Physician verification required',
        },
      ],
    });
    expect(screen.getByText('Chief complaint')).toBeInTheDocument();
    expect(screen.queryByText('chief complaint')).toBeNull();
  });
});

describe('markers', () => {
  it('renders each one as its own chip rather than a joined string', () => {
    // Semicolon-joined into one faint 12px run, the provenance signals read as
    // a serialised array — which is exactly the complaint about this screen.
    show({
      sections: [
        {
          section: 'hpi',
          title: 'History',
          lines: [
            {
              text: 'Fever: 101 °F',
              label: 'Fever',
              value: '101 °F',
              fact_ids: ['f-1'],
              markers: [
                { code: 'low_confidence', text: 'low-confidence reading' },
                { code: 'reporter', text: 'reported by attendant' },
              ],
            },
          ],
        },
      ],
    });
    expect(screen.getByText('low-confidence reading')).toBeInTheDocument();
    expect(screen.getByText('reported by attendant')).toBeInTheDocument();
    expect(
      screen.queryByText('low-confidence reading; reported by attendant'),
    ).toBeNull();
  });
});
