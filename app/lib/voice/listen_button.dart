/// The microphone control on a choice question — 2/3 §16.
///
/// Voice is an alternative to tapping, never the only way and never the pushed
/// one: the option tiles are still there and still the primary path. This
/// button is absent entirely when the device cannot do on-device recognition
/// for the chosen language — the same graceful absence as a missing read-aloud
/// voice. When a language's model has not been fetched yet it offers the
/// one-time download rather than silently doing nothing.
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

enum _Phase { checking, unsupported, needsModel, downloading, ready, listening }

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
  double _progress = 0;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final t = ref.read(transcriberProvider);
    final ready = await t.isReady(widget.language);
    if (!mounted) return;
    if (ready) {
      setState(() => _phase = _Phase.ready);
      return;
    }
    // Not ready: either the device cannot record at all, or the model is
    // missing. `requestPermission` tells the two apart.
    final canRecord = await t.requestPermission();
    if (!mounted) return;
    setState(() => _phase = canRecord ? _Phase.needsModel : _Phase.unsupported);
  }

  Future<void> _download() async {
    setState(() {
      _phase = _Phase.downloading;
      _progress = 0;
    });
    final ok = await ref.read(transcriberProvider).ensureModel(
          widget.language,
          onProgress: (f) {
            if (mounted) setState(() => _progress = f);
          },
        );
    if (!mounted) return;
    setState(() => _phase = ok ? _Phase.ready : _Phase.unsupported);
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
    setState(() => _phase = _Phase.listening);
    await t.start(widget.language);
  }

  @override
  Widget build(BuildContext context) {
    final strings = Strings.of(context);
    switch (_phase) {
      case _Phase.checking:
      case _Phase.unsupported:
        return const SizedBox.shrink();
      case _Phase.needsModel:
        return Align(
          alignment: AlignmentDirectional.centerStart,
          child: TextButton.icon(
            key: const Key('question.voiceDownload'),
            onPressed: _download,
            icon: const Icon(Icons.download),
            label: Text(strings.voiceDownload),
          ),
        );
      case _Phase.downloading:
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            children: [
              SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  value: _progress == 0 ? null : _progress,
                ),
              ),
              const SizedBox(width: 12),
              Text(strings.voiceDownloading),
            ],
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
