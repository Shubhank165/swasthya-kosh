import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/api_service.dart';
import '../services/audio_service.dart';
import '../services/camera_service.dart';
import '../services/discovery.dart';
import '../services/kiosk_client.dart';
import '../services/verbal_matcher.dart';
import '../theme/app_theme.dart';
import '../widgets/kiosk_header.dart';
import 'abha_screen.dart';
import 'choice_screen.dart';
import 'documents_screen.dart';
import 'emergency_screen.dart';
import 'interview_screen.dart';
import 'language_screen.dart';
import 'pathway_hub_screen.dart';
import 'registration_screen.dart';
import 'report_screen.dart';

class KioskControllerScreen extends StatefulWidget {
  const KioskControllerScreen({super.key});

  @override
  State<KioskControllerScreen> createState() => _KioskControllerScreenState();
}

class _KioskControllerScreenState extends State<KioskControllerScreen> {
  late KioskClient _client;
  late ApiService _apiService;
  late AudioService _audioService;
  late CameraService _cameraService;

  // Local stage state overrides server when navigating modern kiosk workflow
  KioskStage? _localStage;
  KioskStage get _effectiveStage => _localStage ?? _client.currentStage;

  // Patient Intake State
  PatientProfile _patientProfile = PatientProfile(
    name: 'Patient / मरीज़',
    age: 35,
    gender: 'MALE',
    isWalkIn: true,
  );

  final List<ClinicalAnswerRecord> _clinicalAnswers = [];
  /// Where the local screens are walking the server to. Null means the server drives.
  KioskStage? _serverTarget;
  /// The stage the last walk command was sent from, so the walk cannot act on it twice.
  KioskStage? _walkedFrom;

  List<String> _scannedDocumentLines = [];
  bool _isDocumentScanning = false;
  String? _scanError;

  // Spoken feedback state
  String? _autoSelectedBanner;
  Timer? _bannerTimer;
  StreamSubscription<Map<String, dynamic>>? _ttsSubscription;
  String _lastHandledTranscript = '';
  DateTime _lastHandledTime = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void initState() {
    super.initState();
    // Default to Jetson Tailscale IP verified online
    _client = KioskClient(host: '100.104.251.40', port: 8000);
    _apiService = ApiService(host: '100.104.251.40', port: 8000);
    _client.addListener(_onClientUpdated);

    // Jetson Linux Whisper STT feed over WebSocket
    _client.onTranscriptReceived = (transcript) {
      _handleSpokenTranscript(transcript, fromMicrophone: false);
    };

    // Tablet microphone: raw PCM streamed to the Jetson's Whisper
    _audioService = AudioService(
      onFinalTranscript: (transcript) {
        _handleSpokenTranscript(transcript, fromMicrophone: true);
      },
    );
    _audioService.onPcm = _client.sendAudio;
    _audioService.addListener(() {
      if (mounted) setState(() {});
    });

    // Speak the Jetson's prompts.
    _ttsSubscription = _client.ttsStream.listen((message) {
      if (message['type'] == 'tts.cancelled') {
        _audioService.stopPlayback();
        return;
      }
      final audio = message['audio'];
      if (audio is! String) return;

      // In language stage, do not play server enumeration of all 9 languages
      if (_effectiveStage == KioskStage.language) {
        return;
      }

      _audioService.playPcm(
        base64Decode(audio),
        (message['sample_rate'] as num?)?.toInt() ?? 22050,
      );
    });

    _cameraService = CameraService();
    _cameraService.addListener(() {
      if (mounted) setState(() {});
    });

    _discover();

    _audioService.initialize().then((available) {
      if (available && mounted) {
        _audioService.startListening(
          localeId: _client.language.replaceAll('-', '_'),
        );
      }
    });
  }

