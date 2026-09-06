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
