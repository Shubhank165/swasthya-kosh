/// The interview's opening line — its own screen, once — 2/3 §5, §14.
///
/// Used to be folded into the same bubble as the first question: one avatar
/// saying "I'll ask a few questions so the doctor understands what's
/// happening" immediately followed, in the same breath, by the first thing
/// actually being asked. A patient who has started reading the question skims
/// straight past the sentence above it, so it was said once and then wasted.
/// Read separately, with nothing to answer here and one thing to do — this
/// stays true for the whole reason `BotSays.intro` exists (§5's "why am I
/// being asked this" belongs in the same glance as the answer, not before
/// it), it is only the *greeting* that never belonged glued to a question.
library;

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../l10n/strings.dart';
import '../../voice/read_aloud_button.dart';
import '../widgets/interview_ui.dart';

class IntakeGreetingScreen extends StatelessWidget {
  const IntakeGreetingScreen({
    super.key,
    required this.language,
    required this.patientName,
    required this.onContinue,
  });

  /// The language already chosen — the greeting is read aloud in it,
  /// automatically, the same as every question that follows (§14).
  final String language;

  /// The patient's own name, or null when they have not given one — the
  /// greeting then simply has no name in it, rather than a placeholder.
  final String? patientName;

  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final greeting = patientName == null
        ? strings.assistantIntro
        : strings.assistantIntroNamed(patientName!);

    return Scaffold(
      appBar: AppBar(),
      bottomNavigationBar: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: FilledButton(
            key: const Key('intake.greetingContinue'),
            onPressed: onContinue,
            child: Text(strings.continueLabel),
          ),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            Sizes.gutter,
            Sizes.gutter,
            Sizes.gutter,
            0,
          ),
          child: BotSays(
            text: greeting,
            trailing: ReadAloudButton(
              // Fixed rather than a question id — there is exactly one of
              // these per intake, so nothing needs to tell this utterance
              // apart from another.
              utteranceKey: 'intake.greeting',
              text: greeting,
              language: language,
            ),
          ),
        ),
      ),
    );
  }
}
