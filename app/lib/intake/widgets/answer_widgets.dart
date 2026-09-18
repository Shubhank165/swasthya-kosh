/// One renderer per `answer_type` — 2/3 §4, §14, §15 item 12.
///
/// Every widget here is a pure function of a [Question] and a callback. They
/// hold no clinical logic: which question is shown, whether it applies, and
/// whether an answer fires a red flag are all the walker's business (§16).
///
/// Two rules apply to all of them:
///
/// **Tap over type, everywhere** (§14). Typing Devanagari or Tamil on a phone
/// keyboard is genuinely painful, so free text appears only where the content
/// says nothing else will do.
///
/// **Voice input is on-device only** (§16, DECISIONS §68). The objection was
/// never speaking — it was that the *keyboard* microphone ships the audio to
/// Google or Apple. [ListenButton] runs an offline recogniser on the phone,
/// keeps nothing and sends nothing: on a choice question it matches the spoken
/// phrase to an option, and on a descriptive question it dictates into the text
/// box, where the patient edits it before it is recorded.
library;

import 'package:flutter/material.dart';

import '../../content/answer.dart';
import '../../content/bundle.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import '../../l10n/strings.dart';
import '../../voice/listen_button.dart';
import '../../voice/option_match.dart';

/// What a renderer hands back when the patient answers.
typedef OnAnswered = void Function(AnswerValue value, String originalText);

/// Builds the renderer for a question's answer type.
///
/// Returns `null` for [AnswerType.unknown]. The walker never offers such a
/// question, so this is defence in depth rather than a path the UI takes — but
/// returning `null` beats rendering an empty box the patient cannot get past.
Widget? buildAnswerWidget({
  required Question question,
  required OnAnswered onAnswered,
  String language = 'en',
  VoidCallback? onDontKnow,
  /// A value a prefill provider suggested for [question.fieldId], from
  /// something the patient already said in an earlier free-text answer — or
  /// `null`, the ordinary case. Never itself an answer: every renderer that
  /// accepts one only ever uses it to pre-fill or pre-highlight what it shows,
  /// and the patient still has to tap or press Continue for anything to be
  /// recorded, exactly as they would with no suggestion at all.
  AnswerValue? suggestion,
  Key? key,
}) {
  // **Keyed by question, always.** Flutter keeps a `State` object when the same
  // widget type appears in the same position on the next build, and every
  // question in the interview renders one answer widget in exactly the same
  // place. So walking from one free-text question to the next kept the previous
  // `TextEditingController` — the patient's answer to "what medicines do you
  // take" was sitting in the box when they were asked about allergies, ready to
  // be confirmed as their answer to that.
  //
  // Text was the visible half. A part-filled multi-select and a dragged pain
  // scale carried over the same way and were harder to notice.
  //
  // The key is the question id rather than the answer type: two consecutive
  // free-text questions are the case that broke, and they share a type.
  final resolved = key ?? ValueKey<String>(question.questionId);
  return switch (question.answerType) {
      AnswerType.singleChoice => SingleChoiceAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow,
          suggestion: suggestion),
      AnswerType.multiChoice => MultiChoiceAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow,
          suggestion: suggestion),
      AnswerType.yesNoUnknown => YesNoAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow,
          suggestion: suggestion),
      AnswerType.number => NumberAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow,
          suggestion: suggestion),
      AnswerType.scale => ScaleAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow,
          suggestion: suggestion),
      AnswerType.duration => DurationAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow,
          suggestion: suggestion),
      // Excluded from prefill by design — see `app/services/prefill.py`'s
      // `PENDING_TYPES`. A descriptive question is the source, not a target,
      // and none of the dates this interview asks for are ones a wrong guess
      // is safe to be wrong about.
      AnswerType.date => DateAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow),
      AnswerType.freeText => FreeTextAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered,
          onDontKnow: onDontKnow),
      AnswerType.unknown => null,
  };
}

/// A tappable option row.
///
/// A full-width card rather than a radio button: 48dp is the floor, and a
/// radio's hit area is the dot unless you are careful. The whole row is the
/// target.
/// A confirm button an answer widget wants shown in the screen's footer.
///
/// Compared by [label] and by whether it is enabled, never by the callback:
/// a closure is a new object on every build and equality on it would mean the
/// notifier fired every frame.
@immutable
class ConfirmAction {
  const ConfirmAction({required this.label, required this.onPressed});

  final String label;
  final VoidCallback? onPressed;

