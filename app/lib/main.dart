/// MediKiosk patient app — 2/3.
///
/// Touch-first pre-consultation intake, now with optional voice that never
/// leaves the phone: read-aloud (`flutter_tts`) and speech input
/// (`sherpa_onnx`, model bundled in the APK) both run on the device, and
/// nothing spoken or heard is stored or sent — see DECISIONS §68 and
/// `test/on_device_voice_test.dart`.
library;

import 'package:flutter/material.dart';
import 'package:medikiosk_app/l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/providers.dart';
import 'core/theme.dart';
import 'home/root.dart';
import 'voice/transcribe.dart';

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
    // Adopt the remembered language before the first frame that needs it.
    // `languageProvider` is what every screen reads; `storedLanguageProvider`
    // is what survives a restart, and this is the one place they are joined.
    ref.listenManual(storedLanguageProvider, (_, next) {
      final stored = next.valueOrNull;
      if (stored != null) ref.read(languageProvider.notifier).state = stored;
    }, fireImmediately: true);
    // Same join for the read-aloud choice: on by default, but if the patient
    // turned it off on a previous run it stays off.
    ref.listenManual(storedReadAloudProvider, (_, next) {
      final stored = next.valueOrNull;
      if (stored != null) {
        ref.read(readAloudEnabledProvider.notifier).state = stored;
      }
    }, fireImmediately: true);
    // Copy the bundled speech model into app storage, off the first frame, so
    // the microphone on the first question is ready without a pause. No
    // network, no prompt; a failure just means voice input is unavailable.
    //
    // Once per language, not once per launch: each language has its own
    // checkpoint (English is Whisper, Hindi is IndicConformer — §76), the
    // patient picks the language after launch, and warming only the one the
    // app started in leaves the first Hindi question paying a 140 MB copy
    // while the patient is looking at it. `ensureInstalled` returns early when
    // the files are already there, so re-warming an already-warm language is
    // a stat call.
    ref.listenManual(languageProvider, (_, language) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(transcriberProvider).ensureModel(language);
      });
    }, fireImmediately: true);
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
      home: const Root(),
    );
  }
}
