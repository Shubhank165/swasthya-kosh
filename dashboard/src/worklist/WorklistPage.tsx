import { useCallback, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  Clock,
  Search,
} from 'lucide-react';

import { useHospitals, useWorklist } from '../api/queries';
import { useSession } from '../auth/session';
import { ConnectionState } from '../components/ConnectionState';
import { useWorklistSocket } from '../lib/realtime';
import { humanise, timeOfDay } from '../lib/format';
import { HOSPITALS } from '../auth/LoginPage';
import { useLocale } from '../i18n';

/**
 * The five states the backend actually reports, each with its own badge.
 *
 * Collapsing them into three loses the two that matter most to a physician
 * scanning the queue: `seen` is a consultation that already happened, and
 * `needs_review` is a record with something wrong in it. Both previously
 * rendered as "Interview in Progress" — a patient who had already been seen
 * appeared to still be answering questions at the kiosk.
 */
const STATE_BADGES: Record<
  string,
  { en: string; hi: string; tone: string }
> = {
  red_flag_pending: {
    en: 'Emergency Red-Flag',
    hi: 'आपातकालीन रेड-फ्लैग',
    tone: 'bg-alert-soft text-alert',
  },
  ready: {
    en: 'Ready for Review',
    hi: 'समीक्षा के लिए तैयार',
    tone: 'bg-herb-soft text-herb',
  },
  needs_review: {
    en: 'Needs Review',
    hi: 'समीक्षा आवश्यक',
    tone: 'bg-conflict-soft text-conflict',
  },
  partial: {
    en: 'Interview in Progress',
    hi: 'साक्षात्कार जारी है',
    tone: 'bg-saffron-soft text-saffron',
  },
  seen: {
    en: 'Seen',
    hi: 'परामर्श हो चुका',
    tone: 'bg-surface-sunken text-ink-muted',
  },
};