  /// Walk the server forward to the stage the local screens have already moved past.
  ///
  /// Registration and the pathway hub are client-side screens with no server stage behind them,
  /// so while the patient is on them the server is still sitting on `abha`. Sending `flow.who`
  /// from there is rejected as a stale stage action and the interview never starts - the mic
  /// listens, the server has no question, and the patient talks to nothing.
  ///
  /// One step per server update rather than a burst: each command is answered with a new screen,
  /// which calls this again, so the two converge instead of racing the client's own in-flight
  /// guard.
  void _catchServerUp() {
    final target = _serverTarget;
    if (target == null) return;

    final stage = _client.currentStage;
    if (stage == target) {
      _handOverToServer();
      return;
    }

    // One command per stage, no matter how many times the client notifies from it. The server
    // re-asserts `interview` on every clinical.question and clears the in-flight guard as it
    // does, so without this the walk fired twice from the same stage and advanced the server
    // one stage past where it was asked to stop.
    if (stage == _walkedFrom) return;
    _walkedFrom = stage;

    switch (stage) {
      case KioskStage.abha:
        final abha = _patientProfile.abhaNumber;
        if (abha != null && abha.isNotEmpty) {
          _client.submitAbha(abha);
        } else {
          _client.nextStage();
        }
        break;
      case KioskStage.who:
        // Registration collects the patient's own details, so the local flow never offers the
        // "answering for someone else" choice. Anyone who needs it uses the server's who screen.
        _client.selectWho('self');
        break;
      case KioskStage.interview:
      case KioskStage.ayurveda:
        // Only walked past on the Prakriti pathway, which is a wellness assessment rather than a
        // clinical intake, so it skips the complaint interview and the per-visit Dashavidha set.
        _client.nextStage();
        break;
      default:
        // The server is somewhere the walk cannot use as a stepping stone - most often past the
        // target, because a patient whose Prakriti is already on record skips that stage. Hand
        // over rather than pushing it further.
        _handOverToServer();
        break;
    }
  }

  /// Stop driving and let the server's own stage decide what is on screen.
  void _handOverToServer() {
    _serverTarget = null;
    _walkedFrom = null;
    _localStage = null;
  }

  void _onClientUpdated() {
    if (!mounted) return;

    final shouldPauseAudio =
        _client.status != ConnectionStatus.connected ||
        !_client.voiceAvailable ||
        _effectiveStage == KioskStage.language ||
        _effectiveStage == KioskStage.registration ||
        _effectiveStage == KioskStage.hub ||
        _effectiveStage == KioskStage.report ||
        _effectiveStage == KioskStage.emergency;

    _audioService.setPaused(shouldPauseAudio);

    if (_client.currentStage == KioskStage.language && _localStage != KioskStage.language) {
      _localStage = null;
      _scannedDocumentLines = [];
      _scanError = null;
    } else if (_client.currentStage == KioskStage.report) {
      _localStage = KioskStage.report;
    }

    _catchServerUp();

    setState(() {});

    final wantsCamera =
        _effectiveStage == KioskStage.registration ||
        _effectiveStage == KioskStage.abha ||
        _effectiveStage == KioskStage.documents;

    if (wantsCamera && !_cameraService.isReady) {
      _cameraService.start();
    } else if (!wantsCamera && _cameraService.isReady) {
      _cameraService.stop();
    }
  }

  Future<void> _discover() async {
    final found = await Discovery.find(remembered: _client.host);
    if (!mounted) return;
    if (found != null) {
      setState(() {
        _client.host = found;
        _apiService = ApiService(host: found, port: 8000);
      });
    }
    _client.connect();
  }

  @override
  void dispose() {
    _bannerTimer?.cancel();
    _ttsSubscription?.cancel();
    _cameraService.dispose();
    _audioService.dispose();
    _client.removeListener(_onClientUpdated);
    _client.dispose();
    super.dispose();
  }

