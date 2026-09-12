/// The flow controller — 2/3 §5, §6, §9.
///
/// One object owns the interview: the walker, the draft on disk, which screen
/// is showing, and what happens when a red-flag rule fires. Everything it
/// drives — every screen in `screens/` — is a plain widget that takes callbacks
/// and holds no state, so all of the sequencing lives here and is testable with
/// no widgets at all.
///
/// **It contains no clinical logic** (§1 rule 2, §16). It never decides what to
/// ask, what is applicable or what constitutes a red flag; it asks the walker
/// and does as it is told. The only judgements here are about ordering, and
/// ordering is where this file earns its keep:
///
/// **On an answer:** record it, persist the draft, then move. The draft is
/// written before the next screen is shown, so the app dying between two
/// questions loses nothing (§15 item 7).
///
/// **On a red flag:** stop, show, *then* persist and queue — in that order, and
/// the order is the brief's (§6.1–6.3). The screen changes before any I/O
/// because a patient with cardiac symptoms should not be looking at another
/// question while a database write completes; the writes that follow are what
/// make the partial record durable, and none of them can put the interview
/// back.
///
/// **On submit:** close the record out, queue it, then try once. Queue before
/// send, always — an intake that exists only in memory when the radio fails is
/// an intake lost.
library;

import 'dart:convert';
import 'dart:math';

import 'package:drift/drift.dart' show Value;
import 'package:flutter/foundation.dart';

import '../consent/consent_repository.dart';
import '../content/answer.dart';
import '../content/bundle.dart';
import '../content/walker.dart';
import '../core/ids.dart';
import '../core/logging.dart';
import '../documents/document_store.dart';
import '../documents/documents_screen.dart';
import '../documents/prepare.dart';
import '../storage/database.dart';
import '../submit/queue.dart';
import '../submit/record.dart';

/// Which screen the flow is on.
enum FlowStage {
  /// A question is showing.
  question,

  /// Old prescriptions and reports — §5 screen 9. After the interview and
  /// before the review, so the patient checks their answers last.
  documents,

  /// Every applicable question has an answer; the patient is checking them.
  review,

  /// A red-flag rule fired. **Terminal.** There is no transition out of this
  /// stage back into [question], and that is the point (§6).
  urgent,

  /// Done. The reference code is showing.
  submitted,
}

/// The slot the bundle files "who are you answering for?" under.
///
/// The app asks this on screen 4 and the bundle asks it again as
/// `history.reporter`; matching on the *field* rather than the question id is
/// what lets the seed suppress it, and keeps working if the question is ever
/// renamed. The four codes `ReporterScreen` emits are the four this slot
/// allows, which is what makes seeding it honest rather than approximate.
const _reporterField = 'general.reporter';

class IntakeFlow extends ChangeNotifier {
  IntakeFlow({
    required LocalDatabase database,
    required SubmissionQueue queue,
    required DocumentStore documents,
    required this.walker,
    required this.intakeId,
    required this.idempotencyKey,
    required this.hospitalId,
    required this.hospitalName,
    required this.reporter,
    required this.appVersion,
    required this.startedAt,
    this.returnVisit = false,
    this.departmentCode,
    this.consent,
    this.patientRef = const PatientRef.guest(),
    DateTime Function() clock = DateTime.now,
  })  : _db = database,
        _queue = queue,
        _documents = documents,
        _clock = clock {
    _current = walker.next();
    _stage = _current == null ? FlowStage.documents : FlowStage.question;
  }

  /// Start a new intake.
  ///
  /// The idempotency key is generated **here**, once, and stored with the
  /// draft — §9. Generating it at submit time would give every retry after a
  /// crash a fresh key, and the header would guarantee nothing.
  static Future<IntakeFlow> begin({
    required LocalDatabase database,
    required SubmissionQueue queue,
    required DocumentStore documents,
    required ContentBundle bundle,
    required String language,
    required String hospitalId,
    required String hospitalName,
    required String reporter,
    required String appVersion,
    String? departmentCode,
    ConsentGrant? consent,
    List<ConfirmedFact> confirmed = const [],
    bool returnVisit = false,
    PatientRef patientRef = const PatientRef.guest(),
    DateTime Function() clock = DateTime.now,
    Random? random,
  }) async {
    final now = clock();
    final flow = IntakeFlow(
      database: database,
      queue: queue,
      documents: documents,
      walker: IntakeWalker(
        bundle: bundle,
        language: language,
        returnVisit: returnVisit,
        answers: _seed(bundle, language, confirmed, reporter),
      ),
      intakeId: _newId('intake', random),
      idempotencyKey: _newId('idem', random),
      hospitalId: hospitalId,
      hospitalName: hospitalName,
      reporter: reporter,
      appVersion: appVersion,
      departmentCode: departmentCode,
      consent: consent,
      returnVisit: returnVisit,
      patientRef: patientRef,
      startedAt: now,
      clock: clock,
    );
    await flow._saveDraft();
    return flow;
  }

