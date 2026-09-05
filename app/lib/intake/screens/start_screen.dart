/// Welcome, language, and sign-in — 2/3 §5 screen 1, §7.
///
/// Language comes first, before anything else is shown. A patient who cannot
/// read the sign-in screen cannot sign in, and the nine-language chooser is the
/// one thing that must be legible without reading.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../storage/database.dart';
import '../../l10n/strings.dart';
import '../flow.dart';
import '../intake_host.dart';
import 'hospital_screen.dart';
import 'sign_in_screen.dart';

/// Endonyms — each language named in its own script.
///
/// "Hindi" written in Latin script is no help to somebody who reads only
/// Devanagari, which is exactly the person this list exists for.
const languageNames = {
  'en': 'English',
  'hi': 'हिन्दी',
  'bn': 'বাংলা',
  'ta': 'தமிழ்',
  'te': 'తెలుగు',
  'mr': 'मराठी',
  'gu': 'ગુજરાતી',
  'kn': 'ಕನ್ನಡ',
  'pa': 'ਪੰਜਾਬੀ',
};

class StartScreen extends ConsumerWidget {
  const StartScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final selected = ref.watch(languageProvider);
    final signedIn = ref.watch(signedInProvider);

    // §4: if the bundle names a schema this app cannot produce, refuse to start
    // an intake and tell the patient to update. **No partial compatibility** —
    // a record that is half of a newer contract is one the backend will either
    // reject or, worse, accept and misread.
    final bundle = ref.watch(currentBundleProvider);
    final mustUpdate = bundle != null && !bundle.isUsable;

    // `--dart-define=MEDIKIOSK_DEV_SIGN_IN=<phone>` signs in without a screen.
    // Announced on screen for the same reason the mocked OTP delivery is: a
    // demo that presents a development shortcut as a real sign-in is a claim
    // nobody in the room can check.
    final autoSignIn = ref.watch(configProvider).autoSignIn;
    // `isLoading`, never "has no value yet". A development shortcut that fails
    // must not leave Continue disabled forever — the ordinary sign-in screen is
    // still there, and reaching it is the correct outcome when the shortcut
    // could not reach the backend.
    final waitingForAutoSignIn = autoSignIn && signedIn.isLoading;

    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Sizes.gutter),
          children: [
            const SizedBox(height: Sizes.gutter),
            Semantics(
              header: true,
              child: Text(
                strings.appTitle,
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: Sizes.gutter * 2),
            for (final entry in languageNames.entries)
              Padding(
                padding: const EdgeInsets.only(bottom: Sizes.gap),
                child: OutlinedButton(
                  key: Key('language.${entry.key}'),
                  onPressed: () =>
                      ref.read(languageProvider.notifier).state = entry.key,
                  style: OutlinedButton.styleFrom(
                    backgroundColor: selected == entry.key
                        ? Theme.of(context).colorScheme.secondaryContainer
                        : null,
                  ),
                  child: Text(entry.value),
                ),
              ),
            const SizedBox(height: Sizes.gutter),
            if (mustUpdate)
              Padding(
                padding: const EdgeInsets.only(bottom: Sizes.gap),
                child: Text(
                  strings.updateRequired,
                  key: const Key('start.updateRequired'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
              ),
            if (autoSignIn)
              Padding(
                padding: const EdgeInsets.only(bottom: Sizes.gap),
                child: Text(
                  strings.mockNotice,
                  key: const Key('start.devSignIn'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            if (!mustUpdate) _ResumePrompt(language: selected),
            FilledButton(
              key: const Key('start.continue'),
              // Disabled until the automatic sign-in has resolved, or an early
              // tap lands on the sign-in screen this define exists to skip.
              onPressed: mustUpdate || waitingForAutoSignIn
                  ? null
                  : () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => signedIn.valueOrNull == true
                              ? const HospitalScreen()
                              : const SignInScreen(),
                        ),
                      ),
              child: Text(strings.continueLabel),
            ),
            if (signedIn.valueOrNull == true)
              Padding(
                padding: const EdgeInsets.only(top: Sizes.gap),
                child: TextButton(
                  key: const Key('start.signOut'),
                  // §10: this wipes the device, not just the token. A patient
                  // on a borrowed phone must be able to leave nothing behind,
                  // and must be able to do it from the first screen rather than
                  // having to find it inside an intake.
                  onPressed: () async {
                    await ref.read(authProvider).signOut();
                    ref
                      ..invalidate(signedInProvider)
                      ..invalidate(resumableDraftProvider)
                      ..invalidate(carryForwardProvider);
                  },
                  child: Text(strings.signOut),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// "Continue where you left off" — 2/3 §5, §15 item 7.
///
/// Offered only when there is something to resume that is still worth
/// resuming. A draft older than a week says so instead and offers nothing: the
/// answers in it have gone stale, and silently submitting week-old answers
/// about how long a pain has lasted would be worse than asking again.
class _ResumePrompt extends ConsumerWidget {
  const _ResumePrompt({required this.language});

  final String language;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final draft = ref.watch(resumableDraftProvider).valueOrNull;
    if (draft == null) return const SizedBox.shrink();

    if (DateTime.now().difference(draft.updatedAt) > draftMaxAge) {
      return Padding(
        padding: const EdgeInsets.only(bottom: Sizes.gap),
        child: Text(
          strings.draftTooOld,
          key: const Key('start.draftTooOld'),
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: OutlinedButton(
        key: const Key('start.resume'),
        onPressed: () => _resume(context, ref, draft),
        child: Text(strings.resumeDraft),
      ),
    );
  }

  Future<void> _resume(BuildContext context, WidgetRef ref, Draft draft) async {
    final bundle = ref.read(currentBundleProvider);
    if (bundle == null) return;
    final database = await ref.read(databaseProvider.future);
    final queue = await ref.read(submissionQueueProvider.future);
    final documents = await ref.read(documentStoreProvider.future);

    final flow = IntakeFlow.resume(
      database: database,
      queue: queue,
      documents: documents,
      bundle: bundle,
      draft: draft,
      appVersion: ref.read(configProvider).appVersion,
    );
    // Null when the content version moved under the draft. Starting a fresh
    // intake is the only safe answer: answers recorded against questions that
    // have since changed are answers to questions nobody can now read.
    if (flow == null || !context.mounted) return;
    ref.read(languageProvider.notifier).state = draft.language;
    await Navigator.of(context).push(intakeRoute(flow));
  }
}
