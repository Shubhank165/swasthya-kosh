import pytest

from medikiosk.clinical.heuristic import HeuristicClinicalExtractor
from medikiosk.clinical.hybrid import HybridClinicalExtractor
from medikiosk.models import ClinicalUpdate
from medikiosk.providers.local_llm_provider import LocalLLMClinicalExtractor

EMPTY = {
    "complaint": None, "duration": None, "onset": None, "severity": None,
    "vomiting": None, "fever": None, "breathlessness": None, "chest_pain": None,
    "pain_radiation": None, "sweating": None, "active_bleeding": None,
    "altered_consciousness": None, "one_sided_weakness": None, "speech_difficulty": None,
    "pregnancy_possible": None, "age_years": None,
    "medications": [], "allergies": [], "evidence": [],
}


class StubExtractor:
    def __init__(self, update: ClinicalUpdate) -> None:
        self.update = update

    async def extract(self, transcript: str) -> ClinicalUpdate:
        return self.update


@pytest.mark.asyncio
async def test_llm_fills_a_field_the_heuristic_left_null() -> None:
    heuristic = StubExtractor(ClinicalUpdate(**{**EMPTY, "complaint": None}))
    llm = StubExtractor(ClinicalUpdate(**{**EMPTY, "complaint": "headache", "evidence": ["headache"]}))
    merged = await HybridClinicalExtractor(heuristic, llm).extract("my head hurts")
    assert merged.complaint == "headache"


@pytest.mark.asyncio
async def test_heuristic_field_is_never_overridden_by_the_llm() -> None:
    heuristic = StubExtractor(ClinicalUpdate(**{**EMPTY, "complaint": "chest pain"}))
    llm = StubExtractor(ClinicalUpdate(**{**EMPTY, "complaint": "abdominal pain"}))
    merged = await HybridClinicalExtractor(heuristic, llm).extract("chest pain")
    assert merged.complaint == "chest pain"


@pytest.mark.asyncio
async def test_no_llm_configured_returns_heuristic_result_unchanged() -> None:
    heuristic = StubExtractor(ClinicalUpdate(**{**EMPTY, "complaint": "chest pain"}))
    merged = await HybridClinicalExtractor(heuristic, None).extract("chest pain")
    assert merged.complaint == "chest pain"


@pytest.mark.asyncio
async def test_llm_can_never_supply_severity() -> None:
    """gemma3:1b invents a 0-10 score from adjectives alone ("a bad headache" -> 10 in on-device
    testing); severity feeds red_flags.py thresholds directly, so a fabricated number there is a
    false or suppressed emergency alert, not a missing detail. Must stay heuristic-only."""

    heuristic = StubExtractor(ClinicalUpdate(**{**EMPTY, "severity": None}))
    llm = StubExtractor(ClinicalUpdate(**{**EMPTY, "severity": 10}))
    merged = await HybridClinicalExtractor(heuristic, llm).extract("a bad headache")
    assert merged.severity is None


@pytest.mark.asyncio
async def test_unreachable_ollama_degrades_instead_of_raising() -> None:
    """The whole point of the fail-safe branch: Ollama timing out or dying mid-session must cost
    the turn nothing but recall. Port 9 (discard) is always refused. This caught a real bug - the
    fallback passed evidence= twice and raised KeyError, so the degraded path crashed harder than
    the failure it was meant to absorb."""

    dead = LocalLLMClinicalExtractor(base_url="http://127.0.0.1:9")
    assert dead.health() is False

    update = await dead.extract("my ankle hurts")
    assert update.complaint is None
    assert update.evidence == ["my ankle hurts"]

    merged = await HybridClinicalExtractor(HeuristicClinicalExtractor(), dead).extract(
        "I have chest pain and I am short of breath"
    )
    assert merged.complaint == "chest pain"
    assert merged.breathlessness is True


@pytest.mark.asyncio
async def test_medication_lists_merge_without_duplicates() -> None:
    heuristic = StubExtractor(ClinicalUpdate(**{**EMPTY, "medications": ["paracetamol"]}))
    llm = StubExtractor(
        ClinicalUpdate(**{**EMPTY, "medications": ["paracetamol", "ibuprofen"]})
    )
    merged = await HybridClinicalExtractor(heuristic, llm).extract("I took paracetamol and ibuprofen")
    assert merged.medications == ["paracetamol", "ibuprofen"]
