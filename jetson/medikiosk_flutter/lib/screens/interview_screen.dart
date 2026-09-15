import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../widgets/body_map_widget.dart';
import '../widgets/faces_severity_widget.dart';
import '../widgets/duration_sun_widget.dart';
import '../widgets/symptom_card_widget.dart';
import '../widgets/vu_meter_widget.dart';

class InterviewScreen extends StatefulWidget {
  final String questionText;
  final String? questionId;
  final String? answerUi;
  final bool isListening;
  final double soundLevel;
  final VoidCallback? onRepeat;
  final String? lastTranscript;
  final bool isProcessing;
  final ValueChanged<String> onSubmitAnswer;
  final VoidCallback? onCompleteIntake;

  const InterviewScreen({
    super.key,
    required this.questionText,
    this.questionId,
    this.answerUi,
    this.isListening = false,
    this.soundLevel = 0,
    this.onRepeat,
    this.lastTranscript,
    this.isProcessing = false,
    required this.onSubmitAnswer,
    this.onCompleteIntake,
  });

  @override
  State<InterviewScreen> createState() => _InterviewScreenState();
}

class _InterviewScreenState extends State<InterviewScreen> {
  BodyZone? _selectedZone;
  int? _selectedSeverity;
  String? _selectedDuration;
  bool _showBodyMap = true;
  final _typedAnswer = TextEditingController();
  @override
  void dispose() {
    _typedAnswer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final qId = widget.questionId ?? 'ask_complaint';

    return Container(
      constraints: const BoxConstraints(maxWidth: 860),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Voice Bar & Microphone Status
          VuMeterWidget(
            isListening: widget.isListening,
            isMuted: !widget.isListening,
            audioLevel: widget.soundLevel,
            isProcessing: widget.isProcessing,
          ),
          const SizedBox(height: 16),

          // Clinical Question Headline Banner
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
            decoration: BoxDecoration(
              color: AppTheme.surface,
              borderRadius: BorderRadius.circular(22),
              border: Border.all(
                color: AppTheme.primaryBlue.withAlpha(80),
                width: 2,
              ),
              boxShadow: AppTheme.cardShadow,
            ),
            child: Column(
              children: [
                Text(
                  widget.questionText.isNotEmpty ? widget.questionText : 'आज आपको क्या परेशानी है? बोलिए या स्क्रीन पर छूकर बताएं',
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: AppTheme.textPrimary,
                  ),
                  textAlign: TextAlign.center,
                ),
                if (widget.lastTranscript != null &&
                    widget.lastTranscript!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    'सुना गया (Heard): “${widget.lastTranscript}”',
                    style: const TextStyle(
                      fontSize: 14,
                      color: AppTheme.primaryDark,
                      fontWeight: FontWeight.w600,
                      fontStyle: FontStyle.italic,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 24),

          // DYNAMIC ICON-DRIVEN QUESTION INTERFACE
          if (widget.answerUi == 'yes_no')
            SymptomCardWidget(
              titleHi: widget.questionText,
              titleEn: '',
              icon: Icons.help_outline,
              accentColor: AppTheme.accentCyan,
              onYes: () => widget.onSubmitAnswer('yes'),
              onNo: () => widget.onSubmitAnswer('no'),
            )
          else
            _buildVisualQuestionComponent(qId),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.surface,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: AppTheme.surfaceBorder),
              boxShadow: AppTheme.cardShadow,
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _typedAnswer,
                    enabled: !widget.isProcessing,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: AppTheme.textPrimary,
                    ),
                    decoration: const InputDecoration(
                      hintText: 'उत्तर लिखें या बोलें (Type or speak answer)...',
                      hintStyle: TextStyle(
                        fontSize: 13,
                        color: AppTheme.textMuted,
                      ),
                      border: InputBorder.none,
                      contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 12),
                    ),
                    onSubmitted: (value) {
                      if (value.trim().isNotEmpty) {
                        widget.onSubmitAnswer(value.trim());
                        _typedAnswer.clear();
                      }
                    },
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send_rounded, color: AppTheme.primaryBlue),
                  tooltip: 'Submit Answer',
                  onPressed: () {
                    if (_typedAnswer.text.trim().isNotEmpty) {
                      widget.onSubmitAnswer(_typedAnswer.text.trim());
                      _typedAnswer.clear();
                    }
                  },
                ),
                if (widget.onRepeat != null) ...[
                  const SizedBox(width: 4),
                  IconButton(
                    onPressed: widget.onRepeat,
                    tooltip: 'Repeat question • प्रश्न दोहराएं',
                    icon: const Icon(Icons.volume_up_rounded, color: AppTheme.textSecondary),
                  ),
                ],
              ],
            ),
          ),
          if (widget.onCompleteIntake != null) ...[
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 52,
              child: ElevatedButton.icon(
                onPressed: widget.onCompleteIntake,
                icon: const Icon(Icons.receipt_long_rounded, size: 22),
                label: const Text(
                  'जाँच पूर्ण करें • पर्ची देखें (Complete Intake & View Slip)',
                  style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.tealAccent,
                  foregroundColor: Colors.white,
                  elevation: 2,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildVisualQuestionComponent(String qId) {
    switch (qId) {
      case 'ask_complaint':
        return _buildComplaintBodyMapAndCards();

      case 'ask_duration':
        return DurationSunWidget(
          selectedDuration: _selectedDuration,
          onSelected: (opt) {
            setState(() => _selectedDuration = opt.value);
            widget.onSubmitAnswer(opt.serverValue);
          },
        );

      case 'ask_severity':
        return FacesSeverityWidget(
          selectedScore: _selectedSeverity,
          onScoreSelected: (score) {
            setState(() => _selectedSeverity = score);
            widget.onSubmitAnswer('$score');
          },
        );

      case 'ask_breathlessness':
        return SymptomCardWidget(
          titleHi: 'क्या आपको साँस लेने में तकलीफ़ हो रही है?',
          titleEn: 'Are you having difficulty breathing?',
          icon: Icons.air,
          accentColor: AppTheme.accentCyan,
          onYes: () => widget.onSubmitAnswer('yes'),
          onNo: () => widget.onSubmitAnswer('no'),
        );

      case 'ask_radiation':
        return SymptomCardWidget(
          titleHi: 'क्या दर्द बाँह, पीठ, गर्दन या जबड़े की तरफ फैल रहा है?',
          titleEn: 'Does pain radiate to left arm, neck, back, or jaw?',
          icon: Icons.alt_route,
          accentColor: AppTheme.alertRedBright,
          onYes: () => widget.onSubmitAnswer('yes'),
          onNo: () => widget.onSubmitAnswer('no'),
        );

      case 'ask_sweating':
        return SymptomCardWidget(
          titleHi: 'क्या इस दर्द के साथ असामान्य पसीना आ रहा है?',
          titleEn: 'Are you experiencing unusual sweating with this?',
          icon: Icons.water_drop,
          accentColor: AppTheme.warningOrange,
          onYes: () => widget.onSubmitAnswer('yes'),
          onNo: () => widget.onSubmitAnswer('no'),
        );

      case 'ask_vomiting':
        return SymptomCardWidget(
          titleHi: 'क्या आपको उल्टी या जी मिचलाने की शिकायत है?',
          titleEn: 'Are you vomiting or feeling nauseous?',
          icon: Icons.sick,
          accentColor: AppTheme.purpleAccent,
          onYes: () => widget.onSubmitAnswer('yes'),
          onNo: () => widget.onSubmitAnswer('no'),
        );

      case 'ask_fever':
        return SymptomCardWidget(
          titleHi: 'क्या आपको बुखार या शरीर तपने की तकलीफ़ है?',
          titleEn: 'Do you have a fever or chills?',
          icon: Icons.thermostat,
          accentColor: AppTheme.alertRedBright,
          onYes: () => widget.onSubmitAnswer('yes'),
          onNo: () => widget.onSubmitAnswer('no'),
        );

      case 'ask_bleeding':
        return SymptomCardWidget(
          titleHi: 'क्या कहीं से ख़ून बह रहा है?',
          titleEn: 'Is there any active bleeding?',
          icon: Icons.bloodtype,
          accentColor: AppTheme.alertRedBright,
          onYes: () => widget.onSubmitAnswer('yes'),
          onNo: () => widget.onSubmitAnswer('no'),
        );

      case 'ask_age':
        return _buildAgeSelector();

      default:
        return _buildComplaintBodyMapAndCards();
    }
  }

  Widget _buildComplaintBodyMapAndCards() {
    return Column(
      children: [
        // Mode Switcher: Body Map vs Quick Symptom Icons
        Wrap(
          spacing: 12,
          runSpacing: 12,
          alignment: WrapAlignment.center,
          children: [
            ElevatedButton.icon(
              onPressed: () => setState(() => _showBodyMap = true),
              style: ElevatedButton.styleFrom(
                backgroundColor: _showBodyMap
                    ? AppTheme.primaryBlue
                    : AppTheme.surfaceHighlight,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
              ),
              icon: const Icon(Icons.accessibility, size: 20),
              label: const Text('शरीर पर बताएं (Body Map)'),
            ),
            ElevatedButton.icon(
              onPressed: () => setState(() => _showBodyMap = false),
              style: ElevatedButton.styleFrom(
                backgroundColor: !_showBodyMap
                    ? AppTheme.primaryBlue
                    : AppTheme.surfaceHighlight,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 10,
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
              ),
              icon: const Icon(Icons.grid_view, size: 20),
              label: const Text('लक्षण कार्ड (Icons)'),
            ),
          ],
        ),
        const SizedBox(height: 20),

        if (_showBodyMap)
          BodyMapWidget(
            selectedZone: _selectedZone,
            onZoneSelected: (zone) {
              setState(() => _selectedZone = zone);
              final meta = bodyZoneMetadata[zone]!;
              widget.onSubmitAnswer('${meta.labelHi} ${meta.commonComplaint}');
            },
          )
        else
          Wrap(
            spacing: 16,
            runSpacing: 16,
            alignment: WrapAlignment.center,
            children: [
              _buildSymptomChip(
                'छाती में दर्द',
                'Chest Pain',
                'chest pain',
                Icons.favorite,
                AppTheme.alertRedBright,
              ),
              _buildSymptomChip(
                'साँस लेने में दिक्कत',
                'Breathlessness',
                'difficulty breathing shortness of breath',
                Icons.air,
                AppTheme.accentCyan,
              ),
              _buildSymptomChip(
                'पेट में दर्द',
                'Stomach Pain',
                'severe stomach abdominal pain',
                Icons.medical_services,
                AppTheme.warningOrange,
              ),
              _buildSymptomChip(
                'सिरदर्द व चक्कर',
                'Headache',
                'severe headache and dizziness',
                Icons.face,
                AppTheme.purpleAccent,
              ),
              _buildSymptomChip(
                'तेज़ बुखार',
                'High Fever',
                'high fever and chills',
                Icons.thermostat,
                AppTheme.alertRedBright,
              ),
              _buildSymptomChip(
                'उल्टी व दस्त',
                'Vomiting / Diarrhea',
                'vomiting and diarrhea',
                Icons.sick,
                AppTheme.warningOrange,
              ),
              _buildSymptomChip(
                'जोड़ों / पैरों में दर्द',
                'Joint Pain',
                'severe leg and knee joint pain',
                Icons.directions_walk,
                AppTheme.primaryBlue,
              ),
              _buildSymptomChip(
                'कमर व पीठ दर्द',
                'Back Pain',
                'severe lower back pain',
                Icons.accessibility_new,
                AppTheme.textSecondary,
              ),
            ],
          ),
      ],
    );
  }

  Widget _buildSymptomChip(
    String labelHi,
    String labelEn,
    String transcript,
    IconData icon,
    Color color,
  ) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => widget.onSubmitAnswer(transcript),
      child: Container(
        width: 170,
        padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 12),
        decoration: BoxDecoration(
          color: AppTheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withAlpha(120), width: 1.5),
          boxShadow: AppTheme.cardShadow,
        ),
        child: Column(
          children: [
            Icon(icon, size: 38, color: color),
            const SizedBox(height: 10),
            Text(
              labelHi,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
                color: AppTheme.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 2),
            Text(
              labelEn,
              style: const TextStyle(
                fontSize: 12,
                color: AppTheme.textSecondary,
                fontWeight: FontWeight.w500,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAgeSelector() => const Text(
    'Enter your age in years below / अपनी उम्र वर्षों में लिखें',
    textAlign: TextAlign.center,
  );
}
