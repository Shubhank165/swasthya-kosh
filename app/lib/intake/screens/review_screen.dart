/// Review and confirm — 2/3 §5 screen 10.
///
/// "The patient sees what was recorded, in their language, and can correct any
/// answer before submitting. Medicines, doses and allergies are shown
/// explicitly."
///
/// **This screen shows the patient their own answers, and nothing else.** It
/// does not show extracted OCR values (§8: unverified OCR shown to a patient is
/// a diagnosis surface), it does not show contradictions the backend found, and
/// it does not interpret anything. Every line here is something the patient
/// typed or tapped.
library;

import 'package:flutter/material.dart';

import '../../content/answer.dart';
import '../../content/bundle.dart';
import '../../core/theme.dart';
import '../../l10n/strings.dart';

class ReviewScreen extends StatelessWidget {
  const ReviewScreen({
    super.key,
    required this.bundle,
    required this.answers,
    required this.language,
    required this.documentCount,
    required this.onEdit,
    required this.onAddDocuments,
    required this.onSubmit,
  });

  final ContentBundle bundle;
  final Map<String, Answer> answers;
  final String language;

  /// How many pages the patient photographed, so the footer can say whether
  /// anything was added at all. A count, never a thumbnail or a reading: §8
  /// keeps unverified OCR off every patient-facing screen.
  final int documentCount;

  final void Function(String questionId) onEdit;
  final VoidCallback onAddDocuments;
  final VoidCallback onSubmit;

  /// Sections whose answers are shown first and in full.
  ///
  /// §5 names medicines, doses and allergies explicitly, and the reason is that
  /// these are the answers a physician acts on soonest and the ones a patient is
  /// most likely to have mistyped.
  static const _emphasised = {'medications', 'allergies'};

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);

    // Only what the patient actually settled. Showing a wall of "not asked"
    // rows would bury the answers they need to check.
    final settled = answers.values.where((a) => a.isSettled).toList();
    final sections = <String, List<Answer>>{};
    for (final answer in settled) {
      final section = bundle.questions[answer.questionId]?.section ?? 'other';
      sections.putIfAbsent(section, () => []).add(answer);
    }

    final ordered = [
      ..._emphasised.where(sections.containsKey),
      ...bundle.sections.where((s) => sections.containsKey(s) && !_emphasised.contains(s)),
    ];

    return Scaffold(
      appBar: AppBar(title: Text(strings.reviewTitle)),
      // Submit is pinned, not parked at the end of the list. A patient with
      // thirty answers had to scroll past all of them to find out the button
      // existed, which reads as a screen with no way forward.
      bottomNavigationBar: _Footer(
        documentCount: documentCount,
        onAddDocuments: onAddDocuments,
        onSubmit: onSubmit,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            for (final section in ordered) ...[
              Padding(
                padding: const EdgeInsets.symmetric(vertical: Sizes.gap),
                child: Semantics(
                  header: true,
                  child: Text(
                    // Section keys are content, not UI strings, and the bundle
                    // carries no translations for them. De-underscored rather
                    // than machine-translated — §16.
                    section.replaceAll('_', ' '),
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                ),
              ),
              for (final answer in sections[section]!)
                Card(
                  margin: const EdgeInsets.only(bottom: Sizes.gap),
                  child: ListTile(
                    key: Key('review.${answer.questionId}'),
                    title: Text(
                      bundle.questions[answer.questionId]?.promptFor(language) ??
                          answer.fieldId,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    subtitle: Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        // The patient's own words, as they were shown. Not the
                        // normalised code — a patient checking their answer
                        // needs to recognise it.
                        answer.originalText ?? '',
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                    ),
                    trailing: TextButton(
                      onPressed: () => onEdit(answer.questionId),
                      child: Text(strings.editAnswer),
                    ),
                    isThreeLine: true,
                  ),
                ),
            ],
            const SizedBox(height: Sizes.gutter),
          ],
        ),
      ),
    );
  }
}

/// The pinned footer: add what was missed, then submit.
///
/// Both controls sit above the fold at all times. The documents route is
/// secondary and stays a text button — it is a detour a few patients need, not
/// a second thing every patient must decide about before they can finish.
class _Footer extends StatelessWidget {
  const _Footer({
    required this.documentCount,
    required this.onAddDocuments,
    required this.onSubmit,
  });

  final int documentCount;
  final VoidCallback onAddDocuments;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Material(
      elevation: 8,
      color: Theme.of(context).colorScheme.surface,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextButton.icon(
                key: const Key('review.addDocuments'),
                onPressed: onAddDocuments,
                icon: const Icon(Icons.add_a_photo_outlined),
                label: Text(
                  documentCount == 0
                      ? strings.reviewAddDocuments
                      : strings.reviewAddMoreDocuments(documentCount),
                ),
              ),
              const SizedBox(height: Sizes.gap),
              FilledButton(
                key: const Key('review.submit'),
                onPressed: onSubmit,
                child: Text(strings.submitIntake),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
