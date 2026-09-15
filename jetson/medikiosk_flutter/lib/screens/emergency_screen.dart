import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class EmergencyScreen extends StatefulWidget {
  final List<Map<String, dynamic>> redFlags;
  final VoidCallback onStaffAcknowledged;

  const EmergencyScreen({
    super.key,
    this.redFlags = const [],
    required this.onStaffAcknowledged,
  });

  @override
  State<EmergencyScreen> createState() => _EmergencyScreenState();
}

class _EmergencyScreenState extends State<EmergencyScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _flashController;

  @override
  void initState() {
    super.initState();
    _flashController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _flashController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _flashController,
      builder: (context, child) {
        final glowAlpha = (60 + (80 * _flashController.value)).toInt();

        return Container(
          constraints: const BoxConstraints(maxWidth: 720),
          padding: const EdgeInsets.all(32),
          decoration: BoxDecoration(
            color: AppTheme.surface,
            borderRadius: BorderRadius.circular(32),
            border: Border.all(
              color: AppTheme.alertRedBright,
              width: 4,
            ),
            boxShadow: [
              BoxShadow(
                color: AppTheme.alertRedBright.withAlpha(glowAlpha),
                blurRadius: 36,
                spreadRadius: 4,
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Flashing Emergency Beacon Icon
              Container(
                width: 96,
                height: 96,
                decoration: BoxDecoration(
                  color: AppTheme.alertRedBright.withAlpha(50),
                  shape: BoxShape.circle,
                  border: Border.all(color: AppTheme.alertRedBright, width: 4),
                ),
                child: const Center(
                  child: Icon(
                    Icons.warning_amber_rounded,
                    size: 58,
                    color: AppTheme.alertRedBright,
                  ),
                ),
              ),
              const SizedBox(height: 24),

              const Text(
                'तुरंत आपातकालीन सहायता बुलाई गई है!',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: AppTheme.alertRedBright,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),

              const Text(
                'EMERGENCY: Immediate Medical Attention Required',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: AppTheme.textPrimary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),

              Container(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                decoration: BoxDecoration(
                  color: AppTheme.alertLight,
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: AppTheme.alertRed.withAlpha(50)),
                ),
                child: const Text(
                  'आपने जो लक्षण बताए हैं, उनके लिए तुरंत डॉक्टर की जाँच ज़रूरी है।\nकृपया यहीं बैठें, अस्पताल स्टाफ़ आपके पास आ रहा है।\n(Please remain seated. Medical staff is alerted and approaching now.)',
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.5,
                    color: AppTheme.textPrimary,
                    fontWeight: FontWeight.w600,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 28),

              ElevatedButton.icon(
                onPressed: widget.onStaffAcknowledged,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.alertRedBright,
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
                ),
                icon: const Icon(Icons.medical_services, size: 22),
                label: const Text(
                  'स्टाफ़ द्वारा सत्यापित (Staff Acknowledged)',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
