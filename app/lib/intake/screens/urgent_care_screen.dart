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
///
/// **What the restyle did and did not change.** The three strings, their order,
/// the two actions and the blocked back gesture are exactly as they were. What
/// changed is that the emergency number is now large enough to read across a
/// waiting room and sits in its own panel, because the one thing a frightened
/// patient has to be able to act on should not be the third line of a
/// paragraph. No colour was added: red is still this screen's alone.
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
    final text = Theme.of(context).textTheme;

    return PopScope(
      // The system back gesture must not dismiss this. A patient returning to
      // the interview from here is exactly the outcome §6 forbids.
      canPop: false,
      child: Scaffold(
        backgroundColor: Palette.urgentSurface,
        body: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Padding(
                  padding: const EdgeInsets.all(Sizes.gutter),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: Sizes.gutter),
                      Center(
                        child: Container(
                          width: 92,
                          height: 92,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: Palette.urgent.withAlpha(28),
                          ),
                          child: const Icon(
                            Icons.priority_high_rounded,
                            size: 48,
                            color: Palette.urgent,
                          ),
                        ),
                      ),
                      const SizedBox(height: Sizes.gutter),
                      Semantics(
                        header: true,
                        child: Text(
                          strings.urgentTitle,
                          key: const Key('urgent.title'),
                          textAlign: TextAlign.center,
                          style: text.headlineMedium?.copyWith(
                            color: Palette.urgent,
                          ),
                        ),
                      ),
                      const SizedBox(height: Sizes.gutter),
                      Text(
                        strings.urgentBody,
                        key: const Key('urgent.body'),
                        textAlign: TextAlign.center,
                        style: text.bodyLarge,
                      ),
                      const SizedBox(height: Sizes.gutter),
                      Container(
                        padding: const EdgeInsets.all(Sizes.gutter),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(Sizes.radiusLarge),
                          border: Border.all(color: Palette.urgent.withAlpha(70)),
                        ),
                        child: Column(
                          children: [
                            const Icon(
                              Icons.call_outlined,
                              color: Palette.urgent,
                              size: 28,
                            ),
                            const SizedBox(height: Sizes.gap),
                            Text(
                              strings.urgentAction(emergencyNumber),
                              key: const Key('urgent.action'),
                              textAlign: TextAlign.center,
                              style: text.bodyLarge?.copyWith(
                                fontWeight: FontWeight.w700,
                                color: Palette.urgent,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: Sizes.gutter * 1.5),
                      FilledButton.icon(
                        key: const Key('urgent.nearest'),
                        onPressed: onShowNearestHospital,
                        style: FilledButton.styleFrom(
                          backgroundColor: Palette.urgent,
                          foregroundColor: Colors.white,
                        ),
                        icon: const Icon(Icons.local_hospital_outlined),
                        label: Text(strings.showNearestHospital),
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
          ),
        ),
      ),
    );
  }
}
