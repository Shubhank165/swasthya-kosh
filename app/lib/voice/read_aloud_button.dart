/// The speaker control beside a question — 2/3 §14.
///
/// Read-aloud is automatic: when a question opens, its prompt and options are
/// spoken without the patient touching anything, in the language they chose.
/// Tapping the control while it speaks silences *that one utterance* — the
/// next question still reads itself automatically, unaffected. Tapping it
/// again while silent replays the current question. Nothing here is
/// remembered between questions or between launches: every new question gets
/// its own fresh, unmuted automatic read, which is what "starts automatically,
/// but the patient can stop it" means for a screen that changes every few
/// seconds.
///
/// It renders nothing when the device has no voice for the chosen language, so
/// a patient is never offered — or played — audio in the wrong one.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../l10n/strings.dart';
import 'read_aloud.dart';

class ReadAloudButton extends ConsumerStatefulWidget {
  const ReadAloudButton({
    super.key,
    required this.utteranceKey,
    required this.text,
    required this.language,
  });

  /// Stable across rebuilds of the same question — the question id — so the
  /// shared engine can tell this utterance from any other, and so the automatic
  /// read fires once per question rather than on every rebuild.
  final String utteranceKey;
  final String text;
  final String language;

  @override
  ConsumerState<ReadAloudButton> createState() => _ReadAloudButtonState();
}

class _ReadAloudButtonState extends ConsumerState<ReadAloudButton> {
  late Future<bool> _available;

  /// Captured in [initState] because `ref` cannot be used from [dispose].
  /// `readAloudProvider` is a plain Provider and never rebuilds, so this stays
  /// valid for the life of the widget.
  late final ReadAloud _service;

  /// The question this button has already started reading, so a rebuild does
  /// not restart it and a manual stop is not immediately undone.
  String? _handled;

  /// True once the patient has silenced *this* question. Reset the moment a
  /// new question arrives — it is never carried forward, unlike the mute this
  /// control used to be.
  bool _mutedByPatient = false;

  @override
  void initState() {
    super.initState();
    _service = ref.read(readAloudProvider);
    _available = _service.canSpeak(widget.language);
    _scheduleAutoRead();
  }

  @override
  void dispose() {
    // Leaving the question flow — to the review screen, urgent care, or the
    // done screen. Whatever this button set talking must not carry on over the
    // next screen; the last question is the one where nothing else cuts it off.
    // Walking question-to-question keeps the same State and never reaches here.
    if (_service.speakingKey.value == widget.utteranceKey) {
      _service.stop();
    }
    super.dispose();
  }

  @override
  void didUpdateWidget(ReadAloudButton old) {
    super.didUpdateWidget(old);
    if (old.language != widget.language) {
      _available = ref.read(readAloudProvider).canSpeak(widget.language);
    }
    if (old.utteranceKey != widget.utteranceKey) {
      // Leaving the previous question for this one. Whatever it was saying
      // must not carry on over the new question — belt-and-braces alongside
      // `speak()`'s own stop-before-play, so a question with nothing to say
      // (or a device that briefly reports no voice available) still leaves
      // the old audio silenced rather than let it run on.
      _service.stop();
      // A fresh question always starts unmuted — silencing one question never
      // silences the next.
      setState(() => _mutedByPatient = false);
      _scheduleAutoRead();
    }
  }

  void _scheduleAutoRead() {
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeAutoRead());
  }

  Future<void> _maybeAutoRead() async {
    if (!mounted) return;
    if (widget.text.trim().isEmpty) return;
    if (_handled == widget.utteranceKey) return;
    if (!await _available) return;
    if (!mounted || _handled == widget.utteranceKey) return;
    _handled = widget.utteranceKey;
    await ref.read(readAloudProvider).speak(
          key: widget.utteranceKey,
          text: widget.text,
          language: widget.language,
        );
  }

  Future<void> _onTap() async {
    final service = ref.read(readAloudProvider);
    final speakingThis = service.speakingKey.value == widget.utteranceKey;
    if (speakingThis) {
      // Silence just this question. The next one is untouched by this — it
      // still reads itself the moment it appears.
      await service.stop();
      _handled = widget.utteranceKey;
      setState(() => _mutedByPatient = true);
      return;
    }
    // Not speaking: replay this question.
    _handled = widget.utteranceKey;
    setState(() => _mutedByPatient = false);
    await service.speak(
      key: widget.utteranceKey,
      text: widget.text,
      language: widget.language,
    );
  }

  @override
  Widget build(BuildContext context) {
    if (widget.text.trim().isEmpty) return const SizedBox.shrink();
    final strings = Strings.of(context);
    final service = ref.watch(readAloudProvider);

    return FutureBuilder<bool>(
      future: _available,
      builder: (context, snap) {
        if (snap.data != true) return const SizedBox.shrink();
        return ValueListenableBuilder<String?>(
          valueListenable: service.speakingKey,
          builder: (context, playing, _) {
            final isThis = playing == widget.utteranceKey;
            return TextButton.icon(
              key: const Key('question.readAloud'),
              onPressed: _onTap,
              icon: Icon(
                isThis
                    ? Icons.stop
                    : (_mutedByPatient ? Icons.volume_off : Icons.volume_up),
              ),
              label:
                  Text(isThis ? strings.stopListening : strings.listenToThis),
            );
          },
        );
      },
    );
  }
}
