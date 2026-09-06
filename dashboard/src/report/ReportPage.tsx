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
import { evidenceFromApi } from '../evidence/fromApi';
import { ReportView } from './ReportView';
import { VerifyControls } from './VerifyControls';
import { HeaderStrip } from './HeaderStrip';

export function ReportPage() {
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
        This record could not be loaded.{' '}
        <Link to="/" className="underline">
          Back to the worklist
        </Link>
      </p>
    );
  }

  if (!intake.data || !report.data) {
    return <p className="text-ink-muted">Loading the record…</p>;
  }

  const body = report.data.report as unknown as PhysicianReport;

  return (
    <div className="space-y-4">
      <HeaderStrip intake={intake.data} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr),minmax(320px,26rem)]">
        <section aria-label="Report" className="rounded border border-line bg-surface p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-ink">
              Draft report — requires physician verification
            </h2>
            {isPhysician && (
              <button
                type="button"
                data-testid="verify-all"
                disabled={verifyRecord.isPending}
                onClick={() => verifyRecord.mutate({})}
                className="rounded border border-verified px-3 py-1.5 text-sm font-medium text-verified hover:bg-verified/10"
              >
                Verify everything settled
              </button>
            )}
          </div>

          {report.data.physician_verified_by && (
            <p className="mb-3 rounded border border-verified/30 bg-verified-soft px-2 py-1 text-sm text-verified">
              Verified by {report.data.physician_verified_by}.
            </p>
          )}

          {verifyFact.isError && (
            <p role="alert" className="mb-3 text-sm text-urgent">
              That change was not recorded. Someone else may have edited this
              line — reload the report before acting on it again.
            </p>
          )}

          <ReportView
            report={body}
            facts={facts}
            selectedFactId={selectedFactId}
            onSelectFact={setSelectedFactId}
            renderActions={renderActions}
          />

          {/* The rendered text, for the physician who prints it or pastes it
              into the HMIS. The backend renders it; nothing here re-renders. */}
          <details className="mt-6">
            <summary className="cursor-pointer text-xs text-ink-muted">
              Plain-text report
            </summary>
            <pre className="mt-2 whitespace-pre-wrap rounded bg-surface-sunken p-3 text-xs text-ink">
              {report.data.text}
            </pre>
          </details>
        </section>

        <div className="lg:sticky lg:top-4 lg:self-start">
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
