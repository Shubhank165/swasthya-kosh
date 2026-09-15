"""Run every available OCR model over a folder of images and score them side by side.

Usage:

    python -m ocr.bench --images ocr/samples                  # all installed models
    python -m ocr.bench --images ocr/samples --models tesseract,ppocrv5-devanagari
    python -m ocr.bench --images ocr/samples --json results.json

Ground truth is optional. Put the expected text in `<image>.gt.txt` beside the image and the run
reports CER, WER, and keyword recall; without it the run still prints each model's output so you
can read the failures yourself, which is usually more informative than an average.

Critical tokens - a drug name, a dose, a date - go one per line in `<image>.keywords.txt`. A model
can post a respectable CER while dropping exactly the token that matters clinically.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path

from ocr.metrics import (
    character_error_rate,
    keyword_recall,
    keyword_recall_fuzzy,
    normalize,
    word_error_rate,
)
from ocr.models.adapters import REGISTRY

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class PageResult:
    image: str
    text: str
    seconds: float
    cer: float | None = None
    wer: float | None = None
    keywords: float | None = None
    keywords_fuzzy: float | None = None
    error: str | None = None


@dataclass
class ModelResult:
    key: str
    name: str
    kind: str
    handwriting: str
    loaded: bool
    load_seconds: float = 0.0
    peak_vram_mb: float = 0.0
    pages: list[PageResult] = None
    error: str | None = None

    def summary(self) -> dict:
        pages = [page for page in (self.pages or []) if page.error is None]
        scored = [page for page in pages if page.cer is not None]
        with_keywords = [page.keywords for page in pages if page.keywords is not None]
        fuzzy = [page.keywords_fuzzy for page in pages if page.keywords_fuzzy is not None]
        return {
            "key": self.key,
            "name": self.name,
            "kind": self.kind,
            "handwriting": self.handwriting,
            "pages_ok": len(pages),
            "pages_failed": len([p for p in (self.pages or []) if p.error]),
            "median_seconds": round(statistics.median([p.seconds for p in pages]), 2)
            if pages
            else None,
            "mean_cer": round(statistics.fmean([p.cer for p in scored]), 4) if scored else None,
            "mean_wer": round(statistics.fmean([p.wer for p in scored]), 4) if scored else None,
            "keyword_recall": round(statistics.fmean(with_keywords), 4) if with_keywords else None,
            "keyword_fuzzy": round(statistics.fmean(fuzzy), 4) if fuzzy else None,
            "peak_vram_mb": round(self.peak_vram_mb, 1),
            "load_seconds": round(self.load_seconds, 1),
            "error": self.error,
        }


def find_images(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(
        p
        for p in root.rglob("*")
        if p.suffix.lower() in IMAGE_SUFFIXES and not p.parent.name.endswith("_lines")
    )


def ground_truth(image: Path) -> str | None:
    candidate = image.with_suffix(image.suffix + ".gt.txt")
    if not candidate.exists():
        candidate = image.with_suffix(".gt.txt")
    return candidate.read_text(encoding="utf-8") if candidate.exists() else None


def keywords_for(image: Path) -> list[str]:
    candidate = image.with_suffix(image.suffix + ".keywords.txt")
    if not candidate.exists():
        candidate = image.with_suffix(".keywords.txt")
    if not candidate.exists():
        return []
    lines = candidate.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def run_model(key: str, images: list[Path], verbose: bool) -> ModelResult:
    """Run one model in a separate process.

    Isolation is not optional here: paddle and torch clash over DLLs when imported into the same
    interpreter on Windows, and a shared process would also report one model's VRAM as another's.
    """

    checkpoint = Path(tempfile.gettempdir()) / f"ocr-bench-{key}-{os.getpid()}.json"
    command = [
        sys.executable,
        "-m",
        "ocr.worker",
        "--partial",
        str(checkpoint),
        key,
        *[str(p) for p in images],
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    if not lines and checkpoint.exists():
        # The worker died part way; keep the pages it did finish rather than discarding them.
        lines = [checkpoint.read_text(encoding="utf-8")]
        print(f"    (worker died; recovered {len(json.loads(lines[0])['pages'])} page(s))")
    if not lines:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        return ModelResult(
            key=key,
            name=key,
            kind="?",
            handwriting="?",
            loaded=False,
            pages=[],
            error=detail[-1][:200] if detail else f"worker exited {completed.returncode}",
        )

    checkpoint.unlink(missing_ok=True)
    payload = json.loads(lines[-1])
    result = ModelResult(
        key=payload["key"],
        name=payload.get("name", key),
        kind=payload.get("kind", "?"),
        handwriting=payload.get("handwriting", "?"),
        loaded=payload["loaded"],
        load_seconds=payload.get("load_seconds", 0.0),
        peak_vram_mb=payload.get("peak_vram_mb", 0.0),
        pages=[],
        error=payload.get("error"),
    )

    for entry in payload["pages"]:
        page = PageResult(
            image=entry["image"],
            text=entry["text"],
            seconds=entry["seconds"],
            error=entry["error"],
        )
        image_path = next((p for p in images if p.name == entry["image"]), None)
        reference = ground_truth(image_path) if image_path else None
        if image_path is not None and page.error is None:
            if reference is not None:
                page.cer = character_error_rate(reference, page.text)
                page.wer = word_error_rate(reference, page.text)
            # Keyword recall needs no full transcript. For handwriting that matters: a list of the
            # drugs and doses a reader is sure of is honest, a whole invented transcript is not,
            # and keyword recall is the number that decides whether a model is safe to use.
            words = keywords_for(image_path)
            if words:
                page.keywords = keyword_recall(words, page.text)
                page.keywords_fuzzy = keyword_recall_fuzzy(words, page.text)
        result.pages.append(page)
        if verbose:
            status = page.error or (normalize(page.text)[:110] or "<empty>")
            print(f"    {page.image:28} {page.seconds:6.2f}s  {status}")
    return result


def _cell(value: float | None) -> str:
    return ("-" if value is None else f"{value:.3f}").ljust(8)


def print_table(results: list[ModelResult], scored: bool) -> None:
    headers = ["model", "kind", "hw", "sec/img", "VRAM MB", "load s"]
    if scored:
        headers[3:3] = ["CER", "WER", "keyword", "kw~fuzzy"]
    widths = [34, 5, 8, 8, 8, 8, 9, 8, 9, 8]
    print()
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=False)))
    print("-" * 96)
    for result in results:
        summary = result.summary()
        if summary["error"]:
            print(f"{summary['name'][:34]:34}  UNAVAILABLE  {summary['error'][:60]}")
            continue
        row = [
            summary["name"][:34].ljust(34),
            summary["kind"].ljust(5),
            summary["handwriting"].ljust(8),
        ]
        if scored:
            row += [
                _cell(summary["mean_cer"]),
                _cell(summary["mean_wer"]),
                _cell(summary["keyword_recall"]),
                _cell(summary["keyword_fuzzy"]),
            ]
        row += [
            f"{summary['median_seconds']}".ljust(8),
            f"{summary['peak_vram_mb']}".ljust(9),
            f"{summary['load_seconds']}".ljust(8),
        ]
        print("  ".join(row))


def write_texts(results: list[ModelResult], out_dir: Path) -> None:
    """Dump what each model actually read, per image and as one file per model.

    The table says which model is better; only the text says *how* it failed, which is what
    decides whether a failure is recoverable (a mangled drug name) or silent (a dropped line).
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    for result in results:
        model_dir = out_dir / result.key
        model_dir.mkdir(exist_ok=True)
        combined = [f"# {result.name}", f"# key: {result.key}"]
        if result.error:
            combined.append(f"# UNAVAILABLE: {result.error}")
        for page in result.pages or []:
            stem = Path(page.image).stem
            body = page.error and f"ERROR: {page.error}" or page.text
            (model_dir / f"{stem}.txt").write_text(body, encoding="utf-8")
            scores = []
            if page.cer is not None:
                scores.append(f"CER={page.cer:.3f} WER={page.wer:.3f}")
            if page.keywords is not None:
                scores.append(f"keywords={page.keywords:.3f}")
            header = f"{page.image}  ({page.seconds:.2f}s"
            header += f", {', '.join(scores)})" if scores else ")"
            combined += ["", "=" * 100, header, "=" * 100, "", body]
        (out_dir / f"{result.key}.txt").write_text(chr(10).join(combined), encoding="utf-8")
    print()
    print(f"text output -> {out_dir}/<model>.txt and {out_dir}/<model>/<image>.txt")


