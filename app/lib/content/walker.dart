/// The bundle walker — 2/3 §3, §4, §6.
///
/// **This is the only file in the app with anything resembling logic in it, and
/// it must stay that way.** If a second file starts making clinical decisions,
/// the design has slipped: the whole point of downloading the same content the
/// Jetson walks is that there is one description of what to ask and when, not
/// three implementations of it.
///
/// What this file does is deliberately small. Touch removes the hard parts of
/// the Jetson's job — no speech, no keyword extraction, no answer-binding
/// ambiguity, no "asked twice and still unresolved". A tap *is* the bound
/// value. So: load bundle, render question, record answer, follow branch, next.
///
/// What it does not do is decide anything clinical. Which questions exist,
/// which follow which complaint, what makes a red flag — all of that is data
/// from `clinical/questions/**`, authored by a clinician and compiled by the
/// backend.
library;

import 'answer.dart';
import 'bundle.dart';

/// Why the walk stopped.
enum WalkOutcome {
  /// More questions remain.
  inProgress,

  /// Every applicable question has an answer.
  complete,

  /// A red-flag rule fired. The intake stops here — §6.
  redFlag,
}

class RedFlagHit {
  const RedFlagHit({required this.ruleId, required this.severity, required this.fields});

  final String ruleId;
  final String severity;

  /// The answers that satisfied the rule, for the partial record the app
  /// submits with `aborted_red_flag` (§6.3).
  final Map<String, String> fields;
}

/// Evaluating a [Condition] against answers so far.
///
/// Three-valued on purpose. A condition over a field nobody has answered yet is
/// neither true nor false — it is *not yet knowable*, and treating that as false
/// would fire preconditions early and, worse, would let a red-flag rule be
/// evaluated against a half-filled record.
enum Tri { yes, no, unknown }

Tri _and(Tri a, Tri b) {
  if (a == Tri.no || b == Tri.no) return Tri.no;
  if (a == Tri.unknown || b == Tri.unknown) return Tri.unknown;
  return Tri.yes;
}

Tri _or(Tri a, Tri b) {
  if (a == Tri.yes || b == Tri.yes) return Tri.yes;
  if (a == Tri.unknown || b == Tri.unknown) return Tri.unknown;
  return Tri.no;
}

/// Evaluate one expression against the answers recorded so far.
Tri evaluate(Condition condition, Map<String, Answer> byField) {
  switch (condition) {
    case AllOf(:final nodes):
      var result = Tri.yes;
      for (final node in nodes) {
        result = _and(result, evaluate(node, byField));
      }
      return result;
    case AnyOf(:final nodes):
      var result = Tri.no;
      for (final node in nodes) {
        result = _or(result, evaluate(node, byField));
      }
      return result;
    case NotNode(:final node):
      return switch (evaluate(node, byField)) {
        Tri.yes => Tri.no,
        Tri.no => Tri.yes,
        Tri.unknown => Tri.unknown,
      };
    case Leaf():
      return _evaluateLeaf(condition, byField);
  }
}

Tri _evaluateLeaf(Leaf leaf, Map<String, Answer> byField) {
  final answer = byField[leaf.fieldId];
  if (answer == null) return Tri.unknown;

  // An unsettled answer cannot satisfy a condition, and cannot refute one
  // either. "I don't know" is not "no": treating it as `Tri.no` would silently
  // clear a red-flag rule that the patient simply could not answer, which is
  // the single most dangerous shortcut available in this file.
  if (!answer.isSettled) return Tri.unknown;

  final value = answer.value;

  if (leaf.status != null) {
    // `present` / `absent` over a yes-no field.
    final asBool = value is BoolValue ? value.value : null;
    if (asBool == null) {
      // A non-boolean field tested for presence counts as present when it has
      // any settled value at all — that is what "the patient reported this"
      // means for a choice or a quantity.
      return leaf.status == 'present' ? Tri.yes : Tri.no;
    }
    final wantPresent = leaf.status == 'present';
    return asBool == wantPresent ? Tri.yes : Tri.no;
  }

  if (leaf.oneOf case final options?) {
    final code = switch (value) {
      CodedValue(:final code) => [code],
      CodedListValue(:final codes) => codes,
      TextValue(:final text) => [text],
      _ => const <String>[],
    };
    return code.any(options.contains) ? Tri.yes : Tri.no;
  }

  if (leaf.equals case final expected?) {
    final actual = switch (value) {
      BoolValue(:final value) => value,
      CodedValue(:final code) => code,
      TextValue(:final text) => text,
      NumberValue(:final value) => value,
      _ => null,
    };
    return actual == expected ? Tri.yes : Tri.no;
  }

  final number = switch (value) {
    NumberValue(:final value) => value,
    DurationValue(:final n) => n,
    _ => null,
  };
  if (number == null) return Tri.unknown;
  if (leaf.gte case final bound?) {
    if (number < bound) return Tri.no;
  }
  if (leaf.lte case final bound?) {
    if (number > bound) return Tri.no;
  }
  return Tri.yes;
}

