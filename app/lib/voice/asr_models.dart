/// On-device ASR model — shipped in the APK, copied to storage, never fetched.
///
/// The recogniser is `sherpa_onnx`, which runs entirely on the device. What it
/// needs is a model: an encoder, a decoder and a token table. Those files ship
/// as Flutter assets under `assets/asr/` and are bundled into the APK — there
/// is **no download and nothing to choose**. sherpa_onnx's native code reads
/// real filesystem paths, not asset-bundle handles, so on first use the assets
/// are copied once into the app's own storage and every later launch reads them
/// from there.
///
/// **Nothing in this feature reaches the network — not for the model, not for
/// anything.** `on_device_voice_test.dart` holds `lib/voice/` to that: no HTTP
/// client, no `Uri`, no `.get`/`.post`. Voice input either works offline or is
/// absent, and the patient uses touch — the same graceful absence as a missing
/// text-to-speech voice.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show AssetBundle, rootBundle;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// One offline Whisper model, bundled as assets.
///
/// [WhisperModel.multilingual] is the only entry today, and it does not serve
/// every language the app offers — see [WhisperModel.servedLanguages] for
/// which, and for the measurements behind that list. A per-language Indic
/// model can be added here later without any caller changing: the registry is
/// addressed by language and answers null where it has nothing.
@immutable
class WhisperModel {
  const WhisperModel({
    required this.id,
    required this.assetDir,
    required this.encoder,
    required this.decoder,
    required this.tokens,
  });

  final String id;

  /// Directory under the Flutter asset root holding the three files below.
  final String assetDir;

  /// File names within [assetDir] (and, once copied, within the on-disk dir).
  final String encoder;
  final String decoder;
  final String tokens;

  /// `sherpa-onnx-whisper-tiny`, int8-quantised. ~103 MB, multilingual — the
  /// interview `language` is set per recognise call, not baked into the file.
  static const multilingual = WhisperModel(
    id: 'whisper-tiny-int8',
    assetDir: 'assets/asr/whisper-tiny',
    encoder: 'tiny-encoder.int8.onnx',
    decoder: 'tiny-decoder.int8.onnx',
    tokens: 'tiny-tokens.txt',
  );

  /// The languages this checkpoint transcribes well enough to put in a record.
  ///
  /// Whisper is nominally multilingual and the language token does reach the
  /// decoder — forcing `ta` changes the output script, so the plumbing works.
  /// What tiny will not do is write Devanagari. Measured against clean
  /// synthesised speech, which is the friendliest input an ASR model ever gets
  /// and an optimistic bound on a patient speaking into a phone in an OPD:
  ///
  ///     तीन दिनों से        -> "Team denose"
  ///     मुझे बुखार है         -> "持jebhukhar"
  ///     दो दिन से खांसी है    -> "Do dense kasi hale"
  ///
  /// whisper-base, three times the size, is no better: the same phrases come
  /// back as "10 de noze" and "m ch he b khar", and one answer came back in
  /// Urdu script. An answer romanised like that is not a rougher transcript,
  /// it is a different sentence, and it would land in a document a physician
  /// acts on. So voice is offered only where the model earns it; everywhere
  /// else the microphone is absent and the patient taps or types, which is
  /// §16's graceful absence and the same rule read-aloud already follows.
  ///
  /// This is a property of the checkpoint, not of this code. A per-language
  /// Indic model — AI4Bharat IndicConformer, once a sherpa-onnx export of it
  /// exists — slots in beside [multilingual] and this set grows with it.
  static const servedLanguages = {'en'};
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

/// Locates the ASR model on disk, copying it out of the app bundle on first use.
class AsrModelStore {
  AsrModelStore({AssetBundle? bundle, Directory? root})
      : _bundle = bundle ?? rootBundle,
        _rootOverride = root;

  final AssetBundle _bundle;
  final Directory? _rootOverride;

  Future<Directory> _root() async {
    final base = _rootOverride ?? await getApplicationSupportDirectory();
    final dir = Directory(p.join(base.path, 'asr'));
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  /// The model that serves [language], or null when none does.
  ///
  /// Null is not a failure to report — it is "this language has no on-device
  /// voice", and every caller above turns it into an absent microphone.
  WhisperModel? _modelFor(String language) =>
      WhisperModel.servedLanguages.contains(language)
          ? WhisperModel.multilingual
          : null;

  ModelFiles _pathsUnder(String dir, WhisperModel model) => ModelFiles(
        encoder: p.join(dir, model.encoder),
        decoder: p.join(dir, model.decoder),
        tokens: p.join(dir, model.tokens),
      );

  /// The model for [language] if its files are already on disk and non-empty,
  /// else null. A disk check only — never copies, never throws. Null also when
  /// no model serves [language] at all.
  Future<ModelFiles?> installed(String language) async {
    try {
      final model = _modelFor(language);
      if (model == null) return null;
      final dir = p.join((await _root()).path, model.id);
      final files = _pathsUnder(dir, model);
      for (final path in [files.encoder, files.decoder, files.tokens]) {
        final f = File(path);
        if (!await f.exists() || await f.length() == 0) return null;
      }
      return files;
    } on Object {
      return null;
    }
  }

  /// Make sure [language]'s model is on disk, copying it out of the bundled
  /// assets if it is not there yet. Returns the file paths, or null if the copy
  /// failed (no space, assets missing in a test), or if no model serves
  /// [language]. Cheap and idempotent after the first call.
  Future<ModelFiles?> ensureInstalled(String language) async {
    final ready = await installed(language);
    if (ready != null) return ready;

    final model = _modelFor(language);
    if (model == null) return null;
    final dir = Directory(p.join((await _root()).path, model.id));
    try {
      await dir.create(recursive: true);
      for (final name in [model.encoder, model.decoder, model.tokens]) {
        final out = File(p.join(dir.path, name));
        // A half-written file from a killed earlier launch: redo it.
        if (await out.exists() && await out.length() > 0) continue;
        final data = await _bundle.load('${model.assetDir}/$name');
        await out.writeAsBytes(
          data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
          flush: true,
        );
      }
      return installed(language);
    } on Object catch (e) {
      debugPrint('asr model provisioning failed: $e');
      return null;
    }
  }
}
