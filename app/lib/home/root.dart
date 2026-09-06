/// What the app shows, depending on how far the patient has got — stage 4.
///
/// Three states and one rule for each:
///
/// - **no language chosen** — the chooser, because nothing else on screen would
///   be readable;
/// - **not signed in** — the sign-in screen, because every tab below reads
///   records that belong to somebody;
/// - **signed in** — the home shell.
///
/// Deciding this here rather than inside a screen is what stopped the app being
/// an interview with a language question bolted to the front. Each screen now
/// does one thing and none of them decides what comes next.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../intake/screens/sign_in_screen.dart';
import '../intake/screens/start_screen.dart';
import 'home_shell.dart';

class Root extends ConsumerWidget {
  const Root({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final language = ref.watch(storedLanguageProvider);
    final signedIn = ref.watch(signedInProvider);

    // While either is still resolving. Both read the platform keystore, which
    // is fast but not instant, and flashing the language chooser at somebody
    // who chose months ago is worse than a moment of blank.
    if (language.isLoading || signedIn.isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    // `null`, not `'en'`. English is a real answer and treating the default as
    // "unanswered" would ask an English speaker on every launch — which is the
    // complaint that started this.
    if (language.valueOrNull == null) {
      return const LanguageScreen();
    }

    if (signedIn.valueOrNull != true) {
      return const SignInScreen();
    }

    return const HomeShell();
  }
}
