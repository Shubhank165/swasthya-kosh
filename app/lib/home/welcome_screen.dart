/// The first thing a new patient sees — stage 5.
///
/// The app used to open on the nine-language chooser, which is correct and
/// still where this screen sends you. What it was missing is the sentence
/// before it: a patient handed a phone in an OPD queue was asked to pick a
/// script before being told what they were about to do or why their answers
/// were being collected.
///
/// **It is shown exactly once**, on the run where no language has been stored
/// yet — see `home/root.dart`. There is no separate "seen the welcome" flag,
/// because choosing a language is the thing that makes this screen redundant
/// and the stored language already records it.
///
/// **The language problem this screen creates, and how it is handled.**
/// Anything shown before the chooser is shown in a language the patient has not
/// picked. `languageProvider` takes its initial value from the phone's own
/// locale when that is one of the nine, so a phone set to Tamil opens on Tamil
/// here. That is a guess and is treated as one: it is never written to
/// `LanguageStore`, the chooser still appears, and nothing clinical is on this
/// screen. The worst case is a patient reading an English sentence and pressing
/// the one large button, which is where the chooser is.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../intake/screens/start_screen.dart';
import '../l10n/strings.dart';
import 'onboarding_demo_screen.dart';

class WelcomeScreen extends ConsumerWidget {
  const WelcomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;

    return Scaffold(
      body: Garnish(
        dense: true,
        child: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) => SingleChildScrollView(
              // Centred when it fits, scrollable when it does not. At 200% text
              // scale on a small phone this content is taller than the screen,
              // and a `Column` with a `Spacer` overflows rather than scrolling.
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: Padding(
                  padding: const EdgeInsets.all(Sizes.gutter),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: Sizes.gap),
                      // The wordmark: a leaf, the name, and one line under it.
                      // Drawn rather than an asset, like everything else on
                      // this screen — see `_WelcomeArt`.
                      Center(
                        child: Column(
                          children: [
                            ExcludeSemantics(
                              child: Icon(
                                Icons.spa,
                                size: 42,
                                color: colors.primary,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              strings.appTitle,
                              style: Theme.of(context)
                                  .textTheme
                                  .titleLarge
                                  ?.copyWith(color: colors.primary),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              strings.appTagline,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: colors.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: Sizes.gutter),
                      const Center(child: _WelcomeArt()),
                      const SizedBox(height: Sizes.gutter * 1.4),
                      ScreenIntro(
                        title: strings.welcomeHeadline,
                        body: strings.welcomeBody,
                        align: TextAlign.center,
                      ),
                      const SizedBox(height: Sizes.gutter * 1.2),
                      // The three things the app does, as icons with one short
                      // label each. A patient who reads none of the paragraph
                      // above still gets the shape of what is coming.
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _Affordance(
                            icon: Icons.record_voice_over_outlined,
                            label: strings.welcomeStepTalk,
                          ),
                          _Affordance(
                            icon: Icons.photo_camera_outlined,
                            label: strings.welcomeStepRecords,
                          ),
                          _Affordance(
                            icon: Icons.local_hospital_outlined,
                            label: strings.welcomeStepVisit,
                          ),
                        ],
                      ),
                      const SizedBox(height: Sizes.gutter * 1.4),
                      FilledButton.icon(
                        key: const Key('welcome.start'),
                        onPressed: () => _onGetStarted(context, ref),
                        icon: const Icon(Icons.arrow_forward),
                        iconAlignment: IconAlignment.end,
                        label: Text(strings.getStarted),
                      ),
                      const SizedBox(height: Sizes.gutter),
                      PrivacyNote(text: strings.dataProtected),
                      const SizedBox(height: Sizes.gap),
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

/// Where the "Get started" tap goes: the first-run demo once, ever, on this
/// device — see `OnboardingStore` — and the real language chooser every time
/// after that. Neither screen is told about the other; this is the one place
/// that decides between them, so the two can never disagree about which a
/// given launch should show.
Future<void> _onGetStarted(BuildContext context, WidgetRef ref) async {
  final seen = await ref.read(onboardingSeenProvider.future);
  if (!context.mounted) return;
  Navigator.of(context).push(MaterialPageRoute<void>(
    // `returnWhenChosen`, because `Root` swaps what is underneath this route
    // the moment a language is stored. Without the pop the patient would be
    // left looking at the chooser they had just answered.
    builder: (_) => seen
        ? const LanguageScreen(returnWhenChosen: true)
        : const OnboardingDemoScreen(),
  ));
}

/// The illustration.
///
/// A flat drawing of somebody using the app, sitting on a background that is
/// within two parts in 255 of [Palette.surface] — which is why it needs no
/// transparency and shows no seam. Purely decorative, so it is excluded from
/// semantics entirely: there is nothing here a screen reader should describe.
///
/// **It fails to a blank box, never to an exception.** An asset that did not
/// make it into the bundle must not take down the first screen a patient ever
/// sees, and a missing picture on a welcome screen costs nothing that matters.
class _WelcomeArt extends StatelessWidget {
  const _WelcomeArt();

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
        child: Image.asset(
          'assets/illustrations/welcome.png',
          height: 190,
          fit: BoxFit.contain,
          // The source is a crop from the design sheet and is being scaled up,
          // so a smoother filter earns its cost here.
          filterQuality: FilterQuality.medium,
          errorBuilder: (_, __, ___) => const SizedBox(height: 190),
        ),
      );
}

class _Affordance extends StatelessWidget {
  const _Affordance({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(
          children: [
            IconChip(icon: icon, size: 54),
            const SizedBox(height: 8),
            Text(
              label,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      );
}
