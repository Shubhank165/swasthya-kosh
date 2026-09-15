import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

enum BodyZone {
  head,
  throat,
  chest,
  abdomen,
  arms,
  back,
  legs,
}

class BodyZoneData {
  final BodyZone zone;
  final String labelEn;
  final String labelHi;
  final IconData icon;
  final String commonComplaint;

  const BodyZoneData({
    required this.zone,
    required this.labelEn,
    required this.labelHi,
    required this.icon,
    required this.commonComplaint,
  });
}

const Map<BodyZone, BodyZoneData> bodyZoneMetadata = {
  BodyZone.head: BodyZoneData(
    zone: BodyZone.head,
    labelEn: 'Head / Eyes / Ears',
    labelHi: 'सिर / आँख / कान',
    icon: Icons.face,
    commonComplaint: 'severe headache and dizziness',
  ),
  BodyZone.throat: BodyZoneData(
    zone: BodyZone.throat,
    labelEn: 'Throat / Neck',
    labelHi: 'गला / गर्दन',
    icon: Icons.record_voice_over,
    commonComplaint: 'sore throat and difficulty swallowing',
  ),
  BodyZone.chest: BodyZoneData(
    zone: BodyZone.chest,
    labelEn: 'Chest / Heart',
    labelHi: 'सीना / छाती / दिल',
    icon: Icons.favorite,
    commonComplaint: 'crushing chest pain',
  ),
  BodyZone.abdomen: BodyZoneData(
    zone: BodyZone.abdomen,
    labelEn: 'Stomach / Abdomen',
    labelHi: 'पेट / हाजमा',
    icon: Icons.medical_services_outlined,
    commonComplaint: 'severe abdominal stomach pain',
  ),
  BodyZone.arms: BodyZoneData(
    zone: BodyZone.arms,
    labelEn: 'Arms / Shoulders',
    labelHi: 'बाँह / कन्धा / हाथ',
    icon: Icons.front_hand,
    commonComplaint: 'arm and shoulder pain radiating',
  ),
  BodyZone.back: BodyZoneData(
    zone: BodyZone.back,
    labelEn: 'Back / Spine',
    labelHi: 'पीठ / कमर',
    icon: Icons.accessibility_new,
    commonComplaint: 'severe lower back pain',
  ),
  BodyZone.legs: BodyZoneData(
    zone: BodyZone.legs,
    labelEn: 'Legs / Knees / Feet',
    labelHi: 'पैर / घुटना',
    icon: Icons.directions_walk,
    commonComplaint: 'leg swelling and joint pain',
  ),
};

class BodyMapWidget extends StatefulWidget {
  final BodyZone? selectedZone;
  final ValueChanged<BodyZone> onZoneSelected;

  const BodyMapWidget({
    super.key,
    this.selectedZone,
    required this.onZoneSelected,
  });

  @override
  State<BodyMapWidget> createState() => _BodyMapWidgetState();
}

