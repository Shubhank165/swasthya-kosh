/// The microphone control on a question — 2/3 §16.
///
/// Voice is an alternative to tapping, never the only way and never the pushed
/// one: the option tiles and the text box are still there and still the primary
/// path. This button is absent entirely when the device cannot do on-device
/// recognition for the chosen language — the same graceful absence as a missing
/// read-aloud voice. The model ships in the APK, so there is nothing to
/// download and no prompt until the patient actually taps to speak.
///
/// What it hands back is a [SpokenMatch]. On a choice question the matcher
/// resolves that to an option, "not sure", or nothing; on a descriptive
/// question the caller takes [SpokenMatch.heardLabel] as dictated text the
/// patient then edits. Recognition runs in a background isolate, so while it
/// works this button shows a spinner rather than freezing the screen.
///
/// **Why it is a pill and not a 96dp glowing orb.** A text button with a
/// 20dp icon was unrecognisable as a microphone to the patients this is for,
/// and it was the smallest target on the screen. A full-width primary mic —
/// the shape every voice assistant uses — fixes both and breaks §16: it makes
/// speaking look like the expected answer, and a patient who cannot pronounce a
/// symptom then feels they have failed the screen rather than chosen the other
/// path. So: unmistakably a microphone, comfortably above the 48dp floor,
/// tinted rather than filled, and never wider than the options above it.
///
/// **Listening is the one state that gets loud**, because that is the state a
/// patient must be able to see from arm's length and must be able to stop. The
/// rings only animate while the microphone is actually open, so the animation
/// is also the recording indicator.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme.dart';
import '../l10n/strings.dart';
import 'option_match.dart';
import 'transcribe.dart';

enum _Phase { checking, unsupported, ready, preparing, listening, recognising }

class ListenButton extends ConsumerStatefulWidget {
  const ListenButton({
    super.key,
    required this.language,
    required this.matcher,
    required this.onResult,
  });

  final String language;

  /// How a raw transcript becomes an intent: a choice question matches against
  /// its option labels, a yes/no question against a yes/no table, a descriptive
  /// question wraps the raw text as [SpokenIntent.option] with no code.
  final SpokenMatch Function(String transcript) matcher;

  final void Function(SpokenMatch match) onResult;

  @override
  ConsumerState<ListenButton> createState() => _ListenButtonState();
}

class _ListenButtonState extends ConsumerState<ListenButton>
    with SingleTickerProviderStateMixin {
  _Phase _phase = _Phase.checking;

  /// Drives the rings while the microphone is open, and only then. A repeating
  /// controller left running behind a question the patient is reading is a
  /// battery cost and a distraction, so it is stopped the moment listening
  /// ends.
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1600),
  );

  @override
  void initState() {
    super.initState();
    _check();
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  Future<void> _check() async {
    final t = ref.read(transcriberProvider);
    // Copy the bundled model to storage if this is the first run, then see
    // whether the device can record at all. Neither step prompts.
    await t.ensureModel(widget.language);
    final ready = await t.isReady(widget.language);
    if (!mounted) return;
    setState(() => _phase = ready ? _Phase.ready : _Phase.unsupported);
  }

  void _setPhase(_Phase phase) {
    setState(() => _phase = phase);
    if (phase == _Phase.listening) {
      _pulse.repeat();
    } else if (_pulse.isAnimating) {
      _pulse.stop();
      _pulse.value = 0;
    }
  }

  Future<void> _toggleListening() async {
    final t = ref.read(transcriberProvider);

    if (_phase == _Phase.listening) {
      _setPhase(_Phase.recognising);
      final transcript = await t.stop();
      if (!mounted) return;
      _setPhase(_Phase.ready);
      final match =
          transcript.trim().isEmpty ? SpokenMatch.none : widget.matcher(transcript);
      if (match.intent == SpokenIntent.none) {
        _snack(Strings.of(context).voiceNotCaught);
      } else {
        widget.onResult(match);
      }
      return;
    }

    if (_phase != _Phase.ready) return;

    // Build the recogniser isolate before opening the mic, so the first words
    // are not lost while the model loads. Only the first use of voice in a
    // session pays this.
    _setPhase(_Phase.preparing);
    final started = await t.start(widget.language);
    if (!mounted) return;
    if (!started) {
      _setPhase(_Phase.ready);
      _snack(Strings.of(context).voiceNoMic);
      return;
    }
    _setPhase(_Phase.listening);
  }

  void _snack(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    switch (_phase) {
      case _Phase.checking:
        // Holds the pill's height while the model check runs. Returning nothing
        // here and the control a frame later shifts every option below it
        // downwards just as the patient is reaching for one — and on a list
        // that sits near the fold, the whole page appears to jump.
        return const SizedBox(height: 60);
      case _Phase.unsupported:
        // Genuinely absent: the device cannot transcribe this language, and
        // reserving space for a control that will never appear leaves a hole.
        return const SizedBox.shrink();
      case _Phase.preparing:
      case _Phase.recognising:
        return _Pill(
          busy: true,
          label: _phase == _Phase.preparing
              ? strings.voicePreparing
              : strings.voiceRecognising,
          onTap: null,
        );
      case _Phase.ready:
      case _Phase.listening:
        final listening = _phase == _Phase.listening;
        return _Pill(
          listening: listening,
          pulse: listening ? _pulse : null,
          label: listening ? strings.voiceListening : strings.voiceSpeak,
          onTap: _toggleListening,
        );
    }
  }
}