  void _handleSpokenTranscript(
    String transcript, {
    required bool fromMicrophone,
  }) {
    final text = transcript.trim();
    if (text.isEmpty) return;
    if (!fromMicrophone && _effectiveStage == KioskStage.interview) {
      _showSpokenActionBanner('🎙️ "$text"');
      return;
    }

    // Deduplication check: ignore exact repetition within 2 seconds
    final now = DateTime.now();
    if (text.toLowerCase() == _lastHandledTranscript.toLowerCase() &&
        now.difference(_lastHandledTime) < const Duration(seconds: 2)) {
      return;
    }

    // Both server-driven touch questionnaires answer from the options the server put on screen.
    // _effectiveStage rather than _client.currentStage so the locally-driven registration and
    // hub screens do not pick up option matching meant for a question.
    final ayurvedaOptions =
        _effectiveStage == KioskStage.ayurveda ||
            _effectiveStage == KioskStage.prakriti
        ? _client.options
        : const <Map<String, dynamic>>[];

    final match = VerbalOptionMatcher.match(
      transcript: text,
      currentStage: _effectiveStage,
      questionId: _client.questionId,
      ayurvedaOptions: ayurvedaOptions,
    );

    if (match.matched) {
      _lastHandledTranscript = text;
      _lastHandledTime = now;
      _audioService.pauseTemporarily(const Duration(milliseconds: 700));
      _showSpokenActionBanner('🎙️ "$text"  →  ${_actionDescription(match)}');

      switch (match.action) {
        case 'language':
          final lang = match.value as String;
          _client.selectLanguage(lang);
          _audioService.setLocale(lang.replaceAll('-', '_'));
          setState(() {
            _localStage = KioskStage.registration;
          });
          break;

        case 'who':
          _client.selectWho(match.value as String);
          break;

        case 'duration':
          final dur = match.value as String;
          _clinicalAnswers.add(
            ClinicalAnswerRecord(
              questionText: _client.headline.isNotEmpty ? _client.headline : 'Duration',
              answerText: dur,
              timestamp: DateTime.now(),
            ),
          );
          _client.submitTranscript(dur);
          break;

        case 'severity':
          final score = '${match.value}';
          _clinicalAnswers.add(
            ClinicalAnswerRecord(
              questionText: _client.headline.isNotEmpty ? _client.headline : 'Severity',
              answerText: '$score / 10',
              timestamp: DateTime.now(),
            ),
          );
          _client.submitTranscript(score);
          break;

        case 'yes_no':
          final val = match.value as bool;
          final ans = val ? 'हाँ (Yes)' : 'नहीं (No)';
          _clinicalAnswers.add(
            ClinicalAnswerRecord(
              questionText: _client.headline.isNotEmpty ? _client.headline : 'Clinical Inquiry',
              answerText: ans,
              timestamp: DateTime.now(),
            ),
          );
          _client.submitTranscript(ans);
          break;

        case 'complaint':
          final comp = match.value as String;
          _clinicalAnswers.add(
            ClinicalAnswerRecord(
              questionText: _client.headline.isNotEmpty ? _client.headline : 'Chief Complaint',
              answerText: comp,
              timestamp: DateTime.now(),
            ),
          );
          _client.submitTranscript(comp);
          break;

        case 'ayurveda_option':
          final index = match.value as int;
          final options = _client.options;
          final id = _client.questionId;
          if (id != null && index >= 0 && index < options.length) {
            _client.submitAyurvedaAnswer(id, options[index]['value'] as String);
          }
          break;

        case 'prakriti_option':
          final index = match.value as int;
          final options = _client.options;
          if (index >= 0 && index < options.length) {
            // questionId is null on the opening gate screen, which is exactly what the server
            // expects there - it tells the gate from a question by that field's absence.
            _client.submitPrakritiAnswer(
              _client.questionId,
              options[index]['value'] as String,
            );
          }
          break;

        case 'scan':
          _handleDocumentScan();
          break;

        case 'next':
          if (_effectiveStage == KioskStage.registration) {
            setState(() => _localStage = KioskStage.hub);
          } else {
            _client.nextStage();
          }
          break;

        case 'back':
          _handleBack();
          break;

        case 'restart':
          _resetSession();
          break;
      }
    } else {
      // Free-form clinical speech during interview stage
      if (_effectiveStage == KioskStage.interview) {
        _lastHandledTranscript = text;
        _lastHandledTime = now;
        _showSpokenActionBanner('🎙️ "$text"');
        if (fromMicrophone) {
          _clinicalAnswers.add(
            ClinicalAnswerRecord(
              questionText: _client.headline.isNotEmpty ? _client.headline : 'Clinical Inquiry',
              answerText: text,
              timestamp: DateTime.now(),
            ),
          );
          _client.submitTranscript(text);
        }
      }
    }
  }

  String _actionDescription(VerbalMatchResult match) {
    switch (match.action) {
      case 'language':
        return 'Language: ${match.value}';
      case 'who':
        return 'Selected: ${match.value}';
      case 'duration':
        return 'Duration: ${match.value}';
      case 'severity':
        return 'Severity: ${match.value}/10';
      case 'yes_no':
        return match.value == true ? 'हाँ (Yes)' : 'नहीं (No)';
      case 'complaint':
        return 'Problem: ${match.value}';
      case 'ayurveda_option':
        return 'Dashavidha Option';
      case 'prakriti_option':
        return 'Prakriti Option';
      case 'scan':
        return 'Scanning Document';
      case 'next':
        return 'Aage / Next';
      case 'back':
        return 'Peeche / Back';
      case 'restart':
        return 'Naya Mareez / Reset';
      default:
        return 'Selected';
    }
  }

