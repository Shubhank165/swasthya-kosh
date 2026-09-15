import { useCallback, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Check,
  FileDown,
  FileText,
  FlaskConical,
  GitCompare,
  Pill,
  Printer,
  Sparkles,
} from 'lucide-react';

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
import { EvidenceDrawer } from '../evidence/EvidencePanel';
import { useLocale, useT } from '../i18n';
import { evidenceFromApi } from '../evidence/fromApi';
import { ReportView, type ReportTab } from './ReportView';
import { VerifyControls } from './VerifyControls';
import { humanise, timeOfDay } from '../lib/format';

const TABS = [
  { id: 'complaint', labelEn: 'Chief Complaint & HPI', labelHi: 'मुख्य शिकायत एवं HPI', icon: FileText },
  { id: 'ayurveda', labelEn: 'Ayurvedic Assessment', labelHi: 'आयुर्वेदिक मूल्यांकन', icon: Sparkles },
  { id: 'meds', labelEn: 'Medications & Safety', labelHi: 'औषधियाँ एवं सुरक्षा', icon: Pill },
  { id: 'labs', labelEn: 'Lab Investigations', labelHi: 'प्रयोगशाला जाँचें', icon: FlaskConical },
  { id: 'discrepancies', labelEn: 'Clinical Discrepancies', labelHi: 'नैदानिक विसंगतियाँ', icon: GitCompare },
  { id: 'all', labelEn: 'Full Record & Print', labelHi: 'संपूर्ण अभिलेख एवं प्रिंट', icon: Printer },
] as const;

