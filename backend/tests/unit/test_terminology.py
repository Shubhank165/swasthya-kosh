"""Terminology and the FHIR resources it produces — §10.

Local and offline: NAMASTE, ICD-11 TM2 and ICD-11 MMS are seeded from
`clinical/terminology/` and searched with a deterministic matcher. No external
API, no model.

The rule that carries the weight is the negative one, again: **where nothing
maps, nothing is returned.** A ConceptMap that invents a correspondence between
an Ayurvedic nosological entity and a biomedical code is worse than an empty
one, because it looks authoritative and it ends up in somebody's discharge
summary.

These tests exist because the two resource builders were being called with an
older signature and both `GET /terminology/CodeSystem/{system}` and
`GET /terminology/ConceptMap` raised at runtime. Nothing failed: the routes were
guarded, documented and untested, and the type checker was the only thing that
had noticed.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import ContentError
from app.repositories.terminology import TerminologyRepository
from app.services.terminology import SUPPORTED_SYSTEMS, TerminologyService, seed_terminology
from tests.conftest import REPO_ROOT


@pytest.fixture
async def terminology(session: Any) -> TerminologyService:
    """The real seed files, loaded into the test database."""
    repository = TerminologyRepository(session)
    loaded = await seed_terminology(repository, REPO_ROOT / "clinical" / "terminology")
    assert loaded > 0, "the terminology seed loaded nothing"
    return TerminologyService(repository)


class TestTheResourcesAreBuildable:
    """Each one is a route's entire response body.

    A signature drift here is a 500 on an endpoint nobody calls until a
    reviewer does.
    """

    @pytest.mark.parametrize("system", SUPPORTED_SYSTEMS)
    async def test_a_code_system_renders_for_every_supported_system(
        self, terminology: TerminologyService, system: str
    ) -> None:
        resource = await terminology.code_system(system)
        assert resource["resourceType"] == "CodeSystem"
        assert resource["content"] == "fragment"
        assert resource["concept"], f"{system} seeded no codes"
        assert all(c["code"] and c["display"] for c in resource["concept"])

    async def test_an_unknown_system_is_refused_rather_than_empty(
        self, terminology: TerminologyService
    ) -> None:
        """An empty CodeSystem for a system we do not hold would read as "this
        vocabulary has no codes"."""
        with pytest.raises(ContentError, match="unknown terminology system"):
            await terminology.code_system("SNOMED-CT")

    async def test_the_concept_map_renders(
        self, terminology: TerminologyService
    ) -> None:
        resource = await terminology.concept_map()
        assert resource["resourceType"] == "ConceptMap"
        assert resource["group"], "the seed authored no mappings"
        for group in resource["group"]:
            assert group["source"].startswith("http")
            assert group["target"].startswith("http")
            for element in group["element"]:
                assert element["code"]
                assert element["target"][0]["code"]

    @pytest.mark.parametrize("system", SUPPORTED_SYSTEMS)
    async def test_a_value_set_renders_for_every_supported_system(
        self, terminology: TerminologyService, system: str
    ) -> None:
        resource = await terminology.value_set(system)
        assert resource["resourceType"] == "ValueSet"
        assert resource["compose"]["include"][0]["concept"]


class TestItMapsOnlyWhatWasAuthored:
    async def test_a_code_with_no_mapping_returns_only_itself(
        self, terminology: TerminologyService
    ) -> None:
        """"We have no equivalent for this" is a real answer.

        The caller writes what is true, not what would be convenient.
        """
        assert await terminology.dual_codes("NAMASTE", "NOT-A-REAL-CODE") == {
            "NAMASTE": "NOT-A-REAL-CODE"
        }

    async def test_the_concept_map_holds_no_element_without_a_target(
        self, terminology: TerminologyService
    ) -> None:
        resource = await terminology.concept_map()
        for group in resource["group"]:
            for element in group["element"]:
                assert element["target"], f"{element['code']} has an empty target list"

    async def test_search_returns_candidates_with_their_scores(
        self, terminology: TerminologyService
    ) -> None:
        """Side by side, with scores, so a Vaidya chooses rather than being
        handed one system's answer as though it were the answer."""
        results = await terminology.search("jwara")
        assert results
        assert all(0.0 <= result.score <= 1.0 for result in results)
        assert [r.score for r in results] == sorted(
            (r.score for r in results), reverse=True
        )

    async def test_search_for_something_absent_returns_nothing(
        self, terminology: TerminologyService
    ) -> None:
        assert await terminology.search("zzzzqqqq") == ()
