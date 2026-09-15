"""What the kiosk reads back from the hospital's cloud, and how it survives without it.

Three documents, all of them configuration rather than patient data, and all three readable by
the kiosk token (everything else on that API answers 403 for role `kiosk` - the worklist, the
terminology service and the intakes themselves belong to staff):

    /api/v1/content/consent          the purposes the hospital asks permission for, with the
                                     patient-facing label in all nine languages and a version
    /api/v1/hospitals                departments, default language, timezone
    /api/v1/content/bundle/version   which question content the hospital is on

Why a cache rather than a live call
-----------------------------------
The kiosk is offline-first and has to run through a whole intake with no internet at all, so
nothing here may be on the path of a patient's turn. Refresh is a startup attempt that is allowed
to fail; every read afterwards comes off the disk. A kiosk that has never reached the cloud has no
cache, and the callers treat that the same way they treat a locked door: the local flow runs
unchanged and nothing is sent.

The consent mapping is the point
--------------------------------
Our notices name local purposes (`local_intake`, `cloud_intake`); the hospital names its own
(`history_intake`, `hospital_record_linkage`). Exporting a record because the patient agreed to a
*local* intake would be consent laundering, so the export asks for `cloud_intake` explicitly and
this module is what says which hospital purposes that maps onto - which is the mapping the
cloud path was blocked on.

`raw_audio_retention` is deliberately absent from the map. The kiosk never retains audio, so
there is nothing that permission could authorize; a mapping entry would imply otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Our purpose -> the hospital purposes that must all be granted for it to mean anything there.
PURPOSE_MAP: dict[str, tuple[str, ...]] = {
    "cloud_intake": ("history_intake", "hospital_record_linkage"),
    "cloud_documents": ("document_processing",),
}

DOCUMENTS = ("consent", "hospitals", "content_version")


def refresh(api: Any, cache_dir: Path) -> dict[str, Any]:
    """Pull the three documents and cache them. Returns what is cached afterwards.

    Never raises on a network failure: a kiosk with no internet is the normal case, and the
    previous cache (or none at all) is the answer then.
    """

    cache_dir.mkdir(parents=True, exist_ok=True)
    for name, call in (
        ("consent", api.consent_notice),
        ("hospitals", api.hospitals),
        ("content_version", api.content_version),
    ):
        response = call()
        if response.ok and response.body:
            path = cache_dir / f"{name}.json"
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(response.body, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)  # atomic on POSIX: a crash never leaves half a document
    return load(cache_dir)


def load(cache_dir: Path) -> dict[str, Any]:
    """Whatever was last cached. Missing or torn documents are simply absent."""

    cached: dict[str, Any] = {}
    for name in DOCUMENTS:
        path = Path(cache_dir) / f"{name}.json"
        try:
            cached[name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return cached


def consent_version(cached: dict[str, Any]) -> str | None:
    """The hospital's consent version, recorded alongside an exported record."""

    return (cached.get("consent") or {}).get("consent_version")


def content_version(cached: dict[str, Any]) -> str | None:
    return (cached.get("content_version") or {}).get("content_version")


def hospital_purposes(cached: dict[str, Any], purpose: str) -> list[dict[str, Any]]:
    """The hospital's own purpose entries behind one of ours, for showing in its own words."""

    by_code = {p.get("code"): p for p in (cached.get("consent") or {}).get("purposes") or []}
    return [by_code[code] for code in PURPOSE_MAP.get(purpose, ()) if code in by_code]


def departments(cached: dict[str, Any], hospital_id: str) -> list[dict[str, Any]]:
    for hospital in (cached.get("hospitals") or {}).get("hospitals") or []:
        if hospital.get("hospital_id") == hospital_id:
            return hospital.get("departments") or []
    return []


def department_code(cached: dict[str, Any], hospital_id: str, queue: str | None) -> str | None:
    """Map our queue name onto a department the hospital actually runs.

    Ours are English specialty names ("Cardiology"); theirs are codes with display names, some
    of them Ayurvedic departments with no specialty equivalent. A name we cannot match returns
    None rather than a guess - the backend files an intake with no department perfectly well,
    and inventing `kayachikitsa` for an orthopaedic complaint would be worse than silence.
    """

    if not queue:
        return None
    wanted = queue.strip().casefold()
    for department in departments(cached, hospital_id):
        names = {
            str(department.get("code", "")).casefold(),
            str(department.get("display_name", "")).casefold(),
        }
        if wanted in names:
            return department.get("code")
    return None
