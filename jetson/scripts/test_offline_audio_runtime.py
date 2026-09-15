import subprocess
import sys
from pathlib import Path

import onnxruntime


def main() -> None:
    model_path = Path(sys.argv[1])
    if not model_path.is_file() or model_path.stat().st_size < 100_000:
        raise SystemExit(f"Silero model is missing or incomplete: {model_path}")

    session = onnxruntime.InferenceSession(
        str(model_path),
        providers=["CPUExecutionProvider"],
    )
    input_names = {item.name for item in session.get_inputs()}
    required = {"input", "state", "sr"}
    if not required.issubset(input_names):
        raise SystemExit(f"Unexpected Silero inputs: {sorted(input_names)}")

    deep_filter_path = Path(sys.argv[2])
    result = subprocess.run(
        [str(deep_filter_path), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    if "deep_filter" not in result.stdout:
        raise SystemExit(f"Unexpected DeepFilterNet version output: {result.stdout}")

    print("Silero ONNX and native DeepFilterNet runtime checks passed")


if __name__ == "__main__":
    main()