export function ReportPage() {
  const t = useT();
  const locale = useLocale((state) => state.locale);
  const isHi = locale === 'hi';
  const { intakeId = '' } = useParams();
  const session = useSession((state) => state.session);
  const isPhysician = session?.role === 'physician' || session?.role === 'admin';

  const intake = useIntake(intakeId);
  const report = useReport(intakeId, locale);
  const documents = useDocuments(intakeId);
  const [selectedFactId, setSelectedFactId] = useState<string | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  // Opens on the whole record, not on one tab. A physician's first look must
  // show everything that is there — prior investigations included, which is
  // where the scanned-document evidence trail starts. The tabs then narrow the
  // view for someone who wants to focus; they never decide what gets seen.
  const [activeTab, setActiveTab] = useState<ReportTab>('all');

  const evidence = useEvidence(intakeId, selectedFactId);
  const verifyFact = useVerifyFact(intakeId);
  const verifyRecord = useVerifyRecord(intakeId);

  const facts = useMemo(() => {
    const byId: Record<string, Fact> = {};
    for (const fact of intake.data?.facts ?? []) byId[fact.fact_id] = fact;
    return byId;
  }, [intake.data]);

  // Coverage as a count, never a percentage (§5). A percentage reads as a score
  // and invites "83% is fine"; "9 of 12 answered" states what is missing.
  const factList = intake.data?.facts ?? [];
  const answered = factList.filter((fact) => fact.status === 'answered').length;
  const total = factList.length;

  const documentUrl = useCallback(
    (documentId: string) =>
      (documents.data ?? []).find((doc) => doc.document_id === documentId)?.url ??
      undefined,
    [documents.data],
  );

  const handleSelectFact = useCallback((factId: string) => {
    setSelectedFactId(factId);
    setIsDrawerOpen(true);
  }, []);

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
      <div className="surface-card p-8 text-center">
        <p role="alert" className="text-sm font-semibold text-alert">
          {t('report.loadError')}
        </p>
        <Link
          to="/"
          className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-herb hover:underline"
        >
          <ArrowLeft className="size-3.5" /> {isHi ? 'ओपीडी कतार पर वापस' : 'Back to OPD queue'}
        </Link>
      </div>
    );
  }

  if (!intake.data || !report.data) {
    return (
      <div className="surface-card p-12 text-center text-xs text-ink-muted">
        {isHi ? 'परामर्श रिपोर्ट लोड हो रही है…' : 'Loading patient consultation report…'}
      </div>
    );
  }

  const body = report.data.report as unknown as PhysicianReport;
  const isVerified = Boolean(report.data.physician_verified_by);
  const refType = String(intake.data.patient_ref?.type ?? 'guest');

  return (
    <div className="space-y-6">
      {/* Back button */}
      <div>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-muted transition-colors hover:text-ink"
        >
          <ArrowLeft className="size-4" /> {isHi ? 'ओपीडी कतार पर वापस' : 'Back to OPD queue'}
        </Link>
      </div>

      {/* Patient Header Banner */}
      <section className="surface-card overflow-hidden animate-fade-rise">
        <div className="ayush-gradient h-1.5 w-full" />
        <div className="flex flex-wrap items-center justify-between gap-6 p-6">
          <div className="flex items-center gap-4">
            <span className="flex size-14 items-center justify-center rounded-2xl bg-herb-soft text-xl font-bold text-herb shadow-sm">
              {refType === 'phone' ? 'P' : 'A'}
            </span>
            <div>
              <h1 className="text-2xl font-bold text-ink">
                {isHi ? 'रोगी' : 'Patient'} #{intakeId.slice(0, 8)}
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-lg bg-surface-sunken px-2.5 py-1 font-medium text-ink-muted border border-line">
                  <span className="text-ink-muted/80">{isHi ? 'संदर्भ: ' : 'Ref: '}</span>
                  <span className="text-ink font-semibold uppercase">{refType}</span>
                </span>
                <span className="rounded-lg bg-surface-sunken px-2.5 py-1 font-medium text-ink-muted border border-line">
                  <span className="text-ink-muted/80">{isHi ? 'आगमन: ' : 'Arrived: '}</span>
                  <span className="text-ink font-semibold">
                    {intake.data.received_at ? timeOfDay(intake.data.received_at) : (isHi ? 'आज' : 'Today')}
                  </span>
                </span>
                <span className="rounded-lg bg-surface-sunken px-2.5 py-1 font-medium text-ink-muted border border-line">
                  <span className="text-ink-muted/80">{isHi ? 'ओपीडी: ' : 'OPD: '}</span>
                  <span className="text-ink font-semibold">
                    {humanise(intake.data.department_code ?? 'Kayachikitsa')}
                  </span>
                </span>
              </div>
            </div>
          </div>

          {isPhysician && (
            <button
              type="button"
              data-testid="verify-all"
              disabled={verifyRecord.isPending}
              onClick={() => verifyRecord.mutate({})}
              className={`inline-flex items-center gap-2 rounded-xl px-5 py-3 text-xs sm:text-sm font-semibold shadow-sm transition-all hover:-translate-y-px ${
                isVerified
                  ? 'bg-herb-soft text-herb border border-herb/30'
                  : 'bg-herb text-white hover:bg-herb-deep'
              }`}
            >
              {isVerified ? <Check className="size-4" /> : <FileDown className="size-4" />}
              {isVerified
                ? (isHi ? 'इनटेक सत्यापित • FHIR R4 निर्यातित' : 'Intake verified • FHIR R4 exported')
                : verifyRecord.isPending
                ? (isHi ? 'सत्यापित हो रहा है…' : 'Verifying…')
                : (isHi ? 'इनटेक सत्यापित करें एवं FHIR R4 निर्यात करें' : 'Verify Intake & Export FHIR R4')}
            </button>
          )}
        </div>
      </section>

      {/* The report must say what it is before anyone reads it (§11): an
          unverified draft, and how much of the interview was actually answered.
          Both were on the old HeaderStrip; the redesign replaced that header
          and they went with it. */}
      <div
        className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border px-5 py-3 text-xs sm:text-sm ${
          isVerified
            ? 'border-verified/30 bg-verified-soft text-verified'
            : 'border-uncertain/30 bg-uncertain-soft text-uncertain'
        }`}
      >
        <span className="font-semibold">
          {isVerified
            ? isHi
              ? 'चिकित्सक द्वारा सत्यापित'
              : 'Verified by physician'
            : t('report.draft')}
        </span>
        <span className="font-medium text-ink-muted" data-testid="coverage">
          {t('header.answered', { answered, total })}
        </span>
      </div>

      {/* Tabs navigation */}
      <div className="flex flex-wrap gap-1.5 rounded-2xl border border-line bg-white p-1.5 shadow-sm">
        {TABS.map((t) => {
          const isActive = activeTab === t.id;
          const label = isHi ? t.labelHi : t.labelEn;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveTab(t.id)}
              className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-herb text-white shadow-sm'
                  : 'text-ink-muted hover:bg-surface-sunken hover:text-ink'
              }`}
            >
              <t.icon className="size-4" /> {label}
            </button>
          );
        })}
      </div>

      {/* Main Tab Content Card */}
      <div className="surface-card p-6 animate-fade-rise">
        {verifyFact.isError && (
          <p role="alert" className="mb-4 text-xs font-semibold text-alert">
            {t('report.writeError')}
          </p>
        )}

        <ReportView
          report={body}
          facts={facts}
          selectedFactId={selectedFactId}
          onSelectFact={handleSelectFact}
          renderActions={renderActions}
          activeTab={activeTab}
        />

        {/* Print and copy actions */}
        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-line pt-4 print:hidden">
          <CopyTextButton text={report.data.text ?? ''} isHi={isHi} />
          <button
            type="button"
            onClick={() => window.print()}
            className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-white px-3.5 py-1.5 text-xs font-semibold text-ink shadow-sm transition-colors hover:bg-surface-sunken"
          >
            <Printer className="size-3.5" /> {isHi ? 'रिपोर्ट प्रिंट करें' : 'Print Report'}
          </button>
        </div>
      </div>

      {/* On-Demand Slide-Out Evidence Drawer */}
      <EvidenceDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        evidence={
          evidence.data ? evidenceFromApi(evidence.data, { documentUrl }) : null
        }
        loading={evidence.isLoading}
        onOpenIntake={(id) => {
          setIsDrawerOpen(false);
          window.location.href = `/intakes/${id}`;
        }}
      />
    </div>
  );
}

function CopyTextButton({ text, isHi = false }: { text: string; isHi?: boolean }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-white px-3.5 py-1.5 text-xs font-semibold text-ink shadow-sm transition-colors hover:bg-surface-sunken"
    >
      {copied ? <Check className="size-3.5 text-herb" /> : null}
      {copied
        ? (isHi ? 'क्लिपबोर्ड पर कॉपी किया गया' : 'Copied to clipboard')
        : (isHi ? 'क्लिनिकल विवरण कॉपी करें' : 'Copy clinical text')}
    </button>
  );
}
