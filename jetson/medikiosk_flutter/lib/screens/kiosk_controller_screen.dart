import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_service.dart';
import '../services/audio_service.dart';
import '../services/camera_service.dart';
import '../services/discovery.dart';
import '../services/kiosk_client.dart';
import '../l10n.dart';
import '../theme/app_theme.dart';
import 'language_screen.dart';
import 'pathway_hub_screen.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'dart:io';

class KioskControllerScreen extends StatefulWidget {
  const KioskControllerScreen({super.key});
  @override
  State<KioskControllerScreen> createState() => _KioskControllerScreenState();
}

class _KioskControllerScreenState extends State<KioskControllerScreen> {
  final _client = KioskClient();
  final _audio = AudioService();
  final _camera = CameraService();
  StreamSubscription<Map<String, dynamic>>? _tts;
  StreamSubscription<Map<String, dynamic>>? _devices;
  String? _seenEpoch;
  bool _scanning = false;
  String? _scanError;
  int _speechGeneration = 0;
  bool _speechPending = false;
  double _playbackRate = 1;

  @override
  void initState() {
    super.initState();
    _client.addListener(_updated);
    _audio.onPcm = _client.sendAudio;
    _audio.addListener(_refresh);
    _camera.addListener(_refresh);
    _tts = _client.ttsStream.listen(_speech);
    _devices = _client.deviceStream.listen((event) {
      if (event['action'] == 'scan' || event['action'] == 'retake') _scan();
    });
    _connect();
    _audio.initialize().then((available) {
      if (available && mounted) {
        _updateMicrophone();
        _audio.startListening();
      }
    });
  }

  Future<void> _connect() async {
    final host = await Discovery.find(remembered: _client.host);
    if (!mounted) return;
    if (host != null) _client.host = host;
    _client.connect();
  }

  void _refresh() { if (mounted) setState(() {}); }

  void _updateMicrophone() {
    _audio.setPaused(_client.status != ConnectionStatus.connected ||
        !_client.voiceAvailable || _speechPending || _client.isProcessing ||
        _client.currentStage == KioskStage.unavailable);
  }

  void _updated() {
    if (!mounted) return;
    if (_seenEpoch != _client.epoch || _client.status != ConnectionStatus.connected) {
      _seenEpoch = _client.epoch;
      final generation = ++_speechGeneration;
      _speechPending = true;
      _client.playbackState(true);
      _audio.stopPlayback().then((_) {
        if (!mounted || generation != _speechGeneration) return;
        _speechPending = _audio.isPlaying;
        _client.playbackState(_speechPending);
        _updateMicrophone();
      });
      _scanError = null;
    }
    _updateMicrophone();
    final wantsCamera = _client.currentStage == KioskStage.abha || _client.currentStage == KioskStage.documents;
    if (wantsCamera && !_camera.isReady) {
      _camera.start();
    } else if (!wantsCamera && _camera.isReady) {
      _camera.stop();
    }
    setState(() {});
  }

  Future<void> _speech(Map<String, dynamic> message) async {
    if (!mounted) return;
    final epoch = '${message['session_id']}:${message['revision']}';
    if (epoch != _client.epoch) return;
    switch (message['type']) {
      case 'tts.start':
        ++_speechGeneration;
        _speechPending = true;
        _playbackRate = (message['playback_rate'] as num?)?.toDouble() ?? 1;
        _client.playbackState(true);
        _updateMicrophone();
        break;
      case 'tts.cancelled':
        final generation = ++_speechGeneration;
        await _audio.stopPlayback();
        if (!mounted || generation != _speechGeneration) return;
        _speechPending = _audio.isPlaying;
        _client.playbackState(_speechPending);
        _updateMicrophone();
        break;
      case 'tts.audio':
        final generation = _speechGeneration;
        final audio = message['audio'];
        if (audio is! String) return;
        _speechPending = true;
        _client.playbackState(true);
        _updateMicrophone();
        await _audio.playPcm(base64Decode(audio), (message['sample_rate'] as num).toInt(), playbackRate: _playbackRate);
        if (!mounted || generation != _speechGeneration || epoch != _client.epoch) return;
        // tts.end means synthesis ended. Only native playback completion reopens capture.
        _speechPending = _audio.isPlaying;
        _client.playbackState(_speechPending);
        _updateMicrophone();
        break;
    }
  }