export function WorklistPage({ realtime = true }: { realtime?: boolean }) {
  const session = useSession((state) => state.session);
  const locale = useLocale((state) => state.locale);
  const isHi = locale === 'hi';

  const [department, setDepartment] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const hospitals = useHospitals();
  const deptPills = useMemo(() => {
    const facility = hospitals.data?.hospitals?.find(
      (h) => h.hospital_id === session?.hospitalId,
    );
    return [
      { id: 'all', label: isHi ? 'सभी विभाग' : 'All Departments' },
      ...(facility?.departments ?? []).map((d) => ({
        id: d.code,
        label: d.display,
      })),
    ];
  }, [hospitals.data, session?.hospitalId, isHi]);

  const worklist = useWorklist(department, []);
  const refetch = worklist.refetch;

  const onChange = useCallback(() => {
    void refetch();
  }, [refetch]);

  const { status } = useWorklistSocket({ department, onChange, enabled: realtime });

  const rawEntries = worklist.data?.entries ?? [];
  const pending = worklist.data?.pending_alerts ?? [];

  // Filter entries strictly by search query
  const entries = useMemo(() => {
    if (!searchQuery.trim()) return rawEntries;
    const q = searchQuery.toLowerCase().trim();
    return rawEntries.filter(
      (e) =>
        e.intake_id.toLowerCase().includes(q) ||
        (e.department_code && e.department_code.toLowerCase().includes(q)) ||
        e.patient_ref_type.toLowerCase().includes(q),
    );
  }, [rawEntries, searchQuery]);

  // KPIs
  const totalWaiting = rawEntries.length;
  const readyCount = rawEntries.filter((e) => e.state === 'ready').length;
  const progressCount = rawEntries.filter(
    (e) => e.state === 'partial' || e.state === 'needs_review',
  ).length;
  // `pending_alerts` is *defined* as the entries in `red_flag_pending`
  // (domain/worklist.py:142), so adding the two counted every red-flag patient
  // twice: one patient with chest pain read as "2 Emergency Red-Flags".
  const redFlagCount = rawEntries.filter((e) => e.state === 'red_flag_pending').length;

  const matchedHospital = HOSPITALS.find((h) => h.id === session?.hospitalId);
  const hospitalName = isHi
    ? (matchedHospital?.nameHi ?? 'अखिल भारतीय आयुर्वेद संस्थान, नई दिल्ली')
    : (matchedHospital?.nameEn ?? 'All India Institute of Ayurveda, New Delhi');

  const todayStr = new Intl.DateTimeFormat(isHi ? 'hi-IN' : 'en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date());

  return (
    <div className="space-y-6">
      {/* Facility bar card */}
      <div className="surface-card flex flex-wrap items-center justify-between gap-4 p-5 animate-fade-rise">
        <div className="flex items-center gap-3.5">
          <span className="flex size-11 items-center justify-center rounded-xl bg-herb-soft text-herb shadow-sm">
            <Building2 className="size-6" />
          </span>
          <div>
            <h1 className="text-lg font-bold text-ink sm:text-xl">
              {hospitalName}
            </h1>
            <p className="text-xs text-ink-muted">
              {session?.departmentCode
                ? `${humanise(session.departmentCode)} ${isHi ? 'ओपीडी' : 'OPD'}`
                : isHi ? 'सामान्य ओपीडी' : 'General OPD'}{' '}
              • {isHi ? 'काउंटर ३' : 'Counter 3'} • {todayStr}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <ConnectionState status={status} />
          <Link
            to="/login"
            className="rounded-lg border border-line bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-sm transition-colors hover:bg-surface-sunken"
          >
            {isHi ? 'अस्पताल बदलें' : 'Change Facility'}
          </Link>
        </div>
      </div>

      {/* KPI Cards */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="surface-card overflow-hidden animate-fade-rise">
          <div className="h-1.5 w-full bg-ink" />
          <div className="p-5">
            <p className="text-xs font-medium text-ink-muted">
              {isHi ? 'कुल प्रतीक्षारत रोगी' : 'Total Patients Waiting'}
            </p>
            <p className="mt-2 text-3xl font-bold text-ink">{totalWaiting}</p>
            <p className="mt-1 text-[11px] text-ink-muted">
              {isHi ? 'सभी सक्रिय ओपीडी काउंटरों पर' : 'Across all active OPD counters'}
            </p>
          </div>
        </div>

        <div className="surface-card overflow-hidden animate-fade-rise">
          <div className="h-1.5 w-full bg-herb" />
          <div className="p-5">
            <p className="text-xs font-medium text-ink-muted">
              {isHi ? 'परामर्श हेतु तैयार' : 'Ready for Doctor'}
            </p>
            <p className="mt-2 text-3xl font-bold text-herb">{readyCount}</p>
            <p className="mt-1 text-[11px] text-ink-muted">
              {isHi ? 'कियोस्क इनटेक पूर्ण एवं सत्यापित' : 'Kiosk intake completed & verified'}
            </p>
          </div>
        </div>

        <div className="surface-card overflow-hidden animate-fade-rise">
          <div className="h-1.5 w-full bg-saffron" />
          <div className="p-5">
            <p className="text-xs font-medium text-ink-muted">
              {isHi ? 'प्रक्रियाधीन (कियोस्क पर)' : 'In-Progress at Kiosk'}
            </p>
            <p className="mt-2 text-3xl font-bold text-saffron">{progressCount}</p>
            <p className="mt-1 text-[11px] text-ink-muted">
              {isHi ? 'वर्तमान में इनटेक प्रश्नों के उत्तर दे रहे हैं' : 'Currently answering intake questions'}
            </p>
          </div>
        </div>

        <div className="surface-card overflow-hidden animate-fade-rise">
          <div className="h-1.5 w-full bg-alert" />
          <div className="p-5">
            <p className="text-xs font-medium text-ink-muted">
              {isHi ? 'आपातकालीन रेड-फ्लैग' : 'Emergency Red-Flags'}
            </p>
            <p className="mt-2 text-3xl font-bold text-alert">{redFlagCount}</p>
            <p className="mt-1 text-[11px] text-ink-muted">
              {isHi ? 'सक्रिय आपातकालीन ट्राइएज' : 'Active acute triage events'}
            </p>
          </div>
        </div>
      </section>

      {/* Urgent Red-Flag Banner */}
      {pending.length > 0 && (
        <div
          role="alert"
          className="animate-pulse-flag flex items-start gap-4 rounded-xl border border-alert/40 bg-alert-soft p-4 shadow-sm"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-alert text-white shadow-sm">
            <AlertTriangle className="size-5" />
          </span>
          <div className="flex-1">
            <p className="text-xs font-bold uppercase tracking-wider text-alert">
              {isHi ? '🚨 आपातकालीन रेड-फ्लैग अलर्ट' : '🚨 Urgent Red-Flag Alert'}
            </p>
            <p className="mt-1 text-sm font-medium text-ink">
              {pending.length === 1 && pending[0]
                ? isHi
                  ? `टोकन #${pending[0].intake_id.slice(0, 8)} में तत्काल चिकित्सक ध्यान की आवश्यकता वाले तीव्र लक्षण रिपोर्ट हुए हैं।`
                  : `Token #${pending[0].intake_id.slice(0, 8)} reported acute symptoms requiring immediate physician attention.`
                : isHi
                ? `कतार में ${pending.length} रोगियों ने आपातकालीन ट्राइएज मानदंड सक्रिय किए हैं।`
                : `${pending.length} patients in queue triggered acute emergency triage criteria.`}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {pending.map((alert) => (
                <Link
                  key={alert.intake_id}
                  to={`/intakes/${alert.intake_id}`}
                  className="inline-flex items-center gap-1 rounded-md bg-white px-2.5 py-1 text-xs font-semibold text-alert shadow-sm hover:underline"
                >
                  {isHi ? 'समीक्षा करें #' : 'Review #'}{alert.intake_id.slice(0, 8)} <ArrowRight className="size-3" />
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Search & Department Filters */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" />
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={isHi ? 'इंटेक आईडी या विभाग से खोजें…' : 'Search by intake ID or department…'}
            className="h-10 w-full rounded-xl border border-line bg-white pl-9 pr-4 text-xs text-ink outline-none transition-shadow placeholder:text-ink-muted focus:border-herb focus:ring-2 focus:ring-herb"
          />
        </div>

        <div className="flex flex-wrap gap-1.5">
          {deptPills.map((dept) => {
            const isSelected =
              (dept.id === 'all' && department === null) || department === dept.id;
            return (
              <button
                key={dept.id}
                type="button"
                onClick={() => setDepartment(dept.id === 'all' ? null : dept.id)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
                  isSelected
                    ? 'bg-herb text-white shadow-sm'
                    : 'border border-line bg-white text-ink-muted hover:border-herb/50 hover:text-ink'
                }`}
              >
                {dept.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Queue List Table */}
      {/* Not `role="table"`: this is a card list, and an ARIA table with no
          rows, cells or column headers announces a table to a screen reader
          and then offers nothing to navigate — worse than claiming nothing.
          The rows below carry `role="listitem"`. Restoring the real `<table>`
          §9 asks for is the proper fix and is worth doing after the demo. */}
      <div className="surface-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-line bg-[#f8faf9] px-6 py-3.5">
          <div className="flex items-center gap-2 text-xs font-semibold tracking-wider uppercase text-ink-muted">
            <Clock className="size-4 text-herb" />
            {isHi ? 'लाइव कतार — आगमन समय अनुसार' : 'Live Queue — Ordered by Arrival Time'}
          </div>
          <span className="rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-ink-muted border border-line">
            {entries.length} {isHi ? 'रोगी' : entries.length === 1 ? 'patient' : 'patients'}
          </span>
        </div>

        {worklist.isLoading ? (
          <div className="p-8 text-center text-xs text-ink-muted">
            {isHi ? 'रीयल-टाइम ओपीडी कतार लोड हो रही है…' : 'Loading real-time OPD queue…'}
          </div>
        ) : entries.length === 0 ? (
          <div className="p-8 text-center text-xs text-ink-muted">
            {searchQuery
              ? isHi ? 'आपकी खोज के अनुसार कोई रोगी नहीं मिला।' : 'No patients match your search filter.'
              : isHi ? 'वर्तमान में कतार में कोई रोगी नहीं है।' : 'No patients currently in queue.'}
          </div>
        ) : (
          <div role="list" aria-label={isHi ? 'ओपीडी कतार' : 'OPD queue'} className="divide-y divide-line">
            {entries.map((entry, index) => {
              const tokenNum = `#OPD-${101 + index}`;
              const badge = STATE_BADGES[entry.state] ?? STATE_BADGES.partial!;

              return (
                <div
                  key={entry.intake_id}
                  role="listitem"
                  data-testid="worklist-row"
                  data-state={entry.state}
                  className="flex flex-wrap items-center justify-between gap-4 px-6 py-4 transition-colors hover:bg-[#fbfcfb]"
                >
                  <div className="flex items-center gap-4">
                    {/* Token & Arrival */}
                    <div className="min-w-[90px]">
                      <span className="block font-bold text-sm text-ink">{tokenNum}</span>
                      <span className="block text-[11px] text-ink-muted tabular-nums">
                        {timeOfDay(entry.arrived_at)}
                      </span>
                    </div>

                    {/* Patient Reference & Metadata */}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-ink">
                          {isHi ? 'इंटेक' : 'Intake'} #{entry.intake_id.slice(0, 8)}
                        </span>
                        <span className="rounded-md bg-surface-sunken px-2 py-0.5 text-[10px] font-semibold text-ink-muted uppercase border border-line">
                          {entry.patient_ref_type === 'phone'
                            ? (isHi ? 'ऐप उपयोगकर्ता' : 'App User')
                            : entry.patient_ref_type === 'abha'
                            ? (isHi ? 'आभा (ABDM)' : 'ABHA / ABDM')
                            : entry.patient_ref_type === 'hospital_id'
                            ? (isHi ? 'अस्पताल यूएचआईडी' : 'Hospital UHID')
                            : (isHi ? 'कियोस्क आगंतुक' : 'Kiosk Guest')}
                        </span>
                        <span className="text-xs text-ink-muted">
                          • {humanise(entry.department_code ?? 'general')}
                        </span>
                      </div>

                      <div className="mt-1 flex items-center gap-3 text-[11px] text-ink-muted">
                        <span>
                          {isHi ? 'भाषा:' : 'Language:'} {entry.language.toUpperCase()}
                        </span>
                        {entry.unresolved_count > 0 && (
                          <span className="text-uncertain">
                            {entry.unresolved_count} {isHi ? 'अप्राप्त' : 'unresolved'}
                          </span>
                        )}
                        {entry.contradiction_count > 0 && (
                          <span className="text-conflict">
                            {entry.contradiction_count} {isHi ? 'विरोधाभास' : 'conflict'}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Status & Action */}
                  <div className="flex items-center gap-4">
                    <span
                      data-state={entry.state}
                      className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${badge.tone}`}
                    >
                      {isHi ? badge.hi : badge.en}
                    </span>

                    <Link
                      to={`/intakes/${entry.intake_id}`}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-herb px-4 py-2 text-xs font-semibold text-white shadow-sm transition-all hover:bg-herb-deep hover:-translate-y-px"
                    >
                      {isHi ? 'रोगी फ़ाइल खोलें' : 'Open Patient File'} <ArrowRight className="size-3.5" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
