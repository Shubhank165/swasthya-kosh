"""The outbox, and the one rule it exists to enforce: an ambiguous upload is never sent twice."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

from medikiosk.kiosk.document_outbox import (
    AMBIGUOUS,
    PENDING,
    REJECTED,
    UPLOADED,
    DocumentOutbox,
    infer_kind,
)
from medikiosk.providers.intake_api import IntakeApi

JPEG = b"\xff\xd8\xff fake jpeg"


class Transport:
    """A scripted transport: each call consumes the next scripted outcome, and every call is
    counted, because "how many times was this document sent" is the whole question."""

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        body, status = step
        resp = io.BytesIO(json.dumps(body).encode())
        resp.status = status
        resp.__enter__ = lambda s=resp: s
        resp.__exit__ = lambda s, *a: False
        return resp


def api(*script) -> tuple[IntakeApi, Transport]:
    t = Transport(*script)
    return IntakeApi("tok", opener=t), t


def accepted(document_id="doc-1"):
    return ({"document_id": document_id, "status": "queued"}, 202)


def timed_out():
    return urllib.error.URLError(TimeoutError("read timed out"))


def unreachable():
    return urllib.error.URLError(ConnectionRefusedError("refused"))


def refused(status=422):
    return urllib.error.HTTPError("u", status, "unprocessable", {}, io.BytesIO(b'{"detail":"bad"}'))


# ------------------------------------------------------------------ holding


def test_a_held_document_survives_on_disk_with_its_reason(tmp_path) -> None:
    """A restart between scan and finish must not lose a patient's prescription."""

    box = DocumentOutbox(tmp_path)
    handle = box.hold(JPEG, "prescription", "33% of 39 lines scored below 0.7")

    reopened = DocumentOutbox(tmp_path)  # a fresh process
    doc = reopened.get(handle)
    assert doc is not None
    assert doc.state == PENDING
    assert doc.kind == "prescription"
    assert "33%" in doc.reason
    assert (tmp_path / f"{handle}.jpg").read_bytes() == JPEG


def test_an_unknown_kind_is_held_as_other(tmp_path) -> None:
    box = DocumentOutbox(tmp_path)
    assert box.get(box.hold(JPEG, "scrawl", "r")).kind == "other"


def test_kind_is_inferred_from_what_the_local_parse_found() -> None:
    assert infer_kind({"medications": [1], "labs": []}) == "prescription"
    assert infer_kind({"medications": [], "labs": [1]}) == "lab_report"
    assert infer_kind({"medications": [], "labs": []}) == "other"
    assert infer_kind({}) == "other"


# ------------------------------------------------------------------ the rule


def test_an_accepted_upload_records_the_id_and_deletes_the_image(tmp_path) -> None:
    box = DocumentOutbox(tmp_path)
    handle = box.hold(JPEG, "prescription", "r")
    client, transport = api(accepted("doc-42"))

    [doc] = box.submit(client, "intake-1", [handle])
    assert doc.state == UPLOADED
    assert doc.document_id == "doc-42"
    assert transport.calls == 1
    # The record has it; the kiosk must not keep a patient's document lying around.
    assert not (tmp_path / f"{handle}.jpg").exists()
    # But the sidecar stays, so the outcome is still auditable.
    assert box.get(handle).state == UPLOADED


def test_an_ambiguous_upload_is_parked_and_never_sent_again(tmp_path) -> None:
    """The failure this whole module exists to prevent.

    The first send connected and timed out - the server may already have the document. A second
    send would put a second copy on the patient's record, and nothing upstream merges them. So
    however many times submit() is called afterwards, the transport is used exactly once.
    """

    box = DocumentOutbox(tmp_path)
    handle = box.hold(JPEG, "prescription", "r")
    client, transport = api(timed_out(), accepted(), accepted(), accepted())

    [doc] = box.submit(client, "intake-1", [handle])
    assert doc.state == AMBIGUOUS
    assert transport.calls == 1

    for _ in range(3):
        [again] = box.submit(client, "intake-1", [handle])
        assert again.state == AMBIGUOUS
    assert transport.calls == 1, "an ambiguous document was resent"

    # And it is still here for a person to look at, image included.
    assert (tmp_path / f"{handle}.jpg").exists()
    assert [d.handle for d in box.needing_attention()] == [handle]


def test_an_ambiguous_verdict_survives_a_restart(tmp_path) -> None:
    """Parking it in memory only would let the next process resend it."""

    box = DocumentOutbox(tmp_path)
    handle = box.hold(JPEG, "prescription", "r")
    client, transport = api(timed_out(), accepted())
    box.submit(client, "intake-1", [handle])

    fresh = DocumentOutbox(tmp_path)
    fresh.submit(client, "intake-1", [handle])
    assert transport.calls == 1


def test_an_unreachable_upload_stays_pending_and_can_be_retried(tmp_path) -> None:
    """Connection refused means the bytes never left, so a later attempt is safe."""

    box = DocumentOutbox(tmp_path)
    handle = box.hold(JPEG, "prescription", "r")
    client, transport = api(unreachable(), accepted("doc-7"))

    [first] = box.submit(client, "intake-1", [handle])
    assert first.state == PENDING
    assert first.attempts == 1

    [second] = box.submit(client, "intake-1", [handle])
    assert second.state == UPLOADED
    assert second.document_id == "doc-7"
    assert transport.calls == 2


def test_a_rejected_upload_is_kept_with_the_servers_reason_and_not_resent(tmp_path) -> None:
    box = DocumentOutbox(tmp_path)
    handle = box.hold(JPEG, "prescription", "r")
    client, transport = api(refused(422), accepted())

    [doc] = box.submit(client, "intake-1", [handle])
    assert doc.state == REJECTED
    assert "422" in doc.detail

    box.submit(client, "intake-1", [handle])
    assert transport.calls == 1


def test_only_the_named_handles_are_sent(tmp_path) -> None:
    """One session's finish() must not sweep up another session's documents."""

    box = DocumentOutbox(tmp_path)
    mine = box.hold(JPEG, "prescription", "r")
    theirs = box.hold(JPEG, "lab_report", "r")
    client, transport = api(accepted("doc-mine"))

    box.submit(client, "intake-1", [mine])
    assert transport.calls == 1
    assert box.get(mine).state == UPLOADED
    assert box.get(theirs).state == PENDING


def test_unknown_handles_are_skipped_not_fatal(tmp_path) -> None:
    box = DocumentOutbox(tmp_path)
    client, transport = api()
    assert box.submit(client, "intake-1", ["never-existed"]) == []
    assert transport.calls == 0


def test_a_torn_sidecar_does_not_take_the_outbox_down(tmp_path) -> None:
    """A crash mid-write leaves half a JSON file. Listing must skip it, not raise."""

    box = DocumentOutbox(tmp_path)
    good = box.hold(JPEG, "prescription", "r")
    (tmp_path / "deadbeef.json").write_text('{"handle": "dead', encoding="utf-8")
    assert [d.handle for d in box.pending()] == [good]


def test_the_sidecar_is_written_atomically(tmp_path) -> None:
    """No `.tmp` left behind, and the final file is complete JSON."""

    box = DocumentOutbox(tmp_path)
    handle = box.hold(JPEG, "prescription", "r")
    assert not list(tmp_path.glob("*.tmp"))
    json.loads(Path(tmp_path / f"{handle}.json").read_text(encoding="utf-8"))