  bool get enabled => onPressed != null;

  @override
  bool operator ==(Object other) =>
      other is ConfirmAction && other.label == label && other.enabled == enabled;

  @override
  int get hashCode => Object.hash(label, enabled);
}

/// Lets an answer widget hand its confirm button to whatever is drawing the
/// footer.
///
/// **A screen that does not provide this keeps the old behaviour**, with the
/// button rendered inline where it always was. That fallback is the whole
/// safety of this mechanism: a screen someone forgets to wrap still shows a way
/// forward, rather than stranding a patient on a question with no button.
class AnswerConfirmScope extends InheritedWidget {
  const AnswerConfirmScope({
    super.key,
    required this.notifier,
    required super.child,
  });

  final ValueNotifier<ConfirmAction?> notifier;

  static ValueNotifier<ConfirmAction?>? of(BuildContext context) => context
      .dependOnInheritedWidgetOfExactType<AnswerConfirmScope>()
      ?.notifier;

  @override
  bool updateShouldNotify(AnswerConfirmScope oldWidget) =>
      oldWidget.notifier != notifier;
}

/// The "Continue" under an answer, wherever the screen wants it drawn.
///
/// Inside an [AnswerConfirmScope] it publishes itself and occupies no space;
/// outside one it is an ordinary button in the flow. The key goes on the real
/// button only, so exactly one widget carries it either way.
class ConfirmButton extends StatefulWidget {
  const ConfirmButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.buttonKey,
  });

  final String label;
  final VoidCallback? onPressed;
  final Key? buttonKey;

  @override
  State<ConfirmButton> createState() => _ConfirmButtonState();
}

class _ConfirmButtonState extends State<ConfirmButton> {
  ValueNotifier<ConfirmAction?>? _notifier;

  @override
  void dispose() {
    // Cleared after the frame: the screen above is being torn down too, and
    // writing to a notifier it is still listening to mid-teardown rebuilds a
    // widget that is on its way out.
    final notifier = _notifier;
    if (notifier != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => notifier.value = null);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final notifier = AnswerConfirmScope.of(context);
    _notifier = notifier;
    if (notifier == null) {
      return FilledButton(
        key: widget.buttonKey,
        onPressed: widget.onPressed,
        child: Text(widget.label),
      );
    }
    // Published after the frame, never during it: assigning here would mark the
    // footer dirty while this subtree is still building.
    final action = ConfirmAction(label: widget.label, onPressed: widget.onPressed);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) notifier.value = action;
    });
    return const SizedBox.shrink();
  }
}

/// The option code that means "none of the above, let me say it".
///
/// A convention, not a guess: the question bank writes `other` for exactly this
/// and nothing else uses the code. A question whose content never offers it
/// simply never shows the box.
const kOtherOptionCode = 'other';

/// What appears when the patient picks "Something else".
///
/// **The code stays `other`; the words become `original_text`.** That split is
/// Decision #3 — `original_text` travels with every fact, forever — and it is
/// what keeps this honest: the branching logic still sees an option it
/// understands, and the Vaidya still reads what the patient actually wrote.
/// Coercing the typed words into a coded value would be the app inventing a
/// clinical term nobody said.
///
/// Confirm is disabled until something is typed. "Something else" with an empty
/// box is not an answer, and recording one would claim the patient described
/// something when they described nothing — "I don't know" is the honest button
/// for that and it is right there.
class OtherEntry extends StatefulWidget {
  const OtherEntry({super.key, required this.onSubmitted, this.label});

  final void Function(String text) onSubmitted;
  final String? label;

  @override
  State<OtherEntry> createState() => _OtherEntryState();
}

class _OtherEntryState extends State<OtherEntry> {
  final _controller = TextEditingController();

  @override
  void initState() {
    super.initState();
    _controller.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final ready = _controller.text.trim().isNotEmpty;
    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            key: const Key('answer.other_text'),
            controller: _controller,
            autofocus: true,
            maxLines: 3,
            minLines: 1,
            textCapitalization: TextCapitalization.sentences,
            style: Theme.of(context).textTheme.bodyLarge,
            decoration: InputDecoration(
              labelText: widget.label ?? strings.somethingElse,
            ),
          ),
          const SizedBox(height: Sizes.gap),
          FilledButton(
            key: const Key('answer.other_confirm'),
            onPressed:
                ready ? () => widget.onSubmitted(_controller.text.trim()) : null,
            child: Text(strings.continueLabel),
          ),
        ],
      ),
    );
  }
}

