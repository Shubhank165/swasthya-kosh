"""Identifier redaction over OCR output.

Runs before anything is persisted, and before anything is logged.

This is not a precaution. The OCR benchmark corpus contained a legible Aadhaar
number on a prescription header, and a model transcribed it straight into its
result JSON. Assume that happens again on the next document. The image itself
still holds the original — that is what the signed URL is for — but no digit run
that looks like a national identifier or a phone number reaches a database row,
a log line or an event payload.

Deliberately over-broad. A masked pharmacy phone number costs a physician
nothing; a leaked Aadhaar number is a reportable breach under the DPDP Act.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Aadhaar: twelve digits, conventionally printed in three groups of four,
#: sometimes run together, sometimes hyphenated. Also matched in Devanagari
#: digits, which is how the benchmark corpus printed them.
_AADHAAR = re.compile(
    r"(?<![\d०-९])"
    r"(?:[\d०-९][ \-]?){11}[\d०-९]"
    r"(?![\d०-९])"
)

#: Indian mobile with its country code. Matched before the Aadhaar rule,
#: because `+91 98765 43210` carries twelve digits and would otherwise be masked
#: as an Aadhaar number — correctly hidden, but wrongly counted, and the counts
#: are what tells an operator which documents to look at.
_PHONE_INTL = re.compile(
    r"(?<![\d०-९])"
    r"\+?91[\s\-]?[6-9][\d०-९]{4}[\s\-]?[\d०-९]{5}"
    r"(?![\d०-९])"
)

#: Indian mobile: ten digits starting 6-9, optionally 0-prefixed.
_PHONE = re.compile(
    r"(?<![\d०-९])"
    r"0?[6-9][\d०-९]{9}"
    r"(?![\d०-९])"
)

#: ABHA number: fourteen digits. ABHA *addresses* (`name@sbx`) are handles, not
#: secrets, and are left alone.
_ABHA = re.compile(
    r"(?<![\d०-९])"
    r"(?:[\d०-९][ \-]?){13}[\d०-९]"
    r"(?![\d०-९])"
)

#: PAN: five letters, four digits, one letter.
_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

AADHAAR_MASK = "[aadhaar-redacted]"
ABHA_MASK = "[abha-redacted]"
PHONE_MASK = "[phone-redacted]"
PAN_MASK = "[pan-redacted]"
EMAIL_MASK = "[email-redacted]"

#: Order matters. ABHA (14) and Aadhaar (12) are matched before the phone
#: pattern, or a phone-shaped substring of a longer identifier would be masked
#: first and leave the remaining digits exposed.
_RULES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (_PHONE_INTL, PHONE_MASK, "phone"),
    (_ABHA, ABHA_MASK, "abha"),
    (_AADHAAR, AADHAAR_MASK, "aadhaar"),
    (_PAN, PAN_MASK, "pan"),
    (_EMAIL, EMAIL_MASK, "email"),
    (_PHONE, PHONE_MASK, "phone"),
)


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Redacted text plus what was found, by kind.

    The counts are safe to log and worth logging: a document that produced four
    Aadhaar hits is a document worth looking at, and the count says so without
    saying what the number was.
    """

    text: str
    counts: tuple[tuple[str, int], ...] = ()

    @property
    def redacted_anything(self) -> bool:
        return bool(self.counts)

    @property
    def total(self) -> int:
        return sum(count for _, count in self.counts)


def redact(text: str) -> RedactionResult:
    """Mask every identifier-shaped run in `text`."""
    if not text:
        return RedactionResult(text=text)
    counts: list[tuple[str, int]] = []
    out = text
    for pattern, mask, label in _RULES:
        out, hits = pattern.subn(mask, out)
        if hits:
            counts.append((label, hits))
    return RedactionResult(text=out, counts=tuple(counts))


def redact_text(text: str) -> str:
    """`redact`, when only the text is wanted."""
    return redact(text).text


def contains_identifier(text: str) -> bool:
    """True when `text` still holds something identifier-shaped.

    Used as an assertion at the persistence boundary and by the redaction test:
    a value that answers True here must never reach a database row.
    """
    return any(pattern.search(text) for pattern, _, _ in _RULES)
