"""Role enforcement — §13.9.

**Every route enumerated from the OpenAPI schema, each asserted against its
required role.**

A previous build annotated the physician-only routes and never wired the guards.
The routes were documented as protected and were open. Documentation is not
enforcement, and a review that reads the decorator is reading the documentation.

So this test does not read decorators. It walks the live dependency tree of every
registered route, finds the `require_roles` guard, and compares it against the
expectations table below. A route with no guard fails. A route missing from the
table fails. A route whose guard changed fails.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.auth import Role, require_roles
from tests.conftest import (
    KIOSK_HEADERS,
    OTHER_STAFF_HEADERS,
    PHYSICIAN_HEADERS,
    STAFF_HEADERS,
)

#: `(method, path) -> the minimum role that may call it`.
#:
#: Kept as data rather than derived, so changing a route's access is a visible
#: edit in a file called `test_roles.py` rather than a one-word change in a
#: router nobody diffs closely.
EXPECTED: dict[tuple[str, str], set[Role]] = {
    # The kiosk. Narrow on purpose: a device in a waiting room is physically
    # accessible to anyone standing next to it, so it may submit and upload and
    # nothing else.
    # Submitting an intake: a kiosk in the corridor, a staff member at a
    # counter, or a patient on their own phone before they travel (2/3 §9).
    # A provisioning check: confirm the bearer token is a real kiosk token and
    # see which hospital it is bound to. Kiosk only — a patient session has no
    # reason to call it.
    ("GET", "/api/v1/kiosk/whoami"): {Role.KIOSK},
    ("POST", "/api/v1/intakes/ingest"): {Role.KIOSK, Role.STAFF, Role.PATIENT},
    ("POST", "/api/v1/intakes/{intake_id}/documents"): {
        Role.KIOSK, Role.STAFF, Role.PATIENT
    },
    ("POST", "/api/v1/intakes/{intake_id}/documents/results"): {
        Role.KIOSK, Role.STAFF, Role.PATIENT
    },
    ("POST", "/api/v1/consent"): {Role.KIOSK, Role.STAFF, Role.PATIENT},
    ("POST", "/api/v1/patients/resolve"): {Role.KIOSK, Role.STAFF},
    # The patient app, reading its own records and nothing else. Note there is
    # no path parameter: the patient comes from the session token.
    ("POST", "/api/v1/patients/me/abha"): {Role.PATIENT},
    # The AYUSH/Prakriti self-report is filed against the patient who answered
    # it, so only a patient session may write one — a kiosk has no patient to
    # attribute it to, and staff entering it would be recording someone else's
    # self-report as their own.
    ("POST", "/api/v1/patients/me/ayush-profile"): {Role.PATIENT},
    # Erasing your own record. Patient only, and the strongest case for it in
    # the table: the route takes no path parameter and no body, so the only
    # record it can destroy is the one belonging to the token's holder. Staff
    # deleting a patient's history on their behalf is a different action with a
    # different audit story, and would need a different route.
    ("DELETE", "/api/v1/patients/me/history"): {Role.PATIENT},
    # Prefill suggests answers to questions not yet asked. Same three callers as
    # ingest, because it is the same interview: nothing is written to the record
    # here, and a suggestion becomes a fact only when the patient accepts it.
    ("POST", "/api/v1/intakes/{intake_id}/prefill"): {
        Role.KIOSK, Role.STAFF, Role.PATIENT
    },
    ("GET", "/api/v1/patients/me/history"): {Role.PATIENT},
    # The Documents tab. Same guard and strictly less content than the staff
    # route on the intake — no confidence figures and nothing read off the page.
    ("GET", "/api/v1/patients/me/documents"): {Role.PATIENT},
    # Clinical reads. Staff and above.
    ("GET", "/api/v1/intakes/{intake_id}"): {Role.STAFF},
    ("GET", "/api/v1/intakes/{intake_id}/report"): {Role.STAFF},
    ("GET", "/api/v1/intakes/{intake_id}/facts/{fact_id}/evidence"): {Role.STAFF},
    ("GET", "/api/v1/intakes/{intake_id}/documents"): {Role.STAFF},
    ("GET", "/api/v1/documents/content/{key:path}"): {Role.STAFF},
    ("GET", "/api/v1/patients/{ref}/history"): {Role.STAFF},
    ("GET", "/api/v1/worklist"): {Role.STAFF},
    ("GET", "/api/v1/alerts"): {Role.STAFF},
    ("POST", "/api/v1/alerts/{intake_id}/acknowledge"): {Role.STAFF},
    ("GET", "/api/v1/metrics/ingest"): {Role.STAFF},
    # A claim about the system rather than about a patient. Admin-scoped so the
    # person quoting the correction rate on a slide is the person who can see
    # how it was computed — 3/3 §6, §10.
    ("GET", "/api/v1/metrics/correction-rate"): {Role.ADMIN},
    ("GET", "/api/v1/consent/{consent_id}"): {Role.STAFF},
    ("GET", "/api/v1/fhir/intakes/{intake_id}"): {Role.STAFF},
    ("GET", "/api/v1/terminology/search"): {Role.STAFF},
    ("GET", "/api/v1/terminology/CodeSystem/{system}"): {Role.STAFF},
    ("GET", "/api/v1/terminology/ConceptMap"): {Role.STAFF},
    ("GET", "/api/v1/terminology/ValueSet/{system}"): {Role.STAFF},
    ("GET", "/api/v1/terminology/dual-codes"): {Role.STAFF},
    # The two routes where the answer changes the clinical weight of the record.
    ("POST", "/api/v1/intakes/{intake_id}/verify"): {Role.PHYSICIAN},
    ("POST", "/api/v1/intakes/{intake_id}/facts/{fact_id}/verify"): {Role.PHYSICIAN},
}

#: Routes that are deliberately open. Each one is here because it must answer
#: before a caller has credentials, and none of them touches patient data.
UNGUARDED: set[tuple[str, str]] = {
    # The question bundle. It holds no patient data — it is the questions an OPD
    # asks — and the app must render a sign-in screen in the patient's own
    # language before the patient has signed in (2/3 §4).
    ("GET", "/api/v1/content/bundle"),
    ("GET", "/api/v1/content/bundle/version"),
    # The consent notice, for the same reason and more sharply: a patient must
    # be able to read what they are agreeing to before they agree to anything,
    # and requiring a credential to fetch it would mean consent is asked for
    # after the app already holds an identifier (2/3 §11).
    ("GET", "/api/v1/content/consent"),
    # The hospital picker, which is screen 2 and precedes any credential. A
    # hospital's name, location and department list is what the signboard says.
    ("GET", "/api/v1/hospitals"),
    # Sign-in itself. These are how a caller acquires a credential, so they
    # cannot require one — which makes them the only writable surface reachable
    # with no token at all. The service rate-limits per number and returns a
    # uniform failure so they cannot be used to enumerate patients (2/3 §7.1).
    ("POST", "/api/v1/auth/otp/request"),
    ("POST", "/api/v1/auth/otp/verify"),
    # Always 204, guarded or not: refusing an invalid token would report whether
    # it was valid, and the app wipes its local state either way (2/3 §10).
    ("POST", "/api/v1/auth/otp/sign-out"),
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
}


def _guarded_roles(route: APIRoute) -> set[Role] | None:
    """The roles a route's `require_roles` guard demands, or `None` if unguarded.

    Walks the resolved dependency tree, which is what actually runs — as opposed
    to the annotation, which is what a reviewer reads.
    """
    probe = require_roles(Role.ADMIN)
    guard_name = probe.__qualname__.rsplit(".", 1)[0]

    for dependency in route.dependant.dependencies:
        call = dependency.call
        if call is None:
            continue
        if getattr(call, "__qualname__", "").startswith(guard_name):
            closure = getattr(call, "__closure__", None) or ()
            for cell in closure:
                contents = cell.cell_contents
                if isinstance(contents, tuple) and all(
                    isinstance(r, Role) for r in contents
                ):
                    return set(contents)
    return None


def _routes(app: FastAPI) -> list[tuple[str, APIRoute]]:
    """Every `APIRoute` the application will actually serve, with its full path.

    This FastAPI version keeps an included router as a nested node carrying its
    own prefix rather than flattening its routes into `app.routes`, so a
    non-recursive walk finds only the two ops endpoints — and every assertion
    below would pass vacuously, which is exactly the failure this file exists to
    prevent. `test_the_table_has_no_stale_entries` is the canary: it fails loudly
    if the walk stops finding routes.
    """
    found: list[tuple[str, APIRoute]] = []
    stack: list[tuple[str, Any]] = [("", node) for node in app.routes]
    while stack:
        prefix, node = stack.pop()
        if isinstance(node, APIRoute):
            found.append((prefix + node.path, node))
            continue
        context = getattr(node, "include_context", None)
        router = getattr(node, "original_router", None) or getattr(node, "app", None)
        if router is not None and hasattr(router, "routes"):
            nested_prefix = prefix + getattr(context, "prefix", "")
            stack.extend((nested_prefix, child) for child in router.routes)
        elif hasattr(node, "routes"):
            stack.extend((prefix, child) for child in node.routes)
    return found


def _keys(path: str, route: APIRoute) -> list[tuple[str, str]]:
    return [(method, path) for method in sorted(route.methods - {"HEAD", "OPTIONS"})]


def _all_keys(app: FastAPI) -> set[tuple[str, str]]:
    return {key for path, route in _routes(app) for key in _keys(path, route)}


class TestEveryRouteIsAccountedFor:
    def test_no_route_is_missing_from_the_table(self, app_client: Any) -> None:
        """A new route with no entry here fails the build.

        Which is the point: adding an endpoint should require stating, in a
        test, who may call it.
        """
        found = _all_keys(app_client.app) - UNGUARDED
        assert found - set(EXPECTED) == set(), (
            "routes with no entry in EXPECTED — declare their required role"
        )

    def test_the_table_has_no_stale_entries(self, app_client: Any) -> None:
        found = _all_keys(app_client.app)
        assert set(EXPECTED) - found == set(), "EXPECTED names routes that do not exist"
        # The walk above is only meaningful if it finds things. A future FastAPI
        # that changes its internals again must fail here, not silently pass.
        assert len(found) >= len(EXPECTED)

    def test_every_expected_route_actually_has_a_guard_wired(
        self, app_client: Any
    ) -> None:
        """The assertion the previous build failed.

        Not "is annotated" — has a `require_roles` dependency in the tree that
        FastAPI will actually execute.
        """
        unguarded = [
            key
            for path, route in _routes(app_client.app)
            for key in _keys(path, route)
            if key not in UNGUARDED and _guarded_roles(route) is None
        ]
        assert unguarded == [], f"routes with no role guard wired: {unguarded}"

    def test_each_guard_demands_the_expected_roles(self, app_client: Any) -> None:
        mismatches = [
            (key, EXPECTED.get(key), _guarded_roles(route))
            for path, route in _routes(app_client.app)
            for key in _keys(path, route)
            if key not in UNGUARDED and _guarded_roles(route) != EXPECTED.get(key)
        ]
        assert mismatches == []

    def test_ops_endpoints_stay_open(self, app_client: Any) -> None:
        """A liveness probe that needs a credential is a liveness probe that
        restarts a healthy container the first time the credential rotates."""
        assert app_client.get("/healthz").status_code == 200


class TestTheGuardsActuallyRefuse:
    """The other half. A wired guard that never refuses is not a guard."""

    def test_a_kiosk_cannot_read_the_worklist(self, app_client: Any) -> None:
        response = app_client.get("/api/v1/worklist", headers=KIOSK_HEADERS)
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"

    def test_a_kiosk_cannot_read_a_report(self, app_client: Any) -> None:
        response = app_client.get("/api/v1/intakes/any/report", headers=KIOSK_HEADERS)
        assert response.status_code == 403

    def test_staff_cannot_verify(self, app_client: Any) -> None:
        """Verification is the one act that changes the clinical weight of the
        record, and it belongs to a physician."""
        response = app_client.post(
            "/api/v1/intakes/any/verify", headers=STAFF_HEADERS, json={}
        )
        assert response.status_code == 403
        assert response.json()["details"]["required"] == ["physician"]

    def test_staff_cannot_act_on_a_single_fact(self, app_client: Any) -> None:
        """Per-fact verification is the same act at a finer grain — 3/3 §6.

        Worth its own assertion rather than trusting the table: the whole-record
        route and this one are guarded in different files, and the finer-grained
        one is the one a dashboard calls hundreds of times a day.
        """
        response = app_client.post(
            "/api/v1/intakes/any/facts/any/verify",
            headers=STAFF_HEADERS,
            json={"action": "verified"},
        )
        assert response.status_code == 403
        assert response.json()["details"]["required"] == ["physician"]

    def test_a_physician_is_not_an_admin(self, app_client: Any) -> None:
        """The correction rate is not a clinical read and does not inherit one."""
        response = app_client.get(
            "/api/v1/metrics/correction-rate", headers=PHYSICIAN_HEADERS
        )
        assert response.status_code == 403

    def test_a_kiosk_cannot_list_alerts(self, app_client: Any) -> None:
        response = app_client.get("/api/v1/alerts", headers=KIOSK_HEADERS)
        assert response.status_code == 403

    def test_a_physician_inherits_staff_access(self, app_client: Any) -> None:
        response = app_client.get("/api/v1/worklist", headers=PHYSICIAN_HEADERS)
        assert response.status_code == 200

    def test_no_credentials_is_401(self, app_client: Any) -> None:
        response = app_client.get("/api/v1/worklist")
        assert response.status_code == 401

    def test_an_unknown_role_fails_closed(self, app_client: Any) -> None:
        """A role nobody recognises lands nowhere permissive."""
        response = app_client.get(
            "/api/v1/worklist",
            headers={
                "X-User-Id": "x",
                "X-User-Role": "superuser",
                "X-Hospital-Id": "aiia-delhi",
            },
        )
        assert response.status_code == 401

    def test_a_bad_service_token_is_401(self, app_client: Any) -> None:
        response = app_client.post(
            "/api/v1/intakes/ingest",
            headers={"Authorization": "Bearer not-a-real-token"},
            json={},
        )
        assert response.status_code == 401

    def test_the_kiosk_token_binds_its_hospital(self, app_client: Any) -> None:
        """A kiosk cannot choose which hospital it writes to.

        The token decides. There is no header a device can send to change it.
        """
        response = app_client.post(
            "/api/v1/intakes/ingest",
            headers={**KIOSK_HEADERS, "X-Hospital-Id": "somewhere-else"},
            json={
                "schema_version": "0.1",
                "intake_id": "cc11dd22-0000-4000-8000-000000000001",
                "hospital_id": "somewhere-else",
                "status": "complete",
                "language": "en",
                "fields": {},
            },
        )
        assert response.status_code == 200
        intake_id = response.json()["intake_id"]

        # Visible to this hospital's staff…
        assert (
            app_client.get(
                f"/api/v1/intakes/{intake_id}", headers=STAFF_HEADERS
            ).status_code
            == 200
        )
        # …and to nobody else's.
        assert (
            app_client.get(
                f"/api/v1/intakes/{intake_id}", headers=OTHER_STAFF_HEADERS
            ).status_code
            == 404
        )


class TestHeaderAuthCanBeTurnedOff:
    def test_disabling_header_auth_leaves_only_service_tokens(
        self, app_client: Any, settings: Any
    ) -> None:
        """`ALLOW_HEADER_AUTH=false` is the production posture.

        The header principal is a stand-in for the hospital's identity provider
        while the dashboard is built. In an environment holding real data it is
        off, and this asserts that turning it off actually closes the door.
        """
        object.__setattr__(settings, "allow_header_auth", False)
        try:
            assert (
                app_client.get("/api/v1/worklist", headers=STAFF_HEADERS).status_code
                == 401
            )
            # The kiosk token still works — it is not header auth.
            assert (
                app_client.post(
                    "/api/v1/intakes/ingest", headers=KIOSK_HEADERS, json={}
                ).status_code
                != 401
            )
        finally:
            object.__setattr__(settings, "allow_header_auth", True)


@pytest.fixture(autouse=True)
def _quiet_logging() -> None:
    from app.core.logging import configure_logging

    configure_logging(level="ERROR", json_output=False)