class _BodyMapWidgetState extends State<BodyMapWidget> {
  bool _isBackView = false;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Front / Back toggle switch
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: AppTheme.surfaceHighlight,
            borderRadius: BorderRadius.circular(30),
            border: Border.all(color: AppTheme.surfaceBorder),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildViewTab(title: 'सामने (Front)', isBack: false),
              _buildViewTab(title: 'पीछे (Back)', isBack: true),
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Interactive Anatomical Silhouette
        Center(
          child: SizedBox(
            width: 320,
            height: 380,
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Silhouette Canvas
                CustomPaint(
                  size: const Size(320, 380),
                  painter: BodySilhouettePainter(isBackView: _isBackView),
                ),

                // Interactive Touch Targets
                // 1. Head Zone
                Positioned(
                  top: 15,
                  child: _buildZoneTapTarget(
                    zone: BodyZone.head,
                    width: 70,
                    height: 70,
                    shape: BoxShape.circle,
                  ),
                ),

                // 2. Throat Zone
                Positioned(
                  top: 90,
                  child: _buildZoneTapTarget(
                    zone: BodyZone.throat,
                    width: 50,
                    height: 30,
                    shape: BoxShape.rectangle,
                  ),
                ),

                // 3. Chest (Front) or Back (Back) Zone
                Positioned(
                  top: 125,
                  child: _buildZoneTapTarget(
                    zone: _isBackView ? BodyZone.back : BodyZone.chest,
                    width: 110,
                    height: 60,
                    shape: BoxShape.rectangle,
                  ),
                ),

                // 4. Arms Zone (Left and Right)
                Positioned(
                  top: 125,
                  left: 30,
                  child: _buildZoneTapTarget(
                    zone: BodyZone.arms,
                    width: 50,
                    height: 120,
                    shape: BoxShape.rectangle,
                  ),
                ),
                Positioned(
                  top: 125,
                  right: 30,
                  child: _buildZoneTapTarget(
                    zone: BodyZone.arms,
                    width: 50,
                    height: 120,
                    shape: BoxShape.rectangle,
                  ),
                ),

                // 5. Abdomen (Front) or Lower Back (Back)
                Positioned(
                  top: 190,
                  child: _buildZoneTapTarget(
                    zone: _isBackView ? BodyZone.back : BodyZone.abdomen,
                    width: 100,
                    height: 55,
                    shape: BoxShape.rectangle,
                  ),
                ),

                // 6. Legs Zone
                Positioned(
                  top: 250,
                  child: _buildZoneTapTarget(
                    zone: BodyZone.legs,
                    width: 110,
                    height: 110,
                    shape: BoxShape.rectangle,
                  ),
                ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 12),

        // Selected zone indicator text
        if (widget.selectedZone != null) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
            decoration: BoxDecoration(
              color: AppTheme.primaryBlue.withAlpha(20),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppTheme.primaryBlue, width: 2),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  bodyZoneMetadata[widget.selectedZone]!.icon,
                  color: AppTheme.primaryBlue,
                  size: 28,
                ),
                const SizedBox(width: 12),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      bodyZoneMetadata[widget.selectedZone]!.labelHi,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                    ),
                    Text(
                      bodyZoneMetadata[widget.selectedZone]!.labelEn,
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppTheme.textSecondary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildViewTab({required String title, required bool isBack}) {
    final isSelected = _isBackView == isBack;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => setState(() => _isBackView = isBack),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? AppTheme.primaryBlue : Colors.transparent,
          borderRadius: BorderRadius.circular(24),
        ),
        child: Text(
          title,
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.bold,
            color: isSelected ? Colors.white : AppTheme.textSecondary,
          ),
        ),
      ),
    );
  }

  Widget _buildZoneTapTarget({
    required BodyZone zone,
    required double width,
    required double height,
    required BoxShape shape,
  }) {
    final isSelected = widget.selectedZone == zone;

    return GestureDetector(
      onTap: () => widget.onZoneSelected(zone),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        width: width,
        height: height,
        decoration: BoxDecoration(
          shape: shape,
          borderRadius: shape == BoxShape.rectangle ? BorderRadius.circular(16) : null,
          color: isSelected
              ? AppTheme.alertRed.withAlpha(180)
              : AppTheme.primaryBlue.withAlpha(40),
          border: Border.all(
            color: isSelected ? AppTheme.alertRedBright : AppTheme.accentCyan.withAlpha(120),
            width: isSelected ? 3 : 1.5,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: AppTheme.alertRedBright.withAlpha(120),
                    blurRadius: 16,
                    spreadRadius: 2,
                  ),
                ]
              : null,
        ),
        child: Center(
          child: Icon(
            bodyZoneMetadata[zone]!.icon,
            color: isSelected ? Colors.white : AppTheme.accentCyan.withAlpha(200),
            size: 20,
          ),
        ),
      ),
    );
  }
}

class BodySilhouettePainter extends CustomPainter {
  final bool isBackView;

  BodySilhouettePainter({required this.isBackView});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFFE2E8F0)
      ..style = PaintingStyle.fill;

    final outlinePaint = Paint()
      ..color = const Color(0xFF94A3B8)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    final cx = size.width / 2;

    // Head
    final headCenter = Offset(cx, 50);
    canvas.drawCircle(headCenter, 32, paint);
    canvas.drawCircle(headCenter, 32, outlinePaint);

    // Torso path
    final torsoPath = Path()
      ..moveTo(cx - 20, 85) // Neck left
      ..lineTo(cx - 65, 110) // Shoulder left
      ..lineTo(cx - 50, 240) // Hip left
      ..lineTo(cx - 10, 250) // Crotch left
      ..lineTo(cx + 10, 250) // Crotch right
      ..lineTo(cx + 50, 240) // Hip right
      ..lineTo(cx + 65, 110) // Shoulder right
      ..lineTo(cx + 20, 85) // Neck right
      ..close();

    canvas.drawPath(torsoPath, paint);
    canvas.drawPath(torsoPath, outlinePaint);

    // Left Arm
    final leftArm = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx - 95, 115, 24, 125),
      const Radius.circular(12),
    );
    canvas.drawRRect(leftArm, paint);
    canvas.drawRRect(leftArm, outlinePaint);

    // Right Arm
    final rightArm = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx + 71, 115, 24, 125),
      const Radius.circular(12),
    );
    canvas.drawRRect(rightArm, paint);
    canvas.drawRRect(rightArm, outlinePaint);

    // Left Leg
    final leftLeg = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx - 45, 245, 36, 125),
      const Radius.circular(14),
    );
    canvas.drawRRect(leftLeg, paint);
    canvas.drawRRect(leftLeg, outlinePaint);

    // Right Leg
    final rightLeg = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx + 9, 245, 36, 125),
      const Radius.circular(14),
    );
    canvas.drawRRect(rightLeg, paint);
    canvas.drawRRect(rightLeg, outlinePaint);
  }

  @override
  bool shouldRepaint(covariant BodySilhouettePainter oldDelegate) {
    return oldDelegate.isBackView != isBackView;
  }
}
