/// On-device ASR models — shipped in the APK, copied to storage, never fetched.
///
/// The recogniser is `sherpa_onnx`, which runs entirely on the device. What it
/// needs is a model: some weights and a token table. Those files ship as
/// Flutter assets under `assets/asr/` and are bundled into the APK — there is
/// **no download and nothing to choose**. sherpa_onnx's native code reads real
/// filesystem paths, not asset-bundle handles, so on first use the assets are
/// copied once into the app's own storage and every later launch reads them
/// from there.
///
/// **Nothing in this feature reaches the network — not for the model, not for
/// anything.** `on_device_voice_test.dart` holds `lib/voice/` to that: no HTTP
/// client, no `Uri`, no `.get`/`.post`. Voice input either works offline or is
/// absent, and the patient uses touch — the same graceful absence as a missing
/// text-to-speech voice.
///
/// Two model families are bundled, because no single checkpoint of a shippable
/// size does both jobs — see [AsrModel.registry] for which language gets which
/// and the measurements behind that split.
library;

import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show AssetBundle, rootBundle;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// Which sherpa_onnx recogniser a checkpoint needs building.
///
/// This is not cosmetic: a Whisper model is an encoder/decoder pair configured
/// through `OfflineWhisperModelConfig`, a NeMo CTC model is one graph
/// configured through `OfflineNemoEncDecCtcModelConfig`, and handing either to
/// the other's constructor fails at load. The isolate switches on this.
enum AsrEngine { whisper, nemoCtc }

/// One offline ASR model, bundled as assets.
@immutable
class AsrModel {
  const AsrModel._({
    required this.id,
    required this.engine,
    required this.assetDir,
    required this.tokens,
    required this.assetNames,
    this.encoder,
    this.decoder,
    this.model,
  });

  /// An encoder/decoder Whisper checkpoint.
  factory AsrModel.whisper({
    required String id,
    required String assetDir,
    required String encoder,
    required String decoder,
    required String tokens,
  }) =>
      AsrModel._(
        id: id,
        engine: AsrEngine.whisper,
        assetDir: assetDir,
        tokens: tokens,
        encoder: encoder,
        decoder: decoder,
        assetNames: [encoder, decoder, tokens],
      );

  /// A single-graph NeMo CTC checkpoint.
  factory AsrModel.nemoCtc({
    required String id,
    required String assetDir,
    required String model,
    required String tokens,
  }) =>
      AsrModel._(
        id: id,
        engine: AsrEngine.nemoCtc,
        assetDir: assetDir,
        tokens: tokens,
        model: model,
        assetNames: [model, tokens],
      );

  final String id;
  final AsrEngine engine;

  /// Directory under the Flutter asset root holding [assetNames].
  final String assetDir;

  /// The token table's file name — every engine has one.
  final String tokens;

  /// Whisper only.
  final String? encoder;
  final String? decoder;

  /// NeMo CTC only.
  final String? model;

  /// Every file this model needs, by name within [assetDir].
  final List<String> assetNames;

  /// `sherpa-onnx-whisper-tiny`, int8-quantised. ~103 MB, multilingual — the
  /// interview `language` is set per recognise call, not baked into the file.
  ///
  /// It serves **English only**, and that is a measurement, not an oversight.
  /// Whisper at a size that fits a mid-range phone will not write Devanagari;
  /// it romanises. On clean synthesised speech — the friendliest input an ASR
  /// model ever gets — `तीन दिनों से` came back as `Team denose` and
  /// `मुझे बुखार है` as `持jebhukhar`; whisper-base, three times the asset, was
  /// no better and returned one answer in Urdu script. An answer romanised
  /// like that is not a rougher transcript, it is a different sentence, and it
  /// would land in a document a physician acts on. DECISIONS §69.
  static final whisperTiny = AsrModel.whisper(
    id: 'whisper-tiny-int8',
    assetDir: 'assets/asr/whisper-tiny',
    encoder: 'tiny-encoder.int8.onnx',
    decoder: 'tiny-decoder.int8.onnx',
    tokens: 'tiny-tokens.txt',
  );