/// Walks a bundle, one question at a time.
///
/// Holds no widgets and no I/O, so the whole of §15's status-vocabulary,
/// red-flag and degradation tests run against it directly with no UI.
class IntakeWalker {
  IntakeWalker({
    required this.bundle,
    required this.language,
    this.returnVisit = false,
    Map<String, Answer>? answers,
  }) : _answers = {...?answers};

  final ContentBundle bundle;

  /// The language the patient chose. Every prompt is recorded as it was shown,
  /// in this language (§9).
  final String language;

  /// Whether this hospital has seen this patient before — §5 screen 8.
  ///
  /// Changes one thing: the Ayurveda section becomes the current-state subset
  /// the content marks, rather than the full module. Which questions those are
  /// is the content's decision and not this file's; all that happens here is
  /// choosing between two lists the bundle supplies.
  final bool returnVisit;

  final Map<String, Answer> _answers;

  /// Answers keyed by `question_id`, in the order they were recorded.
  Map<String, Answer> get answers => Map.unmodifiable(_answers);

  Map<String, Answer> get _byField => {
        for (final answer in _answers.values) answer.fieldId: answer,
      };

  RedFlagHit? _firedFlag;
  RedFlagHit? get firedFlag => _firedFlag;

  final _degraded = <String>{};

  /// Questions this app could not put — §4's degradation rule.
  ///
  /// A branch naming a question this bundle does not carry, or an `answer_type`
  /// this build has never heard of. Both are recorded `not_asked` and neither
  /// crashes; §4 also asks for a content-version mismatch to be logged, and
  /// this is what the caller logs. **The walker does no IO** — it holds no
  /// widgets and no logger, which is what lets every safety test run against it
  /// directly.
  Set<String> get degradedQuestions => Set.unmodifiable(_degraded);

  /// Every question id this intake will walk, in order.
  ///
  /// Core first, then the branch for the chosen complaint. Ayurveda is
  /// deliberately **not** appended here any more — SIH items 3/4: it used to
  /// ride along on every visit as an unlabelled extra section, which made a
  /// symptom intake longer than the symptom warranted. It now lives on its own
  /// screen (`home/ayush_screen.dart`), answered once, whenever the patient
  /// chooses, rather than folded into every visit's required questions. The
  /// branch only appears once a complaint has been chosen, which is why this is
  /// recomputed rather than fixed at the start.
  List<String> get plan {
    final complaint = _selectedComplaint;
    return [
      ...bundle.core,
      if (complaint != null) ...?bundle.branches[complaint],
    ];
  }

  String? get _selectedComplaint {
    final answer = _byField['chief_complaint'];
    if (answer == null || !answer.isSettled) return null;
    return switch (answer.value) {
      CodedValue(:final code) => code,
      TextValue(:final text) => text,
      _ => null,
    };
  }

