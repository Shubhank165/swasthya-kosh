/**
 * Doctor-facing UI, in English and Hindi — 3/3 §9.
 *
 * **This translates the chrome and never the record.** A patient's own words
 * are shown verbatim in their own script, with a translation beneath where one
 * exists — never over the top of it — and that rule is enforced by
 * `ReportView` and `EvidencePanel`, not here. Nothing in this file touches a
 * fact, a marker, a report line, an alert label or a criterion. Those come from
 * the backend in the language the interview happened in, and the language
 * selected here does not change what is fetched.
 *
 * The fact-state labels in `report/factState.ts` are the one boundary case, and
 * they are deliberately **not** here: they are read straight off the report's
 * own markers and are part of the document's meaning rather than its furniture.
 * Translating "not established" is a clinical-wording decision, and §B4 has a
 * queue for those.
 *
 * A flat record of keys rather than nested namespaces, and typed, so a missing
 * Hindi string is a compile error rather than an English word appearing in the
 * middle of a Hindi screen.
 */

export const LOCALES = ['en', 'hi'] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_NAMES: Record<Locale, string> = {
  en: 'English',
  hi: 'हिन्दी',
};

const en = {
  // Shell and navigation
  'app.name': 'MediKiosk',
  'app.subtitle': 'Clinical dashboard',
  'nav.worklist': 'Worklist',
  'nav.alerts': 'Alerts',
  'nav.quality': 'Quality',
  'nav.signOut': 'Sign out',
  'nav.noScreen': 'No such screen.',
  'common.loading': 'Loading…',
  'common.language': 'Language',

  // Sign-in
  'login.userId': 'User ID',
  'login.role': 'Role',
  'login.hospitalId': 'Hospital ID',
  'login.department': 'Department (optional)',
  'login.submit': 'Open the worklist',
  'login.endedIdle': 'Your session was cleared after a period without activity.',
  'login.endedRefused': 'The server refused that request. Sign in again.',
  'login.standInTitle': 'Stand-in sign-in.',
  'login.standIn':
    'This screen sets the backend’s header principal, which is disabled in any environment holding real patient data. It is not authentication and makes no claim to be; the hospital’s identity provider replaces it and changes one file.',

  // Refusal
  'refusal.title': 'Not available to this account',
  'refusal.detail':
    'This screen shows patient records and is limited to clinical staff. Nothing has been loaded.',
  'refusal.notClinicalTitle': 'This account cannot open clinical records',
  'refusal.notClinical':
    'Patient and kiosk credentials are issued to a phone and to a device in a corridor. Neither may read a worklist or a report.',
  'refusal.roleTitle': 'Not available to this role',
  'refusal.signOut': 'Sign in as someone else',

  // Idle
  'idle.warning': 'This session clears in {seconds}s. Any key or click keeps it open.',
  'idle.stay': 'Stay signed in',

  // Connection
  'connection.live': 'Live',
  'connection.connecting': 'Connecting…',
  'connection.reconnecting': 'Not updating — reconnecting',
  'connection.offline': 'Not updating — no connection',

  // Worklist
  'worklist.title': 'Worklist',
  'worklist.allDepartments': 'All departments',
  'worklist.arrivalOrder': 'arrival order',
  'worklist.caption': 'Intakes waiting for a doctor, oldest arrival first',
  'worklist.department': 'Department',
  'worklist.departmentAll': 'all',
  'worklist.filterLegend': 'Filter by state',
  'worklist.colReference': 'Reference',
  'worklist.colArrived': 'Arrived',
  'worklist.colSource': 'Source',
  'worklist.colIntake': 'Intake',
  'worklist.colState': 'State',
  'worklist.colUnresolved': 'Unresolved',
  'worklist.colConflicts': 'Conflicts',
  'worklist.empty': 'Nothing waiting.',
  'worklist.error': 'The worklist could not be loaded.',
  'worklist.hidden': '{count} more intake(s) in this window hidden by the state filter.',
  'worklist.sourceApp': 'App',
  'worklist.sourceKiosk': 'Kiosk or counter',
  'worklist.alertBandLabel': 'Unacknowledged urgent review criteria',
  'worklist.alertBand': '{count} unacknowledged urgent clinical review criteria',
  'worklist.alertBandOne': '1 unacknowledged urgent clinical review criterion',
  'worklist.openAlerts': 'Open the alerts view to acknowledge',
  'worklist.manualReview':
    '{count} intake(s) the repair path could not rescue. A person needs to look before the patient is seen.',
  'worklist.arrived': 'arrived',

  // Worklist states
  'state.ready': 'Ready',
  'state.partial': 'Interview incomplete',
  'state.red_flag_pending': 'Urgent review criterion',
  'state.needs_review': 'Needs review',
  'state.seen': 'Seen',

  // Report header
  'header.reference': 'Reference',
  'header.identifiedBy': 'Identified by',
  'header.language': 'Intake language',
  'header.source': 'Source',
  'header.department': 'Department',
  'header.received': 'Received',
  'header.intakeStatus': 'Intake status',
  'header.coverage': 'Coverage',
  'header.answered': '{answered} of {total} answered',
  'header.demo': 'This deployment is serving demonstration data.',
  'header.activeFlags': '{count} unacknowledged urgent clinical review criteria on this intake.',
  'header.activeFlagsOne': '1 unacknowledged urgent clinical review criterion on this intake.',
  'header.sourceApp': 'Patient app',
  'header.sourceKiosk': 'Kiosk or counter',
  'id.abha': 'ABHA-verified',
  'id.hospital_id': 'Hospital ID',
  'id.phone': 'Phone, in the app',
  'id.aadhaar_last4': 'Aadhaar last four',
  'id.guest': 'Guest — identity not established',
  // The language the interview happened in. A tag on the wire, a name on
  // screen — `hi` is not a word a physician should have to decode.
  'lang.en': 'English',
  'lang.hi': 'Hindi',
  'lang.bn': 'Bengali',
  'lang.ta': 'Tamil',
  'lang.te': 'Telugu',
  'lang.mr': 'Marathi',
  'lang.gu': 'Gujarati',
  'lang.kn': 'Kannada',
  'lang.pa': 'Punjabi',
  // How the intake ended on the device. `aborted_red_flag` humanised reads
  // "aborted red flag", which is not a sentence anyone wrote on purpose.
  'intakeStatus.complete': 'Completed',
  'intakeStatus.partial': 'Left part-way',
  'intakeStatus.aborted_red_flag': 'Stopped — urgent criteria',
  'intakeStatus.abandoned': 'Abandoned',

  // Report
  'report.label': 'Report',
  'report.draft': 'Draft report — requires physician verification',
  'report.verifyAll': 'Verify everything settled',
  'report.verifiedBy': 'Verified by {actor}.',
  'report.loadError': 'This record could not be loaded.',
  'report.backToWorklist': 'Back to the worklist',
  'report.loading': 'Loading the record…',
  'report.plainText': 'Plain-text report',
  'report.writeError':
    'That change was not recorded. Someone else may have edited this line — reload the report before acting on it again.',
  'report.aria': 'Patient report',
  'report.unresolved': 'Unresolved',
  'report.nothingUnresolved': 'Nothing unresolved.',
  'report.conflicts': 'Conflicts',
  'report.noConflicts': 'No conflicting accounts.',
  'report.reportedToday': 'Reported today',
  'report.onRecord': 'Already on record',
  'report.notMentioned': 'Not mentioned in today’s intake.',

  // Sections the backend computes and this screen renders. Drug interactions
  // and the document timeline were being sent and thrown away.
  'report.alerts': 'Urgent review criteria',
  'report.alertsNone': 'No urgent review criteria fired.',
  'report.alertAcknowledged': 'Acknowledged by {actor}.',
  'report.alertUnacknowledged': 'Not yet acknowledged.',
  'report.interactions': 'Medicines to look at together',
  'report.interactionsNone': 'No pairs flagged.',
  'report.interactionSource': 'Source: {source}',
  'report.history': 'Medical history, in time',
  'report.historyPending': 'Not built for this intake yet — reload in a moment.',
  'report.historyNone': 'No dated history on record at this hospital.',
  'report.historyUnfiltered':
    'Every dated entry on record here, newest first. Nothing has been judged for relevance to today.',
  'report.historyFiltered':
    'Selected as related to today’s complaint. {omitted} earlier event(s) were judged unrelated and are not shown; the full record remains available.',
  'report.documentTimeline': 'Uploaded documents, in time',
  'report.documentTimelineNone': 'No documents were uploaded.',
  'report.documentUndated': 'No legible date',
  'report.documentNotes': 'Notes on the documents',
  'report.copy': 'Copy report text',
  'report.copied': 'Copied.',
  'report.copyFailed': 'Could not copy. Use print instead.',
  'report.print': 'Print',
  'report.printHint':
    'Prints the report as laid out here, without the evidence panel or the controls.',

  // Verification
  'verify.accept': 'Accept',
  'verify.amend': 'Amend',
  'verify.reject': 'Reject',
  'verify.verified': 'verified',
  'verify.corrected': 'corrected',
  'verify.acceptHint': 'Confirm this as recorded',
  'verify.acceptDisabled': 'Nothing to confirm — this field was never answered',
  'verify.rejectWarning':
    'This records that the field was never established — not that the answer is no.',
  'verify.confirm': 'Confirm',
  'verify.cancel': 'Cancel',
  'verify.save': 'Save',
  'verify.value': 'Corrected value',
  'verify.unit': 'Unit',
  'verify.reason': 'Reason',
  'verify.reasonPlaceholder': 'Reason (optional)',
  'verify.heard': 'Heard:',
  'verify.yes': 'yes',
  'verify.no': 'no',

  // Evidence
  'evidence.label': 'Evidence',
  'evidence.empty': 'Select any line in the report to see where it came from.',
  'evidence.none': 'No source recorded for this fact.',
  'evidence.voiceTitle': 'What was said',
  'evidence.documentTitle': 'Where it was read',
  'evidence.appTitle': 'What the patient tapped',
  'evidence.carriedTitle': 'From a previous visit',
  'evidence.entryTitle': 'Entered by a person',
  'evidence.asrConfidence': 'Recognition confidence {percent}%',
  'evidence.surrounding': 'Surrounding turns',
  'evidence.imageUnavailable': 'Image unavailable.',
  'evidence.extracted': 'Extracted',
  'evidence.rawText': 'Raw text',
  'evidence.confidence': 'Confidence',
  'evidence.page': 'Document page {page}',
  'evidence.tapped': 'Answered by tapping, in the patient app.',
  'evidence.recorded': 'Recorded',
  'evidence.confirmedToday': 'Confirmed today',
  'evidence.confirmedYes': 'Yes, by the patient',
  'evidence.confirmedNo': 'No',
  'evidence.confirmedNotAsked': 'Not asked',
  'evidence.openVisit': 'Open that visit',
  'evidence.enteredBy':
    'Recorded by {actor}. No recording or document stands behind this line.',
  'evidence.someStaff': 'a member of staff',

  // Alerts
  'alerts.title': 'Urgent review criteria',
  'alerts.subtitle':
    'Criteria that fired on the device during the interview. Unacknowledged first. The device screened a questionnaire; it did not examine anyone.',
  'alerts.hideAcknowledged': 'Hide ones already acknowledged',
  'alerts.error': 'Alerts could not be loaded.',
  'alerts.noneOutstanding': 'Nothing outstanding.',
  'alerts.noneFired': 'No criteria have fired in this window.',
  'alerts.defaultLabel': 'Urgent clinical review criterion triggered',
  'alerts.fired': 'fired {when}',
  'alerts.turn': 'turn {turn}',
  'alerts.intake': 'Intake',
  'alerts.criteria': 'Criteria met',
  'alerts.rule': 'Rule',
  'alerts.note': 'Note (optional)',
  'alerts.acknowledge': 'Acknowledge — I have seen this',
  'alerts.escalate': 'Record an escalation',
  'alerts.escalateConfirm': 'Confirm: I have escalated this to triage',
  'alerts.twoActs':
    'Acknowledging records that you looked. It notifies nobody and moves nothing. Escalation is something you do, in person; this only records that you did.',
  'alerts.conflict':
    'That could not be recorded. It may already have been acknowledged by someone else — reload before acting.',
  'alerts.acknowledgedBy': 'Acknowledged by {actor} at {when}',
  'alerts.arrived': 'arrived',

  // Quality
  'metrics.title': 'Extraction quality',
  'metrics.subtitle': 'How often a physician had to correct what the pipeline recorded.',
  'metrics.correctionRate': 'Correction rate',
  'metrics.notMeasurable': 'Not yet measurable',
  'metrics.breakdown':
    '{amended} amended and {rejected} rejected, out of {reviewed} facts a physician reviewed across {intakes} intake(s).',
  'metrics.reviewed': 'Reviewed',
  'metrics.verified': 'Confirmed as recorded',
  'metrics.amended': 'Amended',
  'metrics.rejected': 'Rejected',
  'metrics.error': 'These counters could not be loaded.',
  'metrics.note':
    'The denominator is facts a physician actually looked at, not every fact stored. A field nobody reviewed says nothing about extraction quality, and counting it would let this number be improved by ingesting more intakes rather than by extracting better. A field acted on twice counts once, with the latest action winning.',
  'metrics.noteEmpty':
    'Until it has data behind it, this figure — and the ones the retired evaluation harness produced — should not appear on a slide.',
} as const;

