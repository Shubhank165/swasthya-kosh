import 'package:flutter/material.dart';
import '../services/camera_service.dart';
import '../theme/app_theme.dart';
import '../widgets/camera_pane.dart';

/// ABHA identification: photograph the card, type the number, or skip.
///
/// The headline comes from the server, so it is in the language the patient chose. This screen
/// previously drew a picture of a camera rather than opening one, so a patient held their card up
/// to a static icon and nothing happened.
class AbhaScreen extends StatefulWidget {
  const AbhaScreen({
    super.key,
    required this.headline,
    required this.onSubmitAbha,
    required this.onSkip,
    required this.cameraService,
    required this.onScanCard,
    this.isScanning = false,
    this.scanError,
  });

  final String headline;
  final ValueChanged<String> onSubmitAbha;
  final VoidCallback onSkip;
  final CameraService cameraService;
  final VoidCallback onScanCard;
  final bool isScanning;
  final String? scanError;

  @override
  State<AbhaScreen> createState() => _AbhaScreenState();
}

class _AbhaScreenState extends State<AbhaScreen> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            widget.headline,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 23, fontWeight: FontWeight.w600, height: 1.3),
          ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 26,
            runSpacing: 22,
            alignment: WrapAlignment.center,
            children: [
              CameraPane(
                service: widget.cameraService,
                onCapture: widget.onScanCard,
                captureLabel: 'Scan card',
                busy: widget.isScanning,
                error: widget.scanError,
              ),
              SizedBox(
                width: 300,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextField(
                      controller: _controller,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(fontSize: 20, letterSpacing: 1.2),
                      decoration: const InputDecoration(
                        labelText: 'ABHA number',
                        hintText: '12-3456-7890-1234',
                        border: OutlineInputBorder(),
                        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 20),
                      ),
                      onSubmitted: widget.onSubmitAbha,
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => widget.onSubmitAbha(_controller.text.trim()),
                        style: ElevatedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                        ),
                        child: const Text('Continue', style: TextStyle(fontSize: 17)),
                      ),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton(
                        onPressed: widget.onSkip,
                        style: OutlinedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          foregroundColor: AppTheme.textSecondary,
                        ),
                        child: const Text('Skip', style: TextStyle(fontSize: 17)),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