  void _showSpokenActionBanner(String message) {
    _bannerTimer?.cancel();
    setState(() {
      _autoSelectedBanner = message;
    });
    _bannerTimer = Timer(const Duration(milliseconds: 2500), () {
      if (mounted) {
        setState(() {
          _autoSelectedBanner = null;
        });
      }
    });
  }

  void _handleBack() {
    if (_effectiveStage == KioskStage.registration) {
      setState(() => _localStage = KioskStage.language);
    } else if (_effectiveStage == KioskStage.hub) {
      setState(() => _localStage = KioskStage.registration);
    } else if (_effectiveStage == KioskStage.ayurveda || _effectiveStage == KioskStage.interview) {
      setState(() => _localStage = KioskStage.hub);
    } else {
      _client.backStage();
    }
  }

  void _resetSession() {
    setState(() {
      _localStage = null;
      _patientProfile = PatientProfile(
        name: 'Patient / मरीज़',
        age: 35,
        gender: 'MALE',
        isWalkIn: true,
      );
      _clinicalAnswers.clear();
      _serverTarget = null;
      _walkedFrom = null;
      _scannedDocumentLines = [];
      _scanError = null;
    });
    _client.restartSession();
    _audioService.setLocale('hi_IN');
  }

  void _showServerConfigDialog() {
    final textController = TextEditingController(text: _client.host);

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
            side: const BorderSide(color: AppTheme.surfaceBorder),
          ),
          title: const Row(
            children: [
              Icon(Icons.router_outlined, color: AppTheme.primaryBlue),
              SizedBox(width: 10),
              Text(
                'Jetson Orin Nano Host',
                style: TextStyle(color: AppTheme.textPrimary, fontWeight: FontWeight.bold),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Select or enter the IP address of the Jetson Orin Nano running MediKiosk:',
                style: TextStyle(fontSize: 13, color: AppTheme.textSecondary),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: textController,
                style: const TextStyle(
                  color: AppTheme.textPrimary,
                  fontWeight: FontWeight.bold,
                ),
                decoration: InputDecoration(
                  labelText: 'Host IP / Hostname',
                  filled: true,
                  fillColor: AppTheme.surfaceHighlight,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 8,
                children: [
                  ActionChip(
                    label: const Text('Tailscale (100.104.251.40)'),
                    onPressed: () => textController.text = '100.104.251.40',
                  ),
                  ActionChip(
                    label: const Text('Localhost (127.0.0.1)'),
                    onPressed: () => textController.text = '127.0.0.1',
                  ),
                  ActionChip(
                    label: const Text('USB Tether (192.168.191.75)'),
                    onPressed: () => textController.text = '192.168.191.75',
                  ),
                ],
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () {
                final newHost = textController.text.trim();
                if (newHost.isNotEmpty) {
                  setState(() {
                    _client.host = newHost;
                    _apiService = ApiService(host: newHost, port: 8000);
                  });
                }
                Navigator.pop(context);
              },
              child: const Text('Connect'),
            ),
          ],
        );
      },
    );
  }

  void _handleDocumentScan() async {
    if (_isDocumentScanning) return;
    final scanStage = _effectiveStage;
    setState(() {
      _isDocumentScanning = true;
      _scanError = null;
    });
    final jpeg = await _cameraService.capture();
    if (!mounted) return;
    if (_effectiveStage != scanStage) {
      setState(() => _isDocumentScanning = false);
      return;
    }
    if (jpeg == null) {
      setState(() {
        _isDocumentScanning = false;
        _scanError = _cameraService.error ?? 'Could not take the photo';
      });
      return;
    }

    final res = await _apiService.scanDocument(Uint8List.fromList(jpeg));
    if (!mounted) return;
    if (_effectiveStage != scanStage) {
      setState(() => _isDocumentScanning = false);
      return;
    }
    final lines = res['lines'] is List
        ? List<String>.from(res['lines'])
        : <String>[];
    setState(() {
      _isDocumentScanning = false;
      _scanError = lines.isEmpty
          ? (res['error']?.toString() ?? 'No text could be read. Reposition and try again.')
          : null;
      _scannedDocumentLines = lines;
    });
    if (lines.isNotEmpty) {
      _client.send({
        'type': 'flow.document',
        'lines': lines,
        'seconds': (res['seconds'] as num?)?.toDouble(),
      });
    }
  }

  Future<void> _handleAbhaScan() async {
    if (_isDocumentScanning) return;
    final scanStage = _effectiveStage;
    setState(() {
      _isDocumentScanning = true;
      _scanError = null;
    });
    final jpeg = await _cameraService.capture();
    if (!mounted) return;
    if (_effectiveStage != scanStage) {
      setState(() => _isDocumentScanning = false);
      return;
    }
    if (jpeg == null) {
      setState(() {
        _isDocumentScanning = false;
        _scanError = _cameraService.error ?? 'Could not take the photo';
      });
      return;
    }
    final res = await _apiService.scanAbhaCard(Uint8List.fromList(jpeg));
    if (!mounted) return;
    if (_effectiveStage != scanStage) {
      setState(() => _isDocumentScanning = false);
      return;
    }
    setState(() {
      _isDocumentScanning = false;
      _scanError = res['found'] == true
          ? null
          : 'No ABHA code found. Try again or enter manually.';
    });
    if (res['found'] == true && res['number'] is String) {
      final abhaNum = res['number'] as String;
      setState(() {
        _patientProfile = _patientProfile.copyWith(abhaNumber: abhaNum);
      });
      _client.submitAbha(abhaNum);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          children: [
            // Top App Bar
            KioskHeader(
              client: _client,
              onBack: _handleBack,
              onRestart: _resetSession,
              onConfigureServer: _showServerConfigDialog,
              onEmergency: () {
                _client.send({
                  'type': 'staff.alert',
                  'alerts': [
                    {'message': 'Emergency assistance requested at kiosk by patient'}
                  ],
                });
              },
            ),

            // 5-Stage Step Progress Bar
            _buildStageProgress(),

            // Spoken HUD Banner (Visual confirmation when an option is auto-selected)
            if (_autoSelectedBanner != null) _buildSpokenActionBanner(),

            if (_client.error != null)
              Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  _client.error!,
                  style: const TextStyle(color: AppTheme.alertRed, fontWeight: FontWeight.bold),
                ),
              ),

            // Main Dynamic Body
            Expanded(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 16,
                  ),
                  child: AbsorbPointer(
                    absorbing: _client.isProcessing && _effectiveStage == KioskStage.interview,
                    child: _buildStageContent(),
                  ),
                ),
              ),
            ),

            // Bottom Audio / Microphone Status Indicator
            _buildMicStatusBar(),
          ],
        ),
      ),
    );
  }

  Widget _buildSpokenActionBanner() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 250),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
      decoration: BoxDecoration(
        color: AppTheme.successGreen.withAlpha(25),
        border: const Border(
          bottom: BorderSide(color: AppTheme.successGreen, width: 1.5),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(4),
            decoration: const BoxDecoration(
              color: AppTheme.successGreen,
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.check, size: 12, color: Colors.white),
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              _autoSelectedBanner!,
              style: const TextStyle(
                color: AppTheme.textPrimary,
                fontWeight: FontWeight.bold,
                fontSize: 13,
                letterSpacing: 0.3,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMicStatusBar() {
    final bool isPhoneMicActive = _audioService.isListening;
    final bool isJetsonConnected = _client.status == ConnectionStatus.connected;
    final bool isInterviewStage = _effectiveStage == KioskStage.interview;

    String micText;
    Color statusColor;
    IconData micIcon;

    if (isPhoneMicActive && isJetsonConnected && isInterviewStage && _client.voiceAvailable) {
      micText = _audioService.currentWords.isNotEmpty
          ? '🎙️ "${_audioService.currentWords}"'
          : '🎙️ माइक सक्रिय है (बोलकर उत्तर दें) • Mic Listening';
      statusColor = AppTheme.successGreen;
      micIcon = Icons.mic;
    } else if (isJetsonConnected && isInterviewStage) {
      micText = _audioService.isPausedTemporarily
          ? 'Microphone paused'
          : 'माइक तैयार है • बोलें या स्क्रीन पर छूएं';
      statusColor = AppTheme.primaryBlue;
      micIcon = Icons.mic;
    } else if (isJetsonConnected) {
      micText = 'स्क्रीन पर छूकर विकल्प चुनें • Touch screen to select';
      statusColor = AppTheme.tealAccent;
      micIcon = Icons.touch_app_outlined;
    } else if (_audioService.isAvailable) {
      micText = 'माइक चालू करने के लिए टैप करें (Tap to listen)';
      statusColor = AppTheme.warningOrange;
      micIcon = Icons.mic_none;
    } else {
      micText = 'Microphone unavailable • Touch to answer';
      statusColor = AppTheme.textMuted;
      micIcon = Icons.touch_app_outlined;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: const BoxDecoration(
        color: AppTheme.surface,
        border: Border(top: BorderSide(color: AppTheme.surfaceBorder)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          GestureDetector(
            onTap: () {
              if (_audioService.isAvailable) {
                _audioService.toggleListening();
              } else {
                _audioService.initialize().then((ok) {
                  if (ok) _audioService.startListening();
                });
              }
            },
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(micIcon, size: 16, color: statusColor),
                const SizedBox(width: 8),
                Text(
                  micText,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: statusColor,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStageProgress() {
    final stages = [
      {'key': 'language', 'label': 'भाषा (Lang)', 'index': 0},
      {'key': 'registration', 'label': 'पंजीकरण (Register)', 'index': 1},
      {'key': 'choice', 'label': 'मार्ग (Choice)', 'index': 2},
      {'key': 'intake', 'label': 'जाँच (Intake)', 'index': 3},
      {'key': 'report', 'label': 'पर्ची (Slip)', 'index': 4},
    ];

    int currentIndex;
    switch (_effectiveStage) {
      case KioskStage.language:
        currentIndex = 0;
        break;
      case KioskStage.registration:
      case KioskStage.abha:
        currentIndex = 1;
        break;
      case KioskStage.hub:
      case KioskStage.who:
        currentIndex = 2;
        break;
      case KioskStage.interview:
      case KioskStage.ayurveda:
      case KioskStage.prakriti:
      case KioskStage.documents:
        currentIndex = 3;
        break;
      case KioskStage.report:
        currentIndex = 4;
        break;
      default:
        currentIndex = 0;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: AppTheme.surfaceHighlight.withAlpha(80),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: stages.map((s) {
            final stageIdx = s['index'] as int;
            final isCurrent = currentIndex == stageIdx;
            final isPassed = currentIndex > stageIdx;

            Color indicatorColor = AppTheme.textMuted;
            if (isCurrent) {
              indicatorColor = AppTheme.primaryBlue;
            } else if (isPassed) {
              indicatorColor = AppTheme.successGreen;
            }

            return Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 5,
                  ),
                  decoration: BoxDecoration(
                    color: isCurrent
                        ? AppTheme.primaryBlue.withAlpha(25)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: isCurrent
                          ? AppTheme.primaryBlue
                          : Colors.transparent,
                      width: 1.5,
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        isPassed ? Icons.check_circle_rounded : Icons.circle,
                        size: 13,
                        color: indicatorColor,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        s['label'] as String,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: isCurrent
                              ? FontWeight.bold
                              : FontWeight.w500,
                          color: isCurrent
                              ? AppTheme.primaryBlue
                              : (isPassed ? AppTheme.textPrimary : AppTheme.textSecondary),
                        ),
                      ),
                    ],
                  ),
                ),
                if (stageIdx < stages.length - 1)
                  Container(
                    width: 16,
                    height: 2,
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    color: isPassed ? AppTheme.successGreen.withAlpha(100) : AppTheme.surfaceBorder,
                  ),
              ],
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _buildStageContent() {
    if (_client.isEmergency) {
      return EmergencyScreen(
        redFlags: _client.redFlags,
        onStaffAcknowledged: _resetSession,
      );
    }

    switch (_effectiveStage) {
      case KioskStage.language:
        return LanguageScreen(
          selectedLanguage: _client.language,
          onLanguageSelected: (code) {
            _client.selectLanguage(code);
            _audioService.setLocale(code.replaceAll('-', '_'));
            setState(() {
              _localStage = KioskStage.registration;
            });
          },
          onRepeatAudio: () {
            _client.sendLog('User requested language audio prompt');
          },
        );

      case KioskStage.registration:
        return RegistrationScreen(
          initialProfile: _patientProfile,
          cameraService: _cameraService,
          onRegister: (profile) {
            setState(() {
              _patientProfile = profile;
              _localStage = KioskStage.hub;
            });
            if (profile.abhaNumber != null && profile.abhaNumber!.isNotEmpty) {
              _client.submitAbha(profile.abhaNumber!);
            }
          },
          onScanCard: _handleAbhaScan,
          isScanning: _isDocumentScanning,
          scanError: _scanError,
        );

      case KioskStage.hub:
        return PathwayHubScreen(
          profile: _patientProfile,
          onSelectSymptoms: () {
            // Stay on the hub while the server catches up, then hand over. Setting the local
            // stage to the destination instead would leave the client showing a question the
            // server has not asked yet, and would never hand control back.
            setState(() {
              _serverTarget = KioskStage.interview;
              _walkedFrom = null;
            });
            _catchServerUp();
          },
          onSelectPrakriti: () {
            setState(() {
              _serverTarget = KioskStage.prakriti;
              _walkedFrom = null;
            });
            _catchServerUp();
          },
          onBackToRegistration: () {
            setState(() {
              _localStage = KioskStage.registration;
            });
          },
        );

      case KioskStage.abha:
        return AbhaScreen(
          headline: _client.headline,
          onSubmitAbha: (abha) {
            setState(() {
              _patientProfile = _patientProfile.copyWith(abhaNumber: abha);
            });
            _client.submitAbha(abha);
          },
          onSkip: () => _client.nextStage(),
          cameraService: _cameraService,
          onScanCard: _handleAbhaScan,
          isScanning: _isDocumentScanning,
          scanError: _scanError,
        );

      case KioskStage.who:
        return ChoiceScreen(
          headline: _client.headline,
          options: _client.options,
          onChoose: (who) => _client.selectWho(who),
          onBack: _handleBack,
          onRepeat: () => _client.repeatQuestion(),
        );

      case KioskStage.interview:
        return InterviewScreen(
          key: ValueKey(_client.questionId),
          questionText: _client.headline,
          answerUi: _client.answerUi,
          isListening: _audioService.isListening && _client.voiceAvailable,
          soundLevel: _audioService.soundLevel,
          onRepeat: _client.repeatQuestion,
          questionId: _client.questionId,
          lastTranscript: _client.lastTranscript,
          isProcessing: _client.isProcessing,
          onSubmitAnswer: (ans) {
            _clinicalAnswers.add(
              ClinicalAnswerRecord(
                questionText: _client.headline.isNotEmpty
                    ? _client.headline
                    : 'Clinical Inquiry',
                answerText: ans,
                timestamp: DateTime.now(),
              ),
            );
            _client.submitTranscript(ans);
          },
          onCompleteIntake: () {
            setState(() {
              _localStage = KioskStage.report;
            });
          },
        );

      case KioskStage.ayurveda:
        // Dashavidha Pariksha, asked every visit. Questions, labels, icons and progress all come
        // from the server, which also validates the answer.
        return ChoiceScreen(
          headline: _client.headline,
          options: _client.options,
          progress: _client.progress,
          onChoose: (value) {
            final id = _client.questionId;
            if (id != null) _client.submitAyurvedaAnswer(id, value);
          },
          onBack: _handleBack,
          onRepeat: () => _client.repeatQuestion(),
        );

      case KioskStage.prakriti:
        // Same screen for the "have you filled this before?" gate and for the 46 questions after
        // it - both are a headline and a list of choices, and the server says which is which by
        // whether it sends a question_id. Nothing about the Ayush form is duplicated in Dart.
        return ChoiceScreen(
          headline: _client.headline,
          options: _client.options,
          progress: _client.progress,
          onChoose: (value) =>
              _client.submitPrakritiAnswer(_client.questionId, value),
          onBack: () => _client.backStage(),
          onRepeat: () => _client.repeatQuestion(),
        );

      case KioskStage.documents:
        return DocumentsScreen(
          headline: _client.headline,
          scannedLines: _scannedDocumentLines,
          isScanning: _isDocumentScanning,
          scanError: _scanError,
          cameraService: _cameraService,
          onScan: _handleDocumentScan,
          onDone: () {
            setState(() {
              _localStage = KioskStage.report;
            });
          },
        );

      case KioskStage.report:
        return ReportScreen(
          reportData: _client.lastReport,
          profile: _patientProfile,
          clinicalAnswers: _clinicalAnswers,
          extractedDocumentLines: _scannedDocumentLines,
          onNewPatient: _resetSession,
        );

      case KioskStage.emergency:
        return EmergencyScreen(
          redFlags: _client.redFlags,
          onStaffAcknowledged: _resetSession,
        );
    }
  }
}
