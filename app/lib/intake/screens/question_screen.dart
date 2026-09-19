/// One question per screen — 2/3 §5, §14.
///
/// "One question per screen throughout the interview — this is an accessibility
/// requirement, not a style choice." A form with twelve fields is unusable at
/// 200% text scale, unreadable to a screen reader in any sensible order, and
/// invites a patient to answer the easy ones and leave the rest blank, which
/// produces `not_asked` where the honest answer was available.
///
/// **Progress is a bar, not a title.** `Section 3 of 8` sitting where an app bar
/// title goes was read as the screen's name. The same sentence sits under a
/// filled track instead, which is the shape a patient recognises as "how much is
/// left" without reading it. Sections, never a percentage: answering "chest
/// pain" adds twenty questions, and a percentage would go backwards.
///
/// **Continue is pinned.** On a multi-select with a dozen options it used to sit
/// past the last one, so a patient who had ticked the first two had to scroll
/// the whole list to find out how to proceed — and nothing on the way down told
/// them their ticks had survived. The button now lives in a fixed footer and
/// carries the count with it. The answer widgets do not know about the footer:
/// they hand their button to [AnswerConfirmScope], and a screen that does not
/// provide one still gets the button inline exactly as before.
///
/// **"I don't know" and Skip stay in the scroll, deliberately.** §4 requires
/// them to look unlike each other and unlike a confirm; putting all three in one
/// fixed row would make them a set of three equal buttons, which is the shape
/// that gets the wrong one pressed.
library;

import 'package:flutter/material.dart';

import '../../content/answer.dart';
import '../../content/bundle.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import '../../l10n/strings.dart';
import '../../voice/read_aloud.dart';
import '../../voice/read_aloud_button.dart';
import '../widgets/answer_actions.dart';
import '../widgets/answer_widgets.dart';
import '../widgets/interview_ui.dart';

