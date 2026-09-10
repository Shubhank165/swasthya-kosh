/// The microphone control on a choice question — 2/3 §16.
///
/// Voice is an alternative to tapping, never the only way and never the pushed
/// one: the option tiles are still there and still the primary path. This
/// button is absent entirely when the device cannot do on-device recognition
/// for the chosen language — the same graceful absence as a missing read-aloud
/// voice. The model ships in the APK, so there is nothing to download and no
/// prompt until the patient actually taps to speak.
///
/// What it hands back is a [SpokenMatch]: a specific option, "I'm not sure", or
/// nothing caught. It never guesses — a phrase that does not clearly land on an
/// option leaves the screen exactly as it was, with a quiet "didn't catch that".
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../l10n/strings.dart';
import 'option_match.dart';
import 'transcribe.dart';

enum _Phase { checking, unsupported, ready, listening }

class ListenButton extends ConsumerStatefulWidget {
  const ListenButton({
    super.key,
    required this.language,
    required this.matcher,
    required this.onResult,
  });

  final String language;

  /// How a raw transcript becomes an intent: a choice question matches against
  /// its option labels, a yes/no question against a yes/no table.
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
      setState(() => _phase = _Phase.ready);
      final transcript = await t.stop();
      if (!mounted) return;
      final match =
          transcript.trim().isEmpty ? SpokenMatch.none : widget.matcher(transcript);
      if (match.intent == SpokenIntent.none) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(Strings.of(context).voiceNotCaught)));
      } else {
        widget.onResult(match);
      }
      return;
    }
    // First tap asks for the microphone. A refusal leaves the button in place
    // — the patient can still tap the options — and says why once.
    setState(() => _phase = _Phase.listening);
    final started = await t.start(widget.language);
    if (!mounted) return;
    if (!started) {
      setState(() => _phase = _Phase.ready);
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(
            SnackBar(content: Text(Strings.of(context).voiceNoMic)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    switch (_phase) {
      case _Phase.checking:
      case _Phase.unsupported:
        return const SizedBox.shrink();
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
