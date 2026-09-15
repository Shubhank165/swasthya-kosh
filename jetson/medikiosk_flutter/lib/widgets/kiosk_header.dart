import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/kiosk_client.dart';
import '../theme/app_theme.dart';

class KioskHeader extends StatelessWidget {
  final KioskClient client;
  final VoidCallback onBack;
  final VoidCallback onRestart;
  final VoidCallback onConfigureServer;
  final VoidCallback? onEmergency;

  const KioskHeader({
    super.key,
    required this.client,
    required this.onBack,
    required this.onRestart,
    required this.onConfigureServer,
    this.onEmergency,
  });

  @override
  Widget build(BuildContext context) {
    Color connColor;
    String connText;

    switch (client.status) {
      case ConnectionStatus.connected:
        connColor = AppTheme.successGreen;
        connText = 'Online (${client.host})';
        break;
      case ConnectionStatus.connecting:
        connColor = AppTheme.warningOrange;
        connText = 'Connecting...';
        break;
      case ConnectionStatus.reconnecting:
        connColor = AppTheme.alertRed;
        connText = 'Reconnecting';
        break;
      case ConnectionStatus.disconnected:
        connColor = AppTheme.textMuted;
        connText = 'Disconnected';
        break;
    }

    final canGoBack = client.currentStage != KioskStage.language &&
        client.currentStage != KioskStage.report &&
        client.currentStage != KioskStage.emergency;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: const BoxDecoration(
        color: AppTheme.surface,
        border: Border(bottom: BorderSide(color: AppTheme.surfaceBorder, width: 1.5)),
        boxShadow: [
          BoxShadow(
            color: Color(0x050F172A),
            blurRadius: 8,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final isCompact = constraints.maxWidth < 640;

          if (isCompact) {
            // COMPACT MOBILE HEADER
            return Row(
              children: [
                if (canGoBack) ...[
                  IconButton(
                    onPressed: onBack,
                    tooltip: 'Back • पीछे जाएं',
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                    icon: const Icon(Icons.arrow_back_rounded, color: AppTheme.textPrimary, size: 22),
                  ),
                  const SizedBox(width: 4),
                ],
                Container(
                  padding: const EdgeInsets.all(6),
                  decoration: BoxDecoration(
                    color: AppTheme.primaryBlue.withAlpha(20),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(
                    Icons.local_hospital_rounded,
                    color: AppTheme.primaryBlue,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'MediKiosk',
                    style: TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 0.3,
                      color: AppTheme.textPrimary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                // Server Connection Indicator Icon
                IconButton(
                  onPressed: onConfigureServer,
                  tooltip: 'Server: $connText',
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                  icon: Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: connColor,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: connColor.withAlpha(100),
                          blurRadius: 6,
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 4),
                // Emergency SOS icon button
                if (client.currentStage != KioskStage.emergency)
                  IconButton(
                    onPressed: onEmergency,
                    tooltip: 'Emergency SOS • आपातकालीन',
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                    icon: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: AppTheme.alertLight,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppTheme.alertRed.withAlpha(80)),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.warning_amber_rounded, size: 14, color: AppTheme.alertRed),
                          SizedBox(width: 4),
                          Text(
                            'SOS',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.bold,
                              color: AppTheme.alertRed,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                const SizedBox(width: 4),
                // Reset Button
                IconButton(
                  onPressed: onRestart,
                  tooltip: 'New Patient • रीसेट',
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                  icon: const Icon(Icons.refresh_rounded, color: AppTheme.textSecondary, size: 22),
                ),
              ],
            );
          }

          // FULL WIDE KIOSK HEADER
          return Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              // Left: Hospital & Kiosk Logo
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: AppTheme.primaryBlue.withAlpha(20),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(
                      Icons.local_hospital_rounded,
                      color: AppTheme.primaryBlue,
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: const [
                      Text(
                        'MediKiosk',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 0.3,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      Text(
                        'AI Clinical Intake & Triage',
                        style: TextStyle(
                          fontSize: 11,
                          color: AppTheme.textSecondary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ],
              ),

              // Right: Server Connection Pill, Emergency SOS, Back & Reset
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Server Status Badge (Clickable)
                  GestureDetector(
                    onTap: onConfigureServer,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: AppTheme.surfaceHighlight,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: connColor.withAlpha(100)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              color: connColor,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            connText,
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: connColor,
                            ),
                          ),
                          const SizedBox(width: 6),
                          const Icon(Icons.settings_outlined, size: 14, color: AppTheme.textMuted),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(width: 12),

                  // Emergency SOS Button
                  if (client.currentStage != KioskStage.emergency)
                    TextButton.icon(
                      onPressed: onEmergency,
                      style: TextButton.styleFrom(
                        backgroundColor: AppTheme.alertLight,
                        foregroundColor: AppTheme.alertRed,
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      ),
                      icon: const Icon(Icons.warning_amber_rounded, size: 16, color: AppTheme.alertRed),
                      label: const Text(
                        'आपातकालीन (SOS)',
                        style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppTheme.alertRed),
                      ),
                    ),

                  const SizedBox(width: 8),

                  // Back Button
                  if (canGoBack)
                    IconButton(
                      onPressed: onBack,
                      tooltip: 'पीछे जाएं (Back)',
                      icon: const Icon(Icons.arrow_back_rounded, color: AppTheme.textPrimary, size: 22),
                    ),

                  const SizedBox(width: 6),

                  // Reset Button
                  OutlinedButton.icon(
                    onPressed: onRestart,
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      side: const BorderSide(color: AppTheme.surfaceBorderStrong),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    ),
                    icon: const Icon(Icons.refresh_rounded, size: 16, color: AppTheme.textSecondary),
                    label: const Text(
                      'Reset',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                    ),
                  ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}
