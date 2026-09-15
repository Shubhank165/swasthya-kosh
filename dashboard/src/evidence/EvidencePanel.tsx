/**
 * Where a fact came from — 3/3 §5.
 *
 * **The demo moment.** One click on a line in the report and its source appears
 * here: the transcript turn that was spoken, the region of the prescription it
 * was read from, or the option the patient tapped. The interaction that sells
 * the system is *"HbA1c 8.2%, 12 June" → click → the original lab report with
 * that value boxed*, so that path is the one kept shortest.
 *
 * Everything shown here is already in the backend's
 * `GET /intakes/{id}/facts/{fact_id}/evidence` response. The work is
 * presentation — §1 rule 1 still holds, and nothing on this panel interprets.
 *
 * The **labels** follow the doctor's chosen interface language (§9). The
 * **content** never does: the transcript, the raw OCR text and the tapped
 * option are the patient's own, shown verbatim in their own script, with a
 * translation beneath where one exists and never over the top of it.
 */
import { X, ScanSearch } from 'lucide-react';
import { useT, type StringKey } from '../i18n';

export interface Evidence {
  channel: 'voice' | 'document' | 'app' | 'carried_forward' | 'entry' | string;
  /** Voice: the turn. App: the question as displayed. */
  question?: string | null;
  transcript?: string | null;
  language?: string | null;
  translation?: string | null;
  asr_confidence?: number | null;
  /** Turns either side, for context. */
  context?: readonly { question?: string | null; transcript?: string | null }[];
  /** Document: the page and the box drawn on it. */
  image_url?: string | null;
  page?: number | null;
  bounding_box?: { x: number; y: number; width: number; height: number } | null;
  raw_text?: string | null;
  extracted_value?: string | null;
  ocr_confidence?: number | null;
  /** App: what the patient tapped. */
  chosen_option?: string | null;
  /** Carried forward: which visit it came from. */
  from_intake_id?: string | null;
  originally_recorded?: string | null;
  confirmed_today?: boolean | null;
  /** Entered by a person: who. The act of entry is the evidence. */
  entered_by?: string | null;
}

