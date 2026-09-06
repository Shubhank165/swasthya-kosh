/// Submitted — 2/3 §5 screen 11, §7.4.
///
/// A reference code to show at registration, and what happens next.
///
/// **The app does not book appointments** (§7.4). The patient picks a hospital
/// and a department, completes intake, and receives a code that links their
/// answers to their visit. Nothing more.
library;

import 'package:flutter/material.dart';

import '../../core/theme.dart';
import '../../l10n/strings.dart';

class SubmittedScreen extends StatelessWidget {
  const SubmittedScreen({
    super.key,
    required this.referenceCode,
    required this.hospitalName,
    required this.queued,
    required this.onDone,
  });

  final String referenceCode;
  final String hospitalName;

  /// Closes the finished intake.
  ///
  /// This screen had no control on it at all, so the only way off was the
  /// system back gesture — which pops the intake route and drops the patient on
  /// the language chooser with no explanation. Finishing something has to be
  /// something you *do*, not something you escape from.
  final VoidCallback onDone;

  /// True when the record is on the device waiting for a connection rather than
  /// accepted by the hospital. The patient is told which, plainly: a code they
  /// believe is registered when it is not is worse than a short wait.
  final bool queued;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Sizes.gutter),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: Sizes.gutter),
              Icon(
                queued ? Icons.schedule : Icons.check_circle_outline,
                size: 64,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(height: Sizes.gutter),
              Semantics(
                header: true,
                child: Text(
                  strings.submittedTitle,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              const SizedBox(height: Sizes.gutter),
              Text(
                strings.referenceCodeLabel,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: Sizes.gap),
              SelectableText(
                referenceCode,
                key: const Key('submitted.code'),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      letterSpacing: 4,
                      fontWeight: FontWeight.w700,
                    ),
              ),
              const SizedBox(height: Sizes.gutter),
              Text(
                queued ? strings.savedOffline : strings.showAtRegistration,
                key: const Key('submitted.next'),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              const SizedBox(height: Sizes.gap),
              Text(
                hospitalName,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const Spacer(),
              FilledButton(
                key: const Key('submitted.done'),
                onPressed: onDone,
                child: Text(strings.doneLabel),
              ),
              const SizedBox(height: Sizes.gutter),
            ],
          ),
        ),
      ),
    );
  }
}