export type StringKey = keyof typeof en;

/**
 * Hindi.
 *
 * **Engineer-authored, and on `CLINICAL_REVIEW_QUEUE.md` for review** like every
 * other non-English string in this repository. These are interface words —
 * "worklist", "acknowledge", "amend" — and getting one subtly wrong makes a
 * control mean something slightly different to a Hindi-reading physician than
 * to an English-reading one, which is exactly the failure §B4 says no test can
 * catch.
 *
 * Terms deliberately left in English: `MediKiosk`, `ABHA`, `Aadhaar`, and the
 * role names, which are the words the hospital's own systems use.
 */
const hi: Record<StringKey, string> = {
  'app.name': 'MediKiosk',
  'app.subtitle': 'क्लिनिकल डैशबोर्ड',
  'nav.worklist': 'कार्य-सूची',
  'nav.alerts': 'सूचनाएँ',
  'nav.quality': 'गुणवत्ता',
  'nav.signOut': 'साइन आउट',
  'nav.noScreen': 'ऐसी कोई स्क्रीन नहीं है।',
  'common.loading': 'लोड हो रहा है…',
  'common.language': 'भाषा',

  'login.userId': 'उपयोगकर्ता आईडी',
  'login.role': 'भूमिका',
  'login.hospitalId': 'अस्पताल आईडी',
  'login.department': 'विभाग (वैकल्पिक)',
  'login.submit': 'कार्य-सूची खोलें',
  'login.endedIdle': 'निष्क्रियता के कारण आपका सत्र समाप्त कर दिया गया।',
  'login.endedRefused': 'सर्वर ने वह अनुरोध अस्वीकार कर दिया। फिर से साइन इन करें।',
  'login.standInTitle': 'अस्थायी साइन-इन।',
  'login.standIn':
    'यह स्क्रीन बैकएंड का हेडर प्रिंसिपल सेट करती है, जो वास्तविक रोगी डेटा रखने वाले किसी भी परिवेश में बंद रहता है। यह प्रमाणीकरण नहीं है और होने का दावा भी नहीं करता; अस्पताल का पहचान प्रदाता इसकी जगह लेगा और उसमें एक ही फ़ाइल बदलेगी।',

  'refusal.title': 'इस खाते के लिए उपलब्ध नहीं',
  'refusal.detail':
    'यह स्क्रीन रोगी के अभिलेख दिखाती है और केवल चिकित्सकीय कर्मचारियों तक सीमित है। कुछ भी लोड नहीं किया गया है।',
  'refusal.notClinicalTitle': 'यह खाता चिकित्सकीय अभिलेख नहीं खोल सकता',
  'refusal.notClinical':
    'रोगी और कियोस्क के क्रेडेंशियल एक फ़ोन और गलियारे में रखे उपकरण के लिए जारी किए जाते हैं। इनमें से कोई भी कार्य-सूची या रिपोर्ट नहीं पढ़ सकता।',
  'refusal.roleTitle': 'इस भूमिका के लिए उपलब्ध नहीं',
  'refusal.signOut': 'किसी और के रूप में साइन इन करें',

  'idle.warning': 'यह सत्र {seconds} सेकंड में समाप्त हो जाएगा। कोई भी कुंजी या क्लिक इसे खुला रखेगा।',
  'idle.stay': 'साइन इन बने रहें',

  'connection.live': 'लाइव',
  'connection.connecting': 'जुड़ रहा है…',
  'connection.reconnecting': 'अद्यतन नहीं हो रहा — पुनः जुड़ रहा है',
  'connection.offline': 'अद्यतन नहीं हो रहा — कोई कनेक्शन नहीं',

  'worklist.title': 'कार्य-सूची',
  'worklist.allDepartments': 'सभी विभाग',
  'worklist.arrivalOrder': 'आगमन क्रम',
  'worklist.caption': 'डॉक्टर की प्रतीक्षा में इनटेक, सबसे पुराना आगमन पहले',
  'worklist.department': 'विभाग',
  'worklist.departmentAll': 'सभी',
  'worklist.filterLegend': 'स्थिति के अनुसार छाँटें',
  'worklist.colReference': 'संदर्भ',
  'worklist.colArrived': 'आगमन',
  'worklist.colSource': 'स्रोत',
  'worklist.colIntake': 'इनटेक',
  'worklist.colState': 'स्थिति',
  'worklist.colUnresolved': 'अनिर्णीत',
  'worklist.colConflicts': 'विरोधाभास',
  'worklist.empty': 'कोई प्रतीक्षा में नहीं।',
  'worklist.error': 'कार्य-सूची लोड नहीं हो सकी।',
  'worklist.hidden': 'इस अवधि के {count} और इनटेक स्थिति-छँटाई द्वारा छिपाए गए हैं।',
  'worklist.sourceApp': 'ऐप',
  'worklist.sourceKiosk': 'कियोस्क या काउंटर',
  'worklist.alertBandLabel': 'अस्वीकृत तत्काल समीक्षा मानदंड',
  'worklist.alertBand': '{count} अस्वीकृत तत्काल चिकित्सकीय समीक्षा मानदंड',
  'worklist.alertBandOne': '1 अस्वीकृत तत्काल चिकित्सकीय समीक्षा मानदंड',
  'worklist.openAlerts': 'स्वीकार करने के लिए सूचनाएँ खोलें',
  'worklist.manualReview':
    '{count} इनटेक जिन्हें रिपेयर पथ ठीक नहीं कर सका। रोगी को देखने से पहले किसी व्यक्ति को देखना होगा।',
  'worklist.arrived': 'आगमन',

  'state.ready': 'तैयार',
  'state.partial': 'साक्षात्कार अधूरा',
  'state.red_flag_pending': 'तत्काल समीक्षा मानदंड',
  'state.needs_review': 'समीक्षा आवश्यक',
  'state.seen': 'देखा गया',

  'header.reference': 'संदर्भ',
  'header.identifiedBy': 'पहचान का आधार',
  'header.language': 'इनटेक की भाषा',
  'header.source': 'स्रोत',
  'header.department': 'विभाग',
  'header.received': 'प्राप्त',
  'header.intakeStatus': 'इनटेक स्थिति',
  'header.coverage': 'कवरेज',
  'header.answered': '{total} में से {answered} उत्तरित',
  'header.demo': 'यह परिनियोजन प्रदर्शन-डेटा दिखा रहा है।',
  'header.activeFlags': 'इस इनटेक पर {count} अस्वीकृत तत्काल चिकित्सकीय समीक्षा मानदंड।',
  'header.activeFlagsOne': 'इस इनटेक पर 1 अस्वीकृत तत्काल चिकित्सकीय समीक्षा मानदंड।',
  'header.sourceApp': 'रोगी ऐप',
  'header.sourceKiosk': 'कियोस्क या काउंटर',
  'id.abha': 'ABHA-सत्यापित',
  'id.hospital_id': 'अस्पताल आईडी',
  'id.phone': 'फ़ोन, ऐप में',
  'id.aadhaar_last4': 'Aadhaar के अंतिम चार अंक',
  'id.guest': 'अतिथि — पहचान स्थापित नहीं',
  'lang.en': 'अंग्रेज़ी',
  'lang.hi': 'हिन्दी',
  'lang.bn': 'बांग्ला',
  'lang.ta': 'तमिल',
  'lang.te': 'तेलुगु',
  'lang.mr': 'मराठी',
  'lang.gu': 'गुजराती',
  'lang.kn': 'कन्नड़',
  'lang.pa': 'पंजाबी',
  'intakeStatus.complete': 'पूर्ण',
  'intakeStatus.partial': 'बीच में छूटा',
  'intakeStatus.aborted_red_flag': 'रोका गया — तत्काल मानदंड',
  'intakeStatus.abandoned': 'परित्यक्त',

  'report.label': 'रिपोर्ट',
  'report.draft': 'मसौदा रिपोर्ट — चिकित्सक सत्यापन आवश्यक',
  'report.verifyAll': 'सभी निर्णीत तथ्य सत्यापित करें',
  'report.verifiedBy': '{actor} द्वारा सत्यापित।',
  'report.loadError': 'यह अभिलेख लोड नहीं हो सका।',
  'report.backToWorklist': 'कार्य-सूची पर लौटें',
  'report.loading': 'अभिलेख लोड हो रहा है…',
  'report.plainText': 'सादा-पाठ रिपोर्ट',
  'report.writeError':
    'वह परिवर्तन दर्ज नहीं हुआ। संभव है किसी और ने यह पंक्ति बदली हो — दोबारा कार्रवाई से पहले रिपोर्ट फिर से लोड करें।',
  'report.aria': 'रोगी रिपोर्ट',
  'report.unresolved': 'अनिर्णीत',
  'report.nothingUnresolved': 'कुछ भी अनिर्णीत नहीं।',
  'report.conflicts': 'विरोधाभास',
  'report.noConflicts': 'कोई विरोधाभासी विवरण नहीं।',
  'report.reportedToday': 'आज बताया गया',
  'report.onRecord': 'पहले से अभिलेख में',
  'report.notMentioned': 'आज के इनटेक में उल्लेख नहीं।',

  'report.alerts': 'तत्काल समीक्षा मानदंड',
  'report.alertsNone': 'कोई तत्काल समीक्षा मानदंड सक्रिय नहीं हुआ।',
  'report.alertAcknowledged': '{actor} द्वारा स्वीकृत।',
  'report.alertUnacknowledged': 'अभी तक स्वीकृत नहीं।',
  'report.interactions': 'साथ में देखने योग्य दवाएँ',
  'report.interactionsNone': 'कोई युग्म चिह्नित नहीं।',
  'report.interactionSource': 'स्रोत: {source}',
  'report.history': 'चिकित्सा इतिहास, समय-क्रम में',
  'report.historyPending': 'इस इंटेक के लिए अभी तैयार नहीं — थोड़ी देर बाद पुनः लोड करें।',
  'report.historyNone': 'इस अस्पताल में कोई तिथि-सहित पूर्व अभिलेख नहीं।',
  'report.historyUnfiltered':
    'यहाँ के सभी तिथि-सहित अभिलेख, नवीनतम पहले। आज की शिकायत से प्रासंगिकता के आधार पर कोई चयन नहीं।',
  'report.historyFiltered':
    'आज की शिकायत से संबंधित मानकर चुने गए। {omitted} पूर्व प्रविष्टि(याँ) असंबंधित मानी गईं और यहाँ नहीं दिखाई गईं; पूरा अभिलेख उपलब्ध है।',
  'report.documentTimeline': 'अपलोड किए गए दस्तावेज़, समय-क्रम में',
  'report.documentTimelineNone': 'कोई दस्तावेज़ अपलोड नहीं हुआ।',
  'report.documentUndated': 'कोई पठनीय तिथि नहीं',
  'report.documentNotes': 'दस्तावेज़ों पर टिप्पणियाँ',
  'report.copy': 'रिपोर्ट का पाठ कॉपी करें',
  'report.copied': 'कॉपी हो गया।',
  'report.copyFailed': 'कॉपी नहीं हो सका। इसके बजाय प्रिंट करें।',
  'report.print': 'प्रिंट करें',
  'report.printHint':
    'रिपोर्ट यहाँ दिखे अनुसार प्रिंट होती है — साक्ष्य पैनल और नियंत्रणों के बिना।',

  'verify.accept': 'स्वीकारें',
  'verify.amend': 'संशोधित करें',
  'verify.reject': 'अस्वीकारें',
  'verify.verified': 'सत्यापित',
  'verify.corrected': 'संशोधित',
  'verify.acceptHint': 'जैसा दर्ज है, वैसा ही पुष्ट करें',
  'verify.acceptDisabled': 'पुष्ट करने को कुछ नहीं — यह प्रश्न कभी उत्तरित नहीं हुआ',
  'verify.rejectWarning':
    'यह दर्ज करता है कि यह तथ्य कभी स्थापित ही नहीं हुआ — यह नहीं कि उत्तर "नहीं" है।',
  'verify.confirm': 'पुष्टि करें',
  'verify.cancel': 'रद्द करें',
  'verify.save': 'सहेजें',
  'verify.value': 'संशोधित मान',
  'verify.unit': 'इकाई',
  'verify.reason': 'कारण',
  'verify.reasonPlaceholder': 'कारण (वैकल्पिक)',
  'verify.heard': 'सुना गया:',
  'verify.yes': 'हाँ',
  'verify.no': 'नहीं',

  'evidence.label': 'साक्ष्य',
  'evidence.empty': 'यह देखने के लिए कि कोई पंक्ति कहाँ से आई, रिपोर्ट में उस पर क्लिक करें।',
  'evidence.none': 'इस तथ्य के लिए कोई स्रोत दर्ज नहीं है।',
  'evidence.voiceTitle': 'क्या कहा गया',
  'evidence.documentTitle': 'कहाँ से पढ़ा गया',
  'evidence.appTitle': 'रोगी ने क्या चुना',
  'evidence.carriedTitle': 'पिछली भेंट से',
  'evidence.entryTitle': 'किसी व्यक्ति द्वारा दर्ज',
  'evidence.asrConfidence': 'पहचान विश्वसनीयता {percent}%',
  'evidence.surrounding': 'आसपास के प्रश्नोत्तर',
  'evidence.imageUnavailable': 'चित्र उपलब्ध नहीं।',
  'evidence.extracted': 'निकाला गया',
  'evidence.rawText': 'मूल पाठ',
  'evidence.confidence': 'विश्वसनीयता',
  'evidence.page': 'दस्तावेज़ पृष्ठ {page}',
  'evidence.tapped': 'रोगी ऐप में छूकर उत्तर दिया गया।',
  'evidence.recorded': 'दर्ज',
  'evidence.confirmedToday': 'आज पुष्ट किया',
  'evidence.confirmedYes': 'हाँ, रोगी द्वारा',
  'evidence.confirmedNo': 'नहीं',
  'evidence.confirmedNotAsked': 'नहीं पूछा गया',
  'evidence.openVisit': 'वह भेंट खोलें',
  'evidence.enteredBy':
    '{actor} द्वारा दर्ज। इस पंक्ति के पीछे कोई रिकॉर्डिंग या दस्तावेज़ नहीं है।',
  'evidence.someStaff': 'एक कर्मचारी',

  'alerts.title': 'तत्काल समीक्षा मानदंड',
  'alerts.subtitle':
    'साक्षात्कार के दौरान उपकरण पर सक्रिय हुए मानदंड। अस्वीकृत पहले। उपकरण ने एक प्रश्नावली की जाँच की; उसने किसी की परीक्षा नहीं की।',
  'alerts.hideAcknowledged': 'पहले से स्वीकृत छिपाएँ',
  'alerts.error': 'सूचनाएँ लोड नहीं हो सकीं।',
  'alerts.noneOutstanding': 'कुछ भी लंबित नहीं।',
  'alerts.noneFired': 'इस अवधि में कोई मानदंड सक्रिय नहीं हुआ।',
  'alerts.defaultLabel': 'तत्काल चिकित्सकीय समीक्षा मानदंड सक्रिय',
  'alerts.fired': 'सक्रिय {when}',
  'alerts.turn': 'प्रश्न {turn}',
  'alerts.intake': 'इनटेक',
  'alerts.criteria': 'पूरे हुए मानदंड',
  'alerts.rule': 'नियम',
  'alerts.note': 'टिप्पणी (वैकल्पिक)',
  'alerts.acknowledge': 'स्वीकारें — मैंने इसे देख लिया है',
  'alerts.escalate': 'एस्केलेशन दर्ज करें',
  'alerts.escalateConfirm': 'पुष्टि: मैंने इसे ट्राइएज तक पहुँचा दिया है',
  'alerts.twoActs':
    'स्वीकारना केवल यह दर्ज करता है कि आपने देखा। यह किसी को सूचित नहीं करता और कुछ नहीं बदलता। एस्केलेशन वह है जो आप स्वयं, व्यक्तिगत रूप से करते हैं; यह केवल यह दर्ज करता है कि आपने किया।',
  'alerts.conflict':
    'यह दर्ज नहीं हो सका। संभव है किसी और ने पहले ही स्वीकार कर लिया हो — कार्रवाई से पहले फिर से लोड करें।',
  'alerts.acknowledgedBy': '{actor} द्वारा {when} पर स्वीकृत',
  'alerts.arrived': 'आगमन',

  'metrics.title': 'निष्कर्षण गुणवत्ता',
  'metrics.subtitle': 'पाइपलाइन ने जो दर्ज किया, उसे चिकित्सक को कितनी बार ठीक करना पड़ा।',
  'metrics.correctionRate': 'संशोधन दर',
  'metrics.notMeasurable': 'अभी मापने योग्य नहीं',
  'metrics.breakdown':
    '{intakes} इनटेक में चिकित्सक द्वारा समीक्षित {reviewed} तथ्यों में से {amended} संशोधित और {rejected} अस्वीकृत।',
  'metrics.reviewed': 'समीक्षित',
  'metrics.verified': 'जैसा दर्ज था, वैसा ही पुष्ट',
  'metrics.amended': 'संशोधित',
  'metrics.rejected': 'अस्वीकृत',
  'metrics.error': 'ये गणनाएँ लोड नहीं हो सकीं।',
  'metrics.note':
    'हर संग्रहीत तथ्य नहीं, बल्कि चिकित्सक ने वास्तव में जितने तथ्य देखे वही हर है। जिस प्रश्न को किसी ने देखा ही नहीं, वह निष्कर्षण की गुणवत्ता के बारे में कुछ नहीं कहता, और उसे गिनने से यह संख्या बेहतर निष्कर्षण के बजाय अधिक इनटेक लेने से सुधर जाती। एक ही तथ्य पर दो बार कार्रवाई एक बार गिनी जाती है, जिसमें अंतिम कार्रवाई मान्य होती है।',
  'metrics.noteEmpty':
    'जब तक इसके पीछे आँकड़े न हों, यह संख्या — और सेवानिवृत्त मूल्यांकन हार्नेस द्वारा दी गई संख्याएँ — किसी स्लाइड पर नहीं आनी चाहिए।',
};

export const STRINGS: Record<Locale, Record<StringKey, string>> = { en, hi };