  /// AI4Bharat IndicConformer, Hindi, int8. ~140 MB, CTC, Hindi only.
  ///
  /// This is §69's "the real fix is a model, not a config", converted. On the
  /// same ten clips that gave whisper-tiny a mean CER of 0.96, this scores
  /// **0.04** and returns eight of them character-perfect:
  ///
  ///     सांस लेने में तकलीफ़ है    -> साँस लेने में तकलीफ़ है
  ///     शुगर की दवा चल रही है   -> शुगर की दवा चल रही है
  ///
  /// It is deliberately a **Hindi-only** checkpoint rather than a multilingual
  /// one. Dolphin, the ready-made alternative, needs no conversion and is the
  /// same size — but sherpa_onnx cannot pin its language, so it auto-detects
  /// over forty languages and changes script inside one sentence
  /// (`सांस लेने में तकलीफ़ है` -> `سانس लेने میں تکلیف है`). A per-language
  /// checkpoint cannot make that mistake at all. DECISIONS §76.
  ///
  /// Built by `tool/asr/build_indicconformer.py`; the same script produces the
  /// other seven Indic languages, which is how this registry grows.
  ///
  /// **Known weak spot:** single-syllable answers. `हाँ` comes back as `हा` or
  /// `ख` — CTC needs encoder context and a 400 ms utterance gives none. Yes/no
  /// and single-choice questions have buttons, and `option_match.dart` refuses
  /// a low-confidence match rather than guessing, so this degrades to touch
  /// rather than to a wrong answer.
  static final indicConformerHindi = AsrModel.nemoCtc(
    id: 'indicconformer-hi-int8',
    assetDir: 'assets/asr/indic-hi',
    model: 'model.int8.onnx',
    tokens: 'tokens.txt',
  );

  /// Which model serves which language — the whole of the policy, in one map.
  ///
  /// A language absent here has no on-device voice, and every caller above
  /// turns that into an absent microphone rather than an error. Adding a key
  /// without adding a checkpoint that was *measured* on that language ships
  /// romanised or mis-scripted answers into a clinical record, which is the
  /// failure §69 exists to prevent; `tool/asr/bench_hindi.py` is how the
  /// measuring is done.
  static final Map<String, AsrModel> registry = {
    'en': whisperTiny,
    'hi': indicConformerHindi,
  };

  /// The languages with an on-device microphone.
  static Set<String> get servedLanguages => registry.keys.toSet();
}

/// Where a language's model lives on disk once it is ready.
///
/// Sealed, so the isolate that builds the recogniser has to handle every
/// engine: a new family cannot be added and silently fall through to Whisper's
/// config.
@immutable
sealed class ModelFiles {
  const ModelFiles(this.tokens);
  final String tokens;

  /// Every path that must exist and be non-empty for this model to load.
  List<String> get paths;
}

/// A Whisper encoder/decoder pair.
@immutable
class WhisperFiles extends ModelFiles {
  const WhisperFiles({
    required this.encoder,
    required this.decoder,
    required String tokens,
  }) : super(tokens);

  final String encoder;
  final String decoder;

  @override
  List<String> get paths => [encoder, decoder, tokens];
}

/// A single-graph NeMo CTC model.
@immutable
class NemoCtcFiles extends ModelFiles {
  const NemoCtcFiles({required this.model, required String tokens})
      : super(tokens);

  final String model;

  @override
  List<String> get paths => [model, tokens];
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
  AsrModel? _modelFor(String language) => AsrModel.registry[language];

  ModelFiles _pathsUnder(String dir, AsrModel model) => switch (model.engine) {
        AsrEngine.whisper => WhisperFiles(
            encoder: p.join(dir, model.encoder!),
            decoder: p.join(dir, model.decoder!),
            tokens: p.join(dir, model.tokens),
          ),
        AsrEngine.nemoCtc => NemoCtcFiles(
            model: p.join(dir, model.model!),
            tokens: p.join(dir, model.tokens),
          ),
      };

  /// The model for [language] if its files are already on disk and non-empty,
  /// else null. A disk check only — never copies, never throws. Null also when
  /// no model serves [language] at all.
  Future<ModelFiles?> installed(String language) async {
    try {
      final model = _modelFor(language);
      if (model == null) return null;
      final dir = p.join((await _root()).path, model.id);
      final files = _pathsUnder(dir, model);
      for (final path in files.paths) {
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
      for (final name in model.assetNames) {
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
