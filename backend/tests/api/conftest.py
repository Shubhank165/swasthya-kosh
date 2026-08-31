"""Role headers for the API tests.

Real authentication is the hospital's identity provider; these exercise the same
role checks the endpoints enforce. The `api` fixture itself lives in the shared
conftest, because the integration suite drives the same app.
"""

from __future__ import annotations

STAFF = {"X-User-Id": "staff-1", "X-User-Role": "staff"}
TRIAGE = {"X-User-Id": "triage-1", "X-User-Role": "triage"}
PHYSICIAN = {"X-User-Id": "dr-1", "X-User-Role": "physician"}
KIOSK = {"X-User-Id": "kiosk-1", "X-User-Role": "patient_session"}
