"""One adapter per candidate OCR model.

Heavy imports live inside `load()` so the bench can list every model, and run the ones that are
installed, without requiring all of them to be installed at once. A model that cannot load reports
why and is skipped rather than aborting the run.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ocr.models.base import ModelInfo, TorchModelMixin

DEFAULT_PROMPT = "Read all the text in this image exactly as written. Output only the text."


class TesseractHindi:
    info = ModelInfo(
        key="tesseract",
        name="Tesseract 5 (hin+eng)",
        kind="page",
        handwriting="no",
        notes="Baseline only. Printed text; doctor handwriting will be poor.",
        requires=["pytesseract", "tesseract binary with hin.traineddata"],
    )

    def __init__(self, languages: str = "hin+eng") -> None:
        self.languages = languages

    def load(self) -> None:
        import pytesseract

        binary = os.environ.get("TESSERACT_EXE")
        if binary:
            pytesseract.pytesseract.tesseract_cmd = binary
        available = pytesseract.get_languages(config="")
        missing = [code for code in self.languages.split("+") if code not in available]
        if missing:
            raise RuntimeError(f"tesseract is missing language data: {missing}")
        self._pytesseract = pytesseract

    def recognize(self, image_path: Path) -> str:
        from PIL import Image

        with Image.open(image_path) as image:
            return self._pytesseract.image_to_string(image, lang=self.languages)

    def unload(self) -> None:
        self._pytesseract = None


class TrOCRDevanagari(TorchModelMixin):
    info = ModelInfo(
        key="trocr-devanagari",
        name="TrOCR Devanagari (paudelanil/trocr-devanagari-2)",
        kind="line",
        handwriting="trained",
        notes="~0.2B. Word/line crops only - it has no detector, so a full page will score badly. "
        "Decoder was built around Nepali, so treat Hindi output as a baseline to fine-tune.",
        requires=["transformers", "torch"],
    )
    repo = "paudelanil/trocr-devanagari-2"

    def load(self) -> None:
        import torch
        from transformers import (
            RobertaTokenizer,
            TrOCRProcessor,
            VisionEncoderDecoderModel,
            ViTImageProcessor,
        )

        # The repo declares the retired "ViTFeatureExtractor", which TrOCRProcessor no longer
        # resolves, so the two halves are built explicitly from the same files.
        image_processor = ViTImageProcessor.from_pretrained(self.repo)
        # The repo ships vocab.json + merges.txt with no tokenizer.json, so the fast tokenizer
        # cannot be built from it; the slow RoBERTa tokenizer reads those files directly.
        tokenizer = RobertaTokenizer.from_pretrained(self.repo)
        self.processor = TrOCRProcessor(image_processor=image_processor, tokenizer=tokenizer)
        self.model = VisionEncoderDecoderModel.from_pretrained(self.repo)
        self.model.to(self.device if torch.cuda.is_available() else "cpu").eval()

    def recognize(self, image_path: Path) -> str:
        import torch
        from PIL import Image

        with Image.open(image_path) as image:
            pixel_values = self.processor(
                images=image.convert("RGB"), return_tensors="pt"
            ).pixel_values.to(self.model.device)
        with torch.no_grad():
            generated = self.model.generate(pixel_values, max_new_tokens=64)
        return self.processor.batch_decode(generated, skip_special_tokens=True)[0]


class QwenHindiHandwritten(TorchModelMixin):
    info = ModelInfo(
        key="qwen2vl-hindi-hw",
        name="Hindi Handwritten OCR Qwen2-VL-2B (ianuragbhatt)",
        kind="page",
        handwriting="trained",
        notes="~2.2B, fine-tuned on IIIT-INDIC-HW-WORDS-Hindi (handwritten *words*, not "
        "prescriptions). bf16 needs ~6-8 GB VRAM.",
        requires=["transformers", "torch", "accelerate", "qwen-vl-utils"],
    )
    repo = "ianuragbhatt/hindi-handwritten-ocr-qwen2vl-2b"

    def __init__(self, prompt: str = DEFAULT_PROMPT, load_in_4bit: bool = False) -> None:
        self.prompt = prompt
        self.load_in_4bit = load_in_4bit

    def load(self) -> None:
        import torch
        from huggingface_hub import list_repo_files
        from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

        files = list_repo_files(self.repo)
        if not any(name.endswith((".safetensors", ".bin")) for name in files):
            raise RuntimeError(
                f"{self.repo} publishes no weights - only {files}. It is a training recipe, not a "
                "downloadable checkpoint. Point `repo` at your own fine-tune, or train from the "
                "included scripts, before benchmarking it."
            )

        kwargs: dict = {"dtype": torch.bfloat16, "device_map": "auto"}
        if self.load_in_4bit:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
            )
        self.processor = AutoProcessor.from_pretrained(self.repo)
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(self.repo, **kwargs).eval()

    def recognize(self, image_path: Path) -> str:
        import torch
        from PIL import Image

        messages = [
            {
                "role": "user",
                "content": [{"type": "image"}, {"type": "text", "text": self.prompt}],
            }
        ]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        with Image.open(image_path) as image:
            inputs = self.processor(
                text=[text], images=[image.convert("RGB")], return_tensors="pt"
            ).to(self.model.device)
        with torch.no_grad():
            generated = self.model.generate(**inputs, max_new_tokens=256, do_sample=False)
        trimmed = generated[:, inputs["input_ids"].shape[1] :]
        return self.processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()


class PaddleRecDevanagari:
    info = ModelInfo(
        key="ppocrv5-devanagari",
        name="PP-OCRv5 Devanagari mobile (detector + recognizer)",
        kind="page",
        handwriting="no",
        notes="Recognizer is ~7.5 MB. Printed Devanagari and mixed Hindi/English/numbers. "
        "Not trained for messy handwriting.",
        requires=["paddleocr", "paddlepaddle"],
    )

    def __init__(self, use_gpu: bool = False, lang: str = "hi") -> None:
        self.use_gpu = use_gpu
        # "hi" resolves to devanagari_PP-OCRv5_mobile_rec; "devanagari" is not a valid lang code.
        self.lang = lang

    def load(self) -> None:
        from paddleocr import PaddleOCR

        self.engine = PaddleOCR(
            lang=self.lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # Paddle's oneDNN CPU path dies on Windows with a PIR attribute error; the plain CPU
            # kernels work and this model is 7.5 MB, so the speed loss is irrelevant.
            enable_mkldnn=False,
            device="gpu" if self.use_gpu else "cpu",
        )

    def recognize(self, image_path: Path) -> str:
        result = self.engine.predict(str(image_path))
        lines: list[str] = []
        for page in result:
            data = page.json.get("res", page) if hasattr(page, "json") else page
            lines.extend(data.get("rec_texts", []))
        return "\n".join(lines)

    def unload(self) -> None:
        self.engine = None


class PaddleOcrVL:
    info = ModelInfo(
        key="paddleocr-vl",
        name="PaddleOCR-VL-0.9B (document VLM)",
        kind="page",
        handwriting="partial",
        notes="0.9B document model: layout, tables, and text in 109 languages. The closest thing "
        "here to a whole-prescription parser. Run through PaddleOCR's own pipeline - the HF "
        "remote code targets transformers 4.x and breaks on 5.x.",
        requires=["paddleocr", "paddlepaddle"],
    )

    def __init__(self, use_gpu: bool = False) -> None:
        self.use_gpu = use_gpu

    def load(self) -> None:
        from paddleocr import PaddleOCRVL

        self.engine = PaddleOCRVL(device="gpu" if self.use_gpu else "cpu")

    def recognize(self, image_path: Path) -> str:
        results = self.engine.predict(str(image_path))
        chunks: list[str] = []
        for page in results:
            data = page.json.get("res", {}) if hasattr(page, "json") else {}
            markdown = data.get("markdown")
            if isinstance(markdown, dict):
                chunks.append(str(markdown.get("markdown_texts", "")))
            elif markdown:
                chunks.append(str(markdown))
            else:
                blocks = data.get("parsing_res_list", [])
                chunks.extend(str(block.get("block_content", "")) for block in blocks)
        return chr(10).join(chunk for chunk in chunks if chunk)

    def unload(self) -> None:
        self.engine = None


class HindiCrnnCtc(TorchModelMixin):
    info = ModelInfo(
        key="crnn-ctc-hindi",
        name="Hindi CRNN+CTC (rajesh-1902/hindi-ocr-crnn-ctc)",
        kind="line",
        handwriting="no",
        notes="Trained on 80k synthetic printed Hindi lines. Lightweight printed-Hindi baseline.",
        requires=["torch", "huggingface_hub", "model-specific code"],
    )
    repo = "rajesh-1902/hindi-ocr-crnn-ctc"

    def load(self) -> None:
        from huggingface_hub import list_repo_files

        files = list_repo_files(self.repo)
        # A bare checkpoint with no config or module has no defined architecture to load into.
        if not any(name.endswith((".py", "config.json")) for name in files):
            raise RuntimeError(
                f"{self.repo} publishes only weights ({files}); it needs the author's model code "
                "before it can be scored. Skipping is more honest than guessing an architecture."
            )
        raise RuntimeError("CRNN loader not implemented yet; see repo files: " + ", ".join(files))

    def recognize(self, image_path: Path) -> str:
        raise NotImplementedError


class SuryaOcr(TorchModelMixin):
    info = ModelInfo(
        key="surya",
        name="Surya OCR (datalab-to/surya)",
        kind="page",
        handwriting="partial",
        notes="Detection + recognition, 90+ languages including Hindi. Non-commercial licence "
        "(cc-by-nc-sa) below a revenue threshold - check before shipping.",
        requires=["surya-ocr", "torch", "vllm or llama.cpp backend"],
    )

    def __init__(self, backend: str = "llamacpp") -> None:
        # Surya 0.22 autodetects "vllm" whenever an NVIDIA GPU is present, and vLLM does not run
        # on Windows - it hangs forever on its own server lock file. llamacpp is the portable path
        # and the only one plausible on a Jetson.
        self.backend = backend

    def load(self) -> None:
        import os

        os.environ["SURYA_INFERENCE_BACKEND"] = self.backend
        from surya.inference import SuryaInferenceManager
        from surya.recognition import RecognitionPredictor

        # Surya 0.22 runs full-page OCR as a single VLM call per page and falls back to
        # layout + per-block OCR itself; the old det_predictor= keyword is gone.
        self.recognizer = RecognitionPredictor(SuryaInferenceManager(method=self.backend))

    def recognize(self, image_path: Path) -> str:
        from PIL import Image

        with Image.open(image_path) as image:
            pages = self.recognizer([image.convert("RGB")], full_page=True)
        # Full-page mode returns layout blocks carrying HTML, not flat text lines.
        chunks = []
        for page in pages:
            for block in page.model_dump().get("blocks", []):
                html = block.get("html") or ""
                if html and not block.get("skipped"):
                    chunks.append(html)
        return chr(10).join(chunks)

    def unload(self) -> None:
        self.recognizer = None
        super().unload()


class ChandraOcr(TorchModelMixin):
    info = ModelInfo(
        key="chandra",
        name="Chandra 9B (datalab-to/chandra)",
        kind="page",
        handwriting="partial",
        notes="9B Qwen3-VL document model, 17.5 GB in bf16. Loaded 4-bit here because the card "
        "has 16 GB. Far too large for an 8 GB Jetson even quantised.",
        requires=["chandra-ocr", "transformers", "torch", "bitsandbytes"],
    )
    repo = "datalab-to/chandra"

    def __init__(self, load_in_4bit: bool = True) -> None:
        self.load_in_4bit = load_in_4bit

    def load(self) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        # Chandra is a Qwen3-VL, which is an image-text-to-text model, not a plain causal LM.
        kwargs: dict = {"dtype": torch.bfloat16, "device_map": "auto", "trust_remote_code": True}
        if self.load_in_4bit:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
            )
        self.processor = AutoProcessor.from_pretrained(self.repo, trust_remote_code=True)
        self.model = AutoModelForImageTextToText.from_pretrained(self.repo, **kwargs).eval()
        self.model.processor = self.processor

    def recognize(self, image_path: Path) -> str:
        from chandra.model.hf import generate_hf
        from chandra.model.schema import BatchInputItem
        from PIL import Image

        with Image.open(image_path) as image:
            batch = [BatchInputItem(image=image.convert("RGB"), prompt_type="ocr_layout")]
            result = generate_hf(batch, self.model)[0]
        return getattr(result, "markdown", None) or getattr(result, "text", "") or str(result)


class GotOcr2(TorchModelMixin):
    info = ModelInfo(
        key="got-ocr2",
        name="GOT-OCR 2.0 (base of HindiOCR-VLM)",
        kind="page",
        handwriting="no",
        notes="580M. This is the BASE model HindiOCR-VLM fine-tunes; the Hindi LoRA adapters are "
        "published only on Google Drive, so this measures the starting point, not their result.",
        requires=["transformers", "torch"],
    )
    # The original stepfun-ai/GOT-OCR2_0 ships custom code with no standard processor class;
    # this is the transformers-native conversion of the same weights.
    repo = "stepfun-ai/GOT-OCR-2.0-hf"

    def load(self) -> None:
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.processor = AutoProcessor.from_pretrained(self.repo)
        self.model = AutoModelForImageTextToText.from_pretrained(
            self.repo, dtype=torch.bfloat16, device_map="auto"
        ).eval()

    def recognize(self, image_path: Path) -> str:
        import torch
        from PIL import Image

        with Image.open(image_path) as image:
            inputs = self.processor(image.convert("RGB"), return_tensors="pt").to(
                self.model.device
            )
        with torch.no_grad():
            generated = self.model.generate(**inputs, max_new_tokens=1024, do_sample=False)
        trimmed = generated[:, inputs["input_ids"].shape[1] :]
        return self.processor.batch_decode(trimmed, skip_special_tokens=True)[0].strip()


class PPOcrOnnx:
    info = ModelInfo(
        key="ppocrv5-onnx",
        name="PP-OCRv5 Devanagari via onnxruntime (RapidOCR)",
        kind="page",
        handwriting="no",
        notes="The same 7.9 MB Devanagari recognizer and 4.8 MB detector as the Paddle build, run "
        "as ONNX. PaddlePaddle segfaults on aarch64, so this is the only way PP-OCRv5 runs on the "
        "Jetson - and onnxruntime is already there for the VAD.",
        requires=["rapidocr", "onnxruntime"],
    )

    def __init__(self, model_dir: str = "offline/jetson/models/ppocr_onnx") -> None:
        self.model_dir = Path(model_dir)
        # The 88 MB server detector finds more text than the 4.8 MB mobile one but costs about
        # four times the wall clock; document capture can afford it, a live viewfinder cannot.
        self.detector = os.environ.get("MEDIKIOSK_PPOCR_DET", "det.onnx")

    def load(self) -> None:
        from rapidocr import RapidOCR

        missing = [
            name
            for name in (self.detector, "rec.onnx", "devanagari_dict.txt")
            if not (self.model_dir / name).exists()
        ]
        if missing:
            raise RuntimeError(f"{self.model_dir} is missing {missing}")
        self.engine = RapidOCR(
            params={
                "Det.model_path": str(self.model_dir / self.detector),
                "Rec.model_path": str(self.model_dir / "rec.onnx"),
                "Rec.rec_keys_path": str(self.model_dir / "devanagari_dict.txt"),
                # Orientation classification is a third model for no gain on kiosk captures.
                "Global.use_cls": False,
            }
        )

    def recognize(self, image_path: Path) -> str:
        text, _ = self.read(image_path)
        return text

    def read(self, image_path: Path) -> tuple[str, list[float]]:
        """Recognized text plus the per-line confidence the recognizer already computed.

        `recognize` threw the scores away. They are the cheapest signal available for telling a
        printed document from a handwritten one: this recognizer is trained on printed Devanagari,
        so its confidence collapses on handwriting rather than the text merely being wrong. Measured
        on this Jetson over the printed sample set, mean line confidence is 0.90-0.98 - 0.90-0.94
        even for camera photographs rather than clean scans.
        """

        result = self.engine(str(image_path))
        return chr(10).join(result.txts or []), [float(s) for s in (result.scores or [])]

    def unload(self) -> None:
        self.engine = None


def tesseract_present() -> bool:
    binary = os.environ.get("TESSERACT_EXE", "tesseract")
    try:
        subprocess.run([binary, "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


REGISTRY: dict[str, type | object] = {
    "tesseract": TesseractHindi,
    "ppocrv5-devanagari": PaddleRecDevanagari,
    "ppocrv5-onnx": PPOcrOnnx,
    "trocr-devanagari": TrOCRDevanagari,
    "qwen2vl-hindi-hw": QwenHindiHandwritten,
    "paddleocr-vl": PaddleOcrVL,
    "crnn-ctc-hindi": HindiCrnnCtc,
    "surya": SuryaOcr,
    "chandra": ChandraOcr,
    "got-ocr2": GotOcr2,
}