class OptionTile extends StatelessWidget {
  const OptionTile({
    super.key,
    required this.label,
    required this.onTap,
    this.selected = false,
    this.icon,
  });

  final String label;
  final VoidCallback onTap;
  final bool selected;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: Padding(
        padding: const EdgeInsets.only(bottom: Sizes.gap),
        child: Container(
          // The shadow is dropped when selected: a chosen row is pressed *in*,
          // and a raised one that is also tinted reads as two states at once.
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(Sizes.radius),
            boxShadow: selected ? null : softShadow,
          ),
          child: Material(
            color: selected ? Palette.tint : Colors.white,
            borderRadius: BorderRadius.circular(Sizes.radius),
            child: InkWell(
              onTap: onTap,
              borderRadius: BorderRadius.circular(Sizes.radius),
              child: Container(
                constraints: const BoxConstraints(minHeight: 60),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(Sizes.radius),
                  border: Border.all(
                    color: selected ? scheme.primary : Colors.transparent,
                    width: 2,
                  ),
                ),
                child: Row(
                  children: [
                    if (icon != null) ...[
                      IconChip(
                        icon: icon!,
                        background: selected ? Colors.white : Palette.tint,
                      ),
                      const SizedBox(width: 14),
                    ],
                    Expanded(
                      child: Text(label, style: Theme.of(context).textTheme.bodyLarge),
                    ),
                    const SizedBox(width: 8),
                    // The indicator is always present, so the row does not
                    // change width on selection and the unchosen options say
                    // out loud that they are choosable.
                    Icon(
                      selected ? Icons.check_circle : Icons.circle_outlined,
                      color: selected ? scheme.primary : Palette.tintStrong,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Last-resort text for an option code.
///
/// De-underscored and sentence-cased, which produces English. Used only where
/// the content carries no label — units, and a bundle that predates option
/// text — and never in preference to one, because "At rest" under a Tamil
/// question is an answer the patient may not have understood, recorded as
/// though they had. The *code* is what is recorded either way.
String optionLabel(String code) {
  final words = code.replaceAll('_', ' ').trim();
  if (words.isEmpty) return code;
  return words[0].toUpperCase() + words.substring(1);
}

/// The label for an option, in the language the patient chose.
///
/// Prefers the content's own text — the questioning engine's bundle authors
/// every option in all nine languages beside the question it belongs to — and
/// falls back to [optionLabel] only when the bundle has none.
String labelFor(Question question, String code, String language) =>
    question.labelForOption(code, language) ?? optionLabel(code);

/// "Based on what you told us" — shown once, above whatever a suggestion
/// pre-filled or pre-highlighted.
///
/// A label, not a claim: it says where the pre-filled value came from and
/// nothing about whether it is right. The patient still has to tap an option
/// or press Continue for anything under it to be recorded, the same as if
/// this badge were not there at all.
class SuggestionBadge extends StatelessWidget {
  const SuggestionBadge({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: Sizes.gap),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.auto_awesome, size: 16, color: scheme.primary),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              Strings.of(context).suggestedAnswer,
              style: Theme.of(context)
                  .textTheme
                  .labelMedium
                  ?.copyWith(color: scheme.primary),
            ),
          ),
        ],
      ),
    );
  }
}

class SingleChoiceAnswer extends StatefulWidget {
  const SingleChoiceAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
    this.suggestion,
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;
  final VoidCallback? onDontKnow;

  /// A suggested option code, or `null`. Only ever a highlight here — tapping
  /// is still what records an answer (§14's "tap *is* the bound value"), so a
  /// suggestion for a tap-to-answer question is shown, never auto-applied.
  final AnswerValue? suggestion;

  @override
  State<SingleChoiceAnswer> createState() => _SingleChoiceAnswerState();
}

class _SingleChoiceAnswerState extends State<SingleChoiceAnswer> {
  /// True once "Something else" has been tapped and the box is open.
  ///
  /// Nothing is recorded at that moment: picking the option is the patient
  /// saying "not one of these", and the answer is what they then write.
  bool _writingOther = false;

