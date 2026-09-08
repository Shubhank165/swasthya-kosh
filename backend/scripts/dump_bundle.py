"""Write the compiled offline bundle to the app's test fixture.

    ./.venv/bin/python -m scripts.dump_bundle

The app's suite walks a real bundle rather than a hand-built one, so that a
question shape the compiler emits and the walker cannot read is caught by a
test rather than by a patient. Committing it keeps `flutter test` free of a
Python toolchain; `TestTheAppFixtureIsCurrent` fails when it goes stale.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.core.content import load_questioning
from app.domain.questions.bundle import canonical_json
from app.normalize.registry import supported_versions
from app.questioning_agent.output.bundle import compile_bundle

FIXTURE = Path(__file__).resolve().parents[2] / "app/test/fixtures/questioning_bundle.json"


def main() -> None:
    settings = get_settings()
    content = load_questioning(settings.questioning_dir)
    bundle = compile_bundle(
        bank=content.bank,
        slots=content.slots,
        localization=content.localization,
        triage=content.triage,
        schema_version=supported_versions()[-1],
    )
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(canonical_json(bundle), encoding="utf-8")
    print(f"{FIXTURE}: {FIXTURE.stat().st_size / 1024:.0f} KB, "
          f"{len(bundle['questions'])} questions, "
          f"{len(bundle['red_flag_rules'])} red-flag rules")


if __name__ == "__main__":
    main()
