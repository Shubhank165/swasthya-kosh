import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';

class PathwayHubScreen extends StatelessWidget {
  final PatientProfile? profile;
  final VoidCallback onSelectSymptoms;
  /// Null when this kiosk's backend does not offer a camera measurement.
  final VoidCallback? onSelectVitals;
  final VoidCallback onBackToRegistration;

  const PathwayHubScreen({
    super.key,
    this.profile,
    required this.onSelectSymptoms,
    this.onSelectVitals,
    required this.onBackToRegistration,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 860),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final isNarrow = constraints.maxWidth < 650;

              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Patient Profile Summary Pill
                  if (profile != null) Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    decoration: BoxDecoration(
                      color: AppTheme.surface,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: AppTheme.surfaceBorder),
                      boxShadow: AppTheme.cardShadow,
                    ),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(
                            color: AppTheme.primaryBlue.withAlpha(20),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(Icons.person_rounded, color: AppTheme.primaryBlue, size: 20),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                profile!.name,
                                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              Text(
                                'Age: ${profile!.age ?? "--"} yrs • ${profile!.gender} • ${profile!.maskedAbha}',
                                style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                        TextButton(
                          onPressed: onBackToRegistration,
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          child: const Text('Edit / बदलें', style: TextStyle(fontSize: 12, color: AppTheme.primaryBlue, fontWeight: FontWeight.bold)),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),

                  const Text(
                    'आप क्या जांचना चाहते हैं? / Select Service',
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Choose one option below • नीचे से एक विकल्प चुनें',
                    style: TextStyle(fontSize: 13, color: AppTheme.textSecondary),
                    textAlign: TextAlign.center,
                  ),

                  const SizedBox(height: 20),

                  // Pathway Cards (Responsive: Column on narrow, Row on wide)
                  if (isNarrow) ...[
                    _buildSymptomsCard(isNarrow),
                    const SizedBox(height: 16),
                  ] else ...[
                    _buildSymptomsCard(isNarrow),
                  ],
                  // Full width under the pair, so one card does not have to fit a half column.
                  if (onSelectVitals != null) ...[
                    const SizedBox(height: 16),
                    _buildVitalsCard(isNarrow),
                  ],
                ],
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildSymptomsCard(bool isNarrow) {
    return Material(
      color: AppTheme.surface,
      elevation: 2,
      shadowColor: Colors.black12,
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        onTap: onSelectSymptoms,
        borderRadius: BorderRadius.circular(24),
        child: Container(
          padding: EdgeInsets.all(isNarrow ? 18 : 24),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: AppTheme.primaryBlue.withAlpha(120), width: 2),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Top Icon & Tag
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTheme.primaryBlue.withAlpha(25),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(Icons.medical_services_rounded, color: AppTheme.primaryBlue, size: 28),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTheme.primaryBlue.withAlpha(20),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Text(
                      'CLINICAL INTAKE',
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.primaryBlue),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),

              // Title
              const Text(
                'लक्षण एवं स्वास्थ्य जाँच',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
              ),
              const SizedBox(height: 2),
              const Text(
                'Symptoms Assessment',
                style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppTheme.primaryDark),
              ),
              const SizedBox(height: 12),

              // Description Bullet Points
              _buildBullet(Icons.mic_rounded, 'Speak or touch answers (बोलें या स्क्रीन छुएं)'),
              const SizedBox(height: 6),
              _buildBullet(Icons.emergency_rounded, 'Emergency red-flag triage detection'),
              const SizedBox(height: 6),
              _buildBullet(Icons.document_scanner_rounded, 'Prescription OCR scan & OPD queue routing'),

              const SizedBox(height: 18),

              // Button
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton.icon(
                  onPressed: onSelectSymptoms,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.primaryBlue,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  icon: const Icon(Icons.arrow_forward_rounded, size: 18),
                  label: const Text('शुरू करें (Start Symptoms)', style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }


  Widget _buildVitalsCard(bool isNarrow) {
    return Material(
      color: AppTheme.surface,
      elevation: 2,
      shadowColor: Colors.black12,
      borderRadius: BorderRadius.circular(24),
      child: InkWell(
        onTap: onSelectVitals,
        borderRadius: BorderRadius.circular(24),
        child: Container(
          padding: EdgeInsets.all(isNarrow ? 18 : 24),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: AppTheme.primaryBlue.withAlpha(120), width: 2),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTheme.primaryBlue.withAlpha(25),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(Icons.favorite_rounded, color: AppTheme.primaryBlue, size: 28),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTheme.primaryBlue.withAlpha(20),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Text(
                      'CAMERA MEASUREMENT',
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppTheme.primaryBlue),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              const Text(
                'हृदय गति जाँच',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
              ),
              const SizedBox(height: 4),
              const Text(
                'Check my heart rate',
                style: TextStyle(fontSize: 13, color: AppTheme.textSecondary),
              ),
              const SizedBox(height: 12),
              _buildBullet(Icons.videocam_rounded, 'Look at the camera, sit still for twenty seconds'),
              const SizedBox(height: 6),
              _buildBullet(Icons.info_outline_rounded, 'An estimate for staff to review, not a diagnosis'),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBullet(IconData icon, String text) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 16, color: AppTheme.textSecondary),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text,
            style: const TextStyle(fontSize: 12, color: AppTheme.textSecondary, height: 1.3),
          ),
        ),
      ],
    );
  }
}
