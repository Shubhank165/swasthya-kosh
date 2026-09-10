/// The speaker control beside a question — 2/3 §14.
///
/// Read-aloud is automatic: when a question opens, its prompt and options are
/// spoken without the patient touching anything, in the language they chose.
/// This control is then a **mute toggle** — tap it while it is speaking (or any
/// time after) to silence it and stop the next question reading itself; tap it
/// again to turn the automatic reading back on and replay the current question.
///
/// It renders nothing when the device has no voice for the chosen language, so
/// a patient is never offered — or played — audio in the wrong one. The choice
/// is remembered between launches via [readAloudEnabledProvider].
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
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

  /// The question this button has already started reading, so a rebuild does
  /// not restart it and a mute is not immediately undone.
  String? _handled;

  @override
  void initState() {
    super.initState();
    _available = ref.read(readAloudProvider).canSpeak(widget.language);
    _scheduleAutoRead();
  }

  @override
  void didUpdateWidget(ReadAloudButton old) {
    super.didUpdateWidget(old);
    if (old.language != widget.language) {
      _available = ref.read(readAloudProvider).canSpeak(widget.language);
    }
    if (old.utteranceKey != widget.utteranceKey) {
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
    if (!ref.read(readAloudEnabledProvider)) return;
    if (!await _available) return;
    if (!mounted || _handled == widget.utteranceKey) return;
    _handled = widget.utteranceKey;
    await ref.read(readAloudProvider).speak(
          key: widget.utteranceKey,
          text: widget.text,
          language: widget.language,
        );
  }

  void _setEnabled(bool value) {
    ref.read(readAloudEnabledProvider.notifier).state = value;
    ref.read(readAloudPrefStoreProvider).write(value);
  }

  Future<void> _onTap() async {
    final service = ref.read(readAloudProvider);
    final speakingThis = service.speakingKey.value == widget.utteranceKey;
    if (speakingThis) {
      // Silence it and keep it silenced — the next question will not read
      // itself until the patient turns this back on.
      await service.stop();
      _handled = widget.utteranceKey;
      _setEnabled(false);
      return;
    }
    // Not speaking: (re)start this question and resume automatic reading.
    if (!ref.read(readAloudEnabledProvider)) _setEnabled(true);
    _handled = widget.utteranceKey;
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
    final enabled = ref.watch(readAloudEnabledProvider);

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
                    : (enabled ? Icons.volume_up : Icons.volume_off),
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
