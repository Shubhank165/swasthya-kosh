/**
 * The patient report, with its evidence beside it — 3/3 §4.2, §5, §6.
 *
 * Two panes. Report left, evidence right. Clicking any line puts its source in
 * the right pane, which is the interaction the whole system is for: *"HbA1c
 * 8.2%, 12 June" → click → the original lab report with that value boxed*.
 *
 * The page fetches three things and combines none of them cleverly: the record
 * (for fact states and the header), the report (for what to print), and the
 * documents (for the signed URLs the evidence panel needs to draw a page
 * image). Everything clinical arrives decided.
 */
import { useCallback, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  useDocuments,
  useEvidence,
  useIntake,
  useReport,
  useVerifyFact,
  useVerifyRecord,
  type FactAction,
} from '../api/queries';
import type { Fact, PhysicianReport } from '../api/types';
import { useSession } from '../auth/session';
import { EvidencePanel } from '../evidence/EvidencePanel';
import { useT } from '../i18n';
import { evidenceFromApi } from '../evidence/fromApi';
import { ReportView } from './ReportView';
import { VerifyControls } from './VerifyControls';
import { HeaderStrip } from './HeaderStrip';

/**
 * Puts the backend's rendered text on the clipboard.
 *
 * The result is stated rather than assumed: `navigator.clipboard` is absent
 * over plain HTTP and can be refused by permissions policy, and a button that
 * silently does nothing is worse than one that says it could not.
 */
function CopyTextButton({ text }: { text: string }) {
  const t = useT();
  const [result, setResult] = useState<'idle' | 'copied' | 'failed'>('idle');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setResult('copied');
    } catch {
      setResult('failed');
    }
  };

  return (
    <>
      <button
        type="button"
        data-testid="copy-report-text"
        onClick={copy}
        className="rounded border border-line px-3 py-1.5 text-sm text-ink hover:bg-surface-sunken"
      >
        {t('report.copy')}
      </button>
      {result !== 'idle' && (
        <span
          role="status"
          className={`text-sm ${result === 'copied' ? 'text-verified' : 'text-urgent'}`}
        >
          {result === 'copied' ? t('report.copied') : t('report.copyFailed')}
        </span>
      )}
    </>
  );
}

export function ReportPage() {
  const t = useT();
  const { intakeId = '' } = useParams();
  const session = useSession((state) => state.session);
  const isPhysician = session?.role === 'physician' || session?.role === 'admin';

  const intake = useIntake(intakeId);
  const report = useReport(intakeId);
  const documents = useDocuments(intakeId);
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null);
  const evidence = useEvidence(intakeId, selectedFactId);
  const verifyFact = useVerifyFact(intakeId);
  const verifyRecord = useVerifyRecord(intakeId);

  const facts = useMemo(() => {
    const byId: Record<string, Fact> = {};
    for (const fact of intake.data?.facts ?? []) byId[fact.fact_id] = fact;
    return byId;
  }, [intake.data]);

  const documentUrl = useCallback(
    (documentId: string) =>
      (documents.data ?? []).find((doc) => doc.document_id === documentId)?.url ??
      undefined,
    [documents.data],
  );

  const renderActions = useCallback(
    (factId: string) => {
      if (!isPhysician) return null;
      const fact = facts[factId];
      if (!fact) return null;
      return (
        <VerifyControls
          fact={fact}
          pending={verifyFact.isPending}
          onAct={(action: FactAction) => verifyFact.mutate(action)}
        />
      );
    },
    [facts, isPhysician, verifyFact],
  );

  if (intake.isError || report.isError) {
    return (
      <p role="alert" className="text-urgent">
        {t('report.loadError')}{' '}
        <Link to="/" className="underline">
          {t('report.backToWorklist')}
        </Link>
      </p>
    );
  }

  if (!intake.data || !report.data) {
    return <p className="text-ink-muted">{t('report.loading')}</p>;
  }

  const body = report.data.report as unknown as PhysicianReport;

  return (
    <div className="space-y-4">
      <HeaderStrip intake={intake.data} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr),minmax(320px,26rem)] print:block">
        <section
          aria-label={t('report.label')}
          className="rounded border border-line bg-surface p-4 sm:p-6 print:border-0 print:p-0"
        >
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-ink">{t('report.draft')}</h2>
            {isPhysician && (
              <button
                type="button"
                data-testid="verify-all"
                disabled={verifyRecord.isPending}
                onClick={() => verifyRecord.mutate({})}
                className="rounded border border-verified px-3 py-1.5 text-sm font-medium text-verified hover:bg-verified/10"
              >
                {t('report.verifyAll')}
              </button>
            )}
          </div>

          {report.data.physician_verified_by && (
            <p className="mb-3 rounded border border-verified/30 bg-verified-soft px-2 py-1 text-sm text-verified">
              {t('report.verifiedBy', { actor: report.data.physician_verified_by })}
            </p>
          )}

          {verifyFact.isError && (
            <p role="alert" className="mb-3 text-sm text-urgent">
              {t('report.writeError')}
            </p>
          )}

          <ReportView
            report={body}
            facts={facts}
            selectedFactId={selectedFactId}
            onSelectFact={setSelectedFactId}
            renderActions={renderActions}
          />

          {/* The backend's rendered text is "what a physician reads, prints, or
              pastes into the HMIS" — a capability worth keeping, and the worst
              possible thing to *display*. Shown as a wall of monospace with
              UPPERCASE headings it was the single most machine-like thing on
              the page, and it is the reason this screen read as JSON. So it
              stays available as an action and is not rendered. */}
          <div className="mt-8 flex flex-wrap items-center gap-2 border-t border-line pt-3 print:hidden">
            <CopyTextButton text={report.data.text ?? ''} />
            <button
              type="button"
              data-testid="print-report"
              onClick={() => window.print()}
              title={t('report.printHint')}
              className="rounded border border-line px-3 py-1.5 text-sm text-ink hover:bg-surface-sunken"
            >
              {t('report.print')}
            </button>
          </div>
        </section>

        {/* Evidence is a screen interaction — click a line, see the page it
            came from. On paper there is nothing to click. */}
        <div className="lg:sticky lg:top-4 lg:self-start print:hidden">
          <EvidencePanel
            loading={evidence.isLoading}
            evidence={
              evidence.data
                ? evidenceFromApi(evidence.data, { documentUrl })
                : null
            }
          />
        </div>
      </div>
    </div>
  );
}