  Future<void> _scan() async {
    if (_scanning || _client.status != ConnectionStatus.connected) return;
    final epoch = _client.epoch;
    final stage = _client.currentStage;
    final headers = _client.scanHeaders;
    if (stage != KioskStage.abha && stage != KioskStage.documents) return;
    setState(() { _scanning = true; _scanError = null; });
    try {
      if (!_camera.isReady) await _camera.start();
      final photo = await _camera.capture();
      if (!mounted || epoch != _client.epoch) return;
      if (photo == null) throw StateError('Camera unavailable. Please ask staff for help.');
      final api = ApiService(host: _client.host);
      final result = stage == KioskStage.abha
          ? await api.scanAbhaCard(Uint8List.fromList(photo), headers: headers)
          : await api.scanDocument(Uint8List.fromList(photo), headers: headers);
      if (!mounted || epoch != _client.epoch) return;
      if (result['error'] != null) throw StateError('Scan failed. Reposition the document or ask staff for help.');
      if (stage == KioskStage.abha) {
        if (result['found'] != true || result['number'] is! String) throw StateError('No ABHA code found. Enter it or skip.');
        _client.submitAbha(result['number'] as String);
      } else if (result['capture_id'] is String) {
        // The server owns all OCR text, confidence and handwriting metadata, including empty text.
        _client.action('preview', {'capture_id': result['capture_id']});
      } else {
        throw StateError('The kiosk did not return an owned capture. Please retake.');
      }
    } catch (_) {
      if (mounted && epoch == _client.epoch) _scanError = 'Scan could not be completed. Retake or ask staff for help.';
    } finally {
      if (mounted) setState(() => _scanning = false);
    }
  }

  Future<void> _configure() async {
    final input = TextEditingController(text: _client.host);
    final host = await showDialog<String>(context: context, builder: (context) => AlertDialog(
      title: const Text('Local Jetson connection'),
      content: TextField(controller: input, decoration: const InputDecoration(labelText: 'Host or local IP')),
      actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: () => Navigator.pop(context, input.text.trim()), child: const Text('Connect'))],
    ));
    input.dispose();
    if (mounted && host != null && host.isNotEmpty) _client.host = host;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('MediKiosk'), actions: [
      IconButton(onPressed: _configure, tooltip: 'Local connection settings', icon: const Icon(Icons.settings)),
      IconButton(
        onPressed: _client.status == ConnectionStatus.connected
            ? () => _client.action('restart')
            : _client.reconnect,
        tooltip: 'Start over',
        icon: const Icon(Icons.restart_alt),
      ),
    ]),
    body: SafeArea(child: Column(children: [
      Padding(padding: const EdgeInsets.all(16), child: Text(
        _client.status != ConnectionStatus.connected ? 'Local connection unavailable — your saved journey will resume.'
          : _speechPending || _audio.isPlaying ? 'Speaking • microphone paused'
          : _client.isProcessing ? 'Saving / processing…'
          : _audio.isListening && _client.voiceAvailable ? 'Listening • speak or use a button'
          : 'Voice unavailable • use buttons or ask staff for help',
        style: Theme.of(context).textTheme.titleMedium, textAlign: TextAlign.center)),
      if (_client.error != null) Padding(padding: const EdgeInsets.all(16), child: Text(_client.error!, style: const TextStyle(color: Colors.red))),
      Expanded(child: SingleChildScrollView(padding: const EdgeInsets.all(24), child: Center(child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1000),
        child: Column(children: [
          if (_camera.isReady && {KioskStage.abha, KioskStage.documents}.contains(_client.currentStage))
            SizedBox(height: 200, child: CameraPreview(_camera.controller!)),
          if (_scanning) const LinearProgressIndicator(),
          if (_scanError != null) Text(_scanError!),
          WorkflowBody(key: ValueKey(_client.epoch), client: _client),
        ]),
      )))),
    ])),
  );

  @override
  void dispose() {
    _client.removeListener(_updated);
    _tts?.cancel();
    _devices?.cancel();
    _audio.removeListener(_refresh);
    _camera.removeListener(_refresh);
    _audio.dispose();
    _camera.dispose();
    _client.dispose();
    super.dispose();
  }
}

/// A touch alternative to the same server prompts/actions used by local speech.
class WorkflowBody extends StatefulWidget {
  final KioskClient client;
  const WorkflowBody({super.key, required this.client});
  @override
  State<WorkflowBody> createState() => _WorkflowBodyState();
}