export function EvidenceDrawer({
  isOpen,
  onClose,
  evidence,
  loading,
  onOpenIntake,
}: {
  isOpen: boolean;
  onClose: () => void;
  evidence: Evidence | null;
  loading: boolean;
  onOpenIntake?: (intakeId: string) => void;
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-ink/40 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-10">
        <aside
          role="dialog"
          aria-modal="true"
          className="w-screen max-w-md bg-white shadow-2xl flex flex-col border-l border-line animate-fade-rise"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-line px-5 py-4 bg-[#f8faf9]">
            <div className="flex items-center gap-2">
              <span className="flex size-8 items-center justify-center rounded-lg bg-herb-soft text-herb">
                <ScanSearch className="size-4" />
              </span>
              <div>
                <h2 className="text-sm font-bold text-ink">Source Evidence</h2>
                <p className="text-[11px] text-ink-muted">Verbatim Kiosk & OCR Proof</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
              aria-label="Close evidence panel"
            >
              <X className="size-5" />
            </button>
          </div>

          {/* Drawer content */}
          <div className="flex-1 overflow-y-auto p-5">
            <EvidencePanel
              evidence={evidence}
              loading={loading}
              onOpenIntake={onOpenIntake}
            />
          </div>
        </aside>
      </div>
    </div>
  );
}

export function EvidencePanel({
  evidence,
  loading,
  onOpenIntake,
}: {
  evidence: Evidence | null;
  loading: boolean;
  onOpenIntake?: (intakeId: string) => void;
}) {
  if (loading) return <Frame titleKey="evidence.label"><Muted textKey="common.loading" /></Frame>;
  if (!evidence) {
    return (
      <Frame titleKey="evidence.label">
        <Muted textKey="evidence.empty" />
      </Frame>
    );
  }

  switch (evidence.channel) {
    case 'voice':
      return <VoiceEvidence evidence={evidence} />;
    case 'document':
      return <DocumentEvidence evidence={evidence} />;
    case 'app':
      return <AppEvidence evidence={evidence} />;
    case 'carried_forward':
      return <CarriedForwardEvidence evidence={evidence} onOpenIntake={onOpenIntake} />;
    case 'entry':
      return <EntryEvidence evidence={evidence} />;
    default:
      return (
        <Frame titleKey="evidence.label">
          <Muted textKey="evidence.none" />
        </Frame>
      );
  }
}

function Muted({ textKey }: { textKey: StringKey }) {
  const t = useT();
  return <p className="text-ink-muted">{t(textKey)}</p>;
}

function Frame({
  titleKey,
  children,
}: {
  titleKey: StringKey;
  children: React.ReactNode;
}) {
  const t = useT();
  return (
    <div
      aria-label={t('evidence.label')}
      className="rounded-2xl border border-line bg-[#f8faf9] p-4"
    >
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-ink-muted">
        {t(titleKey)}
      </h3>
      {children}
    </div>
  );
}

function VoiceEvidence({ evidence }: { evidence: Evidence }) {
  const t = useT();
  return (
    <Frame titleKey="evidence.voiceTitle">
      <div data-testid="evidence-voice" className="space-y-3">
        {evidence.question && (
          <p className="text-sm text-ink-muted">{evidence.question}</p>
        )}
        {/* Verbatim, in the original script. **Never translated in place** —
            §9, and the same rule the record itself follows. */}
        <blockquote
          lang={evidence.language ?? undefined}
          className="border-l-2 border-accent pl-3 text-lg text-ink"
        >
          {evidence.transcript}
        </blockquote>
        {evidence.translation && (
          <p className="pl-3 text-sm italic text-ink-muted">{evidence.translation}</p>
        )}
        {typeof evidence.asr_confidence === 'number' && (
          <p className="text-xs text-ink-faint">
            {t('evidence.asrConfidence', {
              percent: Math.round(evidence.asr_confidence * 100),
            })}
          </p>
        )}
        {(evidence.context?.length ?? 0) > 0 && (
          <details className="text-sm">
            <summary className="cursor-pointer text-ink-muted">
              {t('evidence.surrounding')}
            </summary>
            <ul className="mt-2 space-y-2">
              {evidence.context!.map((turn, index) => (
                <li key={index} className="border-l border-line pl-2">
                  <p className="text-xs text-ink-faint">{turn.question}</p>
                  <p className="text-ink-muted">{turn.transcript}</p>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </Frame>
  );
}

function DocumentEvidence({ evidence }: { evidence: Evidence }) {
  const t = useT();
  const box = evidence.bounding_box;
  return (
    <Frame titleKey="evidence.documentTitle">
      <div data-testid="evidence-document" className="space-y-3">
        <div className="relative overflow-hidden rounded border border-line bg-surface-sunken">
          {evidence.image_url ? (
            <img
              src={evidence.image_url}
              alt={t('evidence.page', { page: evidence.page ?? 1 })}
              className="w-full"
            />
          ) : (
            <p className="p-4 text-sm text-ink-muted">{t('evidence.imageUnavailable')}</p>
          )}
          {box && (
            // Percentages, so the box tracks the image at any zoom rather than
            // drifting off it the moment the pane is resized.
            <span
              data-testid="evidence-bounding-box"
              aria-hidden="true"
              className="pointer-events-none absolute border-2 border-urgent"
              style={{
                left: `${box.x * 100}%`,
                top: `${box.y * 100}%`,
                width: `${box.width * 100}%`,
                height: `${box.height * 100}%`,
              }}
            />
          )}
        </div>
        <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-ink-muted">{t('evidence.extracted')}</dt>
          <dd className="text-ink">{evidence.extracted_value ?? '—'}</dd>
          {/* The raw text beside the extraction, always. A value the physician
              cannot compare with what is on the paper is an assertion. */}
          <dt className="text-ink-muted">{t('evidence.rawText')}</dt>
          <dd className="font-mono text-xs text-ink-muted">{evidence.raw_text ?? '—'}</dd>
          {typeof evidence.ocr_confidence === 'number' && (
            <>
              <dt className="text-ink-muted">{t('evidence.confidence')}</dt>
              <dd className="text-ink">{Math.round(evidence.ocr_confidence * 100)}%</dd>
            </>
          )}
        </dl>
      </div>
    </Frame>
  );
}

function AppEvidence({ evidence }: { evidence: Evidence }) {
  const t = useT();
  return (
    <Frame titleKey="evidence.appTitle">
      <div data-testid="evidence-app" className="space-y-3">
        <p className="text-sm text-ink-muted">{evidence.question}</p>
        <p className="rounded border border-line bg-surface-sunken px-3 py-2 text-lg text-ink">
          {evidence.chosen_option ?? evidence.transcript}
        </p>
        {/* No confidence score, and its absence is deliberate: a tap has none,
            and inventing 1.0 would make it look like a perfectly-heard answer. */}
        <p className="text-xs text-ink-faint">{t('evidence.tapped')}</p>
      </div>
    </Frame>
  );
}

function EntryEvidence({ evidence }: { evidence: Evidence }) {
  const t = useT();
  return (
    <Frame titleKey="evidence.entryTitle">
      <div data-testid="evidence-entry" className="space-y-3">
        <p className="rounded border border-line bg-surface-sunken px-3 py-2 text-lg text-ink">
          {evidence.transcript ?? '—'}
        </p>
        {/* Thin provenance, shown as thin rather than dressed up. The evidence
            here is the act of entry and the person who performed it; there is
            no transcript to check it against and the panel does not imply one. */}
        <p className="text-xs text-ink-faint">
          {t('evidence.enteredBy', {
            actor: evidence.entered_by ?? t('evidence.someStaff'),
          })}
        </p>
      </div>
    </Frame>
  );
}

function CarriedForwardEvidence({
  evidence,
  onOpenIntake,
}: {
  evidence: Evidence;
  onOpenIntake?: (intakeId: string) => void;
}) {
  const t = useT();
  return (
    <Frame titleKey="evidence.carriedTitle">
      <div data-testid="evidence-carried" className="space-y-3">
        <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-ink-muted">{t('evidence.recorded')}</dt>
          <dd className="text-ink">{evidence.originally_recorded ?? '—'}</dd>
          <dt className="text-ink-muted">{t('evidence.confirmedToday')}</dt>
          {/* Three values, and they stay three in both languages: confirmed,
              contradicted, and never asked. */}
          <dd className="text-ink">
            {evidence.confirmed_today === true
              ? t('evidence.confirmedYes')
              : evidence.confirmed_today === false
                ? t('evidence.confirmedNo')
                : t('evidence.confirmedNotAsked')}
          </dd>
        </dl>
        {evidence.from_intake_id && onOpenIntake && (
          <button
            type="button"
            className="text-sm text-accent underline"
            onClick={() => onOpenIntake(evidence.from_intake_id!)}
          >
            {t('evidence.openVisit')}
          </button>
        )}
      </div>
    </Frame>
  );
}
