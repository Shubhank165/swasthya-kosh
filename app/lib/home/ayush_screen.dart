/// The Ayurveda self-report — SIH items 3/4.
///
/// This used to be "Section 4": the last few questions of every symptom
/// intake, asked whether or not the patient wanted them, on top of whatever
/// brought them to the kiosk that day. Item 3 was to stop doing that — see
/// `content/walker.dart`, whose `plan` no longer appends it to a visit at
/// all.
///
/// This screen is where those questions live instead: patient-reported only,
/// answered once, whenever the patient chooses, from the home screen rather
/// than folded into a visit. It asks nothing a patient cannot honestly say
/// about themselves, and it computes no result — no Vata/Pitta/Kapha type is
/// ever shown here. **This is deliberately not a Prakriti assessment.**
/// Prakriti determination is a clinical act performed by the Vaidya through
/// observation and examination; a kiosk cannot do it, and showing a patient a
/// computed "type" would be exactly the overreach `ayurveda_module.yaml`
/// already warns against. What this screen collects is handed to the Vaidya
/// as the patient's own words, the same as every other self-report in this
/// app.
///
/// **The progress bar is why this screen was restyled.** Sixty-two questions
/// behind a bare `Question 3 of 62` in an app bar is a wall a patient abandons
/// at question five. The bar does not make it shorter; it makes the length
/// legible, which is the difference between a long form and an endless one.
/// Nothing about what is asked, in what order, or how it is stored changed.
///
/// **Storage, for now.** These answers are saved on the device only, under a
/// fixed id (`_ayushProfileId`) in the same encrypted local store a visit's
/// draft uses — never queued, never submitted, never purged by
/// `LocalDatabase.purgeIntake` (that only ever runs against a real intake's
/// id). Getting them into the record the Vaidya actually opens needs a
/// decision about how a standalone, one-time, patient-level profile fits
/// the visit-shaped submission contract, which is exactly the kind of
/// content-and-contract call this codebase's own conventions leave to the
/// team rather than to whoever happens to be touching the screen — see the
/// note this file replaces in git history. Worth doing next; not silently
/// invented here.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../content/answer.dart';
import '../content/bundle.dart';
import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../intake/widgets/answer_actions.dart';
import '../intake/widgets/answer_widgets.dart';
import '../intake/widgets/interview_ui.dart';
import '../l10n/strings.dart';
import '../storage/database.dart';

/// Never a real visit, so it is never queued and never purged by
/// `LocalDatabase.purgeIntake`, which only ever runs against a genuine
/// intake's id. Versioned so a future change to the module's questions can
/// tell an old saved profile apart from a current one (`contentVersion`
/// already does this for real drafts; the same check applies here).
const _ayushProfileId = 'ayush_profile_v1';

class AyushScreen extends ConsumerStatefulWidget {
  const AyushScreen({super.key});

  @override
  ConsumerState<AyushScreen> createState() => _AyushScreenState();
}

class _AyushScreenState extends ConsumerState<AyushScreen> {
  /// The confirm button the current question's answer widget has published.
  ///
  /// Null on a tap-to-answer question, where the tap *is* the answer and a
  /// footer would be a permanent grey band under most of the assessment.
  final _confirm = ValueNotifier<ConfirmAction?>(null);

  bool _loading = true;
  Draft? _existing;
  bool _redoing = false;
  bool _finished = false;
  bool _introShown = false;
  int _index = 0;
  final Map<String, Answer> _answers = {};

  @override
  void initState() {
    super.initState();
    _loadExisting();
  }

  @override
  void dispose() {
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _loadExisting() async {
    final db = await ref.read(databaseProvider.future);
    final draft = await db.draftFor(_ayushProfileId);
    if (!mounted) return;
    setState(() {
      _existing = draft;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final bundle = ref.watch(currentBundleProvider);
    final language = ref.watch(languageProvider);
    final ids = bundle?.ayurveda ?? const <String>[];

    if (bundle == null || ids.isEmpty) {
      // No content yet, or this build carries no Ayurveda module at all — the
      // same honest placeholder this screen showed before the module existed.
      return _placeholder(context, strings);
    }

    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: Text(strings.ayushTitle)),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (_existing != null && !_redoing) {
      return _completed(context, strings);
    }

    if (_finished) {
      return _thanks(context, strings);
    }

    // What is about to be asked and why, said once, on a screen of its
    // own — not stacked above question one, where a patient who has
    // already started reading a question skims straight past it. The
    // question screens that follow show nothing but the question.
    if (!_introShown) {
      return _intro(context, strings);
    }

    final question = bundle.questions[ids[_index]]!;
    return AnswerConfirmScope(
      notifier: _confirm,
      child: Scaffold(
      appBar: AppBar(title: Text(strings.ayushTitle)),
      bottomNavigationBar: ValueListenableBuilder<ConfirmAction?>(
        valueListenable: _confirm,
        builder: (context, action, _) {
          if (action == null) return const SizedBox.shrink();
          return DecoratedBox(
            decoration: const BoxDecoration(
              color: Colors.white,
              boxShadow: [
                BoxShadow(
                  color: Color(0x141B5E4A),
                  blurRadius: 20,
                  offset: Offset(0, -6),
                ),
              ],
            ),
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.all(Sizes.gutter),
                child: FilledButton(
                  key: const Key('answer.confirm'),
                  onPressed: action.onPressed,
                  child: Text(action.label),
                ),
              ),
            ),
          );
        },
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(
            Sizes.gutter,
            0,
            Sizes.gutter,
            Sizes.gutter,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              StepProgress(
                label: strings.ayushProgress(_index + 1, ids.length),
                done: _index + 1,
                total: ids.length,
              ),
              const SizedBox(height: Sizes.gutter),
              Semantics(
                header: true,
                child: Text(
                  question.promptFor(language) ?? question.fieldId,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              const SizedBox(height: Sizes.gutter),
              // Prominent here too — this used to be the one screen in the
              // app where voice quietly stopped being the lead interaction,
              // which a patient moving between this and the symptom
              // interview would have felt as the mic getting smaller for no
              // reason.
              ProminentVoice(
                prominent: true,
                child: buildAnswerWidget(
                      question: question,
                      language: language,
                      onAnswered: (value, originalText) => _record(
                          question, language, FieldStatus.answered,
                          value: value, originalText: originalText),
                    ) ??
                    const SizedBox.shrink(),
              ),
              const SizedBox(height: Sizes.gutter),
              const Divider(),
              const SizedBox(height: Sizes.gutter),
              AnswerActions(
                allowUnknown: question.allowUnknown,
                allowSkip: question.allowSkip,
                onDontKnow: () => _record(question, language, FieldStatus.unresolved),
                onSkip: () => _record(question, language, FieldStatus.notAsked),
              ),
            ],
          ),
        ),
      ),
      ),
    );
  }

