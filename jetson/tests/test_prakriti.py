"""The Ayush Prakriti questionnaire: the item set, the scoring, and the once-in-a-lifetime rule."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from medikiosk.kiosk import prakriti
from medikiosk.storage import EncryptedSessionStore

ABHA = "12345678901234"


# ------------------------------------------------------------------ the item set


def test_all_58_form_items_are_accounted_for() -> None:
    """The form numbers 1 to 58, skipping 51 and printing 53 twice: 57 numbers, 58 questions.

    This is the check that catches a question quietly dropped in an edit. Anything the kiosk does
    not ask still has to appear in PENDING with a reason - an unasked question that is also
    unlisted is a hole in the record nobody can see.
    """

    coverage = prakriti.coverage()
    assert coverage["missing"] == []
    assert coverage["unexpected"] == []
    assert coverage["form_numbers_covered"] == 57
    assert coverage["questions"] == prakriti.FORM_ITEM_COUNT == 58


def test_item_ids_and_option_values_are_unique() -> None:
    assert len({item.id for item in prakriti.ITEMS}) == len(prakriti.ITEMS)
    for item in prakriti.ITEMS:
        values = [choice.value for choice in item.choices]
        assert len(values) == len(set(values)), item.id


def test_every_item_is_bilingual_and_offers_at_least_two_answers() -> None:
    for item in prakriti.ITEMS:
        assert item.en.strip() and item.hi.strip(), item.id
        assert len(item.choices) >= 2, item.id
        for choice in item.choices:
            assert choice.en.strip() and choice.hi.strip(), (item.id, choice.value)


def test_hindi_is_served_to_hindi_and_english_to_everyone_else() -> None:
    """Only English and Hindi are printed on the CCRAS form.

    The other seven kiosk languages get the English wording rather than a machine translation of
    clinical text nobody has reviewed - the same rule flow.SCREEN_TEXT follows.
    """

    item = prakriti.BY_ID["pk_sleep_hours"]
    assert item.text_for("hi") == item.hi
    assert item.text_for("hi-IN") == item.hi
    assert item.text_for("ta") == item.en
    assert item.text_for(None) == item.en
    assert item.options_for("hi")[0]["label"] == item.choices[0].hi
    assert item.options_for("ta")[0]["label"] == item.choices[0].en


def test_demographic_items_score_nothing() -> None:
    """Marital status and income are on the form and on the sheet; they are not dosha evidence."""

    for item in prakriti.ITEMS:
        if item.section == "demographic":
            assert all(choice.dosha is None for choice in item.choices), item.id


def test_only_the_documented_official_weights_claim_to_be_official() -> None:
    """`official=True` means the mark is quoted from the CCRAS public preview.

    If this moves, someone has either found more published rules or mislabelled a guess as an
    official one - and the difference matters, because the README leans on the count.
    """

    rules = [
        (item.number, choice.value, choice.dosha)
        for item in prakriti.ITEMS
        for choice in item.choices
        if choice.official and choice.dosha
    ]
    assert len(rules) == 6, rules

    official = {item.id for item in prakriti.ITEMS if any(c.official for c in item.choices)}
    assert official == {
        "pk_veins",          # prominent tendons and veins, Vata = 1 mark
        "pk_eating_speed",   # fast eating Vata = 1, slow eating Kapha = 1
        "pk_indecisive",     # "Often" is Anavasthita atma, Vata = 1
        "pk_enmity",         # Dridhavairam, Kapha = 1
        "pk_polite",         # Vineeta, Kapha = 1
    }


# ------------------------------------------------------------------ scoring


def answer_everything(dosha: str) -> dict[str, str]:
    """Answer each item with its `dosha` option, or with one that scores nothing."""

    answers = {}
    for item in prakriti.ITEMS:
        choice = next(
            (c for c in item.choices if c.dosha == dosha),
            next((c for c in item.choices if c.dosha is None), None),
        )
        if choice is not None:
            answers[item.id] = choice.value
    return answers


@pytest.mark.parametrize(
    ("dosha", "expected"),
    [("vata", "Vataja"), ("pitta", "Pittaja"), ("kapha", "Kaphaja")],
)
def test_a_consistent_patient_gets_the_single_dosha_prakriti(dosha: str, expected: str) -> None:
    summary = prakriti.summarize(answer_everything(dosha))
    assert summary["prakriti"] == expected
    assert summary["doshas"] == [dosha]


@pytest.mark.parametrize(
    ("marks", "expected"),
    [
        ({"vata": 20, "pitta": 2, "kapha": 1}, "Vataja"),
        ({"vata": 1, "pitta": 20, "kapha": 2}, "Pittaja"),
        ({"vata": 2, "pitta": 1, "kapha": 20}, "Kaphaja"),
        ({"vata": 10, "pitta": 10, "kapha": 1}, "Vata-Pittaja"),
        ({"vata": 1, "pitta": 10, "kapha": 10}, "Pitta-Kaphaja"),
        ({"vata": 10, "pitta": 1, "kapha": 10}, "Vata-Kaphaja"),
        ({"vata": 7, "pitta": 7, "kapha": 7}, "Sama (tridoshaja)"),
    ],
)
def test_all_seven_prakriti_are_reachable(marks: dict[str, int], expected: str) -> None:
    """Seven, not ten. The ten-fold thing in Ayurveda is Dashavidha Pariksha - a different
    instrument, in ayurveda.py, asked at every visit."""

    doshas = prakriti.classify(marks)
    assert doshas is not None
    assert prakriti.PRAKRITI_NAMES[doshas]["en"] == expected


def test_seven_types_and_no_more() -> None:
    assert len(prakriti.PRAKRITI_NAMES) == 7


def test_too_few_answers_name_no_prakriti() -> None:
    """A constitution printed from four answers is worse than none: the vaidya cannot tell it is
    thin, and it is on the sheet forever."""

    # Answers that actually score, just too few of them. Taking the first four items instead
    # would take four demographic questions, which score nothing at all - that exercises the
    # zero-marks path and leaves the threshold itself untested.
    scoring = {
        item.id: choice.value
        for item in prakriti.ITEMS
        for choice in item.choices
        if choice.dosha == "vata"
    }
    thin = dict(list(scoring.items())[: prakriti.MIN_SCORED_ANSWERS - 1])
    assert len(thin) == prakriti.MIN_SCORED_ANSWERS - 1
    summary = prakriti.summarize(thin)
    assert summary["total_marks"] == prakriti.MIN_SCORED_ANSWERS - 1
    assert summary["prakriti"] is None
    assert summary["doshas"] == []
    assert "Insufficient" in summary["note"]

    # One more scoring answer is enough.
    enough = dict(list(scoring.items())[: prakriti.MIN_SCORED_ANSWERS])
    assert prakriti.summarize(enough)["prakriti"] == "Vataja"


def test_no_answers_at_all_names_no_prakriti() -> None:
    assert prakriti.summarize({})["prakriti"] is None
    assert prakriti.classify({"vata": 0, "pitta": 0, "kapha": 0}) is None


def test_the_summary_says_the_scoring_is_unreviewed() -> None:
    """The questions are the AYUSH instrument; the weights are a reconstruction of its scoring.

    Reporting that as a finished CCRAS Prakriti would be a clinical claim this code cannot make,
    so the flag and the note travel with every record.
    """

    summary = prakriti.summarize(answer_everything("pitta"))
    assert summary["scoring_reviewed"] is False
    assert "Provisional" in summary["note"]


def test_nothing_on_the_form_goes_unasked() -> None:
    """Every one of the 58 is put to the patient - none is silently dropped.

    Anything that ever cannot be asked has to be recorded in PENDING with a reason, so this
    failing means either the form grew or a question was quietly removed.
    """

    assert prakriti.PENDING == ()
    assert prakriti.coverage()["pending"] == 0


def test_the_summary_flags_which_answers_were_self_reported() -> None:
    """Sixteen items are observed or card-tested by a CCRAS assessor and self-reported here.

    They score like any other answer, so the only protection against reading a self-reported
    trait as an examination finding is that the record says which ones they were.
    """

    summary = prakriti.summarize(answer_everything("vata"))
    reported = summary["self_reported"]
    assert reported, "expected the observed and card-tested items to be flagged"
    assert {entry["number"] for entry in reported} == {
        item.number for item in prakriti.ITEMS if item.proxy
    }
    assert all(entry["instead_of"] for entry in reported)
    # Only what this patient actually answered.
    assert set(summary["self_reported"][0]) == {"number", "item", "instead_of"}
    assert prakriti.summarize({})["self_reported"] == []
    assert summary["pending_measurements"] == list(prakriti.MEASURED)


def test_every_proxy_names_what_it_stands_in_for() -> None:
    proxies = [item for item in prakriti.ITEMS if item.proxy]
    assert len(proxies) == 16
    assert all(item.proxy and item.proxy.strip() for item in proxies)


def test_unanswered_and_unknown_items_do_not_score() -> None:
    assert prakriti.tally({}) == {"vata": 0, "pitta": 0, "kapha": 0}
    assert prakriti.tally({"pk_not_a_question": "yes"}) == {"vata": 0, "pitta": 0, "kapha": 0}


def test_validate_rejects_answers_the_form_does_not_offer() -> None:
    assert prakriti.validate("pk_sleep_hours", "under_6").id == "pk_sleep_hours"
    with pytest.raises(ValueError):
        prakriti.validate("pk_sleep_hours", "nine")
    with pytest.raises(ValueError):
        prakriti.validate("pk_nonsense", "under_6")


def test_asking_walks_every_item_once_then_stops() -> None:
    answers: dict[str, str] = {}
    seen = []
    while (item := prakriti.next_item(answers)) is not None:
        seen.append(item.id)
        answers[item.id] = item.choices[0].value
    assert seen == [item.id for item in prakriti.ITEMS]
    assert len(seen) == len(set(seen))


# ------------------------------------------------------------------ once in a lifetime


def store(tmp_path) -> EncryptedSessionStore:
    return EncryptedSessionStore(tmp_path / "kiosk.db", Fernet.generate_key().decode())


def test_a_prakriti_survives_to_the_next_visit(tmp_path) -> None:
    saved = store(tmp_path)
    assert saved.load_prakriti(ABHA) is None
    saved.save_prakriti(ABHA, prakriti.summarize(answer_everything("kapha")))
    assert saved.load_prakriti(ABHA)["prakriti"] == "Kaphaja"


def test_one_patients_prakriti_is_not_served_to_another(tmp_path) -> None:
    saved = store(tmp_path)
    saved.save_prakriti(ABHA, {"prakriti": "Vataja"})
    assert saved.load_prakriti("99999999999999") is None


def test_the_abha_number_is_not_written_to_disk(tmp_path) -> None:
    """The row has to be findable by ABHA, so its key cannot be random - but a health ID sitting
    in a primary key would defeat the point of an encrypted store."""

    path = tmp_path / "kiosk.db"
    saved = EncryptedSessionStore(path, Fernet.generate_key().decode())
    saved.save_prakriti(ABHA, {"prakriti": "Vataja"})
    raw = path.read_bytes()
    assert ABHA.encode() not in raw
    assert b"Vataja" not in raw


def test_a_reopened_store_still_finds_the_record(tmp_path) -> None:
    """The lookup key is derived from the encryption key, so it has to be stable across restarts -
    a kiosk that forgets every Prakriti on reboot is not once in a lifetime."""

    path, key = tmp_path / "kiosk.db", Fernet.generate_key().decode()
    EncryptedSessionStore(path, key).save_prakriti(ABHA, {"prakriti": "Pittaja"})
    assert EncryptedSessionStore(path, key).load_prakriti(ABHA)["prakriti"] == "Pittaja"


def test_answering_again_replaces_rather_than_duplicates(tmp_path) -> None:
    saved = store(tmp_path)
    saved.save_prakriti(ABHA, {"prakriti": "Vataja"})
    saved.save_prakriti(ABHA, {"prakriti": "Pittaja"})
    assert saved.load_prakriti(ABHA)["prakriti"] == "Pittaja"


def test_the_record_is_stamped_with_when_it_was_taken(tmp_path) -> None:
    """The sheet has to be able to say "recorded in 2023", because that is what justifies not
    asking again."""

    saved = store(tmp_path)
    saved.save_prakriti(ABHA, {"prakriti": "Vataja"})
    assert saved.load_prakriti(ABHA)["recorded_at"]
