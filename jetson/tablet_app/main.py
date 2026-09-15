"""MediKiosk tablet client: the kiosk screen, its microphone, speaker and camera.

Everything clinical stays on the Jetson - language, question order, red flags, the Ayurvedic
questionnaire, queue routing. This app carries pixels and audio in both directions and reports
which button was pressed. It never decides anything.

Why it shows a server-rendered image instead of laying out its own labels: Devanagari conjuncts
(क्ष, त्र) and Tamil/Kannada ligatures need HarfBuzz shaping, and Kivy's SDL2_ttf path renders them
subtly wrong depending on the build. The Jetson already renders every screen correctly with
Pillow+raqm, so this reuses those exact frames and no Indic text is ever laid out here. The option
buttons are numbered to match the numbers drawn on that image.

Audio matches what the browser client sends: 16 kHz mono signed 16-bit PCM, streamed as binary
WebSocket frames, which is what the Jetson's Silero VAD and whisper.cpp expect.

Configure the Jetson address with KIOSK_HOST, or edit HOST below.
"""

from __future__ import annotations

import base64
import io
import json
import os
import threading
import urllib.request
import uuid

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

HOST = os.environ.get("KIOSK_HOST", "192.168.191.75")
SCREEN_URL = f"http://{HOST}:8800/frame.jpg"
SOCKET_URL = f"ws://{HOST}:8000/ws/session"
OCR_URL = f"http://{HOST}:8000/api/ocr"
ABHA_URL = f"http://{HOST}:8000/api/abha-scan"
FRAME_POLL_SECONDS = 0.4

MIC_RATE = 16000
PAPER = (0.07, 0.086, 0.11, 1)
ACCENT = (0.35, 0.667, 1, 1)

# Stages that want the camera pointed at something.
CAMERA_STAGES = ("abha", "documents")


def post_image(url: str, jpeg: bytes) -> dict:
    """Multipart POST of one JPEG. Hand-rolled to avoid pulling requests into the APK."""

    boundary = uuid.uuid4().hex
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="image"; filename="frame.jpg"\r\n',
            b"Content-Type: image/jpeg\r\n\r\n",
            jpeg,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


class KioskClient:
    """WebSocket link to the Jetson, on its own thread so touch never blocks on the network."""

    def __init__(self, on_message, on_status) -> None:
        self.on_message = on_message
        self.on_status = on_status
        self.socket = None
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        import websocket

        while not self._stop.is_set():
            try:
                self.on_status("connecting")
                self.socket = websocket.create_connection(SOCKET_URL, timeout=10)
                # The connect timeout also becomes the *read* timeout, and the server only speaks
                # when something happens. At 10s that meant every quiet moment threw, looked like a
                # dropped link, and reconnected into a brand new session - which is why the kiosk
                # kept jumping back to the language screen mid-interview. Wait far longer, and use
                # a ping to tell real death from ordinary silence.
                self.socket.settimeout(40)
                self.on_status("connected")
                while not self._stop.is_set():
                    try:
                        self.on_message(json.loads(self.socket.recv()))
                    except websocket.WebSocketTimeoutException:
                        self.socket.ping()  # raises if the link is genuinely gone
            except Exception as error:
                # A kiosk cannot ask anyone to restart it. Drop the link and retry forever.
                self.on_status(f"reconnecting ({type(error).__name__})")
                self.socket = None
                self._stop.wait(2)

    def send(self, payload: dict) -> None:
        self._write(lambda s: s.send(json.dumps(payload)))

    def send_audio(self, pcm: bytes) -> None:
        import websocket

        self._write(lambda s: s.send(pcm, opcode=websocket.ABNF.OPCODE_BINARY))

    def _write(self, action) -> None:
        socket = self.socket
        if socket is None:
            return
        try:
            action(socket)
        except Exception:
            self.socket = None  # the reader thread notices and reconnects

    def stop(self) -> None:
        self._stop.set()
        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass


