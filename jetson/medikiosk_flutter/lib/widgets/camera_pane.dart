import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import '../services/camera_service.dart';
import '../theme/app_theme.dart';

/// Live camera preview with a capture button.
///
/// Both places that use a camera - the ABHA card and prescriptions - previously drew a static
/// icon of a camera, so the patient held their document up to a picture and nothing happened.
/// This shows the actual sensor, with a framing guide so people know where to hold the paper.
class CameraPane extends StatelessWidget {
  const CameraPane({
    super.key,
    required this.service,
    required this.onCapture,
    required this.captureLabel,
    this.busy = false,
    this.error,
    this.height = 300,
  });

  final CameraService service;
  final VoidCallback onCapture;
  final String captureLabel;
  final bool busy;
  final String? error;
  final double height;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: service,
      builder: (context, _) {
        final controller = service.controller;
        final ready = service.isReady && controller != null;

        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 300,
              height: height,
              clipBehavior: Clip.antiAlias,
              decoration: BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: AppTheme.surfaceBorder, width: 2),
              ),
              child: ready
                  ? Stack(
                      fit: StackFit.expand,
                      children: [
                        FittedBox(
                          fit: BoxFit.cover,
                          child: SizedBox(
                            width: controller.value.previewSize?.height ?? 300,
                            height: controller.value.previewSize?.width ?? 300,
                            child: CameraPreview(controller),
                          ),
                        ),
                        // Framing guide: people hold a document where the box is, which is what
                        // gets a readable photo rather than a corner of the desk.
                        Center(
                          child: Container(
                            margin: const EdgeInsets.all(26),
                            decoration: BoxDecoration(
                              border: Border.all(color: AppTheme.accentCyan, width: 2),
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                        ),
                        if (busy)
                          Container(
                            color: Colors.black54,
                            child: const Center(child: CircularProgressIndicator()),
                          ),
                      ],
                    )
                  : Center(
                      child: Padding(
                        padding: const EdgeInsets.all(18),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.videocam_off, size: 48, color: Colors.white38),
                            const SizedBox(height: 12),
                            Text(
                              // Say why rather than showing a dead rectangle.
                              service.error ?? 'Starting camera…',
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: Colors.white60, fontSize: 13),
                            ),
                          ],
                        ),
                      ),
                    ),
            ),
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(
                  error!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: AppTheme.warningOrange, fontSize: 14),
                ),
              ),
            const SizedBox(height: 14),
            SizedBox(
              width: 300,
              child: ElevatedButton.icon(
                onPressed: ready && !busy ? onCapture : null,
                icon: const Icon(Icons.camera_alt, size: 24),
                label: Text(captureLabel, style: const TextStyle(fontSize: 17)),
                style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
              ),
            ),
          ],
        );
      },
    );
  }
}
