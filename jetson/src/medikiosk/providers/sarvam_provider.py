import asyncio
import base64
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


def _message_dict(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        return message.model_dump(mode="json")
    if isinstance(message, dict):
        return message
    data = getattr(message, "__dict__", {})
    return {key: value for key, value in data.items() if not key.startswith("_")}


class SarvamRealtimeSTT:
    """Streams 16 kHz mono PCM to Saaras v3 Realtime."""

    def __init__(
        self,
        api_key: str,
        language_code: str = "auto",
        stream_type: str = "fast",
    ) -> None:
        self.api_key = api_key
        self.language_code = language_code
        self.stream_type = stream_type

    async def run(
        self,
        audio_queue: "asyncio.Queue[bytes | None]",
        on_event: EventHandler,
    ) -> None:
        from sarvamai import AsyncSarvamAI, RealtimeAudioInput, RealtimeEnd

        client = AsyncSarvamAI(api_subscription_key=self.api_key)
        async with client.speech_to_text_realtime_streaming.connect(
            language_code=self.language_code,
            stream_type=self.stream_type,
            mode="transcribe",
            endpointing="vad",
            encoding="linear16",
            sample_rate=16000,
            threshold=0.3,
            silence_duration_ms=500,
            min_speech_duration_ms=250,
            return_timestamps=True,
            prompt="clinical symptoms, medicines, duration, severity, Hindi and Hinglish",
        ) as socket:

            async def send_audio() -> None:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        await socket.send_realtime_end(RealtimeEnd())
                        return
                    encoded = base64.b64encode(chunk).decode("ascii")
                    await socket.send_realtime_audio_input(RealtimeAudioInput(audio=encoded))

            async def receive_events() -> None:
                async for message in socket:
                    await on_event(_message_dict(message))
                    if getattr(message, "event", None) == "session.end":
                        return

            await asyncio.gather(send_audio(), receive_events())


class SarvamStreamingTTS:
    """Produces raw 24 kHz LINEAR16 chunks for browser Web Audio playback."""

    def __init__(self, api_key: str, speaker: str = "shubh") -> None:
        self.api_key = api_key
        self.speaker = speaker

    async def stream(self, text: str, language_code: str) -> AsyncIterator[bytes]:
        from sarvamai import AsyncSarvamAI, AudioOutput, EventResponse

        client = AsyncSarvamAI(api_subscription_key=self.api_key)
        async with client.text_to_speech_streaming.connect(
            model="bulbul:v3",
            send_completion_event=True,
        ) as socket:
            await socket.configure(
                language_code=_tts_language(language_code),
                speaker=self.speaker,
                pace=1.0,
                output_audio_codec="linear16",
                min_buffer_size=30,
                max_chunk_length=180,
            )
            await socket.convert(text)
            await socket.flush()
            async for message in socket:
                if isinstance(message, AudioOutput):
                    yield base64.b64decode(message.data.audio)
                elif isinstance(message, EventResponse) and message.data.event_type == "final":
                    return


def _tts_language(language_code: str | None) -> str:
    value = (language_code or "hi-IN").lower()
    supported = {
        "hi-in": "hi-IN",
        "en-in": "en-IN",
        "bn-in": "bn-IN",
        "ta-in": "ta-IN",
        "te-in": "te-IN",
        "kn-in": "kn-IN",
        "ml-in": "ml-IN",
        "mr-in": "mr-IN",
        "gu-in": "gu-IN",
        "pa-in": "pa-IN",
        "or-in": "or-IN",
    }
    if value in {"hinglish", "hi-latn", "auto"}:
        return "hi-IN"
    return supported.get(value, "en-IN")