  @override
  Widget build(BuildContext context) {
    final question = widget.question;
    final language = widget.language;
    final options = question.options ?? const [];
    final suggested = widget.suggestion;
    final suggestedCode =
        suggested is CodedValue && options.contains(suggested.code) ? suggested.code : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (suggestedCode != null) const SuggestionBadge(),
        _VoiceRow(
          language: language,
          matcher: (t) => matchOption(
            transcript: t,
            optionCodes: options,
            labelFor: (c) => question.labelForOption(c, language),
            language: language,
          ),
          onMatch: (m) =>
              widget.onAnswered(CodedValue(m.optionCode ?? ''), m.heardLabel ?? ''),
          onDontKnow: widget.onDontKnow,
        ),
        for (final option in options) ...[
          OptionTile(
            key: Key('option.$option'),
            label: labelFor(question, option, language),
            selected: option == kOtherOptionCode
                ? _writingOther
                : option == suggestedCode,
            // The label recorded is the text the patient actually read (§9),
            // which is why it is the localised one and not the code.
            onTap: option == kOtherOptionCode
                ? () => setState(() => _writingOther = true)
                : () => widget.onAnswered(
                    CodedValue(option), labelFor(question, option, language)),
          ),
          if (option == kOtherOptionCode && _writingOther)
            OtherEntry(
              label: labelFor(question, option, language),
              onSubmitted: (written) =>
                  widget.onAnswered(const CodedValue(kOtherOptionCode), written),
            ),
        ],
      ],
    );
  }
}

/// The [ListenButton] plus the glue that turns a [SpokenMatch] into the same
/// callbacks a tap would fire. Renders nothing at all when voice is
/// unavailable, so a choice question looks exactly as it did before.
class _VoiceRow extends StatelessWidget {
  const _VoiceRow({
    required this.language,
    required this.matcher,
    required this.onMatch,
    this.onDontKnow,
  });

  final String language;
  final SpokenMatch Function(String transcript) matcher;

  /// Called with the whole match rather than a code and a label: a numeric
  /// question needs the number and the unit, which no pair of strings carries.
  final void Function(SpokenMatch match) onMatch;
  final VoidCallback? onDontKnow;

  @override
  Widget build(BuildContext context) => ListenButton(
        language: language,
        matcher: matcher,
        onResult: (match) {
          switch (match.intent) {
            case SpokenIntent.option:
              onMatch(match);
            case SpokenIntent.dontKnow:
              onDontKnow?.call();
            case SpokenIntent.none:
              break;
          }
        },
      );
}

class MultiChoiceAnswer extends StatefulWidget {
  const MultiChoiceAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
    this.suggestion,
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;
  final VoidCallback? onDontKnow;

  /// A suggested set of options, or `null`. Pre-checked, never pre-submitted —
  /// the Continue button below is what records an answer, same as it always
  /// was, so accepting a suggestion here takes exactly the action accepting
  /// nothing would have.
  final AnswerValue? suggestion;

  @override
  State<MultiChoiceAnswer> createState() => _MultiChoiceAnswerState();
}

class _MultiChoiceAnswerState extends State<MultiChoiceAnswer> {
  final _chosen = <String>{};

  /// What the patient wrote beside "Something else", or null.
  ///
  /// Not held in `_chosen`: the codes there are the question's own vocabulary
  /// and free text is not one of them. It rides out as part of the recorded
  /// `original_text` instead — Decision #3.
  String? _otherText;

  /// True once the patient has touched a voice match or a tile. A suggestion
  /// that arrives after that point must not silently rewrite their own
  /// selection.
  bool _touchedByPatient = false;

  @override
  void initState() {
    super.initState();
    _applySuggestion(widget.suggestion);
  }

  @override
  void didUpdateWidget(MultiChoiceAnswer oldWidget) {
    super.didUpdateWidget(oldWidget);
    // The ordinary timing for a suggestion to arrive: the request goes out the
    // moment the prior free-text answer is recorded, and this screen may
    // already be showing by the time it comes back.
    if (!_touchedByPatient && oldWidget.suggestion != widget.suggestion) {
      setState(() => _applySuggestion(widget.suggestion));
    }
  }

