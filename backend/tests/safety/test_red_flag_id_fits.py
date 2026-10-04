"""Every criterion this system ships must be storable.

A red-flag event's primary key is `rf_{intake_id}_{rule_id}` — a deterministic
surrogate so that a retried ingest updates one row instead of inserting a
second. For a long time its column was narrower than the ids it was built from,
and the failure mode was the worst available one: the insert raised
`value too long for type character varying(64)`, ingest returned a 500, and the
device — which had already *stopped asking questions* because the criterion was
critical — retried into the same 500 until it gave up.

The criteria that overflowed were the long-named ones, and in this rule set
those are disproportionately the critical ones. The two that could never be
stored were `breathing_difficulty_at_rest` and
`headache_sudden_with_vision_change`: breathlessness at rest and a thunderclap
headache with visual change. The system could record a sore throat and not a
stroke.

So this test reads the **shipped rule set**, not a fixture. A new criterion with
a long name is a schema problem the day it is written, and this is where it
fails — at `make test`, rather than at a kiosk.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.models.clinical import RedFlagEventRecord

REPO_ROOT = Path(__file__).resolve().parents[3]
RULES = REPO_ROOT / "clinical" / "questioning" / "redflags.yaml"

#: The widest intake id the schema permits. The id is composed, so the bound has
#: to assume the worst case rather than whatever the current fixtures happen to
#: use — a uuid is 36 characters and the column allows 64.
MAX_INTAKE_ID = 64


def _rule_ids() -> list[str]:
    content = yaml.safe_load(RULES.read_text())
    return [rule["id"] for rule in content["rules"]]


def test_the_rule_set_is_not_empty() -> None:
    """Guards the two tests below from passing by finding nothing."""
    assert len(_rule_ids()) >= 9


def test_every_shipped_criterion_fits_its_own_primary_key() -> None:
    limit = RedFlagEventRecord.__table__.c.id.type.length
    assert limit is not None

    too_long = {
        rule_id: len(f"rf_{'x' * MAX_INTAKE_ID}_{rule_id}")
        for rule_id in _rule_ids()
        if len(f"rf_{'x' * MAX_INTAKE_ID}_{rule_id}") > limit
    }

    assert not too_long, (
        f"These criteria cannot be stored: {too_long} exceed id({limit}). "
        "Ingest answers a kiosk firing one of them with a 500, and a kiosk "
        "that fired a critical criterion has already stopped interviewing."
    )


def test_the_id_column_is_wide_enough_for_any_rule_id_the_schema_allows() -> None:
    """Not just today's rule set — anything `rule_id` itself permits.

    Checking only the shipped ids would let the column be exactly as wide as
    the longest name somebody happens to have written, which is a bound that
    moves every time the clinical content does.
    """
    id_limit = RedFlagEventRecord.__table__.c.id.type.length
    rule_limit = RedFlagEventRecord.__table__.c.rule_id.type.length
    assert id_limit is not None and rule_limit is not None

    worst_case = len("rf_") + MAX_INTAKE_ID + len("_") + rule_limit
    assert id_limit >= worst_case, (
        f"id({id_limit}) cannot hold rf_ + intake_id({MAX_INTAKE_ID}) + _ + "
        f"rule_id({rule_limit}) = {worst_case}."
    )