class QuestionScreen extends StatefulWidget {
  const QuestionScreen({
    super.key,
    required this.question,
    required this.language,
    required this.onAnswered,
    required this.onDontKnow,
    required this.onSkip,
    required this.sectionsDone,
    required this.sectionsTotal,
    this.progress,
    this.stepLabel,
    this.onBack,
    this.suggestion,
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;
  final VoidCallback onDontKnow;
  final VoidCallback onSkip;
  final int sectionsDone;
  final int sectionsTotal;

  /// How full the bar is, 0–1 — the walker's question-level estimate, which
  /// moves on every answer instead of once a section. Null falls back to
  /// `sectionsDone / sectionsTotal`, which is what the screen did before and is
  /// still correct, just lumpy.
  final double? progress;

  /// The already-localised label under the bar — "Health history · 3/8".
  ///
  /// Localised by the caller rather than built here, because turning a section
  /// *id* into a name a patient reads is a content decision and this screen
  /// should not be the place that knows the ids. Null falls back to the plain
  /// section count, which is always available and always true.
  final String? stepLabel;

  /// `null` on the first question. **Back is available everywhere else** (§5) —
  /// a patient who mistapped must be able to correct it without abandoning the
  /// intake.
  final VoidCallback? onBack;

  /// A value [IntakeFlow] suggested for this question's field, from something
  /// the patient already said in an earlier free-text answer — or `null`, the
  /// ordinary case. See `buildAnswerWidget`.
  final AnswerValue? suggestion;

  @override
  State<QuestionScreen> createState() => _QuestionScreenState();
}

class _QuestionScreenState extends State<QuestionScreen> {
  final _confirm = ValueNotifier<ConfirmAction?>(null);
  final _scroll = ScrollController();

  /// Whether the scroll view has more below the fold — see [MoreBelowFade].
  /// Read from real scroll metrics, never guessed from how many options a
  /// question happens to carry, so it is right on every screen size and text
  /// scale without this widget needing to know either.
  final _moreBelow = ValueNotifier<bool>(false);

  @override
  void initState() {
    super.initState();
    // Covers a live drag: the controller's own listener fires every frame the
    // position changes, which is smoother than waiting for a notification to
    // bubble.
    _scroll.addListener(() => _updateMoreBelow(_scroll.position));
  }

  @override
  void didUpdateWidget(QuestionScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A new question arrives in the same screen. Its answer widget publishes
    // after the next frame; until then the footer must not still be offering
    // the previous question's Continue.
    if (oldWidget.question.questionId != widget.question.questionId) {
      _confirm.value = null;
      // The next question can be shorter or longer than this one — a
      // yes/no question replacing a seven-option list must not keep
      // yesterday's fade showing over a screen that already fits.
      WidgetsBinding.instance
          .addPostFrameCallback((_) => _updateMoreBelow(_scroll.position));
    }
  }

  void _updateMoreBelow(ScrollMetrics metrics) {
    if (!metrics.hasContentDimensions) return;
    final remaining = metrics.maxScrollExtent - metrics.pixels;
    // A few logical pixels of slack so the chevron does not flicker at rest
    // right at the very end of the list.
    final visible = remaining > 12;
    if (visible != _moreBelow.value) _moreBelow.value = visible;
  }

  @override
  void dispose() {
    _confirm.dispose();
    _scroll.dispose();
    _moreBelow.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final question = widget.question;
    final language = widget.language;
    final prompt = question.promptFor(language);
    final spoken = spokenTextForQuestion(
      prompt: prompt,
      optionLabels: [
        for (final code in question.options ?? const <String>[])
          question.labelForOption(code, language) ?? '',
      ],
    );

    return AnswerConfirmScope(
      notifier: _confirm,
      child: Scaffold(
        appBar: AppBar(
          leading: widget.onBack == null
              ? null
              : IconButton(
                  key: const Key('question.back'),
                  icon: const Icon(Icons.arrow_back),
                  tooltip: strings.backLabel,
                  onPressed: widget.onBack,
                ),
          // The bar carries navigation only. Progress moved into the body,
          // where it has room for a track and is not mistaken for a title.
          title: const SizedBox.shrink(),
        ),
        bottomNavigationBar: ValueListenableBuilder<ConfirmAction?>(
          valueListenable: _confirm,
          builder: (context, action, _) {
            // Nothing to confirm on a tap-to-answer question: the tap *is* the
            // answer, and an empty footer bar would be a permanent grey band
            // under two thirds of the interview.
            if (action == null) return const SizedBox.shrink();
            return DecoratedBox(
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
                    key: const Key('answer.confirm'),
                    onPressed: action.onPressed,
                    child: Text(action.label),
                  ),
                ),
              ),
            );
          },
        ),
        body: SafeArea(
          child: Stack(
            children: [
              // Catches everything a live drag does not: the list growing or
              // shrinking (a new question, "Other" opening a text field, a
              // suggestion badge appearing), the keyboard resizing the
              // viewport, and the very first frame, before anything has been
              // dragged at all.
              NotificationListener<ScrollMetricsNotification>(
                onNotification: (notification) {
                  _updateMoreBelow(notification.metrics);
                  return false;
                },
                child: SingleChildScrollView(
                  controller: _scroll,
                  padding: const EdgeInsets.fromLTRB(
                    Sizes.gutter,
                    0,
                    Sizes.gutter,
                    Sizes.gutter,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      StepProgress(
                        label: widget.stepLabel ??
                            strings.sectionProgress(
                              widget.sectionsDone,
                              widget.sectionsTotal,
                            ),
                        done: widget.sectionsDone,
                        total: widget.sectionsTotal,
                        value: widget.progress,
                        // The plan grows when the chief complaint picks a
                        // branch. Whatever the arithmetic says, the bar does
                        // not retreat.
                        monotonic: true,
                      ),
                      const SizedBox(height: Sizes.gap + 4),
                      BotSays(
                        // The greeting now lives on its own screen, shown
                        // once before the first question ever reaches here
                        // (see `IntakeGreetingScreen`) — every question this
                        // screen renders, first or not, is nothing but the
                        // question.
                        //
                        // Should be unreachable: the walker never offers a
                        // question with no prompt in the chosen language.
                        // Rendering the field id rather than an English
                        // fallback keeps the invariant visible if it ever
                        // breaks — a patient must never be shown a clinical
                        // question in a language they did not choose.
                        text: prompt ?? question.fieldId,
                        // Read-aloud for the patient who chose a script they
                        // cannot read. Absent when the device has no voice for
                        // that language — never spoken in another one.
                        trailing: ReadAloudButton(
                          utteranceKey: question.questionId,
                          text: spoken,
                          language: language,
                        ),
                      ),
                      const SizedBox(height: Sizes.gap),
                      // Prominent on every question, not only the first —
                      // voice is now the interaction this screen leads with
                      // everywhere, and the options underneath remain the
                      // fallback (§16 is now: never the *only* way, not
                      // "never the lead" — every option tile is still
                      // tappable on every question).
                      ProminentVoice(
                        prominent: true,
                        child: buildAnswerWidget(
                              question: question,
                              language: language,
                              onAnswered: widget.onAnswered,
                              onDontKnow: widget.onDontKnow,
                              suggestion: widget.suggestion,
                            ) ??
                            const SizedBox.shrink(),
                      ),
                      const SizedBox(height: Sizes.gap + 4),
                      const Divider(),
                      const SizedBox(height: Sizes.gap + 4),
                      AnswerActions(
                        allowUnknown: question.allowUnknown,
                        allowSkip: question.allowSkip,
                        onDontKnow: widget.onDontKnow,
                        onSkip: widget.onSkip,
                      ),
                    ],
                  ),
                ),
              ),
              // Fixed to the bottom of the *viewport*, not the scroll content
              // — it has to stay put while the list underneath it moves. See
              // [MoreBelowFade] for why this exists at all.
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: ValueListenableBuilder<bool>(
                  valueListenable: _moreBelow,
                  builder: (context, visible, _) =>
                      MoreBelowFade(visible: visible),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
