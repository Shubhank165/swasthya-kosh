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
/// **Never invite voice input** (§1 rule 8, §16). If a patient taps the
/// microphone on their own keyboard, that audio goes to Google or Apple. We
/// cannot prevent it — but no element in this app suggests it, no field is
/// labelled "speak", and no free-text field is presented as the easy path.
library;

import 'package:flutter/material.dart';

import '../../content/answer.dart';
import '../../content/bundle.dart';
import '../../core/theme.dart';
import '../../l10n/strings.dart';

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
          onAnswered: onAnswered),
      AnswerType.multiChoice => MultiChoiceAnswer(
          key: resolved,
          question: question,
          language: language,
          onAnswered: onAnswered),
      AnswerType.yesNoUnknown =>
        YesNoAnswer(key: resolved, question: question, onAnswered: onAnswered),
      AnswerType.number =>
        NumberAnswer(key: resolved, question: question, onAnswered: onAnswered),
      AnswerType.scale =>
        ScaleAnswer(key: resolved, question: question, onAnswered: onAnswered),
      AnswerType.duration =>
        DurationAnswer(key: resolved, question: question, onAnswered: onAnswered),
      AnswerType.date =>
        DateAnswer(key: resolved, question: question, onAnswered: onAnswered),
      AnswerType.freeText =>
        FreeTextAnswer(key: resolved, question: question, onAnswered: onAnswered),
      AnswerType.unknown => null,
  };
}

/// A tappable option row.
///
/// A full-width card rather than a radio button: 48dp is the floor, and a
/// radio's hit area is the dot unless you are careful. The whole row is the
/// target.
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
        child: Material(
          color: selected ? scheme.secondaryContainer : scheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(
              color: selected ? scheme.primary : scheme.outlineVariant,
              width: selected ? 2 : 1,
            ),
          ),
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(12),
            child: Container(
              constraints: const BoxConstraints(minHeight: 56),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(
                children: [
                  if (icon != null) ...[
                    Icon(icon, size: 28),
                    const SizedBox(width: 14),
                  ],
                  Expanded(
                    child: Text(label, style: Theme.of(context).textTheme.bodyLarge),
                  ),
                  if (selected) Icon(Icons.check, color: scheme.primary),
                ],
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

class SingleChoiceAnswer extends StatelessWidget {
  const SingleChoiceAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;

  @override
  Widget build(BuildContext context) {
    final options = question.options ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final option in options)
          OptionTile(
            key: Key('option.$option'),
            label: labelFor(question, option, language),
            // The label recorded is the text the patient actually read (§9),
            // which is why it is the localised one and not the code.
            onTap: () => onAnswered(
                CodedValue(option), labelFor(question, option, language)),
          ),
      ],
    );
  }
}

class MultiChoiceAnswer extends StatefulWidget {
  const MultiChoiceAnswer({
    super.key,
    required this.question,
    required this.onAnswered,
    this.language = 'en',
  });

  final Question question;
  final String language;
  final OnAnswered onAnswered;

  @override
  State<MultiChoiceAnswer> createState() => _MultiChoiceAnswerState();
}

class _MultiChoiceAnswerState extends State<MultiChoiceAnswer> {
  final _chosen = <String>{};

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    final options = widget.question.options ?? const [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final option in options)
          OptionTile(
            key: Key('option.$option'),
            label: labelFor(widget.question, option, widget.language),
            selected: _chosen.contains(option),
            onTap: () => setState(() {
              if (!_chosen.remove(option)) _chosen.add(option);
            }),
          ),
        const SizedBox(height: Sizes.gap),
        FilledButton(
          key: const Key('answer.confirm'),
          // Disabled while nothing is chosen. An empty multi-select submitted
          // as an answer would record "none of these" — which is a clinical
          // claim the patient did not make. If they mean none, the content
          // offers a `none` option; if they cannot say, "I don't know" is there.
          onPressed: _chosen.isEmpty
              ? null
              : () {
                  final chosen = _chosen.toList()..sort();
                  widget.onAnswered(
                    CodedListValue(chosen),
                    chosen
                        .map((c) =>
                            labelFor(widget.question, c, widget.language))
                        .join(', '),
                  );
                },
          child: Text(strings.continueLabel),
        ),
      ],
    );
  }
}

class YesNoAnswer extends StatelessWidget {
  const YesNoAnswer({super.key, required this.question, required this.onAnswered});

  final Question question;
  final OnAnswered onAnswered;

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    // Only yes and no. The third arm of `yes_no_unknown` is the shared
    // "I don't know" affordance, which every question carries anyway —
    // rendering it twice would offer two buttons that record the same status
    // and invite the patient to wonder how they differ.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OptionTile(
          key: const Key('option.yes'),
          label: strings.optYes,
          onTap: () => onAnswered(const BoolValue(true), strings.optYes),
        ),
        OptionTile(
          key: const Key('option.no'),
          label: strings.optNo,
          onTap: () => onAnswered(const BoolValue(false), strings.optNo),
        ),
      ],
    );
  }
}

class NumberAnswer extends StatefulWidget {
  const NumberAnswer({super.key, required this.question, required this.onAnswered});

