#!/usr/bin/env python3
"""Post one intake to a running API, the way a kiosk or the app would.

**This is a stand-in for a device, not a shortcut past one.** It posts the same
`POST /api/v1/intakes/ingest` body the Jetson and the Flutter app post, with the
same bearer token and the same idempotency key, so what the dashboard receives
is indistinguishable from a real submission. It exists because a demo needs a
third patient to walk in on cue, and a camera cannot wait for one.

The token is read from the environment or from `.env` and is never printed,
never defaulted, and never written into this file. A kiosk token with a value
in a public repository is a kiosk token everybody has.

    # local stack
    API=http://localhost:8010 python3 infra/demo/submit_intake.py routine

    # the deployed API
    API=https://... KIOSK_TOKEN=... python3 infra/demo/submit_intake.py critical

`routine`, `high` and `critical` differ only in the criterion the device reports
firing. That is the point of the demo: the queue reorders on severity, and only
`critical` overtakes anybody — see decision 79.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "app" / "test" / "golden" / "app_record_0.1.json"

#: What the device says fired. The backend re-derives nothing from this — it is
#: the device's own judgement, which is why `severity` travels on the wire.
FLAGS: dict[str, list[dict[str, object]]] = {
    "routine": [],
    "high": [
        {
            "rule_id": "high_fever_prolonged",
            "fired_at_turn": 3,
            "criteria_met": ["fever.severity>=8"],
            "severity": "high",
            "label": "Urgent clinical review criterion triggered",
        }
    ],
    "critical": [
        {
            "rule_id": "breathing_difficulty_at_rest",
            "fired_at_turn": 4,
            "criteria_met": ["respiratory.breathlessness=at_rest"],
            "severity": "critical",
            "label": "Urgent clinical review criterion triggered",
        }
    ],
}


def kiosk_token() -> str:
    """The bearer token, from the environment or `.env`. Never printed."""
    token = os.environ.get("KIOSK_TOKEN")
    if token:
        return token

    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("KIOSK_TOKENS="):
                tokens = json.loads(line.split("=", 1)[1].strip())
                if tokens:
                    return next(iter(tokens))

    sys.exit(
        "No kiosk token. Set KIOSK_TOKEN, or run this from a checkout whose\n"
        ".env has KIOSK_TOKENS. There is no default: a token with a default\n"
        "value is a token everybody has."
    )


def build(kind: str, department: str) -> dict[str, object]:
    record = json.loads(GOLDEN.read_text())
    now = dt.datetime.now(dt.timezone.utc)

    # A fresh id and fresh timestamps, so the queue sorts it as an arrival
    # rather than as a replay of the fixture.
    record["intake_id"] = str(uuid.uuid4())
    record["started_at"] = (now - dt.timedelta(minutes=6)).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )
    record["completed_at"] = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    record["department_code"] = department

    flags = FLAGS[kind]
    if flags:
        record["red_flags"] = flags
        # A device that fires a critical criterion stops asking. That is what
        # `aborted_red_flag` means, and it is the device's decision, not ours.
        if kind == "critical":
            record["status"] = "aborted_red_flag"

    # Each run is a different patient, so each needs its own phone reference —
    # the same digest twice is the same person arriving twice.
    record["patient_ref"] = {"type": "phone", "value": uuid.uuid4().hex[:16]}
    return record


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else "routine"
    if kind not in FLAGS:
        sys.exit(f"Unknown kind {kind!r}. One of: {', '.join(FLAGS)}")

    department = os.environ.get("DEPARTMENT", "general_medicine")
    api = os.environ.get("API", "http://localhost:8000").rstrip("/")
    record = build(kind, department)

    request = urllib.request.Request(
        f"{api}/api/v1/intakes/ingest",
        data=json.dumps(record).encode(),
        headers={
            "Authorization": f"Bearer {kiosk_token()}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(uuid.uuid4()),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        print(f"{error.code} {error.read().decode()[:400]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(f"Could not reach {api}: {error.reason}", file=sys.stderr)
        return 1

    print(f"  kind        {kind}")
    print(f"  department  {department}")
    print(f"  intake      {body.get('intake_id')}")
    print(f"  status      {body.get('status')}")
    print(f"  red flags   {len(body.get('red_flags') or [])}")
    print(f"  unresolved  {', '.join(body.get('unresolved_fields') or []) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