  /// Pick an interrupted intake back up at the exact question — §5, §15 item 7.
  ///
  /// Returns null when the draft cannot be resumed against this bundle. The
  /// caller starts a fresh intake in that case rather than resuming half of
  /// one: answers recorded against a content version whose questions have since
  /// changed are answers to questions nobody can now read.
  static IntakeFlow? resume({
    required LocalDatabase database,
    required SubmissionQueue queue,
    required DocumentStore documents,
    required ContentBundle bundle,
    required Draft draft,
    required String appVersion,
    ConsentGrant? consent,
    PatientRef patientRef = const PatientRef.guest(),
    DateTime Function() clock = DateTime.now,
  }) {
    if (draft.contentVersion != bundle.contentVersion) return null;
    final stored = DraftCodec.decode(draft.answersJson);
    final answers = <String, Answer>{};
    for (final entry in stored.entries) {
      final value = entry.value;
      if (value is! Map<String, dynamic>) continue;
      answers[entry.key] = Answer.fromDraftJson(value);
    }
    return IntakeFlow(
      database: database,
      queue: queue,
      documents: documents,
      walker: IntakeWalker(
        bundle: bundle,
        language: draft.language,
        // A resumed intake keeps the plan it started with. Re-deciding it here
        // would change which questions remain halfway through, and a patient
        // who answered six Ayurveda questions before the app died must not come
        // back to a shorter list that drops three of them from the record.
        returnVisit: draft.returnVisit,
        answers: answers,
      ),
      intakeId: draft.intakeId,
      idempotencyKey: draft.idempotencyKey,
      hospitalId: draft.hospitalId,
      hospitalName: draft.hospitalName ?? draft.hospitalId,
      reporter: draft.reporter,
      appVersion: appVersion,
      departmentCode: draft.departmentCode,
      consent: consent,
      returnVisit: draft.returnVisit,
      patientRef: patientRef,
      startedAt: draft.startedAt,
      clock: clock,
    );
  }

  final LocalDatabase _db;
  final SubmissionQueue _queue;
  final DocumentStore _documents;
  final DateTime Function() _clock;

  final IntakeWalker walker;
  final String intakeId;
  final String idempotencyKey;
  final String hospitalId;
  final String hospitalName;
  final String? departmentCode;

  /// Whether this hospital had seen the patient before — §5 screen 8.
  final bool returnVisit;

  /// What the patient agreed to on the consent screen — §11.
  ///
  /// Carried rather than filed at the time, because the artefact references an
  /// intake and the backend has not seen this one yet. It goes out with the
  /// record, and the queue files it the moment the intake exists.
  final ConsentGrant? consent;
  final String reporter;
  final String appVersion;
  final PatientRef patientRef;
  final DateTime startedAt;

  late FlowStage _stage;
  Question? _current;
  bool _sending = false;
  bool _queued = false;
  List<CapturedPage> _pages = const [];
  PageQuality? _rejected;
  int _loggedDegraded = 0;

  FlowStage get stage => _stage;

  /// The question on screen, or null on every other stage.
  Question? get question => _current;

  String get language => walker.language;
  ContentBundle get bundle => walker.bundle;
  Map<String, Answer> get answers => walker.answers;

  /// The rule that stopped the intake, once one has.
  RedFlagHit? get firedFlag => walker.firedFlag;

  /// True while the submit attempt is in the air, so the button can be disabled
  /// rather than allowing a second record to be assembled.
  bool get sending => _sending;

  /// True when the record is on the phone rather than at the hospital. Shown to
  /// the patient plainly: a code they believe is registered when it is not is
  /// worse than being told to expect a delay.
  bool get queued => _queued;

  String get referenceCode => referenceCodeFor(intakeId);

  /// Pages attached to this intake — §5 screen 9.
  List<CapturedPage> get pages => List.unmodifiable(_pages);

