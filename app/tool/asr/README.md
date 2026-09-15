# Hindi on-device ASR — what was tried, and what it measured

`DECISIONS.md §69` turned the Hindi microphone off, because whisper-tiny writes
`तीन दिनों से` as **"Team denose"** and a romanised answer is not a rougher
transcript, it is a different sentence. §69 also said what would reopen it: a
model, not a config. This directory is the search for that model and the export
job it turned out to need.

## The measurement

Ten ordinary OPD answers, synthesised once by a Piper Hindi voice and fed to
every candidate unchanged, scored with the same CER/WER code the kiosk uses
(`jetson/scripts/benchmark_languages.py`). Reproduce with `bench_hindi.py`.

| model | asset | mean CER | what it writes |
|---|---:|---:|---|
| whisper-tiny int8 — **what the APK ships** | 103 MB | **0.96** | `'See name it, Darth Doudin Say'` |
| Dolphin base CTC int8 | 99 MB | **0.42** | `'सینने में درर्द दोدن سے'` |
| **IndicConformer hi, int8** | **140 MB** | **0.04** | `'सीने में दर्द दो दिन से'` |

Synthetic speech is the friendliest input an ASR model ever gets, so read every
number as an upper bound. The ranking is the part that carries.

## Why not Dolphin, which needs no conversion at all

Dolphin is a genuine drop-in: `sherpa-onnx-dolphin-base-ctc-multi-lang-int8`
downloads ready to use, is the same size as the whisper asset already shipped,
covers `hi bn mr gu pa ta te or`, and the Dart binding
(`OfflineDolphinModelConfig`) is already in the pinned `sherpa_onnx 1.13.7`.

It is still not usable here. sherpa-onnx exposes **no way to pin its language** —
`from_dolphin_ctc` takes no language argument — so it auto-detects per clip over
a shared 40-language inventory and drifts mid-sentence:

    सांस लेने में तकलीफ़ है  ->  سانس लेने میں تکلیف है
    तीन दिनों से           ->  ティーンでのせ

Half a sentence in Arabic script is a worse failure than romanisation, not a
better one, and no post-processing recovers the words it did not write. A
Hindi-only checkpoint cannot make this mistake, which is the structural reason
to prefer one over a multilingual model here.

## Why IndicConformer needed converting

AI4Bharat publish NeMo checkpoints. The community has already run NeMo's ONNX
export for all twelve languages, but targeted at the generic `onnx-asr`
library, which reads tensor shapes off the graph. sherpa-onnx reads them off
`metadata_props` and refuses to load without them:

    'vocab_size' does not exist in the metadata

So `build_indicconformer.py` downloads that export, stamps the metadata
(`vocab_size` read from the model's own output dimension — it is checked, not
assumed), writes `tokens.txt` from `vocab.json` with the CTC blank last, and
quantises fp32 → int8. 493 MB becomes 140 MB and, measured on the same clips,
costs nothing: the fp32 and int8 rows are within noise of each other.

    python3 tool/asr/build_indicconformer.py --language hi --out assets/asr/indic-hi

The same command builds `bn gu kn ml mr or pa ta te ur as` — eight of the app's
nine languages. English is the one it does not cover, and whisper-tiny already
serves English, which is why §69 left that microphone on.

## What is still wrong with it

**Single-syllable answers.** `हाँ` comes back as `हा`, `ख` or `खक` depending on
the clip. CTC needs encoder context and a 400 ms utterance does not supply it;
padding with silence helps a little and does not fix it. This matters less than
it reads: yes/no and single-choice questions have buttons, and
`lib/voice/option_match.dart` refuses a match below `kMatchFloor` rather than
guessing. But it means the mic earns its place on free-text answers first.

**Assets are not committed.** 140 MB per language is not something to push
casually; `assets/asr/indic-hi/` is ignored and the build script regenerates it
byte-for-byte. whisper-tiny predates that rule and is still tracked.

**Nothing is wired up yet.** `WhisperModel.servedLanguages` is still `{'en'}`.
Widening it means teaching `lib/voice/asr_models.dart` that a language can map
to a *NeMo CTC* model rather than a Whisper encoder/decoder pair, and
`lib/voice/transcribe.dart` to build `OfflineModelConfig(nemoCtc: …)` instead of
`whisper: …`. Both binding classes already exist in the pinned sherpa_onnx.
