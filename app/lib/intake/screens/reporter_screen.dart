/// Who is this for — 2/3 §5 screen 4, §11.
///
/// Sets `reporter` on the record, which the physician reads as "who told us
/// this". A daughter describing her father's symptoms is second-hand history
/// and is weighted differently from the patient's own account — so this is a
/// clinical field, not a courtesy.
///
/// **Minors: guardian consent is what is recorded, and no birth date is
/// collected to compute age** (§11). Asking directly who is consenting is both
/// simpler and less data.
library;

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../l10n/strings.dart';
import '../widgets/answer_widgets.dart';

class ReporterScreen extends StatelessWidget {
  const ReporterScreen({super.key, required this.onChosen});

  /// Emits the `reporter` value the record carries. These are the kiosk
  /// contract's values, not new ones — the same record shape from both sources.
  final void Function(String reporter, {required bool guardianConsent}) onChosen;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(strings.whoIsThisFor)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            OptionTile(
              key: const Key('reporter.self'),
              label: strings.forMyself,
              icon: Icons.person_outline,
              onTap: () => onChosen('self', guardianConsent: false),
            ),
            OptionTile(
              key: const Key('reporter.parent'),
              label: strings.forMyParent,
              icon: Icons.elderly_outlined,
              onTap: () => onChosen('family_attendant', guardianConsent: false),
            ),
            OptionTile(
              key: const Key('reporter.child'),
              label: strings.forMyChild,
              icon: Icons.child_care_outlined,
              // The only branch where consent is given *by* the reporter *for*
              // the patient. Recorded as guardian consent rather than inferred
              // later from an age we deliberately do not collect.
              onTap: () => onChosen('parent_guardian', guardianConsent: true),
            ),
            OptionTile(
              key: const Key('reporter.other'),
              label: strings.forSomeoneElse,
              icon: Icons.people_outline,
              onTap: () => onChosen('caregiver', guardianConsent: false),
            ),
          ],
        ),
      ),
    );
  }
}
