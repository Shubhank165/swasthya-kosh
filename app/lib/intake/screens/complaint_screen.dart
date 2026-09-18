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
///
/// **"Something else" now asks what.** It used to record the code `other` with
/// the words "Something else" as the patient's own text, which is the least
/// useful thing this screen could hand a Vaidya: it says only that none of six
/// pictures fitted. Tapping it opens a box; the code stays `other` so the
/// branching is unchanged, and what they write becomes `original_text` — the
/// field Decision #3 says travels with every fact forever.
library;

import 'package:flutter/material.dart';

import '../../content/bundle.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
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

class ComplaintScreen extends StatefulWidget {
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
  State<ComplaintScreen> createState() => _ComplaintScreenState();
}

class _ComplaintScreenState extends State<ComplaintScreen> {
  /// True once "Something else" has been tapped and the box is open.
  ///
  /// Nothing is recorded at that moment. Picking the option is the patient
  /// saying "not one of these"; the answer is what they then write.
  bool _writingOther = false;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final options = widget.question.options ?? const [];

    return Scaffold(
      appBar: AppBar(),
      body: Garnish(
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(
              Sizes.gutter,
              0,
              Sizes.gutter,
              Sizes.gutter,
            ),
            children: [
              Semantics(
                header: true,
                child: Text(
                  widget.question.promptFor(widget.language) ??
                      strings.chooseComplaint,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
              ),
              const SizedBox(height: Sizes.gutter),
              for (final option in options) ...[
                OptionTile(
                  key: Key('complaint.$option'),
                  label: option == kOtherOptionCode
                      ? strings.somethingElse
                      : optionLabel(option),
                  icon: _complaintIcons[option],
                  selected: option == kOtherOptionCode && _writingOther,
                  onTap: option == kOtherOptionCode
                      ? () => setState(() => _writingOther = true)
                      : () => widget.onChosen(option, optionLabel(option)),
                ),
                if (option == kOtherOptionCode && _writingOther)
                  OtherEntry(
                    label: strings.somethingElse,
                    onSubmitted: (written) =>
                        widget.onChosen(kOtherOptionCode, written),
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
