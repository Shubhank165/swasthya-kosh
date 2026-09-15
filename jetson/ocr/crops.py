"""Cut pages into line crops with PP-OCRv5's text detector.

TrOCR and the CRNN are *recognizers*: they read one crop and have no idea where text is on a page.
Scoring them on a whole page measures the missing detector, not the model. This produces the crops
once so those models can be judged on the job they actually do.

Detection is Paddle and the recognizers are torch, and importing paddle before torch breaks torch
on Windows, so this deliberately runs as its own step rather than inside the bench process.

    python -m ocr.crops --images ocr/samples
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def line_dir(image: Path) -> Path:
    return image.with_name(image.stem + "_lines")


def crop_page(engine, image_path: Path) -> int:
    from PIL import Image

    result = engine.predict(str(image_path))
    boxes: list[list[list[float]]] = []
    for page in result:
        data = page.json["res"] if hasattr(page, "json") else page
        boxes.extend(data.get("dt_polys", []))

    if not boxes:
        return 0

    # Reading order: top to bottom, then left to right within a band the height of a line.
    def key(box):
        ys = [point[1] for point in box]
        xs = [point[0] for point in box]
        return (round(min(ys) / 20), min(xs))

    target = line_dir(image_path)
    target.mkdir(exist_ok=True)
    for old in target.glob("*.png"):
        old.unlink()

    order = []
    with Image.open(image_path) as image:
        page_image = image.convert("RGB")
        for index, box in enumerate(sorted(boxes, key=key)):
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            pad = 4
            crop = page_image.crop(
                (
                    max(0, int(min(xs)) - pad),
                    max(0, int(min(ys)) - pad),
                    min(page_image.width, int(max(xs)) + pad),
                    min(page_image.height, int(max(ys)) + pad),
                )
            )
            name = f"{index:03d}.png"
            crop.save(target / name)
            order.append(name)
    (target / "order.json").write_text(json.dumps(order), encoding="utf-8")
    return len(order)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=Path("ocr/samples"))
    args = parser.parse_args(argv)

    from paddleocr import PaddleOCR

    engine = PaddleOCR(
        lang="hi",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        device="cpu",
    )

    images = [
        p
        for p in sorted(args.images.rglob("*"))
        if p.suffix.lower() in IMAGE_SUFFIXES and not p.parent.name.endswith("_lines")
    ]
    for image in images:
        count = crop_page(engine, image)
        print(f"{image.name:34} {count} line crops -> {line_dir(image).name}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