class _WorkflowBodyState extends State<WorkflowBody> {
  final _answer = TextEditingController();
  final _narrative = TextEditingController();
  String? _slipStatus;
  KioskClient get client => widget.client;
  bool get _blocked => client.isProcessing || client.status != ConnectionStatus.connected;

  Widget button(String label, String action, [dynamic value]) => Padding(
    padding: const EdgeInsets.all(6), child: FilledButton(
      style: FilledButton.styleFrom(minimumSize: const Size(120, 60)),
      onPressed: _blocked ? null : () {
        if (action == 'answer') {
          client.submitTranscript(_answer.text);
        } else {
          client.action(action, value);
        }
      },
      child: Text(label, textAlign: TextAlign.center),
    ));

  Future<void> _downloadSlip() async {
    setState(() => _slipStatus = tr('preparing_slip', client.language));
    try {
      final bytes = await ApiService(host: client.host).slipPdf(headers: client.scanHeaders);
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/medikiosk-slip.pdf');
      await file.writeAsBytes(bytes, flush: true);
      await Share.shareXFiles([XFile(file.path, mimeType: 'application/pdf')],
          subject: tr('slip_subject', client.language));
      setState(() => _slipStatus = null);
    } catch (_) {
      setState(() => _slipStatus = tr('slip_failed', client.language));
    }
  }