  void _applySuggestion(AnswerValue? suggestion) {
    final options = widget.question.options ?? const [];
    final codes = switch (suggestion) {
      CodedListValue(:final codes) => codes,
      _ => const <String>[],
    };
    final valid = codes.where(options.contains).toSet();
    if (valid.isEmpty) return;
    _chosen
      ..clear()
      ..addAll(valid);
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final options = widget.question.options ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_chosen.isNotEmpty && !_touchedByPatient) const SuggestionBadge(),
        _VoiceRow(
          language: widget.language,
          matcher: (t) => matchOption(
            transcript: t,
            optionCodes: options,
            labelFor: (c) => widget.question.labelForOption(c, widget.language),
            language: widget.language,
          ),
          // Voice toggles one option at a time, exactly like a tap. The patient
          // still presses Continue when they have named everything.
          onMatch: (m) => setState(() {
            _touchedByPatient = true;
            final code = m.optionCode ?? '';
            if (!_chosen.remove(code)) _chosen.add(code);
          }),
          onDontKnow: widget.onDontKnow,
        ),
        for (final option in options) ...[
          OptionTile(
            key: Key('option.$option'),
            label: labelFor(widget.question, option, widget.language),
            selected: _chosen.contains(option),
            onTap: () => setState(() {
              _touchedByPatient = true;
              if (!_chosen.remove(option)) {
                _chosen.add(option);
              } else if (option == kOtherOptionCode) {
                // Unticking "Something else" throws away what was written with
                // it. Keeping the text after the option is gone would submit a
                // description the patient has just withdrawn.
                _otherText = null;
              }
            }),
          ),
          // Multi-select already has a Continue at the bottom, so this box has
          // no button of its own: what is typed is held and travels with the
          // rest of the selection when the patient confirms the lot.
          if (option == kOtherOptionCode && _chosen.contains(option))
            Padding(
              padding: const EdgeInsets.only(bottom: Sizes.gap),
              child: TextField(
                key: const Key('answer.other_text'),
                autofocus: true,
                maxLines: 3,
                minLines: 1,
                textCapitalization: TextCapitalization.sentences,
                style: Theme.of(context).textTheme.bodyLarge,
                decoration: InputDecoration(
                  labelText: labelFor(widget.question, option, widget.language),
                ),
                onChanged: (value) => _otherText = value.trim(),
              ),
            ),
        ],
        const SizedBox(height: Sizes.gap),
        ConfirmButton(
          buttonKey: const Key('answer.confirm'),
          label: strings.continueLabel,
          // Disabled while nothing is chosen. An empty multi-select submitted
          // as an answer would record "none of these" — which is a clinical
          // claim the patient did not make. If they mean none, the content
          // offers a `none` option; if they cannot say, "I don't know" is there.
          onPressed: _chosen.isEmpty
              ? null
              : () {
                  final chosen = _chosen.toList()..sort();
                  // The patient's own words replace the word "Something else"
                  // in the recorded text, and only there — the code list is
                  // untouched, so nothing downstream sees a term the question
                  // bank does not define.
                  final written = _otherText;
                  final labels = chosen.map((c) {
                    final label = labelFor(widget.question, c, widget.language);
                    return c == kOtherOptionCode &&
                            written != null &&
                            written.isNotEmpty
                        ? written
                        : label;
                  });
                  widget.onAnswered(
                    CodedListValue(chosen),
                    labels.join(', '),
                  );
                },
        ),
      ],
    );
  }
}

class YesNoAnswer extends StatelessWidget {
  const YesNoAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
    this.suggestion,
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;
  final VoidCallback? onDontKnow;

  /// A suggested yes/no, or `null`. A highlight only — tapping is still what
  /// records an answer, same as [SingleChoiceAnswer].
  final AnswerValue? suggestion;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final suggested = suggestion;
    final suggestedBool = suggested is BoolValue ? suggested.value : null;
    // Only yes and no. The third arm of `yes_no_unknown` is the shared
    // "I don't know" affordance, which every question carries anyway —
    // rendering it twice would offer two buttons that record the same status
    // and invite the patient to wonder how they differ.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (suggestedBool != null) const SuggestionBadge(),
        _VoiceRow(
          language: language,
          matcher: (t) => matchYesNo(transcript: t, language: language),
          onMatch: (m) => onAnswered(
            BoolValue(m.optionCode == 'yes'),
            m.optionCode == 'yes' ? strings.optYes : strings.optNo,
          ),
          onDontKnow: onDontKnow,
        ),
        OptionTile(
          key: const Key('option.yes'),
          label: strings.optYes,
          selected: suggestedBool == true,
          onTap: () => onAnswered(const BoolValue(true), strings.optYes),
        ),
        OptionTile(
          key: const Key('option.no'),
          label: strings.optNo,
          selected: suggestedBool == false,
          onTap: () => onAnswered(const BoolValue(false), strings.optNo),
        ),
      ],
    );
  }
}

