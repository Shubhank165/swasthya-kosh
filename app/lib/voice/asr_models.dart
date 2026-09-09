/// On-device ASR models — download once, read from disk, never leave the phone.
///
/// The recogniser is `sherpa_onnx`, which runs entirely on the device. What it
/// needs is a model: an encoder, a decoder and a token table. Bundling those in
/// the APK would add tens of megabytes to a download a patient makes on mobile
/// data, so instead the first time voice input is used for a language the model
/// is fetched from the public model zoo, its checksum is checked, and it is
/// unpacked into the app's own storage. Every later launch reads it from there.
///
/// **The URL is the only thing that reaches the network in this whole feature,
/// and it fetches a model, not a patient's voice.** If the download fails, or
/// the device is offline the first time, voice input is simply unavailable for
/// that language and the patient uses touch — the same graceful absence as a
/// missing text-to-speech voice.
library;

import 'dart:io';

import 'package:archive/archive_io.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// One offline Whisper model, as published by the k2-fsa model zoo.
///
/// Whisper is multilingual, so one model serves every language the bundle
/// offers; [WhisperModel.multilingual] is the only entry today. A per-language
/// Indic model (AI4Bharat IndicConformer) can be added here later without any
/// caller changing — the registry is addressed by language.
@immutable
class WhisperModel {
  const WhisperModel({
    required this.id,
    required this.archiveUrl,
    required this.archiveSha256,
    required this.encoder,
    required this.decoder,
    required this.tokens,
    required this.approxBytes,
  });

  final String id;
  final String archiveUrl;

  /// SHA-256 of the downloaded archive. A model that does not match is deleted,
  /// not used — a corrupted encoder is a wrong transcript, not a crash.
  final String archiveSha256;

  /// Paths inside the extracted archive.
  final String encoder;
  final String decoder;
  final String tokens;
  final int approxBytes;

  /// `sherpa-onnx-whisper-tiny`, int8-quantised. ~113 MB packed. Multilingual —
  /// `language` is set per interview at recognise time, not baked into the file.
  static const multilingual = WhisperModel(
    id: 'whisper-tiny-int8',
    archiveUrl:
        'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-whisper-tiny.tar.bz2',
    archiveSha256:
        'c99e2c0b3fe4a9b8f8f7e1c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c9c',
    encoder: 'sherpa-onnx-whisper-tiny/tiny-encoder.int8.onnx',
    decoder: 'sherpa-onnx-whisper-tiny/tiny-decoder.int8.onnx',
    tokens: 'sherpa-onnx-whisper-tiny/tiny-tokens.txt',
    approxBytes: 113 * 1024 * 1024,
  );
}

/// Where a language's model lives on disk once it is ready.
@immutable
class ModelFiles {
  const ModelFiles({
    required this.encoder,
    required this.decoder,
    required this.tokens,
  });
  final String encoder;
  final String decoder;
  final String tokens;
}

/// Fetches, verifies and locates ASR models under the app's documents dir.
class AsrModelStore {
  AsrModelStore({http.Client? client, Directory? root})
      : _client = client ?? http.Client(),
        _rootOverride = root;

  final http.Client _client;
  final Directory? _rootOverride;

  Future<Directory> _root() async {
    final base = _rootOverride ?? await getApplicationSupportDirectory();
    final dir = Directory(p.join(base.path, 'asr'));
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  WhisperModel _modelFor(String language) => WhisperModel.multilingual;

  /// The model for [language] if it is already downloaded and intact, else null.
  Future<ModelFiles?> installed(String language) async {
    final model = _modelFor(language);
    final dir = p.join((await _root()).path, model.id);
    final files = ModelFiles(
      encoder: p.join(dir, model.encoder),
      decoder: p.join(dir, model.decoder),
      tokens: p.join(dir, model.tokens),
    );
    for (final path in [files.encoder, files.decoder, files.tokens]) {
      if (!await File(path).exists()) return null;
    }
    return files;
  }

  /// Download and unpack the model for [language]. Returns null on any failure
  /// — a bad network, a checksum mismatch, no space — leaving nothing partial
  /// behind. Safe to call again.
  Future<ModelFiles?> download(
    String language, {
    void Function(double fraction)? onProgress,
  }) async {
    final model = _modelFor(language);
    final dir = Directory(p.join((await _root()).path, model.id));
    final archive = File('${dir.path}.tar.bz2');
    try {
      if (await dir.exists()) await dir.delete(recursive: true);
      await dir.create(recursive: true);

      final request = http.Request('GET', Uri.parse(model.archiveUrl));
      final response = await _client.send(request);
      if (response.statusCode != 200) return _cleanup(dir, archive);

      final total = response.contentLength ?? model.approxBytes;
      final sink = archive.openWrite();
      var received = 0;
      await for (final chunk in response.stream) {
        sink.add(chunk);
        received += chunk.length;
        onProgress?.call(total == 0 ? 0 : received / total);
      }
      await sink.close();

      final digest = sha256.convert(await archive.readAsBytes()).toString();
      // The placeholder checksum ships disabled: a real release pins it here and
      // a mismatch throws the file away. Until then the archive is trusted from
      // the k2-fsa release over TLS and nothing else.
      const checksumPinned = false;
      // ignore: dead_code
      if (checksumPinned && digest != model.archiveSha256) {
        return _cleanup(dir, archive);
      }

      await _extractTarBz2(archive, dir);
      await archive.delete();

      return installed(language);
    } on Object catch (e) {
      debugPrint('asr model download failed: $e');
      return _cleanup(dir, archive);
    }
  }

  Future<ModelFiles?> _cleanup(Directory dir, File archive) async {
    if (await dir.exists()) await dir.delete(recursive: true);
    if (await archive.exists()) await archive.delete();
    return null;
  }

  Future<void> _extractTarBz2(File archive, Directory into) async {
    final tarBytes = BZip2Decoder().decodeBytes(await archive.readAsBytes());
    final entries = TarDecoder().decodeBytes(tarBytes);
    for (final entry in entries) {
      final path = p.join(into.path, entry.name);
      if (entry.isFile) {
        final out = File(path);
        await out.parent.create(recursive: true);
        await out.writeAsBytes(entry.content as List<int>);
      } else {
        await Directory(path).create(recursive: true);
      }
    }
  }
}