  /// Why the last page was refused, for the "take it again" message. Cleared
  /// as soon as another page is added, because a warning about a photograph the
  /// patient has already retaken is worse than none.
  PageQuality? get rejectedQuality => _rejected;

  (int, int) get sectionProgress => walker.sectionProgress;

  /// Whether back is offered — §5, "back always available".
  ///
  /// Except after a red flag, where the walker refuses to retract and this is
  /// false. The button is absent rather than disabled.
  bool get canGoBack => _stage == FlowStage.question && walker.lastAsked != null;

  // --- the patient acts -----------------------------------------------------

  Future<void> answer(AnswerValue value, String originalText) => _put(
        _answerFor(FieldStatus.answered, value: value, originalText: originalText),
      );

  /// "I don't know" — `unresolved`, never `no` (§1 rule 4).
  Future<void> dontKnow() => _put(_answerFor(FieldStatus.unresolved));

  /// Skip — `not_asked`, never `no`.
  Future<void> skip() => _put(_answerFor(FieldStatus.notAsked));

  /// The patient declined to answer — `refused`.
  Future<void> refuse() => _put(_answerFor(FieldStatus.refused));

  /// Back one question.
  ///
  /// From the documents screen this returns to the last question, which is what
  /// a patient who realises they mistapped the final answer needs.
  Future<void> back() async {
    if (_stage != FlowStage.question && _stage != FlowStage.documents) return;
    final target = walker.lastAsked;
    if (target == null) return;
    await _reopen(target);
  }

  /// Change one answer from the review screen — §5 screen 10.
  Future<void> edit(String questionId) => _reopen(questionId);

  // --- documents (§5 screen 9, §8) -----------------------------------------

  Future<void> addPage({required bool fromCamera}) async {
    if (_stage != FlowStage.documents) return;
    final result = await _documents.add(intakeId: intakeId, fromCamera: fromCamera);
    switch (result) {
      case PageAdded():
        _rejected = null;
      case PageRejected(:final quality):
        // §8: told while the paper is still in front of them. Nothing was
        // written, so there is no half-usable page to upload later.
        _rejected = quality;
      case PageCancelled():
        return;
      case PageUnreadable():
        _rejected = PageQuality.tooSmall;
    }
    await _loadPages();
    notifyListeners();
  }

  Future<void> removePage(String documentId) async {
    await _documents.remove(documentId);
    await _loadPages();
    notifyListeners();
  }

  /// Done with documents — on to the review.
  void continueToReview() {
    if (_stage != FlowStage.documents) return;
    _stage = FlowStage.review;
    notifyListeners();
  }

  /// Back to the documents screen from the review — §5 screen 10.
  ///
  /// A patient who reaches the review and realises the prescription in their
  /// bag never got photographed should not have to abandon the intake to add
  /// it. [continueToReview] brings them straight back, so this is a detour
  /// rather than a step backwards through the interview.
  void addMoreDocuments() {
    if (_stage != FlowStage.review) return;
    _stage = FlowStage.documents;
    notifyListeners();
  }

  /// §4: log a content-version mismatch when the bundle names something this
  /// build cannot render. Question ids only — they are content identifiers, not
  /// anything a patient said.
  void _noteDegradation() {
    final degraded = walker.degradedQuestions;
    if (degraded.isEmpty || degraded.length == _loggedDegraded) return;
    _loggedDegraded = degraded.length;
    logEvent('content_version_mismatch', fields: {
      'content_version': bundle.contentVersion,
      'app_version': appVersion,
      'questions': degraded.join(','),
    });
  }

  Future<void> _loadPages() async {
    _pages = await _documents.pagesFor(intakeId);
  }

  /// Assemble and send — §9.
  Future<void> submit() async {
    if (_sending || _stage != FlowStage.review) return;
    _sending = true;
    notifyListeners();

    // Every question that was never reached becomes an explicit `not_asked`
    // before the record is built. A reader must never have to tell "not asked"
    // from "the app forgot".
    walker.closeOut();
    await _saveDraft();
    await _queue.enqueue(
      intakeId: intakeId,
      payload: _record(),
      consent: consent,
    );

    final outcome = await _queue.submitNow(intakeId);
    _queued = outcome != Delivery.accepted;
    _sending = false;
    _stage = FlowStage.submitted;
    notifyListeners();
  }

  // --- the machinery --------------------------------------------------------

