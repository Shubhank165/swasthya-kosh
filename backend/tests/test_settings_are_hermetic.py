"""The suite must test the code, not the shell it was started from.

`Settings` is a pydantic-settings model, so every field falls back to an
environment variable. That is right for the application and wrong for a test
run: it means the configuration under test is whatever the operator's shell
happens to hold.

It is not hypothetical. `make deploy` is `check build-image migrate-cloud
deploy`, and a real deploy is invoked as

    OCR_PROVIDER=gemini PREFILL_PROVIDER=vertex ... make deploy

so `make check` runs with the cloud providers already in its environment —
while `VERTEX_PROJECT` is assembled *inside* `40-deploy.sh` and never exported.
`prefill_provider` was the one field the `settings` fixture did not pin, so the
suite tried to build a Vertex adapter with no project and roughly two hundred
tests errored with `ProviderNotConfigured`. The deploy could not pass its own
gate, and only when deploying with real models — which is the only time the
gate matters most.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings

#: Every field naming a provider. Derived from the model rather than listed, so
#: a provider added tomorrow is covered by this test the day it is added.
PROVIDER_FIELDS = sorted(
    name for name in Settings.model_fields if name.endswith("_provider")
)


def test_there_are_provider_fields_to_check() -> None:
    """Guards the test below from passing by finding nothing."""
    assert len(PROVIDER_FIELDS) >= 5


@pytest.mark.parametrize("field", PROVIDER_FIELDS)
def test_providers_are_pinned(
    settings: Settings, field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fixture's value must not move when the environment does.

    Asserting "equals mock" would be weaker and would need updating for
    `timeline_provider`, whose off switch is `none`. What matters is not which
    value it is — it is that the environment cannot change it.
    """
    pinned = getattr(settings, field)

    monkeypatch.setenv(field.upper(), "vertex")
    rebuilt = Settings(
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        **{f: getattr(settings, f) for f in PROVIDER_FIELDS},
    )

    assert getattr(rebuilt, field) == pinned, (
        f"{field} is read from ${field.upper()} rather than pinned by the "
        "settings fixture. Add it to the fixture in tests/conftest.py — "
        "otherwise `make deploy` configures its own test gate."
    )