class Audio:
    """Microphone capture and speech playback, both best-effort.

    A tablet that refuses the microphone, or an audiostream build that will not load, must leave
    the kiosk usable by touch rather than crashing it.
    """

    def __init__(self, on_pcm, on_status) -> None:
        self.on_pcm = on_pcm
        self.on_status = on_status
        self.mic = None
        self.output = None
        self.sample = None
        self.output_rate = None
        self.muted = True  # never stream until the interview actually starts
        self.frames = 0  # counted so a dead microphone can be told from a quiet room
        self.thread = None
        self.stopping = False

    def start_microphone(self) -> None:
        """Capture with Android's own AudioRecord.

        Not audiostream: the version p4a builds ships output support only - core.so, plat_android.so
        and the sources package, with no input module at all - so `from audiostream.input import
        get_input` raised ModuleNotFoundError on the device while playback worked fine. AudioRecord
        goes through pyjnius, which Kivy already depends on, so this adds no native build.
        """

        if self.thread is not None:
            return
        try:
            from jnius import autoclass

            AudioFormat = autoclass("android.media.AudioFormat")
            AudioRecord = autoclass("android.media.AudioRecord")
            AudioSource = autoclass("android.media.MediaRecorder$AudioSource")

            channel = AudioFormat.CHANNEL_IN_MONO
            encoding = AudioFormat.ENCODING_PCM_16BIT
            minimum = AudioRecord.getMinBufferSize(MIC_RATE, channel, encoding)
            if minimum <= 0:
                raise RuntimeError(f"AudioRecord rejected {MIC_RATE} Hz (getMinBufferSize={minimum})")
            # VOICE_RECOGNITION asks Android for its echo canceller and noise suppressor, which a
            # kiosk speaking through its own speaker needs.
            self.mic = AudioRecord(
                AudioSource.VOICE_RECOGNITION, MIC_RATE, channel, encoding, max(minimum * 2, 8192)
            )
            if self.mic.getState() != 1:  # STATE_INITIALIZED
                raise RuntimeError("AudioRecord did not initialise; microphone permission denied?")
            self.mic.startRecording()
            self.thread = threading.Thread(target=self._pump, daemon=True)
            self.thread.start()
            self.on_status("mic ready")
        except Exception as error:
            self.mic = None
            # Reported to the server too: the tablet has no console, and a silent microphone is
            # indistinguishable from a patient who is not talking.
            self.on_status(f"mic unavailable ({type(error).__name__}: {error})")

    def _pump(self) -> None:
        """Read PCM in VAD-sized chunks and hand them upward. 1600 samples = 100 ms at 16 kHz."""

        buffer = bytearray(3200)
        while not self.stopping:
            try:
                read = self.mic.read(buffer, 0, len(buffer))
            except Exception as error:
                self.on_status(f"mic read failed ({type(error).__name__}: {error})")
                return
            if read <= 0:
                continue
            self.frames += 1
            if not self.muted:
                self.on_pcm(bytes(buffer[:read]))

    def play(self, pcm: bytes, rate: int) -> None:
        try:
            from audiostream import AudioSample, get_output

            # The output stream is fixed to one rate at creation, but Piper and Flite voices do not
            # share a rate, so rebuild it whenever the server sends audio at a different one.
            if self.output is None or self.output_rate != rate:
                self.output = get_output(channels=1, rate=rate, buffersize=2048, encoding=16)
                self.sample = AudioSample()
                self.output.add_sample(self.sample)
                self.sample.play()
                self.output_rate = rate
            self.sample.write(pcm)
        except Exception as error:
            self.on_status(f"playback failed ({type(error).__name__})")

    def stop(self) -> None:
        self.stopping = True
        try:
            if self.mic is not None:
                self.mic.stop()
                self.mic.release()
        except Exception:
            pass


