/// Submitted — 2/3 §5 screen 11, §7.4.
///
/// A reference code to show at registration, and what happens next.
///
/// **The app does not book appointments** (§7.4). The patient picks a hospital
/// and a department, completes intake, and receives a code that links their
/// answers to their visit. Nothing more. There is no queue position here and no
/// estimated wait: this app cannot see the OPD queue, and a number that looked
/// like one would be read as a promise.
///
/// **The code is the screen.** Everything else is a sentence about the code, so
/// it gets the panel, the size and the letter spacing — this is read aloud
/// across a registration counter by someone who has just been through an
/// interview, and `MK-7EB-703` at body size in the middle of a paragraph is
/// where that goes wrong. It stays selectable, and there is a copy button for
/// the patient who would rather paste it into a message to whoever drove them.
///
/// **The content is centred and Done is pinned.** Top-aligned, this screen was
/// a short block of text with a third of the phone blank underneath it, which
/// reads as a page that failed to finish loading rather than as the end of
/// something.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/theme.dart';
import '../../core/ui.dart';
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
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;

    return Scaffold(
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(
              color: Color(0x141B5E4A),
              blurRadius: 20,
              offset: Offset(0, -6),
            ),
          ],
        ),
        child: SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(Sizes.gutter),
            child: FilledButton(
              key: const Key('submitted.done'),
              onPressed: onDone,
              child: Text(strings.doneLabel),
            ),
          ),
        ),
      ),
      body: Garnish(
        dense: true,
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Padding(
                  padding: const EdgeInsets.all(Sizes.gutter),
                  child: Column(
                    // Centred, so the screen reads as a full stop rather than
                    // as a page that stopped loading.
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Center(
                        child: EmblemMark(
                          // Two states, two icons. A tick over a queued record
                          // would say "the hospital has this", which is the one
                          // thing that is not yet true.
                          icon: queued ? Icons.schedule : Icons.check_rounded,
                          size: 132,
                        ),
                      ),
                      const SizedBox(height: Sizes.gutter),
                      Semantics(
                        header: true,
                        child: Text(
                          strings.submittedTitle,
                          textAlign: TextAlign.center,
                          style: text.headlineMedium,
                        ),
                      ),
                      const SizedBox(height: Sizes.gutter * 1.2),
                      _CodeCard(code: referenceCode),
                      const SizedBox(height: Sizes.gutter * 1.2),
                      _Fact(
                        icon: queued
                            ? Icons.cloud_off_outlined
                            : Icons.how_to_reg_outlined,
                        textKey: const Key('submitted.next'),
                        label: queued
                            ? strings.savedOffline
                            : strings.showAtRegistration,
                      ),
                      const SizedBox(height: Sizes.gap),
                      _Fact(
                        icon: Icons.location_on_outlined,
                        label: hospitalName,
                      ),
                      const SizedBox(height: Sizes.gutter),
                      PrivacyNote(text: strings.dataProtected),
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

/// The code, its label, and a way to copy it.
class _CodeCard extends StatelessWidget {
  const _CodeCard({required this.code});

  final String code;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;

    return SoftCard(
      padding: const EdgeInsets.fromLTRB(
        Sizes.gutter,
        Sizes.gutter,
        Sizes.gutter,
        Sizes.gap,
      ),
      child: Column(
        children: [
          Text(
            strings.referenceCodeLabel,
            textAlign: TextAlign.center,
            style: text.bodySmall?.copyWith(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: Sizes.gap),
          // Shrinks rather than wrapping. A code broken across two lines is a
          // code somebody reads out wrong.
          FittedBox(
            fit: BoxFit.scaleDown,
            child: SelectableText(
              code,
              key: const Key('submitted.code'),
              textAlign: TextAlign.center,
              style: text.headlineMedium?.copyWith(
                fontSize: 34,
                letterSpacing: 5,
                fontWeight: FontWeight.w700,
                color: colors.primary,
              ),
            ),
          ),
          const SizedBox(height: Sizes.gap),
          const Divider(),
          TextButton.icon(
            key: const Key('submitted.copy'),
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: code));
              if (!context.mounted) return;
              ScaffoldMessenger.of(context)
                ..hideCurrentSnackBar()
                ..showSnackBar(SnackBar(content: Text(strings.codeCopied)));
            },
            icon: const Icon(Icons.copy_rounded, size: 20),
            label: Text(strings.copyCode),
          ),
        ],
      ),
    );
  }
}

/// One line of "and here is what that means", with its icon in a chip.
class _Fact extends StatelessWidget {
  const _Fact({required this.icon, required this.label, this.textKey});

  final IconData icon;
  final String label;
  final Key? textKey;

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          IconChip(icon: icon, size: 40),
          const SizedBox(width: Sizes.gap),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                label,
                key: textKey,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ),
          ),
        ],
      );
}
