/// The Ayurveda self-report — review items 3/4.
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
import '../intake/widgets/answer_actions.dart';
import '../intake/widgets/answer_widgets.dart';
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
  bool _loading = true;
  Draft? _existing;
  bool _redoing = false;
  bool _finished = false;
  int _index = 0;
  final Map<String, Answer> _answers = {};

  @override
  void initState() {
    super.initState();
    _loadExisting();
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

    final question = bundle.questions[ids[_index]]!;
    return Scaffold(
      appBar: AppBar(
        title: Text(strings.ayushProgress(_index + 1, ids.length)),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_index == 0) ...[
                Text(strings.ayurvedaTitle, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: Sizes.gap),
                Text(strings.ayushIntro, style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: Sizes.gutter),
                const Divider(),
                const SizedBox(height: Sizes.gap),
              ],
              Semantics(
                header: true,
                child: Text(
                  question.promptFor(language) ?? question.fieldId,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              const SizedBox(height: Sizes.gutter),
              buildAnswerWidget(
                    question: question,
                    language: language,
                    onAnswered: (value, originalText) =>
                        _record(question, language, FieldStatus.answered, value: value, originalText: originalText),
                  ) ??
                  const SizedBox.shrink(),
              const SizedBox(height: Sizes.gutter),
              const Divider(),
              const SizedBox(height: Sizes.gap),
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

  Widget _placeholder(BuildContext context, Strings strings) => Scaffold(
        appBar: AppBar(title: Text(strings.ayushTitle)),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.spa_outlined,
                  size: 64,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(height: Sizes.gutter),
                Text(
                  strings.notAvailableYet,
                  key: const Key('ayush.notAvailable'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
        ),
      );

  Widget _completed(BuildContext context, Strings strings) => Scaffold(
        appBar: AppBar(title: Text(strings.ayushTitle)),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.check_circle_outline,
                  size: 64,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(height: Sizes.gutter),
                Text(
                  strings.ayushCompletedTitle,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: Sizes.gap),
                Text(
                  strings.ayushCompletedBody,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: Sizes.gutter),
                OutlinedButton(
                  key: const Key('ayush.redo'),
                  onPressed: () => setState(() {
                    _redoing = true;
                    _finished = false;
                    _index = 0;
                    _answers.clear();
                  }),
                  child: Text(strings.ayushRedo),
                ),
              ],
            ),
          ),
        ),
      );

  Widget _thanks(BuildContext context, Strings strings) => Scaffold(
        appBar: AppBar(title: Text(strings.ayushTitle)),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(
                  Icons.check_circle_outline,
                  size: 64,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(height: Sizes.gutter),
                Text(
                  strings.ayushCompletedTitle,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: Sizes.gutter),
                FilledButton(
                  key: const Key('ayush.done'),
                  onPressed: () => Navigator.of(context).pop(),
                  child: Text(strings.doneLabel),
                ),
              ],
            ),
          ),
        ),
      );
}
