import 'package:flutter/material.dart';
import '../services/camera_service.dart';
import '../theme/app_theme.dart';
import '../widgets/camera_pane.dart';

/// Photograph prescriptions and reports. The Jetson runs the OCR and returns what it read.
///
/// Lines are shown exactly as read, not tidied: OCR misreads doses, and a clean-looking list
/// invites more trust than a photograph of someone's handwriting deserves. The doctor's sheet
/// marks every one of these as machine-derived for the same reason.
///
/// The headline comes from the server so it is in the patient's chosen language; this screen
/// used to hardcode its own Hindi.
class DocumentsScreen extends StatelessWidget {
  const DocumentsScreen({
    super.key,
    required this.headline,
    required this.onScan,
    required this.onDone,
    required this.cameraService,
    this.scannedLines = const [],
    this.isScanning = false,
    this.scanError,
  });

  final String headline;
  final VoidCallback onScan;
  final VoidCallback onDone;
  final CameraService cameraService;
  final List<String> scannedLines;
  final bool isScanning;
  final String? scanError;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            headline,
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
                service: cameraService,
                onCapture: onScan,
                captureLabel: 'Scan document',
                busy: isScanning,
                error: scanError,
              ),
              SizedBox(
                width: 320,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      constraints: const BoxConstraints(minHeight: 180, maxHeight: 300),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppTheme.surfaceHighlight,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(color: AppTheme.surfaceBorder),
                      ),
                      child: scannedLines.isEmpty
                          ? const Center(
                              child: Text(
                                'Nothing scanned yet',
                                style: TextStyle(color: AppTheme.textSecondary, fontSize: 15),
                              ),
                            )
                          : ListView(
                              children: [
                                Text(
                                  '${scannedLines.length} lines read',
                                  style: const TextStyle(
                                    color: AppTheme.textSecondary,
                                    fontSize: 13,
                                  ),
                                ),
                                const SizedBox(height: 8),
                                for (final line in scannedLines)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 4),
                                    child: Text(line, style: const TextStyle(fontSize: 14)),
                                  ),
                              ],
                            ),
                    ),
                    const SizedBox(height: 14),
                    ElevatedButton(
                      onPressed: onDone,
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      child: Text(
                        scannedLines.isEmpty ? 'No documents' : 'Done',
                        style: const TextStyle(fontSize: 17),
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
