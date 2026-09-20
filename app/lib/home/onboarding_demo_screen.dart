/// The first-run walkthrough — shown once, between Welcome and Language.
///
/// **This is not a video file.** There is no way to ship or maintain a
/// screen-recorded clip that stays honest about what the app actually looks
/// like — the UI changes, a recording does not, and a demo that has drifted
/// from the real screens is worse than none. So this storyboard is built from
/// the same widgets, icons, copy and colours as the real screens it depicts
/// (`ScreenIntro`, `ChoiceRow`, `IconChip`, `EmblemMark`, `BotSays`, the real
/// language list, the real department and complaint icons, the real button
/// labels) rather than inventing a separate look for it. It auto-advances
/// like a video would, over the same ten-to-fifteen seconds, and every frame
/// is decorative: nothing here is tappable as an answer, records anything, or
/// calls the network.
///
/// **Shown exactly once.** `OnboardingStore` remembers that on this device —
/// see its docstring for why that has to be a flag of its own rather than
/// piggybacking on "no language chosen yet" the way the Welcome screen does.
/// `welcome_screen.dart` is what checks it, since this screen sits between
/// Welcome (unchanged) and the real `LanguageScreen` (unchanged) rather than
/// in `Root`'s own dispatch.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../core/ui.dart';
import '../intake/screens/start_screen.dart';
import '../intake/widgets/interview_ui.dart';
import '../l10n/strings.dart';

class OnboardingDemoScreen extends ConsumerStatefulWidget {
  const OnboardingDemoScreen({super.key});

  @override
  ConsumerState<OnboardingDemoScreen> createState() =>
      _OnboardingDemoScreenState();
}

class _OnboardingDemoScreenState extends ConsumerState<OnboardingDemoScreen> {
  static const _frameCount = 7;

  /// Roughly two seconds a frame — seven frames is the 10-15s the demo was
  /// asked for, start to the moment it settles on the last one.
  static const _frameDuration = Duration(milliseconds: 2000);

  final _pageController = PageController();
  Timer? _timer;
  int _index = 0;

  @override
  void initState() {
    super.initState();
    _startAutoplay();
  }

  void _startAutoplay() {
    _timer?.cancel();
    _timer = Timer.periodic(_frameDuration, (_) {
      if (_index >= _frameCount - 1) {
        _timer?.cancel();
        return;
      }
      _pageController.nextPage(
        duration: const Duration(milliseconds: 380),
        curve: Curves.easeOutCubic,
      );
    });
  }

  void _replay() {
    setState(() => _index = 0);
    _pageController.jumpToPage(0);
    _startAutoplay();
  }

