"""What a wrongly wired deployment does — §11, §12.

These are not clinical tests. They are about the half hour after somebody
deploys this for the first time, when the thing that has gone wrong is
configuration rather than code, and the only question that matters is whether
the error says so.

The case here was found by running the compose stack rather than by review: a
kiosk token whose hospital had never been seeded made every ingest return a bare
`Internal Server Error`, with the real cause — a foreign key violation on
`intakes.hospital_id` — five frames deep in a database traceback that only
reaches the server log.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import ConfigurationError


class TestAKioskTokenForAnUnknownHospital:
    async def test_it_names_the_hospital_rather_than_failing_opaquely(
        self,
        ingest_service: Any,
        kiosk_payload: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def explode(*args: Any, **kwargs: Any) -> None:
            raise IntegrityError(
                "INSERT INTO intakes ...",
                {},
                Exception(
                    'insert or update on table "intakes" violates foreign key '
                    'constraint "fk_intakes_hospital_id_hospitals"'
                ),
            )

        monkeypatch.setattr(ingest_service._intakes, "create", explode)

        with pytest.raises(ConfigurationError) as caught:
            await ingest_service.ingest(
                kiosk_payload, hospital_id="never-seeded", actor_id="kiosk-1"
            )

        assert caught.value.details["hospital_id"] == "never-seeded"
        assert "never-seeded" in str(caught.value)

    async def test_any_other_integrity_error_is_not_relabelled(
        self,
        ingest_service: Any,
        kiosk_payload: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A catch-all here would hide the next constraint somebody adds.

        Reporting an unrelated violation as "your hospital does not exist" sends
        the reader to the token map, which is fine, and then to a dead end.
        """

        async def explode(*args: Any, **kwargs: Any) -> None:
            raise IntegrityError(
                "INSERT INTO intakes ...",
                {},
                Exception('duplicate key value violates unique constraint "pk_intakes"'),
            )

        monkeypatch.setattr(ingest_service._intakes, "create", explode)

        with pytest.raises(IntegrityError):
            await ingest_service.ingest(
                kiosk_payload, hospital_id="aiia-delhi", actor_id="kiosk-1"
            )
