#!/usr/bin/env python3
"""Turn AI4Bharat IndicConformer into an asset `sherpa_onnx` will load.

DECISIONS §69 turned off the Hindi microphone because whisper-tiny romanises
Devanagari, and named IndicConformer as the fix that needed "an export job
rather than a download". This is that job, and it is three steps, none of them
a retrain:

1. **Download.** The community has already run NeMo's ONNX export for all 12
   languages (`trysem/indicconformer-120m-onnx`, a mirror of
   `sulabhkatiyar/…`). The graph is correct; nothing here re-exports it.
2. **Stamp the metadata.** That export targets the generic `onnx-asr` library,
   which reads shapes off the graph. sherpa-onnx reads them off
   `metadata_props` instead, and fails with *"'vocab_size' does not exist in
   the metadata"* when they are absent. The values below are not guesses —
   `vocab_size` is the model's own output dimension, read from the graph, and
   the rest are Conformer-CTC's fixed preprocessing contract.
3. **Quantise.** fp32 is 493 MB, which is not going in an APK. Dynamic int8
   takes it to 140 MB — the same order as the 103 MB whisper-tiny already
   shipped — and `bench_hindi.py` measures that it costs nothing: mean CER
   0.12 either way.

`vocab.json` is one shared 5 632-token inventory across all twelve languages
(Devanagari, Bengali, Tamil, Arabic script and more), not a per-language one.
That is expected — the tokenizer is shared and the *weights* are per-language,
so the Hindi checkpoint writes Devanagari without the vocabulary having to
forbid anything else.

    python3 tool/asr/build_indicconformer.py --language hi --out assets/asr/indic-hi

Needs `onnx` and `onnxruntime` (build-time only — neither ships in the app).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path

REPO = "https://huggingface.co/trysem/indicconformer-120m-onnx/resolve/main"

#: The twelve languages that repository carries. Of the nine the app offers,
#: it covers eight — English is the one it does not, and whisper-tiny already
#: serves English well, which is why §69 left that one microphone on.
AVAILABLE = ("as", "bn", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te", "ur")


def _download(url: str, target: Path) -> None:
    """Resumable-enough: skip a file that is already whole, else fetch it."""
    if target.exists() and target.stat().st_size > 0:
        print(f"  have {target.name} ({target.stat().st_size:,} bytes)")
        return
    print(f"  fetching {url}")
    with urllib.request.urlopen(url) as response, target.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(response, out)
    print(f"  wrote {target.name} ({target.stat().st_size:,} bytes)")


def _tokens_txt(vocab: Path, target: Path) -> int:
    """NeMo ships `vocab.json`; sherpa-onnx wants `<token> <id>` lines.

    CTC blank is appended last, which is where NeMo puts it — the model's output
    is one wider than the vocabulary for exactly that reason.
    """
    entries = json.loads(vocab.read_text(encoding="utf-8"))
    tokens = (
        entries
        if isinstance(entries, list)
        else [t for t, _ in sorted(entries.items(), key=lambda kv: kv[1])]
    )
    with target.open("w", encoding="utf-8") as out:
        for index, token in enumerate(tokens):
            out.write(f"{token} {index}\n")
        out.write(f"<blk> {len(tokens)}\n")
    return len(tokens) + 1


def _stamp(model: Path, target: Path, vocab_size: int) -> None:
    import onnx  # noqa: PLC0415 - build-time only, never an app dependency

    graph = onnx.load(str(model))
    declared = graph.graph.output[0].type.tensor_type.shape.dim[-1].dim_value
    if declared != vocab_size:
        raise SystemExit(
            f"tokens.txt has {vocab_size} entries but the model emits {declared} "
            "logits. A mismatch here does not fail loudly — it silently decodes "
            "to the wrong characters."
        )
    del graph.metadata_props[:]
    for key, value in {
        "vocab_size": str(vocab_size),
        "subsampling_factor": "4",
        "normalize_type": "per_feature",
        "model_type": "EncDecCTCModelBPE",
        "feat_dim": "80",
        "is_giga_am": "0",
    }.items():
        prop = graph.metadata_props.add()
        prop.key, prop.value = key, value
    onnx.save(graph, str(target))


def _quantise(model: Path, target: Path) -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic  # noqa: PLC0415

    # Weights only. Activations stay float, which is what keeps the accuracy —
    # measured, not assumed: see bench_hindi.py.
    quantize_dynamic(str(model), str(target), weight_type=QuantType.QInt8)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="hi", choices=AVAILABLE)
    parser.add_argument("--out", type=Path, required=True, help="asset directory to write")
    parser.add_argument("--work", type=Path, default=Path("/tmp/indicconformer"))
    parser.add_argument(
        "--keep-fp32",
        action="store_true",
        help="also leave the 493 MB float model, for measuring what int8 cost",
    )
    args = parser.parse_args()

    work = args.work / args.language
    work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"IndicConformer {args.language}")
    _download(f"{REPO}/{args.language}/model.onnx", work / "model.onnx")
    _download(f"{REPO}/{args.language}/vocab.json", work / "vocab.json")

    size = _tokens_txt(work / "vocab.json", args.out / "tokens.txt")
    print(f"  tokens.txt: {size} entries (vocabulary + CTC blank)")

    stamped = work / "model.stamped.onnx"
    _stamp(work / "model.onnx", stamped, size)
    print("  stamped sherpa-onnx metadata")

    _quantise(stamped, args.out / "model.int8.onnx")
    print(f"  model.int8.onnx ({(args.out / 'model.int8.onnx').stat().st_size:,} bytes)")

    if args.keep_fp32:
        shutil.copy(stamped, args.out / "model.onnx")

    print(f"\nRun tool/asr/bench_hindi.py against {args.out} before shipping it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
