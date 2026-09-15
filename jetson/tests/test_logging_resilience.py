"""Logging must never be able to kill a clinical turn.

The kiosk is Hindi-first. When stdout could not encode Devanagari - a service started with
LANG=C, or a Windows console on cp1252 - printing the transcript raised UnicodeEncodeError out
of the logger. That killed the turn task, so the patient's answer was dropped: no next question,
and no red flag evaluation of what they had just said. Observed live: every Hindi answer in a
full intake vanished, and the session ended with a completely empty clinical state.
"""

import io
import sys

from medikiosk.app import emit_log_line

PAYLOAD = {"session": "abcd1234", "event": "transcript", "text": "मुझे दो दिन से तेज़ बुखार है"}


class AsciiOnlyStream(io.StringIO):
    """A cp1252 console or LANG=C service log: refuses non-ASCII outright."""

    def write(self, text: str) -> int:
        text.encode("ascii")  # raises UnicodeEncodeError, as the real console does
        return super().write(text)


class BrokenStream(io.StringIO):
    def write(self, text: str) -> int:
        raise OSError("log pipe closed")


def test_non_ascii_payload_is_written_as_escaped_ascii(monkeypatch):
    stream = AsciiOnlyStream()
    monkeypatch.setattr(sys, "stdout", stream)

    emit_log_line(PAYLOAD)

    written = stream.getvalue()
    assert "transcript" in written
    assert r"\u092e" in written  # Hindi survived, escaped


def test_a_broken_log_stream_is_swallowed(monkeypatch):
    monkeypatch.setattr(sys, "stdout", BrokenStream())
    emit_log_line(PAYLOAD)  # must not raise


def test_normal_stream_keeps_readable_unicode(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)

    emit_log_line(PAYLOAD)

    assert "मुझे दो दिन से तेज़ बुखार है" in stream.getvalue()