  Future<void> _finish() async {
    // Best-effort, like every other device preference here — a store that
    // failed to write must not trap the patient on the demo, it only means
    // they may see it again next time.
    await ref.read(onboardingStoreProvider).markSeen();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
      builder: (_) => const LanguageScreen(returnWhenChosen: true),
    ));
  }

  @override
  void dispose() {
    _timer?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);

    return Scaffold(
      body: Garnish(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  Sizes.gap,
                  Sizes.gap,
                  Sizes.gap,
                  0,
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      key: const Key('onboarding.skip'),
                      onPressed: _finish,
                      child: Text(strings.onboardingSkip),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: PageView(
                  controller: _pageController,
                  onPageChanged: (value) => setState(() => _index = value),
                  children: [
                    _WelcomeFrame(strings: strings),
                    _LanguageFrame(strings: strings),
                    _DepartmentFrame(strings: strings),
                    _SymptomsFrame(strings: strings),
                    _FollowUpFrame(strings: strings),
                    _UploadFrame(strings: strings),
                    _ReviewFrame(strings: strings),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: Sizes.gap),
                child: Semantics(
                  label: strings.onboardingStepIndicator(_index + 1, _frameCount),
                  child: ExcludeSemantics(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        for (var i = 0; i < _frameCount; i++)
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            margin: const EdgeInsets.symmetric(horizontal: 4),
                            width: i == _index ? 22 : 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: i == _index
                                  ? Theme.of(context).colorScheme.primary
                                  : Palette.tintStrong,
                              borderRadius: BorderRadius.circular(999),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  Sizes.gutter,
                  0,
                  Sizes.gutter,
                  Sizes.gutter,
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        key: const Key('onboarding.replay'),
                        onPressed: _replay,
                        child: Text(strings.onboardingReplay),
                      ),
                    ),
                    const SizedBox(width: Sizes.gap),
                    Expanded(
                      flex: 2,
                      child: FilledButton(
                        key: const Key('onboarding.getStarted'),
                        onPressed: _finish,
                        child: Text(strings.getStarted),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The shared shape every frame opens with: title, then body, in the app's own
/// headline style — nothing about this storyboard invents a different one.
class _Frame extends StatelessWidget {
  const _Frame({required this.title, required this.body, required this.child});

  final String title;
  final String body;
  final Widget child;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
        padding: const EdgeInsets.all(Sizes.gutter),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ScreenIntro(title: title, body: body, align: TextAlign.center),
            const SizedBox(height: Sizes.gutter * 1.2),
            child,
          ],
        ),
      );
}

class _WelcomeFrame extends StatelessWidget {
  const _WelcomeFrame({required this.strings});

  final Strings strings;

  @override
  Widget build(BuildContext context) => _Frame(
        title: strings.onboardingWelcomeTitle,
        body: strings.onboardingWelcomeBody,
        // The same leaf mark and app name the real Welcome screen opens with.
        child: Column(
          children: [
            const EmblemMark(icon: Icons.spa),
            const SizedBox(height: Sizes.gap),
            Text(strings.appTitle, style: Theme.of(context).textTheme.titleLarge),
          ],
        ),
      );
}

class _LanguageFrame extends StatelessWidget {
  const _LanguageFrame({required this.strings});

  final Strings strings;

  @override
  Widget build(BuildContext context) {
    // Three real endonyms from the real chooser (`start_screen.dart`), not a
    // separate invented list — the point of this screen is to show the actual
    // one. One is drawn ticked to show the real chooser's selected state.
    const shown = ['en', 'hi', 'ta'];
    return _Frame(
      title: strings.onboardingLanguageTitle,
      body: strings.onboardingLanguageBody,
      child: Column(
        children: [
          for (final code in shown) ...[
            ChoiceRow(
              title: languageNames[code]!,
              selected: code == 'hi',
              onTap: null,
            ),
            const SizedBox(height: Sizes.gap),
          ],
        ],
      ),
    );
  }
}

class _DepartmentFrame extends StatelessWidget {
  const _DepartmentFrame({required this.strings});

  final Strings strings;

  // The same pictures `hospital_screen.dart` uses for OPD, AYUSH, paediatrics
  // and cardiology — icons only, because the department names themselves are
  // hospital content this app does not own and a demo must not invent.
  static const _icons = [
    Icons.local_hospital_outlined,
    Icons.spa_outlined,
    Icons.child_care_outlined,
    Icons.monitor_heart_outlined,
  ];

  @override
  Widget build(BuildContext context) => _Frame(
        title: strings.onboardingDepartmentTitle,
        body: strings.onboardingDepartmentBody,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [for (final icon in _icons) IconChip(icon: icon, size: 56)],
        ),
      );
}

class _SymptomsFrame extends StatelessWidget {
  const _SymptomsFrame({required this.strings});

  final Strings strings;

  // The same three the real chief-complaint screen offers icons for.
  static const _icons = [
    Icons.favorite_outline,
    Icons.psychology_outlined,
    Icons.thermostat_outlined,
  ];

  @override
  Widget build(BuildContext context) => _Frame(
        title: strings.onboardingSymptomsTitle,
        body: strings.onboardingSymptomsBody,
        child: Column(
          children: [
            const _DemoMic(),
            const SizedBox(height: Sizes.gutter),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [for (final icon in _icons) IconChip(icon: icon)],
            ),
          ],
        ),
      );
}

class _FollowUpFrame extends StatelessWidget {
  const _FollowUpFrame({required this.strings});

  final Strings strings;