class NumberAnswer extends StatefulWidget {
  const NumberAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
    this.suggestion,
  });

  final Question question;
  final OnAnswered onAnswered;
  final String language;
  final VoidCallback? onDontKnow;

  /// A suggested figure, or `null`. Pre-fills the box; the patient still edits
  /// or clears it like any other value and still presses Continue to record
  /// anything — the same bargain a misheard voice figure already makes.
  final AnswerValue? suggestion;

  @override
  State<NumberAnswer> createState() => _NumberAnswerState();
}

class _NumberAnswerState extends State<NumberAnswer> {
  final _controller = TextEditingController();

  /// The unit the answer will be recorded in. Starts as the question's default
  /// and changes only when the patient picks another, so an untouched question
  /// records exactly what it would have before.
  late String? _unit = widget.question.unit;

  /// True once the patient has changed the figure, the unit, or spoken one.
  /// A suggestion that arrives after that point must not overwrite it.
  bool _touchedByPatient = false;

  /// The alternatives, or empty when the question offers no choice.
  ///
  /// A single-entry list is not a choice and does not draw one — the toggle
  /// appears only where the content author listed more than one unit.
  List<String> get _units {
    final units = widget.question.units ?? const [];
    return units.length > 1 ? units : const [];
  }

  @override
  void initState() {
    super.initState();
    _applySuggestion(widget.suggestion);
  }

  @override
  void didUpdateWidget(NumberAnswer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!_touchedByPatient && oldWidget.suggestion != widget.suggestion) {
      setState(() => _applySuggestion(widget.suggestion));
    }
  }

  void _applySuggestion(AnswerValue? suggestion) {
    if (suggestion is! NumberValue) return;
    final n = suggestion.value;
    _controller.text = n == n.roundToDouble() ? n.round().toString() : n.toString();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.suggestion is NumberValue && !_touchedByPatient)
          const SuggestionBadge(),
        // Voice fills the box; it does not answer the question. The patient
        // reads the figure back and presses Continue, which is what makes a
        // misheard vital sign recoverable — the same bargain free text makes.
        _VoiceRow(
          language: widget.language,
          matcher: (t) => matchNumber(
            transcript: t,
            language: widget.language,
            minimum: widget.question.minimum,
            maximum: widget.question.maximum,
            units: widget.question.units ?? const [],
          ),
          onMatch: (m) => setState(() {
            _touchedByPatient = true;
            final n = m.number!;
            _controller.text = n == n.roundToDouble()
                ? n.round().toString()
                : n.toString();
            if (m.unit != null) _unit = m.unit;
          }),
          onDontKnow: widget.onDontKnow,
        ),
        TextField(
          key: const Key('answer.number'),
          controller: _controller,
          // A numeric keypad, not a full keyboard: fewer keys, larger targets,
          // and no microphone key on most Android IMEs (§1 rule 8).
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          style: Theme.of(context).textTheme.bodyLarge,
          decoration: InputDecoration(suffixText: _unit),
          onChanged: (_) => setState(() => _touchedByPatient = true),
        ),
        if (_units.isNotEmpty) ...[
          const SizedBox(height: Sizes.gap),
          for (final unit in _units)
            OptionTile(
              key: Key('unit.$unit'),
              label: optionLabel(unit),
              selected: _unit == unit,
              // Only the label changes. The number the patient typed is left
              // exactly as typed and nothing is converted — 38.5 °C does not
              // silently become 101.3 °F, and the record carries whichever
              // unit was chosen alongside the figure.
              onTap: () => setState(() {
                _touchedByPatient = true;
                _unit = unit;
              }),
            ),
        ],
        const SizedBox(height: Sizes.gap),
        ConfirmButton(
          buttonKey: const Key('answer.confirm'),
          label: strings.continueLabel,
          onPressed: _value == null
              ? null
              : () => widget.onAnswered(
                    NumberValue(_value!, unit: _unit),
                    // The unit travels in the patient's own words too, so a
                    // physician reading `original_text` sees "101 fahrenheit"
                    // rather than a bare number whose unit lives elsewhere.
                    _unit == null
                        ? _controller.text.trim()
                        : '${_controller.text.trim()} $_unit',
                  ),
        ),
      ],
    );
  }

  double? get _value => double.tryParse(_controller.text.trim());
}

class ScaleAnswer extends StatefulWidget {
  const ScaleAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
    this.suggestion,
  });

  final Question question;
  final OnAnswered onAnswered;
  final String language;
  final VoidCallback? onDontKnow;

  /// A suggested score, or `null`. A highlight only, like [SingleChoiceAnswer]
  /// — one of these buttons is what records an answer, exactly as before.
  final AnswerValue? suggestion;

  @override
  State<ScaleAnswer> createState() => _ScaleAnswerState();
}

