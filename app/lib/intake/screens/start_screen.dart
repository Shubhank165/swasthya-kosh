/// The language chooser — 2/3 §5 screen 1, and stage 4.
///
/// Language comes first, before anything else is shown. A patient who cannot
/// read the sign-in screen cannot sign in, and the nine-language chooser is the
/// one thing that must be legible without reading.
///
/// **It is now shown once, not on every launch.** It used to be the app's home
/// screen and carried the continue button, the resume prompt, the update notice
/// and sign-out with it — so a patient who had already answered "English" three
/// times was asked a fourth. The choice is remembered (`LanguageStore`) and this
/// screen appears on a first run, or when the patient opens it from their
/// profile to change the answer.
///
/// Everything else that used to live here now lives on the home screen.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme.dart';
import '../../l10n/strings.dart';

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

class LanguageScreen extends ConsumerWidget {
  const LanguageScreen({super.key, this.returnWhenChosen = false});

  /// True when opened from the profile, where choosing means "go back".
  ///
  /// False on a first run, where there is nothing to go back to — the app
  /// itself is waiting on the answer, and popping would leave a black screen.
  final bool returnWhenChosen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final selected = ref.watch(languageProvider);

    return Scaffold(
      appBar: returnWhenChosen ? AppBar(title: Text(strings.profileLanguage)) : null,
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
                  onPressed: () => _choose(context, ref, entry.key),
                  style: OutlinedButton.styleFrom(
                    backgroundColor: selected == entry.key
                        ? Theme.of(context).colorScheme.secondaryContainer
                        : null,
                  ),
                  child: Text(entry.value),
                ),
              ),
          ],
        ),
      ),
    );
  }

  /// Tapping a language *is* the answer.
  ///
  /// There was a Continue button under this list, and it did nothing a second
  /// tap on the language could not: nine buttons followed by a tenth to confirm
  /// which of the nine you meant.
  Future<void> _choose(BuildContext context, WidgetRef ref, String code) async {
    ref.read(languageProvider.notifier).state = code;
    await ref.read(languageStoreProvider).write(code);
    ref.invalidate(storedLanguageProvider);
    if (returnWhenChosen && context.mounted) Navigator.of(context).pop();
  }
}