  /// The next question to put, or `null` when there is nothing left.
  ///
  /// Skips, in order: questions already answered, questions whose
  /// `answer_type` this app cannot render, and questions with no prompt in the
  /// patient's language. The last two record `not_asked` as a side effect, so
  /// the record says the question was never put rather than leaving a hole a
  /// reader would have to interpret.
  Question? next() {
    if (_firedFlag != null) return null;
    // Built once: this loop runs the length of the plan, and nothing inside it
    // settles a field — the only answers it writes are `not_asked`.
    final settledFields = {
      for (final answer in _answers.values)
        if (answer.isSettled) answer.fieldId,
    };
    for (final id in plan) {
      if (_answers.containsKey(id)) continue;
      final question = bundle.questions[id];

      if (question == null) {
        // A branch naming a question this bundle does not carry. §4: do not
        // crash, record `not_asked`, and let the caller log a content-version
        // mismatch. An older app must degrade, never break.
        _degraded.add(id);
        _answers[id] = Answer(
          questionId: id,
          fieldId: id,
          status: FieldStatus.notAsked,
          language: language,
        );
        continue;
      }

      if (question.answerType == AnswerType.unknown) {
        _degraded.add(id);
        _answers[id] = Answer(
          questionId: id,
          fieldId: question.fieldId,
          status: FieldStatus.notAsked,
          language: language,
        );
        continue;
      }

      if (settledFields.contains(question.fieldId)) {
        // Another question already settled this field. Two questions can carry
        // one `field_id` — the bundle does not enforce uniqueness, and
        // `pain.character` is the field of both `pain.character` and
        // `pain.description` — so without this a patient who has described
        // their pain is asked to describe it again in a different shape.
        //
        // This is the rule the server-side engine already applies when it
        // drops a question whose target slots are all known; it was lost when
        // the bundle was compiled down to a fixed order.
        //
        // Only `answered` counts. A field left unresolved or refused is a field
        // nobody has settled, and a differently-worded question is entitled to
        // try again.
        _answers[id] = Answer(
          questionId: id,
          fieldId: question.fieldId,
          status: FieldStatus.notAsked,
          language: language,
        );
        continue;
      }

      if (question.promptFor(language) == null) {
        // No prompt in the patient's language. Asking it in another one would
        // record an answer to a question they may not have understood.
        _answers[id] = Answer(
          questionId: id,
          fieldId: question.fieldId,
          status: FieldStatus.notAsked,
          language: language,
        );
        continue;
      }

      final resolved = _withRuntimeOptions(question);
      if (resolved == null) {
        // A runtime-filled question whose source answer yielded no options.
        // Putting it would show a list with nothing in it; recording it
        // `not_asked` says plainly that it was never put.
        _answers[id] = Answer(
          questionId: id,
          fieldId: question.fieldId,
          status: FieldStatus.notAsked,
          language: language,
        );
        continue;
      }

      switch (_preconditionState(question)) {
        case Tri.no:
          _answers[id] = Answer(
            questionId: id,
            fieldId: question.fieldId,
            status: FieldStatus.notApplicable,
            language: language,
            notApplicableBecause:
                question.precondition!.fieldsRead.join(', '),
          );
          continue;
        case Tri.unknown:
          // Not yet knowable — the field it depends on has not been asked. Leave
          // it for a later pass rather than deciding on incomplete information.
          continue;
        case Tri.yes:
          return resolved;
      }
    }
    return null;
  }

  /// A question whose options come from an earlier answer, with them filled in.
  ///
  /// Returns the question unchanged when it has no `options_from`, and null
  /// when it has one that yielded nothing to offer. This is the whole of what
  /// the adaptive engine's runtime options amount to on the phone: the second
  /// fixed question offers back the problems ticked on the first, rather than
  /// making somebody re-read a list of fifteen they have just finished reading.
  Question? _withRuntimeOptions(Question question) {
    final from = question.optionsFrom;
    if (from == null) return question;

    final answer = _byField[from];
    if (answer == null || !answer.isSettled) return null;

    final codes = switch (answer.value) {
      CodedListValue(:final codes) => codes,
      CodedValue(:final code) => [code],
      TextValue(:final text) => [text],
      _ => const <String>[],
    };
    if (codes.isEmpty) return null;
    return question.withOptions(List.unmodifiable(codes));
  }

  Tri _preconditionState(Question question) {
    final precondition = question.precondition;
    if (precondition == null) return Tri.yes;
    return evaluate(precondition, _byField);
  }

  /// Record an answer and re-check the red-flag rules.
  ///
  /// Returns [WalkOutcome.redFlag] when a rule fires. The caller must then stop
  /// the intake and show the urgent-care screen — §6 — and must not offer a way
  /// to continue.
  WalkOutcome record(Answer answer) {
    _answers[answer.questionId] = answer;
    final hit = _checkRedFlags();
    if (hit != null) {
      _firedFlag = hit;
      return WalkOutcome.redFlag;
    }
    return next() == null ? WalkOutcome.complete : WalkOutcome.inProgress;
  }

