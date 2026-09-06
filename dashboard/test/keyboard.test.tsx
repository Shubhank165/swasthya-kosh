/**
 * The report, without a mouse — 3/3 §11 item 8, §9.
 *
 * "The report should be workable without a mouse." A physician with a patient
 * in front of them is not reaching for a trackpad to check where a value came
 * from, and a clinician using a screen reader cannot.
 *
 * So: every traceable line is a real `<button>` reachable by Tab, activating it
 * opens the evidence, and the verification controls are reachable from the line
 * they belong to rather than appearing only on hover.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ReportView } from '../src/report/ReportView';
import { renderWithProviders, signOut } from './harness';
import type { PhysicianReport } from '../src/api/types';
import type { FactLike } from '../src/report/factState';

afterEach(() => {
  signOut();
  vi.unstubAllGlobals();
});

const report: PhysicianReport = {
  intake_id: 'i-1',
  hospital_id: 'aiia-delhi',
  language: 'en',
  sections: [
    {
      section: 'hpi',
      title: 'History of present illness',
      lines: [
        { text: 'Abdominal pain for 3 days', fact_ids: ['f-1'] },
        { text: 'HbA1c 8.2%', fact_ids: ['f-2'] },
      ],
    },
  ],
  unresolved: [],
  conflicts: [],
};

const facts: Record<string, FactLike> = {
  'f-1': { status: 'answered' },
  'f-2': { status: 'answered', needs_verification: true },
};

describe('working the report from the keyboard', () => {
  it('reaches every traceable line by tabbing and opens it with Enter', async () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <ReportView
        report={report}
        facts={facts}
        selectedFactId={null}
        onSelectFact={onSelect}
      />,
    );

    await userEvent.tab();
    expect(document.activeElement).toHaveAttribute('data-fact-id', 'f-1');
    await userEvent.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledWith('f-1');

    await userEvent.tab();
    expect(document.activeElement).toHaveAttribute('data-fact-id', 'f-2');
  });

  it('reaches the verification controls for the line the focus is on', async () => {
    // The controls fade in on hover, which is fine for a mouse and useless
    // otherwise — so they are revealed by focus within the row as well, and
    // they are always in the tab order rather than being `display: none`.
    renderWithProviders(
      <ReportView
        report={report}
        facts={facts}
        selectedFactId={null}
        onSelectFact={vi.fn()}
        renderActions={(factId) => (
          <button type="button" data-testid={`act-${factId}`}>
            Accept
          </button>
        )}
      />,
    );

    await userEvent.tab();
    expect(document.activeElement).toHaveAttribute('data-fact-id', 'f-1');
    await userEvent.tab();
    expect(document.activeElement).toBe(screen.getByTestId('act-f-1'));
  });

  it('gives every section a real heading and every line a list item', async () => {
    // Semantic HTML, per §9. A screen reader announcing "History of present
    // illness, list, 2 items" is the difference between a document and a wall.
    renderWithProviders(
      <ReportView
        report={report}
        facts={facts}
        selectedFactId={null}
        onSelectFact={vi.fn()}
      />,
    );
    const section = screen.getByRole('region', { name: /history of present illness/i });
    expect(within(section).getAllByRole('listitem')).toHaveLength(2);
    expect(screen.getByRole('article', { name: /patient report/i })).toBeVisible();
  });

  it('does not put an untraceable line in the tab order', async () => {
    renderWithProviders(
      <ReportView
        report={{
          ...report,
          sections: [
            {
              section: 'hpi',
              title: 'History of present illness',
              lines: [{ text: 'A summary line with no fact behind it' }],
            },
          ],
        }}
        facts={{}}
        selectedFactId={null}
        onSelectFact={vi.fn()}
      />,
    );
    // Disabled rather than clickable-and-inert: a dead click on a clinical
    // screen reads as a broken system, and a keyboard user has no way to tell.
    expect(
      screen.getByText('A summary line with no fact behind it').closest('button'),
    ).toBeDisabled();
  });
});
