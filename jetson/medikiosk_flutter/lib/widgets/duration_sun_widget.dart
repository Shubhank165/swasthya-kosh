import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class DurationOption {
  final String value;
  final String labelHi;
  final String labelEn;
  final String iconEmoji;
  final String serverValue;

  const DurationOption({
    required this.value,
    required this.labelHi,
    required this.labelEn,
    required this.iconEmoji,
    required this.serverValue,
  });
}

const List<DurationOption> durationOptions = [
  DurationOption(
    value: 'today',
    labelHi: 'आज से शुरू हुआ',
    labelEn: 'Started today',
    iconEmoji: '☀️',
    serverValue: 'today',
  ),
  DurationOption(
    value: 'few_days',
    labelHi: '2 - 3 दिन से',
    labelEn: '2 to 3 days',
    iconEmoji: '🌅',
    serverValue: 'three days',
  ),
  DurationOption(
    value: 'one_week',
    labelHi: 'लगभग 1 हफ़्ते से',
    labelEn: 'About 1 week',
    iconEmoji: '📅',
    serverValue: 'one week',
  ),
  DurationOption(
    value: 'one_month',
    labelHi: '1 महीने या ज़्यादा से',
    labelEn: 'Over a month',
    iconEmoji: '🌕',
    serverValue: 'one month',
  ),
];

class DurationSunWidget extends StatelessWidget {
  final String? selectedDuration;
  final ValueChanged<DurationOption> onSelected;

  const DurationSunWidget({
    super.key,
    this.selectedDuration,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Text(
          'यह परेशानी कब से है? (How long have you had this?)',
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.bold,
            color: AppTheme.textPrimary,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 18),
        Wrap(
          spacing: 16,
          runSpacing: 16,
          alignment: WrapAlignment.center,
          children: durationOptions.map((opt) {
            final isSelected = selectedDuration == opt.value;

            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onSelected(opt),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 150,
                padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
                decoration: BoxDecoration(
                  color: isSelected
                      ? AppTheme.warningLight
                      : AppTheme.surface,
                  borderRadius: BorderRadius.circular(22),
                  border: Border.all(
                    color: isSelected ? AppTheme.warningOrange : AppTheme.surfaceBorder,
                    width: isSelected ? 3.0 : 1.5,
                  ),
                  boxShadow: isSelected
                      ? [
                          BoxShadow(
                            color: AppTheme.warningOrange.withAlpha(60),
                            blurRadius: 14,
                            spreadRadius: 1,
                          ),
                        ]
                      : AppTheme.cardShadow,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      opt.iconEmoji,
                      style: const TextStyle(fontSize: 48),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      opt.labelHi,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      opt.labelEn,
                      style: const TextStyle(
                        fontSize: 12,
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
      ],
    );
  }
}