  /// The last question actually put to the patient — where "back" goes.
  ///
  /// Not simply the last entry: [next] writes `not_applicable` and `not_asked`
  /// as it scans ahead, so the last entry is usually a conclusion the walker
  /// drew rather than a screen the patient saw.
  String? get lastAsked {
    for (final answer in _answers.values.toList().reversed) {
      if (answer.wasPut) return answer.questionId;
    }
    return null;
  }

  /// Un-record an answer so the patient can change it — §5, "back always
  /// available".
  ///
  /// **Refuses once a red flag has fired.** §6 forbids any path back into the
  /// interview, and back is a path: a patient who can retract the answer that
  /// fired the rule can carry on answering questions about their diet with
  /// cardiac symptoms, which is the exact outcome that section exists to
  /// prevent.
  ///
  /// Retracting also discards every status the walker derived for itself, and
  /// every answer that is no longer in the plan. Both are necessary rather than
  /// tidy: a `not_applicable` was a conclusion from the retracted answer and
  /// must be reached again, and changing the chief complaint changes the branch
  /// — leaving the old branch's answers in the map would submit answers to
  /// questions this intake no longer asks.
  bool retract(String questionId) {
    if (_firedFlag != null) return false;
    if (_answers.remove(questionId) == null) return false;
    _answers.removeWhere((_, answer) => !answer.wasPut);
    final planned = plan.toSet();
    _answers.removeWhere((id, _) => !planned.contains(id));
    return true;
  }

  /// Mark every question that was never reached.
  ///
  /// Called once at the end so the submitted record accounts for the whole
  /// bundle: a question that was never put is `not_asked`, explicitly, rather
  /// than simply absent. A reader must never have to distinguish "not asked"
  /// from "the app forgot".
  void closeOut() {
    for (final id in plan) {
      if (_answers.containsKey(id)) continue;
      final question = bundle.questions[id];
      _answers[id] = Answer(
        questionId: id,
        fieldId: question?.fieldId ?? id,
        status: FieldStatus.notAsked,
        language: language,
      );
    }
  }

  RedFlagHit? _checkRedFlags() {
    final byField = _byField;
    for (final rule in bundle.redFlagRules) {
      if (evaluate(rule.criteria, byField) != Tri.yes) continue;
      return RedFlagHit(
        ruleId: rule.ruleId,
        severity: rule.severity,
        fields: {
          for (final field in rule.criteria.fieldsRead)
            if (byField[field]?.originalText case final text?) field: text,
        },
      );
    }
    return null;
  }

  /// Sections that have at least one settled answer, over sections with at
  /// least one applicable question.
  ///
  /// §5: progress is "3 of 7 sections", never a percentage — a percentage
  /// implies a precision the branching does not have.
  (int done, int total) get sectionProgress {
    final planned = plan;
    final sections = <String>{};
    final touched = <String>{};
    for (final id in planned) {
      final section = bundle.questions[id]?.section;
      if (section == null) continue;
      sections.add(section);
      if (_answers[id]?.isSettled ?? false) touched.add(section);
    }
    final ordered = bundle.sections.where(sections.contains).toList();
    return (touched.length, ordered.length);
  }

