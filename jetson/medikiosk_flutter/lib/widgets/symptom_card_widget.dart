import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class SymptomCardWidget extends StatelessWidget {
  final String titleHi;
  final String titleEn;
  final IconData icon;
  final Color accentColor;
  final VoidCallback onYes;
  final VoidCallback onNo;
  final bool? currentValue;

  const SymptomCardWidget({
    super.key,
    required this.titleHi,
    required this.titleEn,
    required this.icon,
    this.accentColor = AppTheme.primaryBlue,
    required this.onYes,
    required this.onNo,
    this.currentValue,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 480),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: AppTheme.surfaceBorder, width: 2),
        boxShadow: AppTheme.elevatedCardShadow,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Large Animated Icon Container
          Container(
            width: 100,
            height: 100,
            decoration: BoxDecoration(
              color: accentColor.withAlpha(25),
              shape: BoxShape.circle,
              border: Border.all(color: accentColor, width: 3),
            ),
            child: Center(
              child: Icon(icon, size: 52, color: accentColor),
            ),
          ),
          const SizedBox(height: 20),

          // Hindi Title
          Text(
            titleHi,
            style: const TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: AppTheme.textPrimary,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 6),

          // English Subtitle
          Text(
            titleEn,
            style: const TextStyle(
              fontSize: 15,
              color: AppTheme.textSecondary,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 28),

          // Big YES / NO pictorial touchcards
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // NO Button
              Expanded(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onNo,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(vertical: 20),
                    decoration: BoxDecoration(
                      color: currentValue == false
                          ? AppTheme.alertLight
                          : AppTheme.surfaceHighlight,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: currentValue == false
                            ? AppTheme.alertRed
                            : AppTheme.surfaceBorder,
                        width: currentValue == false ? 3.5 : 1.5,
                      ),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: const [
                        Icon(Icons.close_rounded, size: 48, color: AppTheme.alertRed),
                        SizedBox(height: 8),
                        Text(
                          'नहीं (NO)',
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                            color: AppTheme.alertRed,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 20),

              // YES Button
              Expanded(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onYes,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(vertical: 20),
                    decoration: BoxDecoration(
                      color: currentValue == true
                          ? AppTheme.successLight
                          : AppTheme.surfaceHighlight,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: currentValue == true
                            ? AppTheme.successGreen
                            : AppTheme.surfaceBorder,
                        width: currentValue == true ? 3.5 : 1.5,
                      ),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: const [
                        Icon(Icons.check_rounded, size: 48, color: AppTheme.successGreenBright),
                        SizedBox(height: 8),
                        Text(
                          'हाँ (YES)',
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                            color: AppTheme.successGreenBright,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
