import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class FaceScore {
  final int score;
  final String labelHi;
  final String labelEn;
  final Color color;
  final String emoji;

  const FaceScore({
    required this.score,
    required this.labelHi,
    required this.labelEn,
    required this.color,
    required this.emoji,
  });
}

const List<FaceScore> wongBakerFaces = [
  FaceScore(
    score: 0,
    labelHi: 'कोई दर्द नहीं',
    labelEn: 'No Hurt',
    color: Color(0xFF2EA043),
    emoji: '😊',
  ),
  FaceScore(
    score: 2,
    labelHi: 'हल्का दर्द',
    labelEn: 'Hurts Little Bit',
    color: Color(0xFF7EE787),
    emoji: '🙂',
  ),
  FaceScore(
    score: 4,
    labelHi: 'थोड़ा ज़्यादा दर्द',
    labelEn: 'Hurts Little More',
    color: Color(0xFFD29922),
    emoji: '😐',
  ),
  FaceScore(
    score: 6,
    labelHi: 'काफ़ी दर्द',
    labelEn: 'Hurts Even More',
    color: Color(0xFFFA8E3D),
    emoji: '😟',
  ),
  FaceScore(
    score: 8,
    labelHi: 'बहुत तेज़ दर्द',
    labelEn: 'Hurts Whole Lot',
    color: Color(0xFFF85149),
    emoji: '😢',
  ),
  FaceScore(
    score: 10,
    labelHi: 'असहनीय भयंकर दर्द',
    labelEn: 'Worst Hurt Possible',
    color: Color(0xFFDA3633),
    emoji: '😭',
  ),
];

class FacesSeverityWidget extends StatelessWidget {
  final int? selectedScore;
  final ValueChanged<int> onScoreSelected;

  const FacesSeverityWidget({
    super.key,
    this.selectedScore,
    required this.onScoreSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        const Text(
          'दर्द कितना तेज़ है? छूकर बताएं (Tap your pain level)',
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.bold,
            color: AppTheme.textPrimary,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 18),

        // Grid of 6 FACES
        Wrap(
          spacing: 12,
          runSpacing: 12,
          alignment: WrapAlignment.center,
          children: wongBakerFaces.map((face) {
            final isSelected = selectedScore == face.score;

            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onScoreSelected(face.score),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 140,
                padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
                decoration: BoxDecoration(
                  color: isSelected
                      ? face.color.withAlpha(30)
                      : AppTheme.surface,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: isSelected ? face.color : AppTheme.surfaceBorder,
                    width: isSelected ? 3.0 : 1.5,
                  ),
                  boxShadow: isSelected
                      ? [
                          BoxShadow(
                            color: face.color.withAlpha(60),
                            blurRadius: 12,
                            spreadRadius: 1,
                          ),
                        ]
                      : AppTheme.cardShadow,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Big Emoji Face
                    Text(
                      face.emoji,
                      style: const TextStyle(fontSize: 48),
                    ),
                    const SizedBox(height: 6),

                    // Number Score badge
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: face.color,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        '${face.score}',
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),

                    // Hindi Text
                    Text(
                      face.labelHi,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                      textAlign: TextAlign.center,
                      maxLines: 2,
                    ),

                    // English Subtext
                    Text(
                      face.labelEn,
                      style: const TextStyle(
                        fontSize: 11,
                        color: AppTheme.textSecondary,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),

        const SizedBox(height: 16),

        if (selectedScore != null) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppTheme.accentCyan),
            ),
            child: Text(
              'चयनित दर्द स्कोर (Selected): $selectedScore / 10',
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
                color: AppTheme.accentCyan,
              ),
            ),
          ),
        ],
      ],
    );
  }
}
