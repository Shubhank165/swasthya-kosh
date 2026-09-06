/**
 * English and Hindi — 3/3 §9.
 *
 * Two things are asserted, and the second matters more than the first.
 *
 * 1. The catalogue is complete and the chrome actually switches.
 * 2. **The patient's own words never do.** Switching the doctor's interface
 *    language must not translate a transcript, a raw OCR reading, a report line
 *    or a red-flag label — those are the record, and the record is in the
 *    language the interview happened in. §9 and §12 both say so, and this is
 *    the file that keeps it true when somebody adds a string next month.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EvidencePanel } from '../src/evidence/EvidencePanel';
import { ReportView } from '../src/report/ReportView';
import { LOCALES, translate, useLocale } from '../src/i18n';
import { STRINGS, type StringKey } from '../src/i18n/strings';
import { AlertsPage } from '../src/alerts/AlertsPage';
import { LocaleSwitch } from '../src/components/LocaleSwitch';
import { renderWithProviders, signInAs, signOut, stubFetch } from './harness';
import type { PhysicianReport } from '../src/api/types';

afterEach(() => {
  useLocale.getState().setLocale('en');
  signOut();
  vi.unstubAllGlobals();
});

describe('the catalogue', () => {
  it('has every key in every locale', () => {
    const keys = Object.keys(STRINGS.en) as StringKey[];
    for (const locale of LOCALES) {
      const missing = keys.filter((key) => !STRINGS[locale][key]);
      expect(missing, `missing in ${locale}`).toEqual([]);
    }
  });

  it('leaves no English string sitting in the Hindi catalogue', () => {
    // Excluding the handful that are deliberately identical: product and
    // standard names are not translated, because they are what the hospital's
    // own systems and a patient's ABHA card say.
    const identical = (Object.keys(STRINGS.en) as StringKey[]).filter(
      (key) => STRINGS.hi[key] === STRINGS.en[key],
    );
    expect(identical).toEqual(['app.name']);
  });

  it('substitutes placeholders rather than printing them', () => {
    expect(translate('en', 'header.answered', { answered: 69, total: 75 })).toBe(
      '69 of 75 answered',
    );
    // Hindi puts the total first. A template, not a concatenation, is why that
    // is possible at all.
    expect(translate('hi', 'header.answered', { answered: 69, total: 75 })).toContain('75');
    expect(translate('hi', 'header.answered', { answered: 69, total: 75 })).not.toContain('{');
  });

  it('keeps the coverage claim a count in both languages', () => {
    // §4.2: the count, never a bare percentage. 92% invites rounding to
    // "basically complete"; six unanswered questions does not.
    for (const locale of LOCALES) {
      expect(STRINGS[locale]['header.answered']).not.toContain('%');
    }
  });
});

const report: PhysicianReport = {
  intake_id: 'i-1',
  hospital_id: 'aiia-delhi',
  language: 'hi',
  sections: [
    {
      section: 'hpi',
      title: 'वर्तमान बीमारी का विवरण',
      lines: [
        {
          text: 'अवधि: 3 days',
          fact_ids: ['f-1'],
          original_text: 'तीन दिन से',
          original_language: 'hi',
        },
      ],
    },
  ],
  unresolved: [],
  conflicts: [],
};

describe('switching the interface language', () => {
  it('translates the chrome and leaves the record alone', async () => {
    const { rerender } = render(
      <ReportView
        report={report}
        facts={{ 'f-1': { status: 'answered' } }}
        selectedFactId={null}
        onSelectFact={vi.fn()}
      />,
    );

    expect(screen.getByRole('article', { name: 'Patient report' })).toBeVisible();
    expect(screen.getByText('Unresolved')).toBeVisible();

    useLocale.getState().setLocale('hi');
    rerender(
      <ReportView
        report={report}
        facts={{ 'f-1': { status: 'answered' } }}
        selectedFactId={null}
        onSelectFact={vi.fn()}
      />,
    );

    expect(screen.getByRole('article', { name: 'रोगी रिपोर्ट' })).toBeVisible();
    expect(screen.getByText('अनिर्णीत')).toBeVisible();
    // The section title and the line came from the backend in the interview's
    // language. Neither changed, and neither may.
    expect(screen.getByText('वर्तमान बीमारी का विवरण')).toBeVisible();
    expect(screen.getByText('अवधि: 3 days')).toBeVisible();
    expect(screen.getByText('तीन दिन से')).toHaveAttribute('lang', 'hi');
  });

  it('does not translate a transcript or a raw OCR reading', () => {
    useLocale.getState().setLocale('hi');
    render(
      <EvidencePanel
        loading={false}
        evidence={{
          channel: 'document',
          extracted_value: '8.2 %',
          raw_text: 'HbA1c 8.2',
          ocr_confidence: 0.71,
        }}
      />,
    );
    // Labels in Hindi…
    expect(screen.getByText('निकाला गया')).toBeVisible();
    expect(screen.getByText('मूल पाठ')).toBeVisible();
    // …and what is on the paper exactly as it is on the paper.
    expect(screen.getByText('HbA1c 8.2')).toBeVisible();
    expect(screen.getByText('8.2 %')).toBeVisible();
  });

  it('never rewords a red-flag label the content already fixed', async () => {
    useLocale.getState().setLocale('hi');
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
    });
    signInAs('physician');
    renderWithProviders(<AlertsPage />);

    const card = await screen.findByTestId('alert-card');
    // A clinical string an AIIA mentor signs off. A locale switch is not the
    // place to reword it, and the criterion is a concept id, not prose.
    expect(
      within(card).getByText('Urgent clinical review criterion triggered'),
    ).toBeVisible();
    expect(within(card).getByText('haematemesis')).toBeVisible();
    // The furniture around it did switch.
    expect(within(card).getByText('पूरे हुए मानदंड')).toBeVisible();
  });

  it('switches on the control, and keeps nothing in storage', async () => {
    render(<LocaleSwitch />);
    const select = screen.getByTestId('locale-switch');
    await userEvent.selectOptions(select, 'hi');
    expect(useLocale.getState().locale).toBe('hi');
    // §12: a preference that survives the tab being closed is one the next
    // person at a shared OPD terminal inherits.
    //
    // The lint rule that bans these is doing its job by firing here, and this
    // is the one place the ban has to be lifted: a test that proves nothing was
    // stored has to be able to look.
    /* eslint-disable no-restricted-properties */
    expect({ ...window.localStorage }).toEqual({});
    expect({ ...window.sessionStorage }).toEqual({});
    /* eslint-enable no-restricted-properties */
  });
});
