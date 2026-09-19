/// The furniture of the interview screens — 2/3 §5, §14, §16.
///
/// Three small widgets that the question screens share. None of them decides
/// anything clinical; they are the frame the walker's content is shown in.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme.dart';
import '../../core/ui.dart';
import '../../l10n/strings.dart';
import '../../voice/read_aloud.dart';

/// The assistant's avatar with something it is saying beside it.
///
/// **A face, not a persona.** The mark is a round tinted chip with a simple
/// glyph, and the app never speaks in the first person about anything clinical
/// — it asks the questions the bundle gives it and says who the answers are
/// for. The avatar is there because a bare paragraph at the top of a form does
/// not read as a question addressed to *you*, and a patient who is being
/// interviewed answers more fully than one who is filling in a form.
///
/// It is explicitly **not** a chat bot: there is no reply box, no history, and
/// nothing it says is generated. Every word comes from the content bundle or
/// from the string table.
class BotSays extends StatelessWidget {
  const BotSays({
    super.key,
    required this.text,
    this.intro,
    this.note,
    this.trailing,
  });

  /// What is being said — the question prompt.
  final String text;

  /// A preamble above it, inside the same bubble. Used once, on the first
  /// question, to say what is about to happen and who reads the answers.
  ///
  /// In the bubble rather than in one of its own, because two avatars stacked
  /// down the first screen read as two speakers, and there is only one.
  final String? intro;

  /// A quieter second line under it, or null.
  final String? note;

  /// Sits under the text inside the bubble — the read-aloud control, on a
  /// question.
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Fixed size and never scaled with the text. At 200% scale a growing
        // avatar squeezes the words it belongs to, and the words are the part
        // that has to stay readable (§14).
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            color: Palette.tint,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(
            Icons.assistant_outlined,
            size: 22,
            color: colors.primary,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (intro != null) ...[
                Text(
                  intro!,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: colors.onSurfaceVariant,
                      ),
                ),
                const SizedBox(height: 10),
              ],
              // The question is the heading; the preamble above it is not, so
              // a patient navigating by headings lands on what they have to
              // answer rather than on the sentence introducing it.
              Semantics(
                header: true,
                child: Text(
                  text,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              if (note != null) ...[
                const SizedBox(height: 6),
                Text(
                  note!,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: colors.onSurfaceVariant,
                      ),
                ),
              ],
              if (trailing != null) ...[
                const SizedBox(height: 2),
                Align(alignment: AlignmentDirectional.centerStart, child: trailing!),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

/// What the recogniser understood, offered back before it is recorded.
///
/// **This card is the difference between a guess and a record.** It appears
/// only when the match was not confident enough to record outright, so its
/// presence is itself information: the app is telling the patient it is not
/// sure. Correct records the answer; Change discards it and leaves the patient
/// exactly where they were, with the options and the microphone both still
/// there.
///
/// The transcript is quoted and can be played back, for the patient who chose a
/// script they cannot read — for whom a written confirmation would be no
/// confirmation at all. The speaker is absent when the device has no voice for
/// their language, never substituted with another one.
class HeardCard extends ConsumerStatefulWidget {
  const HeardCard({
    super.key,
    required this.heard,
    required this.language,
    required this.onCorrect,
    required this.onChange,
  });

  final String heard;
  final String language;
  final VoidCallback onCorrect;
  final VoidCallback onChange;

  @override
  ConsumerState<HeardCard> createState() => _HeardCardState();
}

class _HeardCardState extends ConsumerState<HeardCard> {
  late Future<bool> _canSpeak =
      ref.read(readAloudProvider).canSpeak(widget.language);

  @override
  void didUpdateWidget(HeardCard old) {
    super.didUpdateWidget(old);
    if (old.language != widget.language) {
      _canSpeak = ref.read(readAloudProvider).canSpeak(widget.language);
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;

    return SoftCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            strings.heardTitle,
            style: text.bodySmall?.copyWith(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  // Quoted, so it reads as a report of what was said rather
                  // than as the app asserting it.
                  '"${widget.heard}"',
                  key: const Key('heard.text'),
                  style: text.titleMedium,
                ),
              ),
              FutureBuilder<bool>(
                future: _canSpeak,
                builder: (context, snapshot) {
                  if (snapshot.data != true) return const SizedBox.shrink();
                  return IconButton(
                    key: const Key('heard.play'),
                    tooltip: strings.listenToThis,
                    icon: const Icon(Icons.volume_up_outlined),
                    onPressed: () => ref.read(readAloudProvider).speak(
                          key: 'heard',
                          text: widget.heard,
                          language: widget.language,
                        ),
                  );
                },
              ),
            ],
          ),
          const SizedBox(height: Sizes.gap),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  key: const Key('heard.correct'),
                  onPressed: widget.onCorrect,
                  icon: const Icon(Icons.check_rounded, size: 20),
                  label: Text(strings.heardCorrect),
                ),
              ),
              const SizedBox(width: Sizes.gap),
              Expanded(
                child: OutlinedButton.icon(
                  key: const Key('heard.change'),
                  onPressed: widget.onChange,
                  icon: const Icon(Icons.edit_outlined, size: 20),
                  label: Text(strings.heardChange),
                ),
              ),
            ],
          ),
          const SizedBox(height: Sizes.gap),
          QuietNote(icon: Icons.lightbulb_outline, text: strings.heardHint),
        ],
      ),
    );
  }
}