/// The control itself: a microphone disc and a label, in a pill.
class _Pill extends StatelessWidget {
  const _Pill({
    required this.label,
    required this.onTap,
    this.listening = false,
    this.busy = false,
    this.pulse,
  });

  final String label;
  final VoidCallback? onTap;
  final bool listening;
  final bool busy;
  final Animation<double>? pulse;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final background = listening ? colors.primary : Palette.tint;
    final foreground = listening ? colors.onPrimary : colors.primary;

    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: Material(
        color: background,
        borderRadius: BorderRadius.circular(999),
        child: InkWell(
          key: const Key('question.listen'),
          onTap: onTap,
          borderRadius: BorderRadius.circular(999),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 20, 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 44,
                  height: 44,
                  child: busy
                      ? Center(
                          child: SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.5,
                              color: foreground,
                            ),
                          ),
                        )
                      : _MicDisc(
                          listening: listening,
                          pulse: pulse,
                          foreground: foreground,
                          background: listening ? colors.onPrimary : colors.primary,
                        ),
                ),
                const SizedBox(width: Sizes.gap),
                Text(
                  label,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: foreground,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// The disc, with rings that grow outwards while the microphone is open.
class _MicDisc extends StatelessWidget {
  const _MicDisc({
    required this.listening,
    required this.pulse,
    required this.foreground,
    required this.background,
  });

  final bool listening;
  final Animation<double>? pulse;
  final Color foreground;
  final Color background;

  @override
  Widget build(BuildContext context) {
    final disc = Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: listening ? background.withAlpha(48) : background.withAlpha(36),
      ),
      child: Icon(
        // Stop, not a second microphone: the control's job while listening is
        // to end the recording, and an icon that still says "microphone" is an
        // invitation to tap it again expecting something new.
        listening ? Icons.stop_rounded : Icons.mic_rounded,
        color: foreground,
        size: 24,
      ),
    );

    final animation = pulse;
    if (!listening || animation == null) return disc;

    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) => Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          for (final offset in const [0.0, 0.5])
            _Ring(
              progress: (animation.value + offset) % 1.0,
              color: background,
            ),
          child!,
        ],
      ),
      child: disc,
    );
  }
}

class _Ring extends StatelessWidget {
  const _Ring({required this.progress, required this.color});

  final double progress;
  final Color color;

  @override
  Widget build(BuildContext context) {
    // Fades as it grows, so two rings half a cycle apart read as one outward
    // motion rather than two circles.
    final size = 44 + (progress * 26);
    final alpha = ((1 - progress) * 90).round().clamp(0, 255);
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: color.withAlpha(alpha), width: 2),
        ),
      ),
    );
  }
}
