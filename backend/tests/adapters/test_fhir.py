"""The FHIR R4 bundle — §10.

The bundle is the interoperability claim, and it is worth more than a live ABDM
call: an ABDM link proves an integration, a valid bundle proves the data model,
and the data model has to be right before the integration is worth building.

Three things are asserted here, in descending order of how badly they hurt when
wrong:

1. **The five-valued status maps onto `dataAbsentReason` and never onto a
   value.** This is the part most likely to regress, because every downstream
   convenience wants to flatten "unresolved" into "no".
2. **No code is invented.** A field with no mapping gets `text` and no `coding`.
   A guessed ICD-11 code in an exchangeable document is a wrong diagnosis in
   somebody's permanent record.
3. **The bundle is byte-stable**, so it can be diffed against an earlier one and
   the difference means something.

The published validator runs at the bottom, behind the `network` marker, so the
offline suite stays runnable on a train.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.adapters.fhir.mapper import (
    ABSENT_REASONS,
    DeterministicFHIRMapper,
    code_system_resource,
    concept_map_resource,
    system_uri,
    value_set_resource,
)
from app.domain.record import FieldStatus
from tests.conftest import HOSPITAL_ID
from tests.integration.fhir_checks import structural_errors


@pytest.fixture
async def record(ingest_service: Any, report_service: Any, kiosk_payload: dict[str, Any]) -> Any:
    """The reference intake, loaded back.

    Chosen because it carries all five statuses at once: an answered complaint,
    an unresolved severity, a refused tobacco question, a not-applicable
    pregnancy field and a never-asked breathlessness field. A fixture covering
    only `answered` would let the whole of rule 1 above regress unnoticed.
    """
    result = await ingest_service.ingest(
        kiosk_payload, hospital_id=HOSPITAL_ID, actor_id="kiosk-1"
    )
    return await report_service.load_record(
        hospital_id=HOSPITAL_ID, intake_id=result.intake_id
    )


@pytest.fixture
def mapper(content: Any) -> DeterministicFHIRMapper:
    return DeterministicFHIRMapper(
        codes={c.concept_id: dict(c.codes) for c in content.concepts},
        labels=content.field_labels(),
    )


@pytest.fixture
def bundle(mapper: DeterministicFHIRMapper, record: Any) -> dict[str, Any]:
    return mapper.to_bundle(record)


def _resources(bundle: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == kind]


def _by_field(bundle: dict[str, Any], field_id: str, labels: dict[str, str]) -> dict[str, Any]:
    """The resource for one field, found the way a consumer would: by its text."""
    label = labels.get(field_id) or field_id.replace("_", " ")
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if resource.get("code", {}).get("text") == label:
            return resource
    raise AssertionError(f"no resource carrying {label!r}")


class TestItIsAWellFormedBundle:
    def test_no_structural_errors(self, bundle: dict[str, Any]) -> None:
        assert structural_errors(bundle) == []

    def test_it_opens_with_the_patient_and_the_encounter(
        self, bundle: dict[str, Any]
    ) -> None:
        kinds = [e["resource"]["resourceType"] for e in bundle["entry"]]
        assert kinds[:2] == ["Patient", "Encounter"]

    def test_the_patient_carries_identifiers_and_nothing_else(
        self, bundle: dict[str, Any]
    ) -> None:
        """This service is not a demographics store.

        A bundle carrying name, address or phone would make it one, and the
        record model deliberately never held them.
        """
        patient = _resources(bundle, "Patient")[0]
        assert set(patient) <= {"resourceType", "id", "identifier", "communication"}
        assert patient["identifier"][0]["value"] == "UHID-100241"

    def test_the_aadhaar_fragment_is_never_emitted(
        self, mapper: DeterministicFHIRMapper, record: Any
    ) -> None:
        """Four digits identify nobody, and putting them in an exchangeable
        document invites a receiver to treat them as an identifier."""
        from app.domain.record import PatientRef, PatientRefType

        with_fragment = record.model_copy(
            update={
                "patient_ref": PatientRef(type=PatientRefType.AADHAAR_LAST4, value="4321")
            }
        )
        rendered = json.dumps(mapper.to_bundle(with_fragment), ensure_ascii=False)
        assert "4321" not in rendered
        assert _resources(json.loads(rendered), "Patient")[0]["identifier"] == []


class TestTheFiveStatusesSurvive:
    """The part most likely to regress.

    FHIR has `dataAbsentReason` codes for exactly these distinctions. A bundle
    that collapsed them would be lying in a standard format, which is worse than
    lying in a proprietary one — the receiver has no reason to doubt it.
    """

    @pytest.mark.parametrize(
        ("field_id", "expected"),
        [
            ("severity", "unknown"),
            ("tobacco", "asked-declined"),
            ("pregnancy", "not-applicable"),
            ("breathlessness", "not-asked"),
        ],
    )
    def test_each_unsettled_status_maps_to_its_own_code(
        self, bundle: dict[str, Any], content: Any, field_id: str, expected: str
    ) -> None:
        resource = _by_field(bundle, field_id, content.field_labels())
        assert resource["dataAbsentReason"]["coding"][0]["code"] == expected

    def test_an_unsettled_field_never_carries_a_value(
        self, bundle: dict[str, Any]
    ) -> None:
        """Not a value, and emphatically not `false`.

        `unresolved` means the device asked twice and could not bind an answer.
        Rendering that as `valueBoolean: false` is the single worst thing this
        mapper could do, and it is one careless `or` away at all times.
        """
        for entry in bundle["entry"]:
            resource = entry["resource"]
            if "dataAbsentReason" not in resource:
                continue
            assert not [key for key in resource if key.startswith("value")], (
                f"{resource['id']} has both a value and a dataAbsentReason"
            )

    def test_every_unsettled_status_has_a_mapping(self) -> None:
        """The table is exhaustive, checked against the enum rather than a list.

        A sixth status added to `FieldStatus` without a `dataAbsentReason` would
        otherwise silently fall through to `unknown` — which is a different
        clinical claim from whatever the new status means.
        """
        unsettled = set(FieldStatus) - {FieldStatus.ANSWERED}
        assert unsettled == set(ABSENT_REASONS)

    def test_the_status_travels_verbatim_as_an_extension_as_well(
        self, bundle: dict[str, Any], content: Any
    ) -> None:
        """`dataAbsentReason` is the receiver's vocabulary; this is ours.

        A consumer that understands only FHIR loses nothing; one that reads the
        extension gets the exact status the device reported.
        """
        severity = _by_field(bundle, "severity", content.field_labels())
        statuses = {
            extension["valueCode"]
            for extension in severity["extension"]
            if extension["url"].endswith("/field-status")
        }
        assert statuses == {"unresolved"}


class TestItInventsNoCodes:
    def test_a_field_with_no_mapping_gets_text_and_no_coding(
        self, bundle: dict[str, Any], content: Any
    ) -> None:
        """`chief_complaint` has no code in the terminology tables.

        `CodeableConcept` with `text` and no `coding` is valid R4 and is the
        honest representation of "we know what this is, we have no code for it".
        """
        complaint = _by_field(bundle, "chief_complaint", content.field_labels())
        assert complaint["code"]["text"]
        assert "coding" not in complaint["code"]

    def test_a_field_with_a_mapping_gets_every_system_it_is_mapped_in(
        self, bundle: dict[str, Any], content: Any
    ) -> None:
        """`known_diabetes` is dual-coded — ICD-11 MMS and NAMASTE.

        Dual coding is the whole point of the terminology work, so it has to
        reach the exchange format rather than stopping at the search endpoint.
        """
        diabetes = _by_field(bundle, "known_diabetes", content.field_labels())
        systems = {coding["system"] for coding in diabetes["code"]["coding"]}
        assert system_uri("ICD11-MMS") in systems
        assert system_uri("NAMASTE") in systems

    def test_with_no_terminology_at_all_nothing_acquires_a_code(
        self, record: Any
    ) -> None:
        """An empty mapping table must produce a bundle with no codings.

        The failure this guards against is a fallback: a mapper that, finding no
        mapping, reaches for the field id, a default system, or a plausible
        guess. Any of those puts an unverified code in a clinical document.
        """
        bare = DeterministicFHIRMapper(codes={}, labels={}).to_bundle(record)
        codings = [
            coding
            for entry in bare["entry"]
            for coding in entry["resource"].get("code", {}).get("coding", [])
        ]
        assert codings == []
        # And it is still a valid bundle: text-only concepts are legal R4.
        assert structural_errors(bare) == []


class TestItIsStable:
    def test_the_same_record_produces_the_same_bytes(
        self, mapper: DeterministicFHIRMapper, record: Any
    ) -> None:
        first = json.dumps(mapper.to_bundle(record), ensure_ascii=False, indent=2)
        second = json.dumps(mapper.to_bundle(record), ensure_ascii=False, indent=2)
        assert first == second

    def test_resource_ids_are_derived_rather_than_generated(
        self, mapper: DeterministicFHIRMapper, record: Any
    ) -> None:
        """Two mappers, two bundles, the same ids.

        Generated ids would make every export a full diff, which is the same as
        having no diff at all.
        """
        other = DeterministicFHIRMapper(codes={}, labels={})
        assert [e["resource"]["id"] for e in mapper.to_bundle(record)["entry"]] == [
            e["resource"]["id"] for e in other.to_bundle(record)["entry"]
        ]

    def test_fact_order_in_the_record_does_not_change_the_bundle(
        self, mapper: DeterministicFHIRMapper, record: Any
    ) -> None:
        shuffled = record.model_copy(update={"facts": list(reversed(record.facts))})
        assert mapper.to_bundle(shuffled) == mapper.to_bundle(record)


class TestTheTerminologyResources:
    def test_a_code_system_carries_only_the_codes_that_were_seeded(
        self, content: Any
    ) -> None:
        """`content: fragment`, because the seed is a fragment.

        Claiming `complete` for a partial extract would tell a receiver that a
        code absent from the resource does not exist.
        """
        concepts = [{"code": "MD81", "display": "Abdominal pain"}]
        resource = code_system_resource("ICD11-MMS", concepts)
        assert resource["content"] == "fragment"
        assert resource["url"] == system_uri("ICD11-MMS")
        assert [c["code"] for c in resource["concept"]] == ["MD81"]

    def test_a_concept_map_holds_only_authored_rows(self) -> None:
        """A code with no target is simply absent.

        The resource never asserts an equivalence nobody established, which is
        the same rule as `TestItInventsNoCodes` in a different shape.
        """
        resource = concept_map_resource(
            [
                {
                    "source_system": "NAMASTE",
                    "source_code": "AY-MDH",
                    "target_system": "ICD11-MMS",
                    "target_code": "5A11",
                    "equivalence": "relatedto",
                }
            ]
        )
        assert len(resource["group"]) == 1
        assert resource["group"][0]["element"][0]["target"][0]["code"] == "5A11"

    def test_a_value_set_is_expanded_rather_than_intensional(self) -> None:
        resource = value_set_resource(
            "namaste-seed", "NAMASTE", [{"code": "AY-MDH", "display": "Madhumeha"}]
        )
        include = resource["compose"]["include"][0]
        assert include["system"] == system_uri("NAMASTE")
        assert include["concept"] == [{"code": "AY-MDH", "display": "Madhumeha"}]

    def test_namaste_uses_a_medikiosk_scoped_uri(self) -> None:
        """NAMASTE has no published canonical URI.

        So this one is clearly ours, rather than squatting on a plausible
        government domain that may one day mean something else.
        """
        assert system_uri("NAMASTE").startswith("https://medikiosk.in/")
        assert system_uri("ICD11-MMS") == "http://id.who.int/icd/release/11/mms"


@pytest.mark.network
class TestThePublishedValidatorAccepts:
    """The bundle, against a real FHIR R4 validator — §10.

    Marked `network` and deselected by default (`-m 'not network'`), because a
    suite that needs the internet is a suite that fails in the room where the
    demo happens.

    A connection failure skips rather than fails: somebody else's server being
    down is not a defect in this bundle. A returned `error` or `fatal` issue
    fails, loudly, because that is the validator doing its job.
    """

    ENDPOINT = "https://hapi.fhir.org/baseR4/Bundle/$validate"

    def test_it_validates(self, bundle: dict[str, Any]) -> None:
        import httpx

        try:
            response = httpx.post(
                self.ENDPOINT,
                content=json.dumps(bundle, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Content-Type": "application/fhir+json",
                    "Accept": "application/fhir+json",
                },
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            pytest.skip(f"the public FHIR validator was unreachable: {exc}")

        if response.status_code >= 500:
            pytest.skip(f"the public FHIR validator returned {response.status_code}")

        outcome = response.json()
        assert outcome.get("resourceType") == "OperationOutcome", outcome
        serious = [
            issue
            for issue in outcome.get("issue", [])
            if issue.get("severity") in {"error", "fatal"}
        ]
        assert not serious, "\n".join(
            f"{issue.get('severity')}: "
            f"{issue.get('diagnostics') or issue.get('details', {}).get('text')}"
            for issue in serious
        )
