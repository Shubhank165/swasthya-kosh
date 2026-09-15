import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';

/// The tablet's rear camera, used for the ABHA card and for prescriptions.
///
/// Opened only on the two stages that need it and released immediately afterwards. A camera left
/// running holds the sensor, drains the battery and keeps a preview of the previous patient's
/// document alive on screen — which is a privacy problem in a queue, not just a resource one.
///
/// Decoding happens on the Jetson: it already reads ABHA QR codes with OpenCV and prescriptions
/// with PP-OCRv5, so the app ships no vision library of its own and there is one implementation
/// to keep correct rather than two.
class CameraService extends ChangeNotifier {
  CameraController? _controller;
  bool _starting = false;
  bool _disposed = false;
  int _generation = 0;
  String? _error;

  CameraController? get controller => _controller;
  bool get isReady => _controller?.value.isInitialized ?? false;
  String? get error => _error;

  Future<void> start() async {
    if (_disposed || isReady || _starting) return;
    final generation = ++_generation;
    CameraController? candidate;
    _starting = true;
    _error = null;
    notifyListeners();
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        throw CameraException('none', 'This device reports no camera');
      }
      final rear = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      // Documents need resolution for OCR to read small print; a preview-grade image produces
      // plausible-looking nonsense rather than an honest failure.
      final controller = candidate = CameraController(
        rear,
        ResolutionPreset.high,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await controller.initialize();
      if (_disposed || generation != _generation) {
        await controller.dispose();
        return;
      }
      _controller = controller;
    } on CameraException catch (e) {
      await candidate?.dispose();
      _error = '${e.code}: ${e.description ?? ""}';
      _controller = null;
    } catch (e) {
      await candidate?.dispose();
      _error = '$e';
      _controller = null;
    } finally {
      _starting = false;
      if (!_disposed) notifyListeners();
    }
  }

  /// One JPEG frame, or null with [error] set. Never throws into the intake.
  Future<List<int>?> capture() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      _error = 'camera not ready';
      notifyListeners();
      return null;
    }
    try {
      final shot = await controller.takePicture();
      final bytes = await File(shot.path).readAsBytes();
      // The temporary file is the patient's document. Delete it as soon as it is in memory
      // rather than leaving it in the app's cache for the next person.
      try {
        await File(shot.path).delete();
      } catch (_) {
        // Best effort; the OS clears the cache eventually.
      }
      return bytes;
    } catch (e) {
      _error = 'capture failed: $e';
      if (!_disposed) notifyListeners();
      return null;
    }
  }

  Future<void> stop() async {
    ++_generation;
    final controller = _controller;
    _controller = null;
    notifyListeners();
    await controller?.dispose();
  }

  @override
  void dispose() {
    _disposed = true;
    ++_generation;
    _controller?.dispose();
    super.dispose();
  }
}