/// A tinted aside — why a question is being asked, or what happens next.
///
/// Used for statements about the *app*, never about the patient: "this helps
/// your Vaidya understand how strong the symptom is" is a fact about the form,
/// while anything shaped like "this suggests…" would be the app interpreting
/// clinical content at a patient, which §8 forbids.
class QuietNote extends StatelessWidget {
  const QuietNote({super.key, required this.text, this.icon});

  final String text;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: Palette.tint,
        borderRadius: BorderRadius.circular(Sizes.radius),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon ?? Icons.info_outline, size: 18, color: colors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: colors.onSurfaceVariant,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The display name for a section id, or null when this app has none.
///
/// **Null is a supported answer, not a gap.** Section ids come from the content
/// bundle, so a clinician can add one tomorrow that this app has never heard
/// of. Falling back to the raw id would put `red_flag_screen` in front of a
/// patient; inventing a name from the id would put a guess there. The caller
/// shows the plain section count instead, which is always true (§4 — an older
/// app degrades, it does not break).
String? sectionDisplayName(Strings strings, String section) =>
    switch (section) {
      'presenting' => strings.sectionNamePresenting,
      'symptoms' => strings.sectionNameSymptoms,
      'history' => strings.sectionNameHistory,
      'ayurveda' => strings.sectionNameAyurveda,
      _ => null,
    };

/// Whether the microphone under this subtree draws as the large hero control.
///
/// An inherited flag rather than a parameter threaded through six answer
/// widgets: every one of them renders the same voice row, none of them cares
/// how big it is, and adding an argument to all six so that one screen can set
/// it once is how a widget tree acquires parameters nobody can later delete.
class ProminentVoice extends InheritedWidget {
  const ProminentVoice({
    super.key,
    required this.prominent,
    required super.child,
  });

  final bool prominent;

  /// False when there is no scope — the ordinary case, and the safe default:
  /// a screen nobody wrapped gets the quiet pill.
  static bool of(BuildContext context) =>
      context
          .dependOnInheritedWidgetOfExactType<ProminentVoice>()
          ?.prominent ??
      false;

  @override
  bool updateShouldNotify(ProminentVoice old) => old.prominent != prominent;
}

/// A soft fade with a chevron, pinned to the bottom of a scrollable question
/// screen while there is more of it below the fold.
///
/// **Why this exists.** The hero microphone is the biggest thing on a question
/// screen by design (§16 — voice leads, every question). On a two-option
/// question that leaves the second option sitting right at the bottom edge
/// with nothing visibly below it and no shadow, scrollbar, or affordance
/// hinting that dragging up would reveal more — a patient reads "two options"
/// as the whole question rather than as what happened to fit above the fold.
///
/// It is purely decorative: [IgnorePointer] always, so it never intercepts a
/// tap meant for the option tile underneath it, and it never gates Continue —
/// the pinned footer already tells the patient when nothing more is needed.
/// [visible] is computed by the caller from real scroll metrics rather than
/// guessed from content length, so it disappears the moment there is nothing
/// left to scroll to, on any device and any text scale.
class MoreBelowFade extends StatelessWidget {
  const MoreBelowFade({super.key, required this.visible});

  final bool visible;

  @override
  Widget build(BuildContext context) {
    final background = Theme.of(context).colorScheme.surface;
    final chevron = Theme.of(context).colorScheme.onSurfaceVariant;
    return IgnorePointer(
      child: AnimatedOpacity(
        opacity: visible ? 1 : 0,
        duration: const Duration(milliseconds: 180),
        child: Container(
          height: 40,
          alignment: Alignment.bottomCenter,
          padding: const EdgeInsets.only(bottom: 2),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [background.withAlpha(0), background],
            ),
          ),
          child: Icon(Icons.keyboard_arrow_down_rounded, color: chevron, size: 22),
        ),
      ),
    );
  }
}
