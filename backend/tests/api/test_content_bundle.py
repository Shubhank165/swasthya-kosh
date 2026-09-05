"""The bundle endpoint — 2/3 §4, §12."""

from __future__ import annotations

from typing import Any


class TestServingTheBundle:
    def test_it_is_reachable_without_a_credential(self, app_client: Any) -> None:
        """The app renders a sign-in screen in the patient's own language before
        the patient has signed in, which it cannot do without the prompts."""
        assert app_client.get("/api/v1/content/bundle").status_code == 200

    def test_it_carries_an_etag_and_a_version_header(self, app_client: Any) -> None:
        response = app_client.get("/api/v1/content/bundle")
        assert response.headers["ETag"].startswith('"')
        assert response.headers["X-Content-Version"]

    def test_a_matching_etag_gets_304_and_no_body(self, app_client: Any) -> None:
        """80 KB on every app launch, on what may be mobile data. The 304 is the
        difference between an app that opens on a bad connection and one that
        does not."""
        first = app_client.get("/api/v1/content/bundle")
        second = app_client.get(
            "/api/v1/content/bundle",
            headers={"If-None-Match": first.headers["ETag"]},
        )
        assert second.status_code == 304
        assert not second.content

    def test_a_stale_etag_gets_the_body(self, app_client: Any) -> None:
        response = app_client.get(
            "/api/v1/content/bundle", headers={"If-None-Match": '"stale"'}
        )
        assert response.status_code == 200

    def test_it_must_revalidate_rather_than_cache_blindly(
        self, app_client: Any
    ) -> None:
        """A stale red-flag rule is a safety problem, and the 304 makes
        revalidating nearly free — so there is no max-age here."""
        response = app_client.get("/api/v1/content/bundle")
        assert "no-cache" in response.headers["Cache-Control"]

    def test_the_cheap_version_check_agrees_with_the_bundle(
        self, app_client: Any
    ) -> None:
        """For a client deciding whether to refresh on a metered connection."""
        bundle = app_client.get("/api/v1/content/bundle")
        version = app_client.get("/api/v1/content/bundle/version").json()
        assert version["etag"] == bundle.headers["ETag"]
        assert version["content_version"] == bundle.headers["X-Content-Version"]

    def test_it_holds_no_patient_data(self, app_client: Any) -> None:
        """The justification for serving it unauthenticated.

        It is the questions an OPD asks — the same questions printed on the
        clipboard in the waiting room.
        """
        body = app_client.get("/api/v1/content/bundle").json()
        assert set(body) == {
            "bundle_format", "content_version", "schema_version", "languages",
            "sections", "core", "branches", "ayurveda",
            "ayurveda_current_state", "questions", "red_flag_rules",
        }

    def test_the_return_visit_ayurveda_subset_is_a_subset(
        self, app_client: Any
    ) -> None:
        """2/3 §5 screen 8 — the full set on a first visit, the current-state
        subset on a return.

        Which items belong in it is a clinical judgement and lives in the
        content. What is asserted here is only that it *is* a subset: an entry
        the full plan does not contain would be a question the app puts to
        returning patients and to nobody else, which no clinician authored.
        """
        body = app_client.get("/api/v1/content/bundle").json()
        full = set(body["ayurveda"])
        subset = set(body["ayurveda_current_state"])
        assert subset
        assert subset < full


class TestServingTheConsentNotice:
    """§11, DPDP: the patient reads what they are agreeing to, before they agree."""

    def test_it_is_reachable_without_a_credential(self, app_client: Any) -> None:
        assert app_client.get("/api/v1/content/consent").status_code == 200

    def test_the_kiosk_is_offered_audio_retention_and_the_app_is_not(
        self, app_client: Any
    ) -> None:
        """The app has no microphone (2/3 §1 rule 1).

        Asking a patient to consent to the retention of audio the app cannot
        capture would produce a DPDP artefact describing something that never
        happened — and it would produce one for every app intake, which is worse
        than producing none.
        """
        kiosk = app_client.get("/api/v1/content/consent?source=kiosk").json()
        app = app_client.get("/api/v1/content/consent?source=app").json()

        codes = {"kiosk": {p["code"] for p in kiosk["purposes"]},
                 "app": {p["code"] for p in app["purposes"]}}
        assert "raw_audio_retention" in codes["kiosk"]
        assert "raw_audio_retention" not in codes["app"]
        # Everything else is the same notice. A purpose that quietly applied to
        # one surface and not the other would be a second consent regime.
        assert codes["kiosk"] - {"raw_audio_retention"} == codes["app"]

    def test_every_purpose_carries_a_label_in_every_bundle_language(
        self, app_client: Any
    ) -> None:
        """A purpose shown in a language the patient did not choose is not
        consent, and a missing translation must fail here rather than on a
        phone."""
        body = app_client.get("/api/v1/content/consent?source=app").json()
        assert body["purposes"]
        for purpose in body["purposes"]:
            assert set(purpose["label"]) >= {"en", "hi"}
            assert set(purpose["description"]) >= {"en", "hi"}

    def test_the_required_purpose_is_marked_required(self, app_client: Any) -> None:
        body = app_client.get("/api/v1/content/consent?source=app").json()
        required = {p["code"] for p in body["purposes"] if p["required"]}
        assert required == {"history_intake"}