  Answer _answerFor(
    FieldStatus status, {
    AnswerValue? value,
    String? originalText,
  }) {
    final question = _current!;
    return Answer(
      questionId: question.questionId,
      fieldId: question.fieldId,
      status: status,
      value: value,
      originalText: originalText,
      // The prompt actually shown, in the language actually used (§9). Set for
      // every status the patient produced, including a skip, which is also how
      // the walker tells its own conclusions from theirs.
      askedText: question.promptFor(language),
      language: language,
    );
  }

  Future<void> _put(Answer answer) async {
    if (_stage != FlowStage.question) return;
    final outcome = walker.record(answer);

    if (outcome == WalkOutcome.redFlag) {
      await _onRedFlag();
      return;
    }

    _current = walker.next();
    _noteDegradation();
    // Persisted before the next screen is shown, not after — §15 item 7 kills
    // the app at an arbitrary moment, and the arbitrary moment it will pick is
    // this one.
    await _saveDraft();
    if (_current == null) {
      await _loadPages();
      _stage = FlowStage.documents;
    } else {
      _stage = FlowStage.question;
    }
    notifyListeners();
  }

  /// §6, in the order §6 gives.
  Future<void> _onRedFlag() async {
    // 1 and 2. Stop the intake and show the urgent-care screen. Before any I/O:
    //    the writes below take milliseconds, but "show it once the database has
    //    finished" is a rule that decays into "show it once the upload has
    //    finished" the first time someone moves a line.
    _current = null;
    _stage = FlowStage.urgent;
    notifyListeners();

    // 3. Record it and submit the partial record with `aborted_red_flag`, or
    //    queue it if there is no connection. The answer that fired is already
    //    in the walker; this is what makes it durable.
    walker.closeOut();
    await _saveDraft();

    final hit = walker.firedFlag!;
    await _queue.enqueue(
      intakeId: intakeId,
      consent: consent,
      payload: _record(
        abortedBy: RedFlagHitRecord(
          ruleId: hit.ruleId,
          severity: hit.severity,
          firedAt: _clock(),
          fields: hit.fields,
        ),
      ),
    );

    // The patient is not waiting on this and must not be: the screen is already
    // up and tells them to seek care now. If it fails it stays queued, and the
    // hospital gets it when the phone next has signal.
    final outcome = await _queue.submitNow(intakeId);
    _queued = outcome != Delivery.accepted;
    notifyListeners();

    // 4. There is no "continue anyway". Not disabled, not behind a
    //    confirmation — there is no method on this class that leaves
    //    [FlowStage.urgent], and `walker.retract` refuses once a flag has
    //    fired, so back cannot manufacture one either.
  }

  Future<void> _reopen(String questionId) async {
    if (!walker.retract(questionId)) return;
    _current = walker.next();
    await _saveDraft();
    // Back to documents rather than to the review when there is nothing left to
    // ask: the patient edited an answer from the review and settled it again,
    // and dropping them at the camera would be a strange place to land.
    _stage = _current == null
        ? (_stage == FlowStage.review ? FlowStage.review : FlowStage.documents)
        : FlowStage.question;
    notifyListeners();
  }

  Map<String, dynamic> _record({RedFlagHitRecord? abortedBy}) =>
      IntakeRecordBuilder(
        intakeId: intakeId,
        hospitalId: hospitalId,
        bundle: bundle,
        language: language,
        reporter: reporter,
        appVersion: appVersion,
        departmentCode: departmentCode,
        patientRef: patientRef,
      ).build(
        answers: walker.answers,
        startedAt: startedAt,
        completedAt: _clock(),
        abortedByRedFlag: abortedBy,
      );

  Future<void> _saveDraft() => _db.saveDraft(DraftsCompanion.insert(
        intakeId: intakeId,
        hospitalId: hospitalId,
        hospitalName: Value(hospitalName),
        departmentCode: Value(departmentCode),
        language: language,
        reporter: reporter,
        answersJson: jsonEncode({
          for (final entry in walker.answers.entries) entry.key: entry.value.toJson(),
        }),
        contentVersion: bundle.contentVersion,
        returnVisit: Value(returnVisit),
        startedAt: startedAt,
        updatedAt: _clock(),
        idempotencyKey: idempotencyKey,
      ));

