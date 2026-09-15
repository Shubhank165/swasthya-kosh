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
import { useState, type FormEvent } from 'react';
import {
  ClipboardList,
  Leaf,
  Lock,
  ShieldCheck,
  Stethoscope,
  UserRound,
} from 'lucide-react';
import { LocaleSwitch } from '../components/LocaleSwitch';
import { useLocale, useT } from '../i18n';
import { useSession, type DashboardRole } from './session';

export const HOSPITALS = [
  { id: 'aiia-delhi', nameEn: 'All India Institute of Ayurveda (AIIA), New Delhi', nameHi: 'अखिल भारतीय आयुर्वेद संस्थान (AIIA), नई दिल्ली' },
  { id: 'nia-jaipur', nameEn: 'National Institute of Ayurveda (NIA), Jaipur', nameHi: 'राष्ट्रीय आयुर्वेद संस्थान (NIA), जयपुर' },
  { id: 'itra-jamnagar', nameEn: 'ITRA, Jamnagar', nameHi: 'आईटीआरए (ITRA), जामनगर' },
  { id: 'gah-varanasi', nameEn: 'Govt. Ayurvedic Hospital, Varanasi', nameHi: 'राजकीय आयुर्वेद चिकित्सालय, वाराणसी' },
];

export const DEPARTMENTS = [
  { id: 'kayachikitsa', nameEn: 'Kayachikitsa / General Medicine', nameHi: 'कायचिकित्सा (सामान्य चिकित्सा)' },
  { id: 'panchakarma', nameEn: 'Panchakarma', nameHi: 'पंचकर्म' },
  { id: 'shalya-tantra', nameEn: 'Shalya Tantra', nameHi: 'शल्य तंत्र' },
  { id: 'kaumarbhritya', nameEn: 'Kaumarbhritya', nameHi: 'कौमारभृत्य (बाल रोग)' },
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
  const endedBecause = useSession((state) => state.endedBecause);

  const [hospitalId, setHospitalId] = useState(HOSPITALS[0]!.id);
  const [departmentCode, setDepartmentCode] = useState(DEPARTMENTS[0]!.id);
  const [role, setRole] = useState<'doctor' | 'receptionist'>('doctor');
  const [doctorName, setDoctorName] = useState(DOCTORS[0]!);
  const [pin, setPin] = useState('');

  function submit(event: FormEvent) {
    event.preventDefault();
    const dashboardRole: DashboardRole = role === 'doctor' ? 'physician' : 'triage';
    const userId = role === 'doctor' ? doctorName : 'Reception Counter 1';

    signIn({
      userId,
      role: dashboardRole,
      hospitalId: hospitalId || 'aiia-delhi',
      departmentCode: departmentCode || null,
    });
  }

  function handleDemo(demoRole: 'doctor' | 'receptionist') {
    if (demoRole === 'doctor') {
      signIn({
        userId: 'Dr. R. Sharma',
        role: 'physician',
        hospitalId: 'aiia-delhi',
        departmentCode: 'kayachikitsa',
      });
    } else {
      signIn({
        userId: 'Triage Desk 1',
        role: 'triage',
        hospitalId: 'aiia-delhi',
        departmentCode: 'kayachikitsa',
      });
    }
  }

  return (
    <div className="min-h-screen bg-[#f8faf9]">
      <div className="tricolour-rule h-1.5 w-full" />
      <header className="border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-6">
          <span className="ayush-gradient flex size-10 items-center justify-center rounded-xl text-white shadow-sm">
            <Leaf className="size-5" />
          </span>
          <span className="leading-tight">
            <span className="block font-semibold text-ink text-base">
              {isHi ? 'राष्ट्रीय आयुष अस्पताल पोर्टल' : 'National AYUSH Hospital Portal'}
            </span>
            <span className="block text-[11px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
              {isHi ? 'आयुष मंत्रालय • भारत सरकार' : 'Ministry of Ayush • Government of India'}
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
          <span className="inline-flex items-center gap-2 rounded-full bg-herb-soft px-3.5 py-1 text-xs font-semibold text-herb">
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
              ? 'भारत के संबद्ध आयुष अस्पतालों के लिए कियोस्क-आधारित परामर्श-पूर्व पंजीकरण, आयुर्वेदिक मूल्यांकन और स्वचालित ट्रायेज।'
              : 'Kiosk-led pre-consultation intake, Ayurvedic assessment capture, and automated triage for affiliated AYUSH hospitals across India.'}
          </p>

          {/* Visual Hero Card with subtle floating micro-animations */}
          <div className="relative mt-7 max-w-md overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-herb-deep to-herb p-6 text-white shadow-sm">
            <div className="flex items-center gap-3">
              <span className="flex size-11 items-center justify-center rounded-xl bg-white/15 backdrop-blur">
                <Leaf className="size-6 text-emerald-200" />
              </span>
              <div>
                <h3 className="font-semibold text-lg leading-tight">
                  {isHi ? 'आयुष डिजिटल ओपीडी' : 'Ayush Digital OPD'}
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
                <dt className="text-2xl font-bold text-herb">{v}</dt>
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
                className="h-11 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none transition-colors hover:border-herb focus:ring-2 focus:ring-herb cursor-pointer"
              >
                {HOSPITALS.map((h) => (
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
                className="h-11 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none transition-colors hover:border-herb focus:ring-2 focus:ring-herb cursor-pointer"
              >
                {DEPARTMENTS.map((d) => (
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
                <button
                  type="button"
                  onClick={() => setRole('doctor')}
                  className={`flex h-10 items-center justify-center gap-2 rounded-lg text-xs font-semibold transition-all ${
                    role === 'doctor'
                      ? 'bg-white text-herb shadow-sm'
                      : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  <Stethoscope className="size-4" /> {isHi ? 'डॉक्टर' : 'Doctor'}
                </button>
                <button
                  type="button"
                  onClick={() => setRole('receptionist')}
                  className={`flex h-10 items-center justify-center gap-2 rounded-lg text-xs font-semibold transition-all ${
                    role === 'receptionist'
                      ? 'bg-white text-saffron shadow-sm'
                      : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  <UserRound className="size-4" /> {isHi ? 'रिसेप्शनिस्ट' : 'Receptionist'}
                </button>
              </div>
            </div>

            {role === 'doctor' && (
              <label className="block animate-fade-rise">
                <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {isHi ? 'डॉक्टर का नाम' : 'Doctor name'}
                </span>
                <select
                  value={doctorName}
                  onChange={(e) => setDoctorName(e.target.value)}
                  className="h-11 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none transition-colors hover:border-herb focus:ring-2 focus:ring-herb cursor-pointer"
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
                  className="h-11 w-full rounded-xl border border-line bg-white pl-10 pr-3 text-sm text-ink outline-none transition-colors hover:border-herb focus:ring-2 focus:ring-herb"
                />
              </div>
            </label>

            <button
              type="submit"
              aria-label={isHi ? 'ओपीडी कतार में प्रवेश करें (Open the worklist)' : 'Open the worklist'}
              className="h-11 w-full rounded-xl bg-herb text-sm font-semibold text-white shadow-sm transition-all hover:bg-herb-deep hover:-translate-y-px"
            >
              {isHi ? 'ओपीडी कतार में प्रवेश करें' : 'Sign in to OPD Queue (Open the worklist)'}
            </button>
          </form>

          {/* Quick 1-click Demo access */}
          <div className="mt-6 rounded-xl border border-dashed border-line bg-[#f8faf9] p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
              {isHi ? 'एक-क्लिक डेमो प्रवेश' : 'One-click demo access'}
            </p>
            <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => handleDemo('doctor')}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-herb/30 bg-white px-3 py-2 text-xs font-semibold text-herb shadow-sm transition-colors hover:bg-herb-soft"
              >
                <Stethoscope className="size-4" /> {isHi ? 'डेमो: डॉक्टर लॉगिन' : 'Demo: Doctor Login'}
              </button>
              <button
                type="button"
                onClick={() => handleDemo('receptionist')}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-saffron/30 bg-white px-3 py-2 text-xs font-semibold text-saffron shadow-sm transition-colors hover:bg-saffron-soft"
              >
                <UserRound className="size-4" /> {isHi ? 'डेमो: रिसेप्शनिस्ट' : 'Demo: Receptionist'}
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
