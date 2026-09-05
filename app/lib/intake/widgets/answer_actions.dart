/// The two affordances every question carries — 2/3 §4.
///
/// **"I don't know" and "Skip" are different answers and must look different.**
/// One records `unresolved` — the patient was asked and could not say. The other
/// records `not_asked` — the question was never put. Neither is "no", and a
/// patient who cannot tell them apart will produce the wrong one.
///
/// So they are rendered distinctly and never as a matched pair of equal
/// buttons: "I don't know" is the answer, offered on every question; "Skip" is
/// an escape hatch, quieter, and absent where the content says the question
/// cannot be skipped.
library;

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../l10n/strings.dart';

class AnswerActions extends StatelessWidget {
  const AnswerActions({
    super.key,
    required this.allowUnknown,
    required this.allowSkip,
    required this.onDontKnow,
    required this.onSkip,
  });

  final bool allowUnknown;
  final bool allowSkip;
  final VoidCallback onDontKnow;
  final VoidCallback onSkip;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (allowUnknown)
          OutlinedButton(
            key: const Key('answer.dont_know'),
            onPressed: onDontKnow,
            child: Text(strings.answerDontKnow),
          ),
        if (allowSkip) ...[
          const SizedBox(height: Sizes.gap),
          TextButton(
            key: const Key('answer.skip'),
            onPressed: onSkip,
            child: Text(strings.answerSkip),
          ),
        ],
      ],
    );
  }
}
