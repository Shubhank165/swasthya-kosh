/// The chief complaint — 2/3 §5 screen 6, §14.
///
/// An icon grid, because this is the screen where a patient who reads poorly
/// most needs help: it is the first clinical question, and getting it wrong
/// sends the whole interview down the wrong branch.
///
/// The complaint options come from the bundle, not from this file. The icons are
/// a presentation detail mapped by option code, and an option with no icon
/// renders as text rather than as a wrong picture — a stomach icon on a headache
/// row is worse than no icon.
library;

import 'package:flutter/material.dart';

import '../../content/bundle.dart';
import '../../core/theme.dart';
import '../../l10n/strings.dart';
import '../widgets/answer_widgets.dart';

const _complaintIcons = <String, IconData>{
  'abdominal_pain': Icons.sick_outlined,
  'chest_pain': Icons.favorite_outline,
  'fever': Icons.thermostat_outlined,
  'headache': Icons.psychology_outlined,
  'joint_pain': Icons.accessibility_new_outlined,
  'follow_up_visit': Icons.event_repeat_outlined,
  'other': Icons.more_horiz,
};

class ComplaintScreen extends StatelessWidget {
  const ComplaintScreen({
    super.key,
    required this.question,
    required this.language,
    required this.onChosen,
  });

  final Question question;
  final String language;
  final void Function(String code, String label) onChosen;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final options = question.options ?? const [];
    return Scaffold(
      appBar: AppBar(title: Text(strings.chooseComplaint)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            Semantics(
              header: true,
              child: Text(
                question.promptFor(language) ?? strings.chooseComplaint,
                style: Theme.of(context).textTheme.titleLarge,
              ),
            ),
            const SizedBox(height: Sizes.gutter),
            for (final option in options)
              OptionTile(
                key: Key('complaint.$option'),
                label: option == 'other'
                    ? strings.somethingElse
                    : optionLabel(option),
                icon: _complaintIcons[option],
                onTap: () => onChosen(
                  option,
                  option == 'other' ? strings.somethingElse : optionLabel(option),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
