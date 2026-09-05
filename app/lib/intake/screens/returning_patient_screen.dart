/// The returning-patient check — 2/3 §5 screen 5.
///
/// "Our record shows diabetes and Metformin. Still correct?" per item: Yes / No
/// / Not sure. **Never re-asks confirmed history from scratch** — a patient who
/// has told this hospital three times that they take Metformin should not be
/// asked a fourth time as though nobody wrote it down.
///
/// **This is confirmation of what the hospital already holds**, which the
/// patient themselves reported on a previous visit. It is not OCR output and it
/// is not an interpretation, so it does not run into §8's rule against showing
/// extracted values back to a patient. What is shown here came from their own
/// mouth, at this hospital, on a recorded date.
library;

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../l10n/strings.dart';

/// One thing the hospital already has on record.
class CarriedItem {
  const CarriedItem({
    required this.fieldId,
    required this.label,
    required this.recordedOn,
  });

  final String fieldId;

  /// The patient's own words from the earlier visit, not a normalised code.
  final String label;
  final String recordedOn;
}

/// What the patient said about a carried item.
enum CarryDecision { stillCorrect, noLongerCorrect, notSure }

class ReturningPatientScreen extends StatefulWidget {
  const ReturningPatientScreen({
    super.key,
    required this.items,
    required this.onDone,
  });

  final List<CarriedItem> items;
  final void Function(Map<String, CarryDecision> decisions) onDone;

  @override
  State<ReturningPatientScreen> createState() => _ReturningPatientScreenState();
}

class _ReturningPatientScreenState extends State<ReturningPatientScreen> {
  final _decisions = <String, CarryDecision>{};

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(strings.stillCorrectHeading)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            for (final item in widget.items)
              Card(
                key: Key('carry.${item.fieldId}'),
                margin: const EdgeInsets.only(bottom: Sizes.gap),
                child: Padding(
                  padding: const EdgeInsets.all(Sizes.gap),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item.label,
                          style: Theme.of(context).textTheme.bodyLarge),
                      Text(item.recordedOn,
                          style: Theme.of(context).textTheme.bodyMedium),
                      const SizedBox(height: Sizes.gap),
                      Row(
                        children: [
                          for (final (decision, label) in [
                            (CarryDecision.stillCorrect, strings.optYes),
                            (CarryDecision.noLongerCorrect, strings.optNo),
                            // Kept distinct from "no". A patient who is unsure
                            // whether they still take a medicine has not said
                            // they stopped, and recording it as a stop would
                            // remove a drug from their history on a guess.
                            (CarryDecision.notSure, strings.optNotSure),
                          ])
                            Padding(
                              padding: const EdgeInsets.only(right: Sizes.gap),
                              child: ChoiceChip(
                                key: Key('carry.${item.fieldId}.${decision.name}'),
                                label: Text(label),
                                selected: _decisions[item.fieldId] == decision,
                                onSelected: (_) => setState(
                                  () => _decisions[item.fieldId] = decision,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: Sizes.gutter),
            FilledButton(
              key: const Key('carry.continue'),
              // Every item must be decided. An undecided carried item silently
              // becomes "still correct" otherwise, which is the system asserting
              // a clinical fact on the patient's behalf.
              onPressed: _decisions.length == widget.items.length
                  ? () => widget.onDone(Map.unmodifiable(_decisions))
                  : null,
              child: Text(strings.continueLabel),
            ),
          ],
        ),
      ),
    );
  }
}
