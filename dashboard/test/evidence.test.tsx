/**
 * The evidence panel — 3/3 §11 item 3, §5.
 *
 * The interaction that sells the system: a fact, one click, and the thing it
 * came from. What is asserted here is that each channel shows its own kind of
 * source, and that the two rules the panel must not break hold — the patient's
 * words are never translated in place, and an extracted value never appears
 * without the raw text beside it.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvidencePanel } from '../src/evidence/EvidencePanel';
import { evidenceFromApi } from '../src/evidence/fromApi';

describe('evidence by channel', () => {
  it('opens the transcript turn for a voice fact', () => {
    render(
      <EvidencePanel
        loading={false}
        evidence={{
          channel: 'voice',
          question: 'यह दर्द कब से है?',
          transcript: 'तीन दिन से',
          language: 'hi',
          translation: 'For three days',
          asr_confidence: 0.82,
        }}
      />,
    );

    const spoken = screen.getByText('तीन दिन से');
    expect(spoken).toBeVisible();
    // Verbatim, in the original script, with the translation beneath — never
    // over the top of it (§9).
    expect(spoken).toHaveAttribute('lang', 'hi');
    expect(screen.getByText('For three days')).toBeVisible();
    expect(screen.getByText(/82%/)).toBeVisible();
  });

  it('opens the page with the region boxed for a document fact', () => {
    render(
      <EvidencePanel
        loading={false}
        evidence={{
          channel: 'document',
          image_url: '/api/v1/documents/content/page1',
          page: 1,
          bounding_box: { x: 0.1, y: 0.2, width: 0.3, height: 0.05 },
          extracted_value: 'HbA1c 8.2%',
          raw_text: 'HbAlc 8.2 %',
          ocr_confidence: 0.71,
        }}
      />,
    );

    const box = screen.getByTestId('evidence-bounding-box');
    expect(box).toBeInTheDocument();
    // Percentages, so the box tracks the image rather than drifting off it.
    expect(box).toHaveStyle({ left: '10%', top: '20%' });
    // The raw text is always beside the extraction: a value the physician
    // cannot compare with the paper is an assertion.
    expect(screen.getByText('HbAlc 8.2 %')).toBeVisible();
    expect(screen.getByText('HbA1c 8.2%')).toBeVisible();
  });

  it('shows the question and the option for an app fact, and no confidence', () => {
    render(
      <EvidencePanel
        loading={false}
        evidence={{
          channel: 'app',
          question: 'How long have you had this pain?',
          chosen_option: '3 days',
        }}
      />,
    );

    expect(screen.getByText('3 days')).toBeVisible();
    // A tap has no confidence to report, and inventing one would make a tapped
    // answer look like a perfectly-heard spoken one.
    expect(screen.queryByText(/confidence/i)).toBeNull();
  });

  it('names the visit a carried-forward fact came from', () => {
    render(
      <EvidencePanel
        loading={false}
        evidence={{
          channel: 'carried_forward',
          from_intake_id: 'i0',
          originally_recorded: '2026-06-12',
          confirmed_today: true,
        }}
      />,
    );

    expect(screen.getByText('2026-06-12')).toBeVisible();
    expect(screen.getByText('Yes, by the patient')).toBeVisible();
  });

  it('says nothing rather than guessing when there is no source', () => {
    render(<EvidencePanel loading={false} evidence={{ channel: 'unknown' }} />);
    expect(screen.getByText(/no source recorded/i)).toBeVisible();
  });
});

/**
 * The adapter between the backend's vocabulary and the panel's — `fromApi.ts`.
 *
 * Worth testing apart from the component because this is where two vocabularies
 * meet: the backend speaks `FactChannel` (`voice`, `touch`, `document`,
 * `prior_record`, `staff`) and the panel speaks in terms of what the physician
 * is about to look at.
 */
describe('the backend payload as evidence', () => {
  const base = {
    fact_id: 'f-1',
    field_id: 'known_diabetes',
    status: 'answered',
    certainty: 'reported',
    recorded_at: '2026-09-06T09:00:00Z',
  };

  it('routes a carried-forward fact to the previous visit, whatever its channel', () => {
    const evidence = evidenceFromApi({
      ...base,
      channel: 'prior_record',
      source: { kind: 'entry', entered_by: 'carried_forward', prior_intake_id: 'i-0' },
      carried_forward: {
        from_intake_id: 'i-0',
        originally_recorded: '2026-06-12',
        confirmed_today: true,
      },
    });
    expect(evidence.channel).toBe('carried_forward');
    expect(evidence.originally_recorded).toBe('2026-06-12');
    expect(evidence.confirmed_today).toBe(true);
    expect(evidence.from_intake_id).toBe('i-0');
  });

  it('keeps "not re-asked" distinct from "the patient said no"', () => {
    const evidence = evidenceFromApi({
      ...base,
      channel: 'prior_record',
      source: { kind: 'entry', entered_by: 'carried_forward', prior_intake_id: 'i-0' },
      carried_forward: { from_intake_id: 'i-0', originally_recorded: '2026-06-12' },
    });
    // `null`, not `false`. The panel renders it "Not asked".
    expect(evidence.confirmed_today).toBeNull();

    render(<EvidencePanel loading={false} evidence={evidence} />);
    expect(screen.getByText('Not asked')).toBeVisible();
  });

  it('renders a tapped answer as a tap, not as speech with no confidence', () => {
    const evidence = evidenceFromApi({
      ...base,
      channel: 'touch',
      value: { kind: 'boolean', value: true },
      source: { kind: 'turn', turn_id: 4, question_id: 'ask_diabetes' },
    });
    expect(evidence.channel).toBe('app');
    expect(evidence.chosen_option).toBe('yes');
    // A tap has no ASR confidence, and inventing 1.0 would make it look like a
    // perfectly-heard answer rather than a different kind of answer.
    expect(evidence.asr_confidence).toBeUndefined();
  });

  it('carries the signed document URL and the box through unchanged', () => {
    const evidence = evidenceFromApi(
      {
        ...base,
        channel: 'document',
        value: { kind: 'quantity', magnitude: 8.2, unit: '%' },
        original_text: 'HbA1c 8.2',
        confidence: 0.71,
        source: {
          kind: 'document',
          document_id: 'doc-1',
          page: 1,
          bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.05 },
        },
      },
      { documentUrl: (id) => `https://signed.example/${id}.png` },
    );
    expect(evidence.image_url).toBe('https://signed.example/doc-1.png');
    expect(evidence.bounding_box).toEqual({ x: 0.1, y: 0.2, width: 0.3, height: 0.05 });
    expect(evidence.extracted_value).toBe('8.2 %');
    expect(evidence.raw_text).toBe('HbA1c 8.2');
  });

  it('shows a staff-entered fact as thin provenance rather than dropping it', () => {
    const evidence = evidenceFromApi({
      ...base,
      channel: 'staff',
      value: { kind: 'text', text: 'Penicillin' },
      source: { kind: 'entry', entered_by: 'nurse-2' },
    });
    expect(evidence.channel).toBe('entry');

    render(<EvidencePanel loading={false} evidence={evidence} />);
    // A fact with a blank evidence panel reads as a bug. A fact whose evidence
    // is "a person typed this" has real, if thin, provenance — and the panel
    // says out loud that nothing stands behind it.
    expect(screen.getByText(/nurse-2/)).toBeVisible();
    expect(screen.getByText(/No recording or document/i)).toBeVisible();
  });
});
