"""Holds handwritten document images until there is an intake to attach them to, then sends them.

Why an outbox exists at all
---------------------------
The intake API attaches documents to an intake, and an intake only exists once the completed
record has been ingested - which happens at the end of the session, at `finish()`. But the kiosk
scans documents two stages earlier, through a stateless HTTP call that deletes the photo as soon
as the local OCR has read it. So a handwritten page has to be kept somewhere between "scanned" and
"the record exists", and that somewhere has to survive a process restart, because the alternative
is a patient's prescription silently vanishing between two stages of one visit.

Each held document is a JPEG plus a small JSON sidecar on disk, keyed by a random handle. The
handle is what travels: back to the tablet in the OCR response, forward again in the
`flow.document` message, and into the session's document list, so that when the record is
finally ingested the session knows exactly which files are its own.

The one rule that matters
-------------------------
The upload endpoint is not idempotent. A document whose upload ended AMBIGUOUS - connected, then
timed out - may already be on the patient's record, and sending it again puts a second copy there
which nothing upstream will merge. So:

    pending    -> may be sent
    uploaded   -> done, document_id recorded
    ambiguous  -> NEVER sent again by this code. Left on disk with the reason, for a person.
    rejected   -> the server said no; kept on disk with the reason, not resent

`submit()` enforces that: it only ever sends `pending` documents, and a document that comes back
AMBIGUOUS is moved out of `pending` before anything else can happen. An UNREACHABLE result - the
bytes never left - keeps the document `pending` so a later attempt can try again.

What is kept on disk is the patient's document. The directory is inside the encrypted-store's
parent, it is not the kiosk source tree, and uploaded documents are deleted the moment their
document_id is recorded. Ambiguous and rejected ones are deliberately kept: they are the evidence
a person needs to decide whether the record is complete.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from medikiosk.providers.intake_api import KINDS, IntakeApi, Outcome

PENDING, UPLOADED, AMBIGUOUS, REJECTED = "pending", "uploaded", "ambiguous", "rejected"


@dataclass
class HeldDocument:
    handle: str
    kind: str
    state: str = PENDING
    reason: str = ""  # why it was routed here: the classifier's verdict
    held_at: float = field(default_factory=time.time)
    document_id: str | None = None
    detail: str = ""  # what the API said, for the states where that matters
    attempts: int = 0

    @property
    def sendable(self) -> bool:
        return self.state == PENDING


def infer_kind(structured: dict) -> str:
    """Best guess at the API's document kind from what the local parse found.

    Cheap and honest: a page with parsed medications is a prescription, one with lab values is a
    lab report, anything else is "other". The cloud reader sees the image anyway; this only tells
    it what to expect.
    """

    if structured.get("medications"):
        return "prescription"
    if structured.get("labs"):
        return "lab_report"
    return "other"


class DocumentOutbox:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ holding

    def hold(self, image: bytes, kind: str, reason: str) -> str:
        """Keep one image until an intake exists for it. Returns the handle that names it."""

        handle = uuid.uuid4().hex
        if kind not in KINDS:
            kind = "other"
        self._image_path(handle).write_bytes(image)
        self._save(HeldDocument(handle=handle, kind=kind, reason=reason))
        return handle

    def get(self, handle: str) -> HeldDocument | None:
        path = self._meta_path(handle)
        if not path.exists():
            return None
        return HeldDocument(**json.loads(path.read_text(encoding="utf-8")))

    def pending(self) -> list[HeldDocument]:
        return [d for d in self._all() if d.state == PENDING]

    def needing_attention(self) -> list[HeldDocument]:
        """Documents a person has to look at: sent but unconfirmed, or refused by the server."""

        return [d for d in self._all() if d.state in (AMBIGUOUS, REJECTED)]

    # ------------------------------------------------------------------ sending

    def submit(self, api: IntakeApi, intake_id: str, handles: list[str]) -> list[HeldDocument]:
        """Upload the named documents against an intake. Returns each one's resulting state.

        Only `pending` documents are ever sent. A handle that is unknown, already uploaded, or
        parked as ambiguous/rejected is returned as-is and not touched - which is what makes it
        safe to call this again after a crash, a restart, or a retried session.
        """

        results: list[HeldDocument] = []
        for handle in handles:
            doc = self.get(handle)
            if doc is None:
                continue
            if not doc.sendable:
                results.append(doc)
                continue

            doc.attempts += 1
            response = api.upload_document(intake_id, self._image_path(handle), doc.kind)

            if response.ok:
                doc.state = UPLOADED
                doc.document_id = (response.body or {}).get("document_id")
                doc.detail = f"HTTP {response.status}"
                self._save(doc)
                # The record has it now; the kiosk must not keep a patient's document around.
                self._image_path(handle).unlink(missing_ok=True)
            elif response.outcome is Outcome.AMBIGUOUS:
                # May have landed. Park it before anything else can retry it.
                doc.state = AMBIGUOUS
                doc.detail = response.detail
                self._save(doc)
            elif response.outcome is Outcome.REJECTED:
                doc.state = REJECTED
                doc.detail = f"HTTP {response.status}: {response.detail}"[:300]
                self._save(doc)
            else:
                # UNREACHABLE: never left. Stays pending; the attempt count records that we tried.
                doc.detail = response.detail
                self._save(doc)
            results.append(doc)
        return results

    # ------------------------------------------------------------------ files

    def _all(self) -> list[HeldDocument]:
        docs = []
        for meta in sorted(self.directory.glob("*.json")):
            try:
                docs.append(HeldDocument(**json.loads(meta.read_text(encoding="utf-8"))))
            except (ValueError, TypeError):
                continue  # a torn write from a crash; not this call's problem to repair
        return docs

    def _save(self, doc: HeldDocument) -> None:
        path = self._meta_path(doc.handle)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(doc), ensure_ascii=False), encoding="utf-8")
        # Atomic on POSIX: a crash leaves the old sidecar intact, never half of a new one.
        tmp.replace(path)

    def _image_path(self, handle: str) -> Path:
        return self.directory / f"{handle}.jpg"

    def _meta_path(self, handle: str) -> Path:
        return self.directory / f"{handle}.json"
