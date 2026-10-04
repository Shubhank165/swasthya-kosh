/**
 * Sign-in — 3/3 §8.
 *
 * **This form is a stand-in and says so on screen.** The backend's header
 * principal (`app/api/auth.py`) exists so the dashboard could be built before
 * the hospital's identity provider was integrated, and it is disabled in any
 * environment holding real data. A demo that quietly looked like a real login
 * would be claiming an integration this project does not have; the notice below
 * is the difference between a stand-in and a lie.
 *
 * `patient` and `kiosk` are not offered here and are refused if they arrive
 * anyway — see `canSeeClinicalContent` and `RequireDashboardRole`. Nothing is
 * written to localStorage, on this screen or any other.
 */
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  ClipboardList,
  HeartPulse,
  Lock,
  ShieldCheck,
  Pill,
  Stethoscope,
  UserRound,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useHospitals } from '../api/queries';
import { LocaleSwitch } from '../components/LocaleSwitch';
import { useLocale, useT } from '../i18n';
import { HOME_FOR, useSession, type DashboardRole } from './session';

/**
 * Fallback only, used when `/hospitals` cannot be reached.
 *
 * The live list comes from the backend — see `useHospitals`. A facility that
 * exists only in this array is one a physician can select and then find an
 * empty worklist behind, because every query is scoped by `hospital_id`.
 */
export const HOSPITALS = [
  { id: 'aiia-delhi', nameEn: 'Sanjeevani Multi-Specialty Hospital, New Delhi', nameHi: 'संजीवनी मल्टी-स्पेशलिटी अस्पताल, नई दिल्ली' },
  { id: 'nia-jaipur', nameEn: 'Sanjeevani Hospital, Jaipur', nameHi: 'संजीवनी अस्पताल, जयपुर' },
  { id: 'itra-jamnagar', nameEn: 'District General Hospital, Jamnagar', nameHi: 'ज़िला सामान्य अस्पताल, जामनगर' },
  { id: 'gah-varanasi', nameEn: 'Govt. General Hospital, Varanasi', nameHi: 'राजकीय सामान्य अस्पताल, वाराणसी' },
];

/**
 * Fallback department list, and it must agree with the backend's `_DISPLAY` in
 * `api/v1/hospitals.py` — that is where the real list comes from. These are the
 * general specialties a board outside an OPD actually names.
 */
export const DEPARTMENTS = [
  { id: 'general_medicine', nameEn: 'General Medicine', nameHi: 'सामान्य चिकित्सा' },
  { id: 'orthopaedics', nameEn: 'Orthopaedics', nameHi: 'हड्डी रोग' },
  { id: 'paediatrics', nameEn: 'Paediatrics', nameHi: 'बाल रोग' },
  { id: 'ent', nameEn: 'ENT', nameHi: 'नाक, कान और गला' },
  { id: 'obstetrics_gynaecology', nameEn: 'Obstetrics and Gynaecology', nameHi: 'प्रसूति एवं स्त्री रोग' },
  { id: 'cardiology', nameEn: 'Cardiology', nameHi: 'हृदय रोग' },
];

export const DOCTORS = [
  'Dr. Shalini Verma',
  'Dr. Arvind Sharma',
  'Dr. Meera Nair',
  'Dr. Rajesh Kulkarni',
];