class KioskRoot(BoxLayout):
    def __init__(self, **kwargs) -> None:
        super().__init__(orientation="vertical", **kwargs)
        with self.canvas.before:
            Color(*PAPER)
            self._background = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._resize, size=self._resize)

        self.screen_image = Image(allow_stretch=True, keep_ratio=True)
        self.add_widget(self.screen_image)

        self.camera = None
        self.camera_box = BoxLayout(size_hint_y=None, height=0)
        self.add_widget(self.camera_box)

        # Typing is always available. Speech recognition mishears, rooms are loud, and a patient
        # who cannot be understood must still be able to answer rather than restart the intake.
        self.typed = TextInput(
            hint_text="type your answer", multiline=False, size_hint_y=None, height=0,
            font_size="20sp", padding=(12, 12),
        )
        self.typed.bind(on_text_validate=lambda _w: self.submit_typed())
        self.add_widget(self.typed)

        self.buttons = BoxLayout(size_hint_y=None, height=0, spacing=8, padding=8)
        self.add_widget(self.buttons)

        # Always-present navigation, so a mistap is recoverable and staff can reset between
        # patients without killing the app.
        self.nav = BoxLayout(size_hint_y=None, height=64, spacing=8, padding=(8, 4))
        self.add_widget(self.nav)

        self.status = Label(
            text="starting", size_hint_y=None, height=28, color=(0.55, 0.58, 0.63, 1),
            font_size="13sp",
        )
        self.add_widget(self.status)

        self.stage = None
        self.question_id = None
        self.option_values: list[str] = []
        self.control: dict | None = None
        self.control_value: float = 0.0
        self.value_label = None

        self.audio = Audio(self._send_audio, self.set_status)
        self.client = KioskClient(self.handle_message, self.set_status)
        self.client.start()
        self.build_nav()
        Clock.schedule_interval(self.refresh_frame, FRAME_POLL_SECONDS)
        Clock.schedule_once(lambda _dt: self.audio.start_microphone(), 2)
        # Mirror the app's own status into the server log once connected. Without this a failed
        # microphone or camera is invisible from anywhere but the tablet's own status line.
        Clock.schedule_once(lambda _dt: self.report_health(), 6)

    def build_nav(self) -> None:
        for label, handler, colour in (
            ("BACK", lambda: self.client.send({"type": "flow.back"}), (0.24, 0.33, 0.4, 1)),
            ("KEYBOARD", self.toggle_keyboard, (0.24, 0.33, 0.4, 1)),
            ("NEW PATIENT", self.restart, (0.55, 0.22, 0.25, 1)),
        ):
            button = Button(
                text=label, font_size="17sp", background_normal="", background_color=colour,
                color=(0.93, 0.96, 0.98, 1), bold=True,
            )
            button.bind(on_release=lambda _b, h=handler: h())
            self.nav.add_widget(button)

    def toggle_keyboard(self) -> None:
        showing = self.typed.height == 0
        self.typed.height = 64 if showing else 0
        if showing:
            self.typed.focus = True

    def submit_typed(self) -> None:
        text = self.typed.text.strip()
        if not text:
            return
        self.typed.text = ""
        if self.stage == "abha":
            self.client.send({"type": "flow.abha", "value": text})
        else:
            self.client.send({"type": "transcript.submit", "text": text, "language": "auto"})

    def restart(self) -> None:
        self.client.send({"type": "flow.restart"})
        self.typed.text = ""

    def report_health(self) -> None:
        self.client.send(
            {
                "type": "client.log",
                "message": f"mic={'up' if self.audio.mic else 'DOWN'} "
                           f"frames={self.audio.frames} status={self.status.text}",
            }
        )

    def _resize(self, *_):
        self._background.pos = self.pos
        self._background.size = self.size

    def _send_audio(self, pcm: bytes) -> None:
        self.client.send_audio(pcm)

    # ---------------------------------------------------------------- display

    def refresh_frame(self, _dt) -> None:
        threading.Thread(target=self._fetch_frame, daemon=True).start()

    def _fetch_frame(self) -> None:
        try:
            with urllib.request.urlopen(SCREEN_URL, timeout=6) as response:
                data = response.read()
        except Exception:
            return  # nothing rendered yet, or the link blipped
        self._apply_frame(data)

    @mainthread
    def _apply_frame(self, data: bytes) -> None:
        try:
            self.screen_image.texture = CoreImage(io.BytesIO(data), ext="jpg").texture
        except Exception:
            return

    @mainthread
    def set_status(self, text: str) -> None:
        self.status.text = f"{HOST} - {text}"

    # ---------------------------------------------------------------- server messages

    def handle_message(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "flow.screen":
            self.show_screen(message["data"])
        elif kind == "flow.report":
            routing = message["data"].get("routing", {})
            self.set_status(f"{routing.get('queue', '?')} - {routing.get('priority', '')}")
        elif kind == "tts.audio":
            self.audio.play(base64.b64decode(message["audio"]), message.get("sample_rate", 22050))

    # ---------------------------------------------------------------- touch

    @mainthread
    def show_screen(self, screen: dict) -> None:
        self.stage = screen.get("stage")
        self.question_id = screen.get("question_id")
        options = screen.get("options") or []
        self.option_values = [option["value"] for option in options]

        # Only stream audio during the interview. Sending the language screen's ambient room noise
        # to the recognizer is how a bystander's chatter becomes a chief complaint.
        self.audio.muted = self.stage != "interview"
        if self.stage == "interview":
            # Retry here as well as at startup: the Android permission dialog is usually still on
            # screen when the app first tries, and a mic that failed then would never come back.
            self.audio.start_microphone()

        self.set_camera(self.stage in CAMERA_STAGES)
        self.buttons.clear_widgets()

        control = screen.get("control")
        self.control = control
        self.value_label = None
        if control:
            # A quantity, not a choice. The question itself is still the frame above, rendered on
            # the Jetson with raqm; only digits and +/- are laid out here, and digits need no
            # shaping. That keeps the rule this client exists for - no Indic text is composed on
            # the tablet - while giving the patient something to press instead of a voice prompt
            # they may not answer.
            self.build_control(control)
        else:
            for index in range(1, len(options) + 1):
                # Numbers only: the labels are already drawn, correctly shaped, on the frame above.
                self.add_button(str(index), lambda i=index: self.choose(i), font_size="30sp")

        if not options and self.stage == "abha":
            self.add_button("SCAN CARD", self.scan_abha)
            self.add_button("SKIP", lambda: self.client.send({"type": "flow.next"}))
        elif not options and self.stage == "documents":
            self.add_button("SCAN", self.scan_document)
            self.add_button("DONE", lambda: self.client.send({"type": "flow.next"}))

        # A stepper needs room: 48sp glyphs on the +/- keys and a 64sp value between them do not
        # fit the 96px a row of numbered option buttons uses. Taller only when there is a control,
        # so every existing screen keeps the height it was laid out against.
        if not self.buttons.children:
            self.buttons.height = 0
        elif self.control:
            self.buttons.height = 160
        else:
            self.buttons.height = 96

    @mainthread
    def build_control(self, control: dict) -> None:
        """A touch control for a quantity: a stepper, or a 0-10 scale.

        The value lives here and only the confirmed number is sent. Round-tripping every press to
        the Jetson for a re-render would put a frame poll between a finger and the digit it
        changed, which on a 1 second poll reads as a broken button and gets pressed again.
        """
        self.control = control
        kind = control.get("type")
        if kind == "scale":
            self._build_scale(control)
        else:
            self._build_stepper(control)

    def _build_scale(self, control: dict) -> None:
        low, high = int(control.get("min", 0)), int(control.get("max", 10))
        for value in range(low, high + 1):
            self.add_button(str(value), lambda v=value: self.submit_value(str(v)), font_size="26sp")

    def _build_stepper(self, control: dict) -> None:
        self.control_value = float(control.get("initial", control.get("min", 0)))
        self.value_label = Label(
            text=self._format_value(),
            font_size="64sp",
            bold=True,
            color=(0.95, 0.96, 0.98, 1),
        )
        # Minus and plus are the widest targets on screen and sit at the two edges, so a patient
        # holding the tablet with both hands reaches them with either thumb without looking.
        self.add_button("-", lambda: self.nudge(-1), font_size="48sp")
        self.buttons.add_widget(self.value_label)
        self.add_button("+", lambda: self.nudge(1), font_size="48sp")
        self.add_button("OK", lambda: self.submit_value(self._format_value()), font_size="26sp")

    def _format_value(self) -> str:
        decimals = int((self.control or {}).get("decimals", 0))
        if decimals:
            return f"{self.control_value:.{decimals}f}"
        return str(int(round(self.control_value)))

    def nudge(self, direction: int) -> None:
        """One press. Clamped, so the control can never offer an impossible answer."""
        control = self.control or {}
        step = float(control.get("step", 1))
        low = float(control.get("min", 0))
        high = float(control.get("max", 999))
        self.control_value = max(low, min(high, self.control_value + direction * step))
        if self.value_label is not None:
            self.value_label.text = self._format_value()

    def submit_value(self, value: str) -> None:
        """Send a confirmed quantity down the same path a tapped option takes."""
        self.client.send(
            {
                "type": "flow.action",
                "action": "answer",
                "value": value,
                "question_id": self.question_id,
                "method": "touch",
            }
        )

    def add_button(self, label: str, handler, font_size: str = "22sp") -> None:
        button = Button(
            text=label, font_size=font_size, background_normal="",
            background_color=ACCENT, color=(0.05, 0.07, 0.09, 1), bold=True,
        )
        button.bind(on_release=lambda _b: handler())
        self.buttons.add_widget(button)

    def choose(self, index: int) -> None:
        try:
            value = self.option_values[index - 1]
        except IndexError:
            return
        if self.stage == "language":
            self.client.send({"type": "flow.language", "value": value})
        elif self.stage == "who":
            self.client.send({"type": "flow.who", "value": value})
        elif self.stage == "ayurveda":
            self.client.send(
                {"type": "flow.ayurveda", "question_id": self.question_id, "value": value}
            )

    # ---------------------------------------------------------------- camera

    def set_camera(self, wanted: bool) -> None:
        if wanted and self.camera is None:
            try:
                from kivy.uix.camera import Camera

                self.camera = Camera(resolution=(1280, 960), play=True)
                self.camera_box.add_widget(self.camera)
                self.camera_box.height = 260
            except Exception as error:
                self.camera = None
                detail = f"camera unavailable ({type(error).__name__}: {error})"
                self.set_status(detail)
                # Kivy's Android camera provider is the least reliable part of this app, so say so
                # out loud rather than leaving a button that appears to do nothing.
                self.client.send({"type": "client.log", "message": detail})
        elif not wanted and self.camera is not None:
            self.camera.play = False
            self.camera_box.remove_widget(self.camera)
            self.camera = None
            self.camera_box.height = 0

    def grab_jpeg(self) -> bytes | None:
        if self.camera is None or self.camera.texture is None:
            reason = "no camera" if self.camera is None else "camera has no frame yet"
            self.set_status(f"scan: {reason}")
            self.client.send({"type": "client.log", "message": f"scan failed: {reason}"})
            return None
        texture = self.camera.texture
        from kivy.core.image import Image as KvImage

        image = KvImage(texture)
        buffer = io.BytesIO()
        image.save(buffer, fmt="jpg")
        return buffer.getvalue()

    def scan_abha(self) -> None:
        threading.Thread(target=self._scan_abha, daemon=True).start()

    def _scan_abha(self) -> None:
        jpeg = self.grab_jpeg()
        if jpeg is None:
            self.set_status("no camera frame")
            return
        try:
            result = post_image(ABHA_URL, jpeg)
        except Exception as error:
            self.set_status(f"scan failed ({type(error).__name__})")
            return
        if result.get("found"):
            self.client.send({"type": "flow.abha", "value": result["number"]})
        else:
            self.set_status("no ABHA code found - try again or skip")

    def scan_document(self) -> None:
        threading.Thread(target=self._scan_document, daemon=True).start()

    def _scan_document(self) -> None:
        jpeg = self.grab_jpeg()
        if jpeg is None:
            self.set_status("no camera frame")
            return
        try:
            result = post_image(OCR_URL, jpeg)
        except Exception as error:
            self.set_status(f"OCR failed ({type(error).__name__})")
            return
        self.client.send(
            {"type": "flow.document", "lines": result.get("lines", []),
             "seconds": result.get("seconds")}
        )
        self.set_status(f"read {len(result.get('lines', []))} lines")


class MediKioskApp(App):
    def build(self):
        Window.clearcolor = PAPER
        try:
            from android.permissions import Permission, request_permissions

            request_permissions([Permission.RECORD_AUDIO, Permission.CAMERA])
        except ImportError:
            pass  # running on a desktop for layout work
        return KioskRoot()

    def on_stop(self) -> None:
        self.root.client.stop()
        self.root.audio.stop()


if __name__ == "__main__":
    MediKioskApp().run()