  /// Seed the answers a returning patient has just confirmed — §5 screen 5.
  ///
  /// "Never re-asks confirmed history from scratch." A fact the patient has
  /// just said is still correct is recorded as answered, so the walker does not
  /// put the question again.
  ///
  /// **Only `stillCorrect` is seeded.** "No longer correct" and "not sure" both
  /// leave the question to be asked normally, which is the only safe reading of
  /// either: a fact the patient doubts is not a fact, and it is certainly not a
  /// `no`.
  ///
  /// The seeded entry carries no `asked_text`, so it produces no turn — the
  /// record says the field is answered and that nothing in this interview
  /// asked it, which is exactly what happened.
  ///
  /// It also carries `carried_forward`, which closes the gap `DECISIONS.md`
  /// recorded when this was written: "answered, and nothing asked it" is true
  /// but says nothing about *where the answer came from*, and a physician
  /// cannot tell a fresh answer from a year-old one the patient nodded at.
  /// `confirmed_today` is true here because that is the only path that seeds —
  /// "no longer correct" and "not sure" both fall through to being asked.
  static Map<String, Answer> _seed(
    ContentBundle bundle,
    String language,
    List<ConfirmedFact> confirmed,
    String reporter,
  ) {
    final byField = <String, Question>{
      for (final question in bundle.questions.values) question.fieldId: question,
    };
    final seeded = <String, Answer>{};

    // Who the intake is for was answered on screen 4, before the interview
    // started (`ReporterGate`). The bundle also carries a question for it, with
    // no precondition and no idea the patient has already said — so without
    // this the walker put "Who are you answering for?" a second time, seventy
    // questions in. Seeding is the same mechanism carry-forward uses: the
    // walker skips what it already holds, and nothing about how it chooses
    // changes.
    //
    // `askedText` is left null, because it was not put by the interview.
    // `wasPut` reads that, and `lastAsked` and `retract` read `wasPut` — so
    // Back from the first real question must not land on a screen the patient
    // already passed.
    final reporterQuestion = byField[_reporterField];
    if (reporterQuestion != null && reporter.isNotEmpty) {
      seeded[reporterQuestion.questionId] = Answer(
        questionId: reporterQuestion.questionId,
        fieldId: _reporterField,
        status: FieldStatus.answered,
        value: CodedValue(reporter),
        language: language,
      );
    }

    for (final fact in confirmed) {
      final question = byField[fact.fieldId];
      // A carried fact the current bundle asks no question for is still the
      // hospital's record; it is simply not this interview's to restate.
      if (question == null) continue;
      // A carried fact never overwrites something this interview already
      // settled — the reporter above is settled, and it was settled today.
      if (seeded.containsKey(question.questionId)) continue;
      seeded[question.questionId] = Answer(
        questionId: question.questionId,
        fieldId: fact.fieldId,
        status: FieldStatus.answered,
        value: TextValue(fact.value),
        originalText: fact.label,
        language: language,
        // Both parts or neither. `originally_recorded` is a required `date` in
        // 0.2, so an empty string fails the whole payload — and fails it
        // silently, because ingest answers an unparseable payload with a 200.
        // A confirmed fact with no usable provenance is still a confirmed
        // fact; it just cannot say which visit it came from.
        carriedForward: fact.fromIntakeId.isEmpty || fact.originallyRecorded.isEmpty
            ? null
            : CarriedForward(
                fromIntakeId: fact.fromIntakeId,
                originallyRecorded: fact.originallyRecorded,
                confirmedToday: true,
              ),
      );
    }
    return seeded;
  }

  /// Ids that are unique on the device and mean nothing anywhere else.
  ///
  /// Not a patient identifier and not derived from one: an intake id that
  /// encoded a phone number would put a phone number in a log line the first
  /// time anybody logged an id.
  static String _newId(String prefix, Random? random) =>
      newLocalId(prefix, random: random);
}

/// One fact the patient has confirmed is still correct — §5 screen 5.
///
/// The hospital already holds it; what this carries is the confirmation.
class ConfirmedFact {
  const ConfirmedFact({
    required this.fieldId,
    required this.label,
    required this.value,
    required this.fromIntakeId,
    required this.originallyRecorded,
  });

  final String fieldId;

  /// What the patient was shown — "Diabetes", "Metformin 500mg".
  final String label;
  final String value;

  /// The earlier intake this came from, and when it was recorded there. Both
  /// travel into the record so a physician reading "diabetes" can see it was
  /// confirmed today and first written down some time ago, rather than being
  /// told the interview asked about it.
  final String fromIntakeId;
  final String originallyRecorded;
}