  Widget _narrativeBox(List<String> actions) {
    // The box mirrors what the kiosk heard; the patient can type over it.
    if (_narrative.text != client.narrative) {
      _narrative.value = TextEditingValue(text: client.narrative,
          selection: TextSelection.collapsed(offset: client.narrative.length));
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Semantics(header: true, child: Text(client.headline, style: Theme.of(context).textTheme.headlineSmall)),
      const SizedBox(height: 12),
      Row(children: [
        Icon(client.voiceAvailable ? Icons.mic_rounded : Icons.keyboard_rounded, color: AppTheme.primaryBlue),
        const SizedBox(width: 8),
        Expanded(child: Text(tr('narrative_hint', client.language),
            style: const TextStyle(color: AppTheme.textSecondary))),
      ]),
      const SizedBox(height: 12),
      TextField(controller: _narrative, minLines: 6, maxLines: 12, maxLength: 1500,
        style: const TextStyle(fontSize: 20),
        onChanged: client.setNarrative,
        decoration: InputDecoration(border: const OutlineInputBorder(),
          hintText: tr('narrative_example', client.language))),
      const SizedBox(height: 8),
      SizedBox(height: 64, child: FilledButton.icon(
        onPressed: _blocked || client.narrative.trim().isEmpty ? null : client.submitNarrative,
        icon: const Icon(Icons.arrow_forward_rounded),
        label: Text(tr('proceed', client.language), style: const TextStyle(fontSize: 20)))),
      Wrap(children: [
        for (final action in actions.where((a) => !{'answer', 'choose', 'edit', 'preview', 'document'}.contains(a)))
          button(_label(action), action),
      ]),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final screen = client.screen;
    final input = screen['input'];
    final actions = List<String>.from(screen['allowed_actions'] as List? ?? []);
    final review = List<Map<String, dynamic>>.from(screen['review'] as List? ?? []);
    final report = client.lastReport;
    final preview = screen['capture_preview'] as Map?;
    final stage = client.currentStage;
    final optionValues = client.options.map((o) => '${o['value']}').toList();

    if (stage == KioskStage.language && client.options.isNotEmpty) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        LanguageScreen(selectedLanguage: client.language, codes: optionValues,
          onLanguageSelected: (code) { if (!_blocked) client.action('choose', code); },
          onRepeatAudio: () => client.action('repeat')),
        Wrap(alignment: WrapAlignment.center, children: [
          for (final action in actions.where((a) => {'help', 'restart'}.contains(a))) button(_label(action), action),
        ]),
      ]);
    }
    if (stage == KioskStage.hub && optionValues.contains('clinical')) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        PathwayHubScreen(
          onSelectSymptoms: () { if (!_blocked) client.action('choose', 'clinical'); },
          onSelectPrakriti: () { if (!_blocked) client.action('choose', 'prakriti'); },
          onSelectVitals: optionValues.contains('vitals')
              ? () { if (!_blocked) client.action('choose', 'vitals'); }
              : null,
          onBackToRegistration: () => client.action('back')),
        Wrap(alignment: WrapAlignment.center, children: [
          for (final action in actions.where((a) => !{'answer', 'choose', 'back'}.contains(a))) button(_label(action), action),
        ]),
      ]);
    }
    if (stage == KioskStage.interview && client.accumulate) return _narrativeBox(actions);

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Semantics(header: true, child: Text(client.headline, style: Theme.of(context).textTheme.headlineSmall)),
      if (client.progress case final progress?) Padding(padding: const EdgeInsets.symmetric(vertical: 16), child: Text('${progress[0]} / ${progress[1]}')),
      const SizedBox(height: 20),
      for (final entry in client.options.indexed)
        button('${entry.$1 + 1}. ${entry.$2['label']}', 'choose', entry.$2['value']),
      if (client.options.isEmpty && ['text', 'number', 'camera_or_text', 'voice'].contains(input)) ...[
        TextField(controller: _answer, maxLength: 500,
          onChanged: (_) => setState(() {}),
          keyboardType: input == 'number' ? TextInputType.number : TextInputType.text,
          decoration: InputDecoration(labelText: tr('your_answer', client.language), border: const OutlineInputBorder()),
          onSubmitted: (_) { if (_answer.text.trim().isNotEmpty) client.submitTranscript(_answer.text); }),
        button(tr('submit_answer', client.language), 'answer', _answer.text),
      ],
      if (preview != null) ...[
        Text(tr('preview_title', client.language), style: Theme.of(context).textTheme.titleLarge),
        Text((preview['lines'] as List? ?? []).join('\n').isEmpty ? tr('preview_empty', client.language) : (preview['lines'] as List).join('\n')),
        Text('${preview['confidence_note'] ?? ''}'),
      ],
      for (final entry in review.indexed)
        Padding(padding: const EdgeInsets.symmetric(vertical: 10), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${entry.$1 + 1}. ${entry.$2['question']}'),
          Text(entry.$2['status'] == 'answered' ? '${entry.$2['answer']}' : '${entry.$2['status']}'),
          button('${tr('edit_answer', client.language)} ${entry.$1 + 1}', 'edit', entry.$2['id']),
        ])),
      if (stage == KioskStage.report && report != null) ...[
        Text(tr('saved_local', client.language), style: Theme.of(context).textTheme.titleLarge),
        if (report['queue_entry'] case final Map queue)
          Text('${queue['specialty']} • ${tr('token', client.language)} ${queue['number']}', style: Theme.of(context).textTheme.headlineMedium),
        if (report['cloud_status'] == 'sent') Text(tr('sent_to_hospital', client.language)),
        Text(tr('not_diagnosis', client.language)),
        if (report['prakriti'] case final Map prakriti)
          Text(prakriti['complete'] == false ? tr('prakriti_incomplete', client.language)
            : '${tr('provisional_prakriti', client.language)}: ${prakriti['prakriti'] ?? tr('not_established', client.language)}'),
        Padding(padding: const EdgeInsets.all(6), child: FilledButton.icon(
          style: FilledButton.styleFrom(minimumSize: const Size(120, 60)),
          onPressed: client.status != ConnectionStatus.connected ? null : _downloadSlip,
          icon: const Icon(Icons.picture_as_pdf_rounded),
          label: Text(tr('download_slip', client.language)))),
        if (_slipStatus != null) Text(_slipStatus!),
      ],
      if (stage == KioskStage.unavailable) Text(tr('unsupported', client.language)),
      Wrap(children: [
        for (final action in actions.where((a) => !{'answer', 'choose', 'edit', 'preview', 'document'}.contains(a)))
          button(_label(action), action),
      ]),
    ]);
  }

  String _label(String action) => switch (action) {
    'confirm' => tr('confirm', client.language),
    'unknown' => tr('unknown', client.language),
    'refuse' => tr('refuse', client.language),
    'skip' => tr('skip', client.language),
    'repeat' => tr('repeat', client.language),
    'slower' => tr('slower', client.language),
    'more_time' => tr('more_time', client.language),
    'help' => tr('help', client.language),
    'restart' => tr('restart', client.language),
    'back' => tr('back', client.language),
    'cancel' => tr('cancel', client.language),
    'measure' => tr('measure', client.language),
    'scan' => tr('scan', client.language),
    'retake' => tr('retake', client.language),
    'keep' => tr('keep', client.language),
    'discard' => tr('discard', client.language),
    'done' => tr('done', client.language),
    'withdraw' => tr('withdraw', client.language),
    _ => action,
  };
  @override
  void dispose() { _answer.dispose(); _narrative.dispose(); super.dispose(); }
}
