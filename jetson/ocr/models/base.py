"""Common shape for every OCR model in the bench.

Models are loaded one at a time and unloaded before the next: several of these want most of a
GPU, and a benchmark that leaves them resident measures memory pressure instead of accuracy.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class ModelInfo:
    key: str
    name: str
    kind: str  # "line" (crop in, text out) or "page" (whole document in)
    handwriting: str  # "trained", "partial", or "no"
    notes: str = ""
    requires: list[str] = field(default_factory=list)


class OcrModel(Protocol):
    info: ModelInfo

    def load(self) -> None: ...

    def recognize(self, image_path: Path) -> str: ...

    def unload(self) -> None: ...


class TorchModelMixin:
    """Shared load/unload bookkeeping for the torch-based models."""

    device: str = "cuda"
    model = None
    processor = None

    def unload(self) -> None:
        self.model = None
        self.processor = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
        except ImportError:
            pass
