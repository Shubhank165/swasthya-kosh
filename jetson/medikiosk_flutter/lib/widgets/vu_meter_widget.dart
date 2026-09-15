import 'dart:math';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class VuMeterWidget extends StatefulWidget {
  final bool isListening;
  final bool isMuted;
  final bool isProcessing;
  final double? audioLevel; // 0.0 to 1.0

  const VuMeterWidget({
    super.key,
    required this.isListening,
    required this.isMuted,
    this.isProcessing = false,
    this.audioLevel,
  });

  @override
  State<VuMeterWidget> createState() => _VuMeterWidgetState();
}

class _VuMeterWidgetState extends State<VuMeterWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Color badgeColor;
    String statusText;
    IconData statusIcon;

    if (widget.isProcessing) {
      badgeColor = AppTheme.warningOrange;
      statusText = 'आवाज़ समझ रहे हैं... (Processing)';
      statusIcon = Icons.auto_awesome;
    } else if (widget.isMuted) {
      badgeColor = AppTheme.textMuted;
      statusText = 'माइक बंद है (Mic Muted)';
      statusIcon = Icons.mic_off;
    } else if (widget.isListening) {
      badgeColor = AppTheme.successGreenBright;
      statusText = 'माइक चालू है, बोलिए (Listening...)';
      statusIcon = Icons.mic;
    } else {
      badgeColor = AppTheme.primaryBlue;
      statusText = 'माइक तैयार (Ready)';
      statusIcon = Icons.mic_none;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.surfaceHighlight,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: badgeColor.withAlpha(120), width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(statusIcon, color: badgeColor, size: 20),
          const SizedBox(width: 8),
          Text(
            statusText,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: badgeColor,
            ),
          ),
          if (widget.isListening && !widget.isMuted) ...[
            const SizedBox(width: 12),
            // Waveform simulation bars
            AnimatedBuilder(
              animation: _animController,
              builder: (context, _) {
                return Row(
                  mainAxisSize: MainAxisSize.min,
                  children: List.generate(5, (index) {
                    final height = 6.0 +
                        (_random.nextDouble() * 14 * _animController.value);
                    return Container(
                      margin: const EdgeInsets.symmetric(horizontal: 1.5),
                      width: 3.5,
                      height: height,
                      decoration: BoxDecoration(
                        color: badgeColor,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    );
                  }),
                );
              },
            ),
          ],
        ],
      ),
    );
  }
}
