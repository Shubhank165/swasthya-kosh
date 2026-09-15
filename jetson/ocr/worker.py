"""Run one OCR model over a list of images and print the result as JSON.

Each model runs in its own process for two reasons. Paddle and torch fight over DLLs on Windows -
importing paddle first makes a later `import torch` die with `WinError 127` on shm.dll - and a
fresh process is the only way to measure a model's peak VRAM without another model's allocator
still holding memory.

Not meant to be called directly; `ocr.bench` drives it.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from ocr.crops import line_dir
from ocr.models.adapters import REGISTRY


def read_page(model, image: Path) -> str:
    """Recognizers with no detector read pre-cut line crops; page models read the page."""

    crops = line_dir(image)
    if model.info.kind == "line" and crops.is_dir():
        order = json.loads((crops / "order.json").read_text(encoding="utf-8"))
        joined = [model.recognize(crops / name) for name in order]
        return chr(10).join(joined)
    return model.recognize(image)


def main(argv: list[str]) -> int:
    # Devanagari through a cp1252 console raises UnicodeEncodeError and loses the whole run.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    partial: Path | None = None
    if argv[0] == "--partial":
        partial, argv = Path(argv[1]), argv[2:]
    key, image_paths = argv[0], [Path(p) for p in argv[1:]]
    payload: dict = {"key": key, "loaded": False, "pages": [], "error": None}

    factory = REGISTRY[key]
    model = factory()
    payload["name"] = model.info.name
    payload["kind"] = model.info.kind
    payload["handwriting"] = model.info.handwriting

    started = time.monotonic()
    try:
        model.load()
    except Exception as error:
        payload["error"] = f"{type(error).__name__}: {error}"
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    payload["loaded"] = True
    payload["load_seconds"] = round(time.monotonic() - started, 2)

    for image in image_paths:
        began = time.monotonic()
        page: dict = {"image": image.name, "text": "", "error": None}
        try:
            page["text"] = read_page(model, image)
        except Exception as error:
            page["error"] = f"{type(error).__name__}: {error}"
        page["seconds"] = round(time.monotonic() - began, 3)
        payload["pages"].append(page)
        # Checkpoint every page: a model that takes two minutes a page must not lose an hour of
        # work because it dies on the last one, and paddle can take the process down with it.
        if partial is not None:
            partial.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"    {image.name:28} {page['seconds']:6.2f}s", file=sys.stderr, flush=True)

    payload["peak_vram_mb"] = 0.0
    if "torch" in sys.modules:
        import torch

        if torch.cuda.is_available():
            payload["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 1)

    model.unload()
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