class _ScaleAnswerState extends State<ScaleAnswer> {
  @override
  Widget build(BuildContext context) {
    final min = (widget.question.minimum ?? 0).round();
    final max = (widget.question.maximum ?? 10).round();
    final suggested = widget.suggestion;
    final suggestedValue = suggested is ScaleValue ? suggested.value.round() : null;
    final scheme = Theme.of(context).colorScheme;
    // Numbered buttons rather than a slider. A slider requires a drag, reports
    // a value the patient did not deliberately choose if they nudge it, and is
    // near-unusable with a screen reader or a tremor.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (suggestedValue != null && suggestedValue >= min && suggestedValue <= max)
          const SuggestionBadge(),
        // A spoken score answers outright, unlike the free-figure questions:
        // the scale is bounded and whole, so "six" either lands on a button
        // that is on screen or is not a match at all.
        _VoiceRow(
          language: widget.language,
          matcher: (t) => matchNumber(
            transcript: t,
            language: widget.language,
            minimum: min.toDouble(),
            maximum: max.toDouble(),
          ),
          onMatch: (m) {
            final value = m.number!.roundToDouble();
            widget.onAnswered(ScaleValue(value), '${value.round()}');
          },
          onDontKnow: widget.onDontKnow,
        ),
        const SizedBox(height: Sizes.gap),
        Wrap(
          spacing: Sizes.gap,
          runSpacing: Sizes.gap,
          children: [
            for (var value = min; value <= max; value++)
              SizedBox(
                width: 56,
                height: 56,
                child: OutlinedButton(
                  key: Key('scale.$value'),
                  onPressed: () => widget.onAnswered(
                    ScaleValue(value.toDouble()),
                    '$value',
                  ),
                  style: OutlinedButton.styleFrom(
                    padding: EdgeInsets.zero,
                    minimumSize:
                        const Size(Sizes.minTouchTarget, Sizes.minTouchTarget),
                    side: BorderSide(
                      color: value == suggestedValue ? scheme.primary : scheme.outlineVariant,
                      width: value == suggestedValue ? 2 : 1,
                    ),
                  ),
                  child: Text('$value'),
                ),
              ),
          ],
        ),
      ],
    );
  }
}

class DurationAnswer extends StatefulWidget {
  const DurationAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
    this.suggestion,
  });

  final Question question;
  final OnAnswered onAnswered;
  final String language;
  final VoidCallback? onDontKnow;

  /// A suggested figure and unit, or `null`. Pre-fills both; the patient still
  /// edits either and still presses Continue, exactly as a voice match already
  /// requires.
  final AnswerValue? suggestion;

  @override
  State<DurationAnswer> createState() => _DurationAnswerState();
}

class _DurationAnswerState extends State<DurationAnswer> {
  final _controller = TextEditingController();
  String _unit = 'day';

  /// True once the patient has changed the figure, the unit, or spoken one.
  bool _touchedByPatient = false;

  /// The units the backend's `_duration_unit` recognises. Anything else would
  /// coerce to a plain quantity and lose the fact that it is a duration.
  static const _units = ['hour', 'day', 'week', 'month', 'year'];

  @override
  void initState() {
    super.initState();
    _applySuggestion(widget.suggestion);
  }

