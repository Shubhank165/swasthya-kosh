"""Offline speech synthesis: Piper where a voice exists, Flite everywhere else.

Piper is a neural voice and sounds markedly better, but it only covers five of the nine kiosk
languages. Flite's CMU Indic voices cover the rest. Both are plain binaries invoked per prompt, so
neither holds memory between turns.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class SynthesisFailed(RuntimeError):
    """The local TTS binary could not produce audio."""


class PiperTTS:
    """A resident Piper process, one per voice.

    Invoking the binary per prompt reloaded the 63 MB model every time and cost about two seconds
    a turn. Kept alive and fed a line at a time, the model loads once and a prompt costs inference
    alone.
    """

    def __init__(self, binary: Path | str, voice: Path | str) -> None:
        # Absolute: synthesis runs with cwd set to the binary's own directory (Piper loads its
        # espeak data from there), and a relative program path would be resolved against that.
        self.binary = Path(binary).resolve()
        self.voice = Path(voice).resolve()
        self._workdir = tempfile.TemporaryDirectory(prefix="piper-")
        self._process: subprocess.Popen[bytes] | None = None

    def _start(self) -> subprocess.Popen[bytes]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self._process = subprocess.Popen(
            [
                str(self.binary),
                "--model", str(self.voice),
                "--output_dir", self._workdir.name,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=str(self.binary.parent),
        )
        return self._process

    def synthesize(self, text: str) -> bytes:
        if not text.strip():
            raise ValueError("Refusing to synthesize empty text")
        # One line in, one output path out. Newlines would be read as separate utterances.
        line = " ".join(text.split()) + chr(10)
        process = self._start()
        assert process.stdin is not None and process.stdout is not None
        try:
            process.stdin.write(line.encode("utf-8"))
            process.stdin.flush()
            path = process.stdout.readline().decode("utf-8").strip()
        except (BrokenPipeError, OSError) as error:
            self.close()
            raise SynthesisFailed(f"piper died: {error}") from error
        if not path or not Path(path).exists():
            self.close()
            raise SynthesisFailed(f"piper produced no audio for {text[:40]!r}")
        audio = Path(path).read_bytes()
        Path(path).unlink(missing_ok=True)
        return audio

    def close(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None


class FliteTTS:
    def __init__(self, binary: Path | str, voice: Path | str) -> None:
        self.binary = Path(binary)
        self.voice = Path(voice)

    def synthesize(self, text: str, duration_stretch: float = 1.0, f0_mean: int = 110) -> bytes:
        if not text.strip():
            raise ValueError("Refusing to synthesize empty text")
        with tempfile.TemporaryDirectory() as workdir:
            output = Path(workdir) / "out.wav"
            result = subprocess.run(
                [
                    str(self.binary),
                    "-voice", str(self.voice),
                    "--setf", f"duration_stretch={duration_stretch}",
                    "--setf", f"int_f0_target_mean={f0_mean}",
                    "-t", text,
                    str(output),
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0 or not output.exists():
                raise SynthesisFailed(result.stderr.decode("utf-8", "replace")[-400:])
            return output.read_bytes()