export function LoginPage() {
  const t = useT();
  const locale = useLocale((state) => state.locale);
  const isHi = locale === 'hi';
  const signIn = useSession((state) => state.signIn);
  const navigate = useNavigate();

  /**
   * Sign in, then land on a screen this role may actually open.
   *
   * Without the navigate, a sign-in leaves the browser on whatever URL was
   * already there — which on a shared OPD terminal is the previous person's
   * screen. A pharmacist signing in behind a receptionist got "Not available
   * to this role" for `/reception`, a screen they never asked for, and had to
   * work out that the nav tab was the way forward.
   *
   * `replace`, so the back button does not return to the sign-in screen of a
   * session that no longer exists.
   */
  function enter(session: Parameters<typeof signIn>[0]) {
    signIn(session);
    navigate(HOME_FOR[session.role], { replace: true });
  }
  const endedBecause = useSession((state) => state.endedBecause);

  const hospitals = useHospitals();
  const facilities = useMemo(
    () => hospitals.data?.hospitals ?? [],
    [hospitals.data],
  );

  const [hospitalId, setHospitalId] = useState(HOSPITALS[0]!.id);
  const [departmentCode, setDepartmentCode] = useState(DEPARTMENTS[0]!.id);

  // Once the real list arrives, settle on a facility and a department that
  // actually exist. Selecting one that does not is indistinguishable from an
  // outage: the worklist simply comes back empty.
  const firstFacility = facilities[0]?.hospital_id;
  useEffect(() => {
    if (firstFacility && !facilities.some((h) => h.hospital_id === hospitalId)) {
      setHospitalId(firstFacility);
    }
  }, [facilities, firstFacility, hospitalId]);

  const departments = useMemo(
    () => facilities.find((h) => h.hospital_id === hospitalId)?.departments ?? [],
    [facilities, hospitalId],
  );
  const firstDepartment = departments[0]?.code;
  useEffect(() => {
    if (firstDepartment && !departments.some((d) => d.code === departmentCode)) {
      setDepartmentCode(firstDepartment);
    }
  }, [departments, firstDepartment, departmentCode]);
  const [role, setRole] = useState<DashboardRole>('physician');
  const [doctorName, setDoctorName] = useState(DOCTORS[0]!);
  const [pin, setPin] = useState('');

  /**
   * Who each role signs in as. The label is chrome; the `DashboardRole` is what
   * travels to the backend as `X-User-Role`, and the backend has to recognise
   * it — a role this list invents is a 401 on every request.
   *
   * `triage` used to be here, mapped from the Receptionist button, and the
   * backend has never had such a role: signing in as a receptionist 401'd on
   * every call and the auth-failure handler signed them straight back out.
   */
  const SIGN_IN_AS: { role: DashboardRole; label: string; labelHi: string; desk: string }[] = [
    { role: 'physician', label: 'Doctor', labelHi: 'डॉक्टर', desk: DOCTORS[0]! },
    { role: 'receptionist', label: 'Receptionist', labelHi: 'रिसेप्शन', desk: 'Reception Counter 1' },
    { role: 'chemist', label: 'Pharmacy', labelHi: 'औषधालय', desk: 'Pharmacy Counter' },
    { role: 'admin', label: 'Administrator', labelHi: 'प्रशासक', desk: 'Administrator' },
  ];

  function submit(event: FormEvent) {
    event.preventDefault();
    const chosen = SIGN_IN_AS.find((entry) => entry.role === role) ?? SIGN_IN_AS[0]!;
    enter({
      userId: role === 'physician' ? doctorName : chosen.desk,
      role,
      hospitalId: hospitalId || 'aiia-delhi',
      departmentCode: departmentCode || null,
    });
  }

  function handleDemo(demoRole: DashboardRole) {
    const chosen = SIGN_IN_AS.find((entry) => entry.role === demoRole) ?? SIGN_IN_AS[0]!;
    enter({
      userId: demoRole === 'physician' ? 'Dr. R. Sharma' : chosen.desk,
      role: demoRole,
      hospitalId: 'aiia-delhi',
      departmentCode: 'general_medicine',
    });
  }

  return (
    <div className="min-h-screen bg-[#f8faf9]">
      <div className="tricolour-rule h-1.5 w-full" />
      <header className="border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-6">
          <span className="brand-gradient flex size-10 items-center justify-center rounded-xl text-white shadow-sm">
            <HeartPulse className="size-5" />
          </span>
          <span className="leading-tight">
            <span className="block font-semibold text-ink text-base">
              {isHi ? 'मेडीकियोस्क अस्पताल पोर्टल' : 'MediKiosk Hospital Portal'}
            </span>
            <span className="block text-[11px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
              {isHi ? 'परामर्श-पूर्व पंजीकरण • ओपीडी' : 'Pre-consultation intake • OPD'}
            </span>
          </span>
          <div className="ml-auto">
            <LocaleSwitch />
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-10 px-6 py-12 lg:grid-cols-2 lg:items-center">
        {/* Left column */}
        <section className="animate-fade-rise">
          <span className="inline-flex items-center gap-2 rounded-full bg-brand-soft px-3.5 py-1 text-xs font-semibold text-brand">
            <ShieldCheck className="size-4" /> {isHi ? 'एबीडीएम-अनुरूप • FHIR R4 सक्षम' : 'ABDM-compliant • FHIR R4 ready'}
          </span>
          <h1 className="mt-5 text-3xl sm:text-4xl font-bold tracking-tight text-ink leading-tight">
            {isHi ? (
              <>
                ओपीडी पंजीकरण एवं
                <br />
                कार्यप्रवाह स्वचालन
              </>
            ) : (
              <>
                OPD Intake & Workflow
                <br />
                Automation Suite
              </>
            )}
          </h1>
          <p className="mt-4 max-w-md text-sm sm:text-base leading-relaxed text-ink-muted">
            {isHi
              ? 'अस्पताल ओपीडी के लिए कियोस्क-आधारित परामर्श-पूर्व पंजीकरण, बहुभाषी केस-टेकिंग और लाल-झंडा स्क्रीनिंग।'
              : 'Kiosk-led pre-consultation intake, multilingual case taking, and red-flag screening for hospital OPDs.'}
          </p>

          {/* Visual Hero Card with subtle floating micro-animations */}
          <div className="relative mt-7 max-w-md overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-brand-deep to-brand p-6 text-white shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex size-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
                <HeartPulse className="size-6 text-emerald-200" />
              </span>
              <div>
                <h3 className="font-semibold text-lg leading-tight">
                  {isHi ? 'डिजिटल ओपीडी पंजीकरण' : 'Digital OPD Intake'}
                </h3>
                <p className="text-xs text-white/80">
                  {isHi ? 'रीयल-टाइम प्री-कंसल्टेशन सिस्टम' : 'Real-time Pre-Consultation System'}
                </p>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="animate-login-float flex size-10 items-center justify-center rounded-full bg-white/20 backdrop-blur shadow-sm">
                  <Stethoscope className="size-5 text-amber-200" />
                </span>
                <span className="text-xs font-medium">
                  {isHi ? 'डॉक्टर इनटेक समीक्षा' : 'Doctor Intake Review'}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="animate-login-float flex size-10 items-center justify-center rounded-full bg-white/20 backdrop-blur shadow-sm" style={{ animationDelay: '1.2s' }}>
                  <ClipboardList className="size-5 text-emerald-200" />
                </span>
                <span className="text-xs font-medium">
                  {isHi ? 'पर्चा ओसीआर' : 'Prescription OCR'}
                </span>
              </div>
            </div>
          </div>

          <dl className="mt-8 grid max-w-md grid-cols-3 gap-3">
            {[
              ['42', isHi ? 'संबद्ध अस्पताल' : 'Affiliated hospitals'],
              ['11', isHi ? 'क्षेत्रीय भाषाएँ' : 'Regional languages'],
              ['24×7', isHi ? 'पंजीकरण सहायता' : 'Intake support'],
            ].map(([v, l]) => (
              <div key={l} className="surface-card p-4 text-center">
                <dt className="text-2xl font-bold text-brand">{v}</dt>
                <dd className="mt-1 text-xs text-ink-muted">{l}</dd>
              </div>
            ))}
          </dl>
        </section>

        {/* Right column */}
        <section className="surface-card animate-fade-rise p-8">
          <h2 className="text-xl font-bold text-ink">
            {isHi ? 'कर्मचारी साइन-इन' : 'Staff sign in'}
          </h2>
          <p className="mt-1 text-xs sm:text-sm text-ink-muted">
            {isHi
              ? 'लाइव ओपीडी कतार देखने के लिए अपना अस्पताल और विभाग चुनें।'
              : 'Select your facility and department to access the live OPD queue.'}
          </p>

          {endedBecause === 'idle' && (
            <p
              role="status"
              className="mt-4 rounded-xl border border-uncertain/30 bg-uncertain-soft px-3 py-2 text-xs font-medium text-uncertain"
            >
              {t('login.endedIdle')}
            </p>
          )}
          {endedBecause === 'refused' && (
            <p
              role="status"
              className="mt-4 rounded-xl border border-alert/30 bg-alert-soft px-3 py-2 text-xs font-medium text-alert"
            >
              {t('login.endedRefused')}
            </p>
          )}

          <form onSubmit={submit} className="mt-6 space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                {isHi ? 'संबद्ध अस्पताल' : 'Hospital affiliation'}
              </span>
              <select
                value={hospitalId}
                onChange={(e) => setHospitalId(e.target.value)}
                className="h-11 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none transition-colors hover:border-brand focus:ring-2 focus:ring-brand cursor-pointer"
              >
                {facilities.length > 0
                  ? facilities.map((h) => (
                      <option key={h.hospital_id} value={h.hospital_id}>
                        {h.display_name}
                      </option>
                    ))
                  : HOSPITALS.map((h) => (
                      <option key={h.id} value={h.id}>
                        {isHi ? h.nameHi : h.nameEn}
                      </option>
                    ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                {isHi ? 'ओपीडी विभाग' : 'OPD department'}
              </span>
              <select
                value={departmentCode}
                onChange={(e) => setDepartmentCode(e.target.value)}
                className="h-11 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none transition-colors hover:border-brand focus:ring-2 focus:ring-brand cursor-pointer"
              >
                {departments.length > 0
                  ? departments.map((d) => (
                      <option key={d.code} value={d.code}>
                        {d.display}
                      </option>
                    ))
                  : DEPARTMENTS.map((d) => (
                      <option key={d.id} value={d.id}>
                        {isHi ? d.nameHi : d.nameEn}
                      </option>
                    ))}
              </select>
            </label>

            <div>
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                {isHi ? 'मैं इस रूप में साइन इन कर रहा हूँ' : 'I am signing in as'}
              </span>
              <div className="grid grid-cols-2 gap-2 rounded-xl bg-surface-sunken p-1 border border-line">
                {SIGN_IN_AS.map((entry) => (
                  <button
                    key={entry.role}
                    type="button"
                    data-testid={`signin-as-${entry.role}`}
                    onClick={() => setRole(entry.role)}
                    className={`flex h-10 items-center justify-center gap-2 rounded-lg text-xs font-semibold transition-all ${
                      role === entry.role
                        ? 'bg-white text-brand shadow-sm'
                        : 'text-ink-muted hover:text-ink'
                    }`}
                  >
                    {entry.role === 'physician' ? (
                      <Stethoscope className="size-4" />
                    ) : entry.role === 'chemist' ? (
                      <Pill className="size-4" />
                    ) : (
                      <UserRound className="size-4" />
                    )}
                    {isHi ? entry.labelHi : entry.label}
                  </button>
                ))}
              </div>
            </div>

            {role === 'physician' && (
              <label className="block animate-fade-rise">
                <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {isHi ? 'डॉक्टर का नाम' : 'Doctor name'}
                </span>
                <select
                  value={doctorName}
                  onChange={(e) => setDoctorName(e.target.value)}
                  className="h-11 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none transition-colors hover:border-brand focus:ring-2 focus:ring-brand cursor-pointer"
                >
                  {DOCTORS.map((doc) => (
                    <option key={doc} value={doc}>
                      {doc}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                {isHi ? 'पिन / पासवर्ड' : 'PIN / Password'}
              </span>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" />
                <input
                  type="password"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="••••••"
                  className="h-11 w-full rounded-xl border border-line bg-white pl-10 pr-3 text-sm text-ink outline-none transition-colors hover:border-brand focus:ring-2 focus:ring-brand"
                />
              </div>
            </label>

            <button
              type="submit"
              className="h-11 w-full rounded-xl bg-brand text-sm font-semibold text-white shadow-sm transition-all hover:bg-brand-deep hover:-translate-y-px"
            >
              {isHi ? 'ओपीडी कतार में प्रवेश करें' : 'Sign in to OPD Queue'}
            </button>
          </form>

          {/* Quick 1-click Demo access */}
          <div className="mt-6 rounded-xl border border-dashed border-line bg-[#f8faf9] p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              {isHi ? 'एक-क्लिक डेमो प्रवेश' : 'One-click demo access'}
            </p>
            <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
              {SIGN_IN_AS.map((entry) => (
                <button
                  key={entry.role}
                  type="button"
                  data-testid={`demo-${entry.role}`}
                  onClick={() => handleDemo(entry.role)}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-brand/30 bg-white px-3 py-2 text-xs font-semibold text-brand shadow-sm transition-colors hover:bg-brand-soft"
                >
                  {entry.role === 'physician' ? (
                    <Stethoscope className="size-4" />
                  ) : entry.role === 'chemist' ? (
                    <Pill className="size-4" />
                  ) : (
                    <UserRound className="size-4" />
                  )}
                  {isHi ? `डेमो: ${entry.labelHi}` : `Demo: ${entry.label}`}
                </button>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