  @override
  void didUpdateWidget(DurationAnswer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!_touchedByPatient && oldWidget.suggestion != widget.suggestion) {
      setState(() => _applySuggestion(widget.suggestion));
    }
  }

  void _applySuggestion(AnswerValue? suggestion) {
    if (suggestion is! DurationValue || !_units.contains(suggestion.unit)) return;
    _controller.text = suggestion.n.round().toString();
    _unit = suggestion.unit;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final n = double.tryParse(_controller.text.trim());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (widget.suggestion is DurationValue && !_touchedByPatient)
          const SuggestionBadge(),
        // "three days" sets both halves. A number with no unit is not a
        // duration, so `matchDuration` returns nothing rather than filling the
        // figure and leaving whichever unit happened to be selected standing
        // beside it.
        _VoiceRow(
          language: widget.language,
          matcher: (t) => matchDuration(
            transcript: t,
            language: widget.language,
            units: _units,
          ),
          onMatch: (m) => setState(() {
            _touchedByPatient = true;
            _controller.text = m.number!.round().toString();
            _unit = m.unit!;
          }),
          onDontKnow: widget.onDontKnow,
        ),
        TextField(
          key: const Key('answer.duration_n'),
          controller: _controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: false),
          style: Theme.of(context).textTheme.bodyLarge,
          onChanged: (_) => setState(() => _touchedByPatient = true),
        ),
        const SizedBox(height: Sizes.gap),
        for (final unit in _units)
          OptionTile(
            key: Key('duration.$unit'),
            label: optionLabel(unit),
            selected: _unit == unit,
            onTap: () => setState(() {
              _touchedByPatient = true;
              _unit = unit;
            }),
          ),
        const SizedBox(height: Sizes.gap),
        ConfirmButton(
          buttonKey: const Key('answer.confirm'),
          label: strings.continueLabel,
          onPressed: n == null
              ? null
              : () => widget.onAnswered(
                    DurationValue(n: n, unit: _unit),
                    '${_controller.text.trim()} $_unit',
                  ),
        ),
      ],
    );
  }
}

class DateAnswer extends StatefulWidget {
  const DateAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
  });

  final Question question;
  final OnAnswered onAnswered;

  /// Taken like every other widget's, and not yet used to offer a mic: a spoken
  /// date has to resolve "last Tuesday", "around Diwali" and "2nd of Jan" to a
  /// calendar day, and the ones this interview asks for — when a surgery was,
  /// when a period started — are the ones a wrong answer misleads on most.
  /// The picker stays the only way in until that parser is worth trusting.
  final String language;
  final VoidCallback? onDontKnow;

  @override
  State<DateAnswer> createState() => _DateAnswerState();
}

class _DateAnswerState extends State<DateAnswer> {
  DateTime? _chosen;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final now = DateTime.now();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton(
          key: const Key('answer.date_picker'),
          onPressed: () async {
            final picked = await showDatePicker(
              context: context,
              firstDate: DateTime(now.year - 100),
              lastDate: now,
              initialDate: _chosen ?? now,
            );
            if (picked != null) setState(() => _chosen = picked);
          },
          child: Text(_chosen == null
              ? strings.continueLabel
              : _chosen!.toIso8601String().split('T').first),
        ),
        const SizedBox(height: Sizes.gap),
        ConfirmButton(
          buttonKey: const Key('answer.confirm'),
          label: strings.continueLabel,
          onPressed: _chosen == null
              ? null
              : () {
                  final iso = _chosen!.toIso8601String().split('T').first;
                  widget.onAnswered(DateValue(iso), iso);
                },
        ),
      ],
    );
  }
}

class FreeTextAnswer extends StatefulWidget {
  const FreeTextAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
    this.onDontKnow,
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;
  final VoidCallback? onDontKnow;

  @override
  State<FreeTextAnswer> createState() => _FreeTextAnswerState();
}

class _FreeTextAnswerState extends State<FreeTextAnswer> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// Dictated words land in the box, appended to whatever is already there, for
  /// the patient to read and fix. They are not recorded until Continue — the
  /// edit is the safety step that a spoken option match does not have.
  void _dictated(String text) {
    if (text.trim().isEmpty) return;
    final existing = _controller.text.trimRight();
    final joined = existing.isEmpty ? text.trim() : '$existing ${text.trim()}';
    setState(() {
      _controller.text = joined;
      _controller.selection =
          TextSelection.collapsed(offset: _controller.text.length);
    });
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // On-device dictation — the recogniser runs on the phone and keeps
        // nothing (§16). This is the one place free text is the answer rather
        // than a fallback, so it is also the one place voice helps most; the
        // patient still edits what comes back before it counts.
        _VoiceRow(
          language: widget.language,
          matcher: (t) => matchDictation(transcript: t, language: widget.language),
          onMatch: (m) => _dictated(m.heardLabel ?? ''),
          onDontKnow: widget.onDontKnow,
        ),
        TextField(
          key: const Key('answer.free_text'),
          controller: _controller,
          maxLines: 4,
          style: Theme.of(context).textTheme.bodyLarge,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: Sizes.gap),
        ConfirmButton(
          buttonKey: const Key('answer.confirm'),
          label: strings.continueLabel,
          onPressed: _controller.text.trim().isEmpty
              ? null
              : () {
                  final text = _controller.text.trim();
                  widget.onAnswered(TextValue(text), text);
                },
        ),
      ],
    );
  }
}
