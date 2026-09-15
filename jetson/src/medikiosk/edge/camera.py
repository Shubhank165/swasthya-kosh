"""Live camera preview for the kiosk, as MJPEG over the private tailnet.

The camera already emits MJPEG in hardware, so frames are forwarded byte for byte: no decode, no
re-encode, almost no CPU. That matters because this has to share an 8 GB board with Whisper.

Binds to the tailnet address by default, never 0.0.0.0. A camera pointed at prescriptions and
patients is clinical data, and the handoff notes are explicit that the kiosk must not be reachable
from the public internet.

    python3 -m medikiosk.edge.camera                     # tailnet only
    python3 -m medikiosk.edge.camera --host 127.0.0.1    # local only
    python3 -m medikiosk.edge.camera --size 1920x1080
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOI = b"\xff\xd8"  # JPEG start of image
EOI = b"\xff\xd9"  # JPEG end of image

PAGE = b"""<!doctype html>
<title>MediKiosk camera</title>
<style>
  html,body{margin:0;height:100%;background:#111;color:#ddd;
            font:14px system-ui,sans-serif;display:flex;flex-direction:column}
  header{padding:.5rem .75rem;background:#000;border-bottom:1px solid #333}
  img{flex:1;min-height:0;object-fit:contain;background:#000}
</style>
<header>MediKiosk camera preview &mdash; live from /dev/video0</header>
<img src="/stream.mjpg" alt="camera">
"""


class FrameSource:
    """One ffmpeg reader shared by every viewer; the newest frame is what anyone gets."""

    def __init__(self, device: str, size: str, fps: int) -> None:
        self.command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", size,
            "-framerate", str(fps),
            "-i", device,
            "-c", "copy",  # the sensor already gives us JPEG; do not spend CPU re-encoding
            "-f", "mjpeg",
            "pipe:1",
        ]
        self.frame: bytes | None = None
        self.updated = threading.Condition()
        self.process: subprocess.Popen[bytes] | None = None
        self.stopped = False

    def start(self) -> None:
        self.process = subprocess.Popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        buffer = b""
        while not self.stopped:
            chunk = self.process.stdout.read(16384)
            if not chunk:
                break
            buffer += chunk
            # Frames arrive back to back; cut on the JPEG markers rather than guessing a size.
            while True:
                start = buffer.find(SOI)
                end = buffer.find(EOI, start + 2) if start != -1 else -1
                if start == -1 or end == -1:
                    break
                with self.updated:
                    self.frame = buffer[start : end + 2]
                    self.updated.notify_all()
                buffer = buffer[end + 2 :]
        self._fail()

    def _fail(self) -> None:
        detail = ""
        if self.process is not None and self.process.stderr is not None:
            detail = self.process.stderr.read().decode("utf-8", "replace").strip()[-300:]
        print(f"camera stream ended. {detail}", file=sys.stderr, flush=True)
        with self.updated:
            self.stopped = True
            self.updated.notify_all()

    def latest(self, timeout: float = 5.0) -> bytes | None:
        with self.updated:
            if self.stopped:
                return None
            self.updated.wait(timeout)
            return self.frame

    def stop(self) -> None:
        self.stopped = True
        if self.process is not None:
            self.process.terminate()


def make_handler(source: FrameSource) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            pass  # one line per frame is not useful

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            if self.path in ("/", "/index.html"):
                self._send(PAGE, "text/html; charset=utf-8")
            elif self.path == "/frame.jpg":
                frame = source.latest()
                if frame is None:
                    self.send_error(503, "no frame from camera")
                    return
                self._send(frame, "image/jpeg")
            elif self.path == "/stream.mjpg":
                self._stream()
            else:
                self.send_error(404)

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _stream(self) -> None:
            self.send_response(200)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=medikioskframe"
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            previous = None
            try:
                while True:
                    frame = source.latest()
                    if frame is None:
                        break
                    if frame is previous:
                        continue
                    previous = frame
                    self.wfile.write(b"--medikioskframe\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # viewer closed the tab

    return Handler


def tailnet_address() -> str | None:
    try:
        output = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return output.splitlines()[0] if output else None
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="/dev/video0")
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument(
        "--host",
        default=None,
        help="default: the tailnet address, so the feed never leaves the private network",
    )
    args = parser.parse_args(argv)

    host = args.host or tailnet_address() or "127.0.0.1"
    source = FrameSource(args.device, args.size, args.fps)
    source.start()

    try:
        server = ThreadingHTTPServer((host, args.port), make_handler(source))
    except OSError as error:
        source.stop()
        if error.errno in (48, 98):  # EADDRINUSE on mac/linux
            print(
                f"camera preview is already running: http://{host}:{args.port}/"
                " -- stop it with: pkill -f medikiosk.edge.camera"
            )
            return 0
        raise
    server.daemon_threads = True
    print(f"camera preview: http://{host}:{args.port}/   (snapshot: /frame.jpg)", flush=True)
    if host not in {"127.0.0.1", "localhost"} and not tailnet_address():
        print("WARNING: bound to a non-tailnet address; this feed is visible on the LAN.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        source.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
