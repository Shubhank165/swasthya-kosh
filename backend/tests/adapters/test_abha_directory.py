"""The fake ABHA directory, and the honesty rules it must not break.

`DECISIONS.md §56` — ABHA is offered, never asked for, and a mocked government
integration is never presented as a live one. Adding fixtures makes the mock
*more* convincing, which is exactly when that rule needs a test rather than a
paragraph.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.adapters.abha.providers import MockABHAProvider
from app.core.config import get_settings

FIXTURES = Path(__file__).resolve().parents[2] / "app" / "adapters" / "abha" / "fixtures"


class TestAKnownAddressReturnsItsInventedPerson:
    async def test_the_demo_patient_resolves(self) -> None:
        provider = MockABHAProvider(FIXTURES)
        result = await provider.verify("asha.devi@sbx")
        assert result is not None
        assert result["verified"] is True
        assert result["demographics"]["display_name"] == "Asha Devi"

    async def test_the_address_is_matched_case_insensitively(self) -> None:
        provider = MockABHAProvider(FIXTURES)
        result = await provider.verify("Asha.Devi@SBX")
        assert result is not None
        assert result["demographics"]["external_mrn"] == "UHID-100241"


class TestItNeverPretendsToBeReal:
    async def test_source_is_mock_on_every_answer(self) -> None:
        """The app keys `isMocked` off this field and not off the notice."""
        provider = MockABHAProvider(FIXTURES)
        for address in ("asha.devi@sbx", "nobody.here@sbx"):
            result = await provider.verify(address)
            if result is not None:
                assert result["source"] == "mock"

    async def test_every_demographic_block_declares_itself_synthetic(self) -> None:
        provider = MockABHAProvider(FIXTURES)
        result = await provider.verify("ramesh.kumar@sbx")
        assert result is not None
        assert result["demographics"]["synthetic"] is True

    async def test_a_fixture_that_forgot_the_flag_still_gets_it(self, tmp_path: Path) -> None:
        """Re-asserted in code rather than trusted from the file, so an entry
        somebody adds without it cannot read as a real person."""
        (tmp_path / "mock_directory.json").write_text(
            json.dumps({"entries": {"careless@sbx": {"display_name": "Nobody"}}}),
            encoding="utf-8",
        )
        result = await MockABHAProvider(tmp_path).verify("careless@sbx")
        assert result is not None
        assert result["demographics"]["synthetic"] is True

    async def test_the_notice_is_unchanged(self) -> None:
        provider = MockABHAProvider(FIXTURES)
        result = await provider.verify("asha.devi@sbx")
        assert result is not None
        assert "No ABDM call was made" in result["notice"]


class TestTheNotFoundPathSurvivedTheFixtures:
    async def test_an_unknown_address_can_still_fail_to_verify(self) -> None:
        """Roughly one unknown address in eight, by the old hash rule. Fixtures
        must not turn "could not be verified, carry on as a guest" into a state
        the demo can no longer show."""
        provider = MockABHAProvider(FIXTURES)
        outcomes = [
            await provider.verify(f"person{n}@sbx") for n in range(64)
        ]
        assert any(outcome is None for outcome in outcomes)
        assert any(outcome is not None for outcome in outcomes)

    async def test_a_malformed_address_is_never_verified(self) -> None:
        provider = MockABHAProvider(FIXTURES)
        assert await provider.verify("not an address") is None

    async def test_a_missing_directory_is_not_an_error(self, tmp_path: Path) -> None:
        """Failing to start because a demo fixture is absent would be the wrong
        trade — the provider falls back to what it did before fixtures."""
        provider = MockABHAProvider(tmp_path)
        assert await provider.verify("asha.devi@sbx") is not None


class TestItIsWiredByDefault:
    def test_the_settings_point_at_the_shipped_directory(self) -> None:
        assert (get_settings().abha_fixtures_dir / "mock_directory.json").exists()