  /// How far through the questions the patient is, as a fraction — the number
  /// the bar draws.
  ///
  /// [sectionProgress] is the honest *label*; this is the honest *shape*. They
  /// are deliberately different measures. A bar driven by sections sits
  /// perfectly still for eight questions and then leaps a third of the way
  /// across, which a patient reads as an app that has stopped responding.
  ///
  /// The hard part is that [plan] is not a fixed length: it is `core` until the
  /// chief complaint is settled and `core + branch` afterwards. So the naive
  /// `answered / plan.length` would climb to nearly full during core and then
  /// fall off a cliff the moment the patient says "chest pain" — progress
  /// running *backwards*, for exactly the patients with the most left to
  /// answer and the least patience for it.
  ///
  /// The fix is to put a branch in the denominator before we know which branch
  /// it is: the longest one this bundle carries. That is an over-estimate on
  /// purpose. When the real branch turns out shorter, the denominator shrinks
  /// and the bar jumps *forward* — which reads as good news. Backwards is the
  /// one direction it must never move, and `StepProgress` clamps monotonically
  /// on top of this so that a retracted answer cannot walk it back either.
  ///
  /// Every planned question that has an entry in the answer map counts as
  /// behind us, including the `not_applicable` and `not_asked` ones [next]
  /// writes as it scans ahead. Those are questions the patient will never see,
  /// so counting them is what keeps the bar in step with what is on screen.
  double get questionFraction {
    final planned = plan;
    if (planned.isEmpty) return 0;
    var answered = 0;
    for (final id in planned) {
      if (_answers.containsKey(id)) answered++;
    }
    final total = _selectedComplaint == null
        ? planned.length + _longestBranch
        : planned.length;
    if (total <= 0) return 0;
    return (answered / total).clamp(0.0, 1.0);
  }

  /// Where one question sits inside its own section — "3 of 8", for the label
  /// beside the bar.
  ///
  /// **Section-relative, not interview-relative.** "Question 41 of 77" is true
  /// and useless: it is a number nobody wants to see at the start of a medical
  /// form, and it is the number that moves most when a branch opens. Counting
  /// within the section keeps it small and keeps it meaningful — these eight
  /// questions really are one subject.
  ///
  /// **It does not, on its own, keep the count still.** A section can hold
  /// both core and branch-only questions — `symptoms` carries three screening
  /// questions every patient sees and then whatever follow-ups the chosen
  /// complaint adds, which can be five or can be fifty. [total] here is
  /// therefore only ever honest for the complaint that produced it; a
  /// different one can produce a wildly different number for the very same
  /// section. [stable] is what tells the caller whether this section happens
  /// to be one where that cannot happen — see
  /// [ContentBundle.sectionCountIsStable] — and a caller building a patient-
  /// facing label checks it before showing [position]/[total] at all.
  ///
  /// **Only counts screens the patient can actually land on.** The compiled
  /// content puts every domain's follow-up questions in `symptoms` — one
  /// precondition per question, checked against what was ticked on the "what
  /// brought you in" screen — rather than a hand-picked branch per complaint.
  /// A patient who reported only a headache will never see the fever or
  /// bowel questions also filed under `symptoms`; [next] rules every one of
  /// them out — correctly — the moment the complaint is known, in the same
  /// pass, and records that with no screen shown ([Answer.wasPut] false).
  /// Counting those in [total]/[position] anyway is what used to make the
  /// label leap from a small number straight to something like "27 of 63" on
  /// the very next screen — every question in between was real to the
  /// bundle and invisible to the patient, which reads as the interview
  /// skipping ahead even though nothing was skipped. So this only counts a
  /// question that was actually put, or that has not been resolved either
  /// way yet — never one already ruled out silently.
  ///
  /// Returns null for a question this bundle does not carry or that is not in
  /// the plan. The caller then shows the section count instead; a progress
  /// label is not worth a crash.
  ({String section, int position, int total, bool stable})? sectionStepFor(
      String questionId) {
    final section = bundle.questions[questionId]?.section;
    if (section == null) return null;
    var position = 0;
    var total = 0;
    for (final id in plan) {
      if (bundle.questions[id]?.section != section) continue;
      final resolved = _answers[id];
      // Ruled out with no screen shown — §4's `not_applicable`/`not_asked`,
      // written by [next] as it scans past questions this patient will never
      // see. Those never counted as a step for this patient and must not
      // inflate [total] or make [position] jump past them.
      if (resolved != null && !resolved.wasPut) continue;
      total++;
      if (id == questionId) position = total;
    }
    if (position == 0) return null;
    return (
      section: section,
      position: position,
      total: total,
      stable: bundle.sectionCountIsStable(section),
    );
  }

  /// The most questions any one branch in this bundle can add.
  ///
  /// The pessimistic guess, not the average: guessing the average would leave
  /// the bar retreating for every patient whose branch is longer than typical,
  /// and that set is not random — it is the sicker half.
  int get _longestBranch {
    var longest = 0;
    for (final branch in bundle.branches.values) {
      if (branch.length > longest) longest = branch.length;
    }
    return longest;
  }
}
