/// The urgent-care screen — 2/3 §6.
///
/// **The most safety-critical screen in this app.** Get it wrong and it tells
/// someone with cardiac symptoms to keep answering questions about their diet.
///
/// It tells the patient *what to do*. It never names a condition, never states
/// a likelihood, and never says what might be wrong. The wording is bounded by
/// the brief and lives in the ARB files as `urgentTitle` / `urgentBody` /
/// `urgentAction`, checked by `test/l10n_completeness_test.dart` for disease
/// names in every language.
///
/// **There is no "continue anyway".** Not disabled, not hidden behind a
/// confirmation — absent. The two actions are finding a hospital and
/// acknowledging.
library;

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../l10n/strings.dart';

class UrgentCareScreen extends StatelessWidget {
  const UrgentCareScreen({
    super.key,
    required this.emergencyNumber,
    required this.onShowNearestHospital,
    required this.onAcknowledge,
  });

  /// From the hospital record where one is loaded, not a constant.
  ///
  /// 108 is the common ambulance number across most Indian states but is not
  /// universal, so a hospital in a state that differs must be able to change it
  /// without an app release. §6 flags this for clinician confirmation before
  /// shipping.
  final String emergencyNumber;
  final VoidCallback onShowNearestHospital;
  final VoidCallback onAcknowledge;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return PopScope(
      // The system back gesture must not dismiss this. A patient returning to
      // the interview from here is exactly the outcome §6 forbids.
      canPop: false,
      child: Scaffold(
        backgroundColor: Palette.urgentSurface,
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: Sizes.gutter),
                const Icon(Icons.error_outline, size: 64, color: Palette.urgent),
                const SizedBox(height: Sizes.gutter),
                Semantics(
                  header: true,
                  child: Text(
                    strings.urgentTitle,
                    key: const Key('urgent.title'),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          color: Palette.urgent,
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                ),
                const SizedBox(height: Sizes.gutter),
                Text(
                  strings.urgentBody,
                  key: const Key('urgent.body'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                const SizedBox(height: Sizes.gap),
                Text(
                  strings.urgentAction(emergencyNumber),
                  key: const Key('urgent.action'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
                const Spacer(),
                FilledButton(
                  key: const Key('urgent.nearest'),
                  onPressed: onShowNearestHospital,
                  style: FilledButton.styleFrom(backgroundColor: Palette.urgent),
                  child: Text(strings.showNearestHospital),
                ),
                const SizedBox(height: Sizes.gap),
                OutlinedButton(
                  key: const Key('urgent.acknowledge'),
                  onPressed: onAcknowledge,
                  child: Text(strings.iUnderstand),
                ),
                const SizedBox(height: Sizes.gutter),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
