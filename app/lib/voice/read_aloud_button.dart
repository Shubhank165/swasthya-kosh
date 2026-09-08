/// The speaker control beside a question — 2/3 §14.
///
/// Renders nothing when the device has no voice for the chosen language, so a
/// patient is never offered audio that would come out in the wrong one. While
/// its own utterance is playing it becomes a stop button; another read-aloud
/// button starting elsewhere flips this one back on its own, because they share
/// one engine keyed by utterance.
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
  /// shared engine can tell this utterance from any other.
  final String utteranceKey;
  final String text;
  final String language;

  @override
  ConsumerState<ReadAloudButton> createState() => _ReadAloudButtonState();
}

class _ReadAloudButtonState extends ConsumerState<ReadAloudButton> {
  late Future<bool> _available;

  @override
  void initState() {
    super.initState();
    _available = ref.read(readAloudProvider).canSpeak(widget.language);
  }

  @override
  void didUpdateWidget(ReadAloudButton old) {
    super.didUpdateWidget(old);
    if (old.language != widget.language) {
      _available = ref.read(readAloudProvider).canSpeak(widget.language);
    }
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
              onPressed: () => service.toggle(
                key: widget.utteranceKey,
                text: widget.text,
                language: widget.language,
              ),
              icon: Icon(isThis ? Icons.stop : Icons.volume_up),
              label: Text(isThis ? strings.stopListening : strings.listenToThis),
            );
          },
        );
      },
    );
  }
}