  void _record(
    Question question,
    String language,
    FieldStatus status, {
    AnswerValue? value,
    String? originalText,
  }) {
    _answers[question.questionId] = Answer(
      questionId: question.questionId,
      fieldId: question.fieldId,
      status: status,
      value: value,
      originalText: originalText,
      askedText: question.promptFor(language),
      language: language,
    );
    final bundle = ref.read(currentBundleProvider)!;
    final atEnd = _index + 1 >= bundle.ayurveda.length;
    // The next question's widget publishes after the next frame; until then the
    // footer must not still offer the previous question's Continue.
    _confirm.value = null;
    setState(() => _index++);
    if (atEnd) {
      unawaited(_save(bundle, language));
    }
  }

  Future<void> _save(ContentBundle bundle, String language) async {
    final db = await ref.read(databaseProvider.future);
    final now = DateTime.now();
    await db.saveDraft(DraftsCompanion.insert(
      intakeId: _ayushProfileId,
      // Not a hospital visit — there is no hospital to name.
      hospitalId: '',
      language: language,
      reporter: 'self',
      answersJson: jsonEncode({
        for (final entry in _answers.entries) entry.key: entry.value.toJson(),
      }),
      contentVersion: bundle.contentVersion,
      startedAt: now,
      updatedAt: now,
      // Never actually submitted, so never actually retried — a fixed value
      // is fine where a real intake needs a fresh one per attempt (§9).
      idempotencyKey: _ayushProfileId,
    ));
    if (!mounted) return;
    setState(() => _finished = true);
  }

  /// What this module asks and why, said once, before question one.
  ///
  /// It used to sit stacked above the marital-status question, which put a
  /// paragraph about "not about today's problem" in the same glance as the
  /// first thing being asked — read once, then never again, but taking up
  /// the same space at the top of every later question if it had stayed
  /// there keyed to `_index == 0`. A screen of its own says it once and gets
  /// out of the way; every question after this is nothing but the question.
  Widget _intro(BuildContext context, Strings strings) => Scaffold(
        appBar: AppBar(title: Text(strings.ayushTitle)),
        bottomNavigationBar: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: FilledButton(
              key: const Key('ayush.introContinue'),
              onPressed: () => setState(() => _introShown = true),
              child: Text(strings.continueLabel),
            ),
          ),
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  strings.ayurvedaTitle,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                const SizedBox(height: Sizes.gap + 4),
                TintPanel(
                  padding: const EdgeInsets.all(Sizes.gap + 4),
                  child: Text(
                    strings.ayushIntro,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
              ],
            ),
          ),
        ),
      );

  /// The three end states share a shape: an emblem, a line, and at most one
  /// action. They are separate methods because they mean different things —
  /// "this build has no content", "you have already done this", "you have just
  /// finished" — and collapsing them into one parameterised widget is how the
  /// second of those quietly starts claiming the third.
  Widget _endState(
    BuildContext context,
    Strings strings, {
    required IconData icon,
    required String title,
    Key? titleKey,
    String? body,
    Widget? action,
  }) =>
      Scaffold(
        appBar: AppBar(title: Text(strings.ayushTitle)),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Center(child: EmblemMark(icon: icon, size: 116)),
                const SizedBox(height: Sizes.gutter),
                Text(
                  title,
                  key: titleKey,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
                if (body != null) ...[
                  const SizedBox(height: Sizes.gap),
                  Text(
                    body,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                  ),
                ],
                if (action != null) ...[
                  const SizedBox(height: Sizes.gutter * 1.5),
                  action,
                ],
              ],
            ),
          ),
        ),
      );

  Widget _placeholder(BuildContext context, Strings strings) => _endState(
        context,
        strings,
        icon: Icons.spa_outlined,
        title: strings.notAvailableYet,
        titleKey: const Key('ayush.notAvailable'),
      );

  Widget _completed(BuildContext context, Strings strings) => _endState(
        context,
        strings,
        icon: Icons.verified_outlined,
        title: strings.ayushCompletedTitle,
        body: strings.ayushCompletedBody,
        action: OutlinedButton(
          key: const Key('ayush.redo'),
          onPressed: () => setState(() {
            _redoing = true;
            _finished = false;
            _introShown = false;
            _index = 0;
            _answers.clear();
          }),
          child: Text(strings.ayushRedo),
        ),
      );

  Widget _thanks(BuildContext context, Strings strings) => _endState(
        context,
        strings,
        icon: Icons.check_rounded,
        title: strings.ayushCompletedTitle,
        action: FilledButton(
          key: const Key('ayush.done'),
          onPressed: () => Navigator.of(context).pop(),
          child: Text(strings.doneLabel),
        ),
      );
}
