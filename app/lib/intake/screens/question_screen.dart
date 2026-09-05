/// One question per screen — 2/3 §5, §14.
///
/// "One question per screen throughout the interview — this is an accessibility
/// requirement, not a style choice." A form with twelve fields is unusable at
/// 200% text scale, unreadable to a screen reader in any sensible order, and
/// invites a patient to answer the easy ones and leave the rest blank, which
/// produces `not_asked` where the honest answer was available.
library;

import 'package:flutter/material.dart';

import '../../content/bundle.dart';
import '../../core/theme.dart';
import '../../l10n/strings.dart';
import '../widgets/answer_actions.dart';
import '../widgets/answer_widgets.dart';

class QuestionScreen extends StatelessWidget {
  const QuestionScreen({
    super.key,
    required this.question,
    required this.language,
    required this.onAnswered,
    required this.onDontKnow,
    required this.onSkip,
    required this.sectionsDone,
    required this.sectionsTotal,
    this.onBack,
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;
  final VoidCallback onDontKnow;
  final VoidCallback onSkip;
  final int sectionsDone;
  final int sectionsTotal;

  /// `null` on the first question. **Back is available everywhere else** (§5) —
  /// a patient who mistapped must be able to correct it without abandoning the
  /// intake.
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final prompt = question.promptFor(language);

    return Scaffold(
      appBar: AppBar(
        leading: onBack == null
            ? null
            : IconButton(
                key: const Key('question.back'),
                icon: const Icon(Icons.arrow_back),
                tooltip: strings.backLabel,
                onPressed: onBack,
              ),
        title: Text(
          // Sections, never a percentage. A percentage implies a precision the
          // branching does not have: answering "chest pain" adds twenty
          // questions and would make progress go backwards.
          strings.sectionProgress(sectionsDone, sectionsTotal),
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Semantics(
                header: true,
                child: Text(
                  // Should be unreachable: the walker never offers a question
                  // with no prompt in the chosen language. Rendering the field
                  // id rather than an English fallback keeps the invariant
                  // visible if it ever breaks — a patient must never be shown a
                  // clinical question in a language they did not choose.
                  prompt ?? question.fieldId,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              const SizedBox(height: Sizes.gutter),
              buildAnswerWidget(question: question, onAnswered: onAnswered) ??
                  const SizedBox.shrink(),
              const SizedBox(height: Sizes.gutter),
              const Divider(),
              const SizedBox(height: Sizes.gap),
              AnswerActions(
                allowUnknown: question.allowUnknown,
                allowSkip: question.allowSkip,
                onDontKnow: onDontKnow,
                onSkip: onSkip,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
