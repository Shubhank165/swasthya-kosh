import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';

class LanguageScreen extends StatelessWidget {
  final String selectedLanguage;
  final ValueChanged<String> onLanguageSelected;
  final VoidCallback onRepeatAudio;
  /// Backend language codes ('en', 'hi') to offer; null shows every card.
  final List<String>? codes;

  const LanguageScreen({
    super.key,
    required this.selectedLanguage,
    required this.onLanguageSelected,
    required this.onRepeatAudio,
    this.codes,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 880),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              // Headline & Audio Prompt Indicator
              Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: AppTheme.surface,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: AppTheme.surfaceBorder),
                  boxShadow: AppTheme.cardShadow,
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: AppTheme.primaryBlue.withAlpha(25),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.translate_rounded,
                        color: AppTheme.primaryBlue,
                        size: 22,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: const [
                          FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: Alignment.centerLeft,
                            child: Text(
                              'अपनी भाषा चुनें / Select Language',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                color: AppTheme.textPrimary,
                              ),
                            ),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Touch an icon below • स्क्रीन पर छूकर चुनें',
                            style: TextStyle(
                              fontSize: 12,
                              color: AppTheme.textSecondary,
                              fontWeight: FontWeight.w500,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    IconButton(
                      icon: const Icon(Icons.volume_up_rounded, color: AppTheme.primaryBlue, size: 24),
                      tooltip: 'Repeat: "Select Language"',
                      onPressed: onRepeatAudio,
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 24),

              // Icon-based Grid of Languages
              LayoutBuilder(
                builder: (context, constraints) {
                  final cardWidth = constraints.maxWidth < 580
                      ? constraints.maxWidth
                      : (constraints.maxWidth < 840 ? (constraints.maxWidth - 16) / 2 : 260.0);

                  return Wrap(
                    spacing: 16,
                    runSpacing: 16,
                    alignment: WrapAlignment.center,
                    children: supportedLanguages.where((lang) =>
                        codes == null || codes!.contains(lang.code.split('-').first)).map((lang) {
                      final short = lang.code.split('-').first;
                      final isSelected = selectedLanguage == lang.code || selectedLanguage == short;

                      return SizedBox(
                        width: cardWidth,
                        height: 110,
                    child: Material(
                      color: isSelected ? AppTheme.surfaceHighlight : AppTheme.surface,
                      elevation: isSelected ? 4 : 1,
                      shadowColor: Colors.black12,
                      borderRadius: BorderRadius.circular(20),
                      child: InkWell(
                        onTap: () => onLanguageSelected(short),
                        borderRadius: BorderRadius.circular(20),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(
                              color: isSelected ? AppTheme.primaryBlue : AppTheme.surfaceBorder,
                              width: isSelected ? 2.5 : 1.2,
                            ),
                          ),
                          child: Row(
                            children: [
                              // Script Emblem Icon Circle
                              Container(
                                width: 58,
                                height: 58,
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    begin: Alignment.topLeft,
                                    end: Alignment.bottomRight,
                                    colors: isSelected
                                        ? [AppTheme.primaryBlue, AppTheme.accentCyan]
                                        : [
                                            AppTheme.primaryBlue.withAlpha(25),
                                            AppTheme.tealAccent.withAlpha(20),
                                          ],
                                  ),
                                  shape: BoxShape.circle,
                                  boxShadow: isSelected
                                      ? [
                                          BoxShadow(
                                            color: AppTheme.primaryBlue.withAlpha(70),
                                            blurRadius: 10,
                                            offset: const Offset(0, 3),
                                          )
                                        ]
                                      : null,
                                ),
                                alignment: Alignment.center,
                                child: Text(
                                  lang.scriptEmblem,
                                  style: TextStyle(
                                    fontSize: 26,
                                    fontWeight: FontWeight.bold,
                                    color: isSelected ? Colors.white : AppTheme.primaryBlue,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 14),
                              // Language Names
                              Expanded(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      lang.nativeName,
                                      style: TextStyle(
                                        fontSize: 20,
                                        fontWeight: FontWeight.w700,
                                        color: isSelected ? AppTheme.primaryDark : AppTheme.textPrimary,
                                      ),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      '${lang.englishName} • ${lang.greeting}',
                                      style: const TextStyle(
                                        fontSize: 12,
                                        color: AppTheme.textSecondary,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                              if (isSelected)
                                const Icon(
                                  Icons.check_circle_rounded,
                                  color: AppTheme.primaryBlue,
                                  size: 24,
                                ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              );
            },
          ),

              const SizedBox(height: 24),

              // Helper Footer Pill
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  color: AppTheme.surfaceHighlight,
                  borderRadius: BorderRadius.circular(30),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.touch_app_rounded, size: 16, color: AppTheme.textSecondary),
                    SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        'Touch your language to begin • आगे बढ़ने के लिए भाषा चुनें',
                        style: TextStyle(fontSize: 12, color: AppTheme.textSecondary, fontWeight: FontWeight.w500),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