  final Question question;
  final OnAnswered onAnswered;

  @override
  State<NumberAnswer> createState() => _NumberAnswerState();
}

class _NumberAnswerState extends State<NumberAnswer> {
  final _controller = TextEditingController();

  /// The unit the answer will be recorded in. Starts as the question's default
  /// and changes only when the patient picks another, so an untouched question
  /// records exactly what it would have before.
  late String? _unit = widget.question.unit;

  /// The alternatives, or empty when the question offers no choice.
  ///
  /// A single-entry list is not a choice and does not draw one — the toggle
  /// appears only where the content author listed more than one unit.
  List<String> get _units {
    final units = widget.question.units ?? const [];
    return units.length > 1 ? units : const [];
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
        TextField(
          key: const Key('answer.number'),
          controller: _controller,
          // A numeric keypad, not a full keyboard: fewer keys, larger targets,
          // and no microphone key on most Android IMEs (§1 rule 8).
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          style: Theme.of(context).textTheme.bodyLarge,
          decoration: InputDecoration(suffixText: _unit),
          onChanged: (_) => setState(() {}),
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
              onTap: () => setState(() => _unit = unit),
            ),
        ],
        const SizedBox(height: Sizes.gap),
        FilledButton(
          key: const Key('answer.confirm'),
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
          child: Text(strings.continueLabel),
        ),
      ],
    );
  }

  double? get _value => double.tryParse(_controller.text.trim());
}

class ScaleAnswer extends StatefulWidget {
  const ScaleAnswer({super.key, required this.question, required this.onAnswered});

  final Question question;
  final OnAnswered onAnswered;

  @override
  State<ScaleAnswer> createState() => _ScaleAnswerState();
}

class _ScaleAnswerState extends State<ScaleAnswer> {
  @override
  Widget build(BuildContext context) {
    final min = (widget.question.minimum ?? 0).round();
    final max = (widget.question.maximum ?? 10).round();
    // Numbered buttons rather than a slider. A slider requires a drag, reports
    // a value the patient did not deliberately choose if they nudge it, and is
    // near-unusable with a screen reader or a tremor.
    return Wrap(
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
                minimumSize: const Size(Sizes.minTouchTarget, Sizes.minTouchTarget),
              ),
              child: Text('$value'),
            ),
          ),
      ],
    );
  }
}

class DurationAnswer extends StatefulWidget {
  const DurationAnswer({super.key, required this.question, required this.onAnswered});

  final Question question;
  final OnAnswered onAnswered;

  @override
  State<DurationAnswer> createState() => _DurationAnswerState();
}

class _DurationAnswerState extends State<DurationAnswer> {
  final _controller = TextEditingController();
  String _unit = 'day';

  /// The units the backend's `_duration_unit` recognises. Anything else would
  /// coerce to a plain quantity and lose the fact that it is a duration.
  static const _units = ['hour', 'day', 'week', 'month', 'year'];

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
        TextField(
          key: const Key('answer.duration_n'),
          controller: _controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: false),
          style: Theme.of(context).textTheme.bodyLarge,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: Sizes.gap),
        for (final unit in _units)
          OptionTile(
            key: Key('duration.$unit'),
            label: optionLabel(unit),
            selected: _unit == unit,
            onTap: () => setState(() => _unit = unit),
          ),
        const SizedBox(height: Sizes.gap),
        FilledButton(
          key: const Key('answer.confirm'),
          onPressed: n == null
              ? null
              : () => widget.onAnswered(
                    DurationValue(n: n, unit: _unit),
                    '${_controller.text.trim()} $_unit',
                  ),
          child: Text(strings.continueLabel),
        ),
      ],
    );
  }
}

class DateAnswer extends StatefulWidget {
  const DateAnswer({super.key, required this.question, required this.onAnswered});

  final Question question;
  final OnAnswered onAnswered;

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
        FilledButton(
          key: const Key('answer.confirm'),
          onPressed: _chosen == null
              ? null
              : () {
                  final iso = _chosen!.toIso8601String().split('T').first;
                  widget.onAnswered(DateValue(iso), iso);
                },
          child: Text(strings.continueLabel),
        ),
      ],
    );
  }
}

class FreeTextAnswer extends StatefulWidget {
  const FreeTextAnswer({super.key, required this.question, required this.onAnswered});

  final Question question;
  final OnAnswered onAnswered;

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

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          key: const Key('answer.free_text'),
          controller: _controller,
          maxLines: 4,
          style: Theme.of(context).textTheme.bodyLarge,
          // No hint text suggesting dictation, and no voice affordance of any
          // kind. §1 rule 8: if the patient taps their keyboard's microphone
          // that audio goes to Google or Apple, and while we cannot stop it,
          // nothing here invites it.
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: Sizes.gap),
        FilledButton(
          key: const Key('answer.confirm'),
          onPressed: _controller.text.trim().isEmpty
              ? null
              : () {
                  final text = _controller.text.trim();
                  widget.onAnswered(TextValue(text), text);
                },
          child: Text(strings.continueLabel),
        ),
      ],
    );
  }
}