def rescore(path: Path, images_root: Path, out_dir: Path | None = None) -> int:
    """Re-apply the current metrics to text a previous run already produced.

    Scoring rules change - stripping table markup, adding keywords - and re-running a model that
    takes two minutes a page to answer a question about arithmetic would be wasteful.
    """

    images = {image.name: image for image in find_images(images_root)}
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for entry in payload:
        summary = entry["summary"]
        result = ModelResult(
            key=summary["key"],
            name=summary["name"],
            kind=summary["kind"],
            handwriting=summary["handwriting"],
            loaded=summary["error"] is None,
            peak_vram_mb=summary.get("peak_vram_mb", 0.0),
            load_seconds=summary.get("load_seconds", 0.0),
            pages=[],
            error=summary["error"],
        )
        for saved in entry["pages"]:
            page = PageResult(
                image=saved["image"],
                text=saved["text"],
                seconds=saved["seconds"],
                error=saved["error"],
            )
            image_path = images.get(saved["image"])
            if image_path is not None and page.error is None:
                reference = ground_truth(image_path)
                if reference is not None:
                    page.cer = character_error_rate(reference, page.text)
                    page.wer = word_error_rate(reference, page.text)
                words = keywords_for(image_path)
                if words:
                    page.keywords = keyword_recall(words, page.text)
                    page.keywords_fuzzy = keyword_recall_fuzzy(words, page.text)
            result.pages.append(page)
        results.append(result)
    print(f"rescored {path} against {len(images)} image(s)")
    print_table(results, scored=True)
    if out_dir:
        write_texts(results, out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, which cannot print a Devanagari transcript at all.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--images", type=Path, default=Path("ocr/samples"))
    parser.add_argument("--models", default="", help="comma-separated keys; default is all")
    parser.add_argument("--json", type=Path, default=None, help="write full results here")
    parser.add_argument("--quiet", action="store_true", help="table only, no per-image output")
    parser.add_argument("--list", action="store_true", help="list model keys and exit")
    parser.add_argument(
        "--rescore",
        type=Path,
        default=None,
        help="re-score a saved --json result with the current metrics, without re-running models",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        help="write each model's recognized text into this directory",
    )
    args = parser.parse_args(argv)

    if args.list:
        for key, factory in REGISTRY.items():
            info = factory().info
            print(f"{key:22} {info.name}")
            print(f"{'':22} kind={info.kind} handwriting={info.handwriting}")
            print(f"{'':22} needs: {', '.join(info.requires)}")
            print(f"{'':22} {info.notes}")
        return 0

    if args.rescore:
        return rescore(args.rescore, args.images, args.export)

    images = find_images(args.images)
    if not images:
        print(f"No images under {args.images}. Drop prescriptions/reports there and re-run.")
        return 2
    scored = any(ground_truth(image) is not None or keywords_for(image) for image in images)
    keys = [k.strip() for k in args.models.split(",") if k.strip()] or list(REGISTRY)
    unknown = [k for k in keys if k not in REGISTRY]
    if unknown:
        print(f"Unknown model keys: {unknown}. Known: {list(REGISTRY)}")
        return 2

    with_gt = sum(1 for image in images if ground_truth(image) is not None)
    with_kw = sum(1 for image in images if keywords_for(image))
    print(
        f"{len(images)} image(s), {len(keys)} model(s), "
        f"{with_gt} with ground truth, {with_kw} with keyword lists"
    )
    results = []
    for key in keys:
        print(f"\n== {key} ==")
        try:
            results.append(run_model(key, images, verbose=not args.quiet))
        except Exception:
            traceback.print_exc()
    print_table(results, scored)

    if args.export:
        write_texts(results, args.export)

    if args.json:
        payload = [
            {"summary": r.summary(), "pages": [asdict(p) for p in (r.pages or [])]} for r in results
        ]
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nfull output -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