  @override
  Widget build(BuildContext context) => _Frame(
        title: strings.onboardingFollowUpTitle,
        body: strings.onboardingFollowUpBody,
        // The actual assistant bubble the interview opens with, word for word
        // — `BotSays` and `assistantIntro` are the real ones, not a mock-up.
        child: SoftCard(child: BotSays(text: strings.assistantIntro)),
      );
}

class _UploadFrame extends StatelessWidget {
  const _UploadFrame({required this.strings});

  final Strings strings;

  @override
  Widget build(BuildContext context) => _Frame(
        title: strings.onboardingUploadTitle,
        body: strings.onboardingUploadBody,
        // The same emblem and the same two actions `documents_screen.dart`
        // offers — take a photo, or choose one already on the phone.
        child: Column(
          children: [
            const EmblemMark(icon: Icons.document_scanner_outlined),
            const SizedBox(height: Sizes.gutter),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: const [
                IconChip(icon: Icons.photo_camera_outlined),
                IconChip(icon: Icons.photo_library_outlined),
              ],
            ),
          ],
        ),
      );
}

class _ReviewFrame extends StatelessWidget {
  const _ReviewFrame({required this.strings});

  final Strings strings;

  @override
  Widget build(BuildContext context) => _Frame(
        title: strings.onboardingReviewTitle,
        body: strings.onboardingReviewBody,
        child: Column(
          children: [
            SoftCard(
              child: Column(
                children: [
                  for (var i = 0; i < 3; i++) ...[
                    if (i > 0) const SizedBox(height: Sizes.gap),
                    Row(
                      children: [
                        Icon(Icons.check_circle,
                            color: Theme.of(context).colorScheme.primary),
                        const SizedBox(width: Sizes.gap),
                        Expanded(
                          child: Container(
                            height: 12,
                            decoration: BoxDecoration(
                              color: Palette.tint,
                              borderRadius: BorderRadius.circular(999),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: Sizes.gutter),
            // Disabled: nothing on this screen is a real submission, and a
            // patient must never be able to mistake it for one.
            FilledButton(
              onPressed: null,
              child: Text(strings.submitIntake),
            ),
          ],
        ),
      );
}

/// A still picture of the real microphone hero — see `voice/listen_button.dart`
/// for the widget this echoes. Not the real one: that is wired to on-device
/// speech recognition, and this screen must not touch a microphone or ask for
/// permission before a patient has even chosen a language.
class _DemoMic extends StatefulWidget {
  const _DemoMic();

  @override
  State<_DemoMic> createState() => _DemoMicState();
}

class _DemoMicState extends State<_DemoMic>
    with SingleTickerProviderStateMixin {
  // Plays once and stops — deliberately not `repeat()`. A demo screen a
  // patient sits in front of for a couple of seconds does not need a
  // microphone breathing forever, and an animation with no natural end is
  // also one a widget test can never settle past. `TweenSequence` rather than
  // `repeat(reverse: true)` is what gives "up, then back down" without ever
  // looping.
  late final _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..forward();

  late final _scale = TweenSequence<double>([
    TweenSequenceItem(
      tween: Tween(begin: 1.0, end: 1.08).chain(CurveTween(curve: Curves.easeOut)),
      weight: 1,
    ),
    TweenSequenceItem(
      tween: Tween(begin: 1.08, end: 1.0).chain(CurveTween(curve: Curves.easeIn)),
      weight: 1,
    ),
  ]).animate(_controller);

  // Matches `_Hero`'s own sizing in `listen_button.dart`, so a patient who
  // sees the real question screen a few taps later recognises it.
  static const _outer = 122.0;
  static const _inner = 92.0;
  static const _iconDisc = 54.0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return ScaleTransition(
      scale: _scale,
      child: SizedBox(
        width: _outer,
        height: _outer,
        child: Center(
          child: Container(
            width: _inner,
            height: _inner,
            decoration: const BoxDecoration(
              color: Palette.tint,
              shape: BoxShape.circle,
            ),
            child: Icon(
              Icons.mic_rounded,
              size: _iconDisc,
              color: colors.primary,
            ),
          ),
        ),
      ),
    );
  }
}
