/// MediKiosk patient app — 2/3.
///
/// Touch-only pre-consultation intake. **There is no voice capture anywhere in
/// this app** (§1 rule 1): no microphone permission, no speech package, and no
/// UI element that invites dictation into a clinical field. That is not a
/// feature decision — it is what preserves the project's privacy claim, which
/// is that at the kiosk the patient's voice never leaves the device.
library;

import 'package:flutter/material.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/providers.dart';
import 'core/theme.dart';
import 'intake/screens/start_screen.dart';

void main() {
  runApp(const ProviderScope(child: MediKioskApp()));
}

class MediKioskApp extends ConsumerStatefulWidget {
  const MediKioskApp({super.key});

  @override
  ConsumerState<MediKioskApp> createState() => _MediKioskAppState();
}

class _MediKioskAppState extends ConsumerState<MediKioskApp> {
  @override
  void initState() {
    super.initState();
    // Drain the submission queue on launch — §9, §15 item 8.
    //
    // Unawaited and unannounced: an intake finished on a train goes out the
    // next time the app opens with signal, and the patient is not shown a
    // spinner for a record they already believe is sent. Failures leave the
    // payload exactly where it was.
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final queue = await ref.read(submissionQueueProvider.future);
      await queue.flush();
    });
  }

  @override
  Widget build(BuildContext context) {
    final language = ref.watch(languageProvider);
    return MaterialApp(
      title: 'MediKiosk',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      locale: Locale(language),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      // The OS text-scale setting is respected up to 200% (§14). Clamped at the
      // top so the "I don't know" affordance cannot be pushed off screen.
      builder: (context, child) => withClampedTextScale(context, child!),
      home: const StartScreen(),
    );
  }
}
