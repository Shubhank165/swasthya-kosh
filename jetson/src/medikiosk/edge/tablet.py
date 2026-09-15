"""The kiosk screen, on a tablet instead of the 2.8" SPI panel.

No Android tablet can be a display sink - there is no cable that makes the Jetson see it as a
monitor - so the pixels have to arrive through something running on the tablet, and the browser is
the one that needs no install. This serves the exact frames `KioskPanel` would have pushed over
SPI, as an MJPEG stream the tablet holds open fullscreen. From the patient's side it is a screen
showing the interview; there is nothing to tap and no page to navigate.

Same open/show/close shape as KioskPanel on purpose, so PanelView drives either without caring
which one is attached, and a tablet that gets unplugged mid-interview fails exactly the way a
loose panel cable already does - the interview keeps going without a screen.

    python3 -m medikiosk.edge.tablet --demo       # serve a sample screen to check the tablet
"""

from __future__ import annotations

import argparse
import io
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Fullscreen, black, no chrome, image scaled to fit whatever the tablet's screen is. The stream
# reconnects itself if the Jetson restarts, so the tablet never has to be touched again once it is
# showing this page.
PAGE = b"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>MediKiosk</title>
<style>
  html,body{margin:0;height:100%;background:#12161c;overflow:hidden}
  body{display:flex;align-items:center;justify-content:center}
  img{max-width:100%;max-height:100%;object-fit:contain;display:block}
</style>
<img id="screen" src="/stream.mjpg" alt="">
<script>
  const img = document.getElementById("screen");
  // A dropped stream (Jetson restart, cable nudge) must recover on its own - nobody is going to
  // walk over and reload a kiosk screen mid-demo.
  img.onerror = () => setTimeout(() => { img.src = "/stream.mjpg?t=" + Date.now(); }, 1000);
  // Keep the tablet awake without needing its screen-timeout setting changed.
  if ("wakeLock" in navigator) {
    const hold = () => navigator.wakeLock.request("screen").catch(() => {});
    hold();
    document.addEventListener("visibilitychange", () => { if (!document.hidden) hold(); });
  }
</script>
"""


class TabletPanel:
    """Serves rendered kiosk screens to a tablet browser over the USB (or any) network link."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8800, scale: int = 4) -> None:
        self.host = host
        self.port = port
        self.scale = scale
        self.server: ThreadingHTTPServer | None = None
        self._frame: bytes | None = None
        # Viewers block on this instead of polling, so a screen change reaches the tablet as soon
        # as it is rendered rather than on the next poll tick.
        self._changed = threading.Condition()

    def open(self) -> None:
        self.server = ThreadingHTTPServer((self.host, self.port), _make_handler(self))
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def show(self, image) -> None:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=90)
        with self._changed:
            self._frame = buffer.getvalue()
            self._changed.notify_all()

    def latest(self, previous: bytes | None, timeout: float = 30.0) -> bytes | None:
        """Block until the displayed frame differs from `previous`, or the timeout expires."""

        with self._changed:
            if self._frame is not None and self._frame is not previous:
                return self._frame
            self._changed.wait(timeout)
            return self._frame

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        with self._changed:
            self._changed.notify_all()


def _make_handler(panel: TabletPanel) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            pass  # a line per frame is noise in the intake log

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(PAGE, "text/html; charset=utf-8")
            elif path == "/frame.jpg":
                frame = panel.latest(None, timeout=5.0)
                if frame is None:
                    self.send_error(503, "no screen rendered yet")
                    return
                self._send(frame, "image/jpeg")
            elif path == "/stream.mjpg":
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
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=medikioskframe")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            previous = None
            try:
                while True:
                    frame = panel.latest(previous)
                    if frame is None:
                        # Nothing rendered yet, or the panel closed. Keep the connection open so a
                        # tablet opened before the interview starts still lights up when it does.
                        if panel.server is None:
                            break
                        continue
                    previous = frame
                    self.wfile.write(b"--medikioskframe\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # tablet went to sleep or the cable moved

    return Handler


def usb_address() -> str | None:
    """The Jetson's address on the USB link to the tablet, so the URL can be printed."""

    try:
        output = subprocess.run(
            ["ip", "-4", "-brief", "addr"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0].startswith("usb"):
            return fields[2].split("/")[0]
    return None


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Serve kiosk screens to a tablet")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--scale", type=int, default=4)
    parser.add_argument("--language", default="hi")
    parser.add_argument("--demo", action="store_true", help="show one sample screen and wait")
    args = parser.parse_args(argv)

    from medikiosk.edge.display import question_screen, render

    panel = TabletPanel(port=args.port, scale=args.scale)
    panel.open()
    address = usb_address() or socket.gethostbyname(socket.gethostname())
    print(f"tablet display: http://{address}:{args.port}/", flush=True)

    if args.demo:
        panel.show(render(question_screen("ask_complaint", args.language, step=(1, 7)), args.scale))
        print("showing a sample screen; Ctrl+C to stop", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        panel.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
