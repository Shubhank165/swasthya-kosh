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
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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

class _ListenButtonState extends ConsumerState<ListenButton> {
  _Phase _phase = _Phase.checking;

  @override
  void initState() {
    super.initState();
    _check();
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

  Future<void> _toggleListening() async {
    final t = ref.read(transcriberProvider);

    if (_phase == _Phase.listening) {
      setState(() => _phase = _Phase.recognising);
      final transcript = await t.stop();
      if (!mounted) return;
      setState(() => _phase = _Phase.ready);
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
    setState(() => _phase = _Phase.preparing);
    final started = await t.start(widget.language);
    if (!mounted) return;
    if (!started) {
      setState(() => _phase = _Phase.ready);
      _snack(Strings.of(context).voiceNoMic);
      return;
    }
    setState(() => _phase = _Phase.listening);
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
      case _Phase.unsupported:
        return const SizedBox.shrink();
      case _Phase.preparing:
      case _Phase.recognising:
        return Align(
          alignment: AlignmentDirectional.centerStart,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 12),
                Text(_phase == _Phase.preparing
                    ? strings.voicePreparing
                    : strings.voiceRecognising),
              ],
            ),
          ),
        );
      case _Phase.ready:
      case _Phase.listening:
        final listening = _phase == _Phase.listening;
        return Align(
          alignment: AlignmentDirectional.centerStart,
          child: TextButton.icon(
            key: const Key('question.listen'),
            onPressed: _toggleListening,
            icon: Icon(listening ? Icons.stop : Icons.mic),
            label: Text(listening ? strings.voiceListening : strings.voiceSpeak),
          ),
        );
    }
  }
}
