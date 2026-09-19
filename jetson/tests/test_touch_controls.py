"""Touch controls for quantity questions, and the two defects that shipped without these.

Both failures this file catches were real, were reviewed, and both compiled cleanly — which is
why neither a syntax check nor a type check would have found them.

**A dead key.** `TOUCH_CONTROLS` is keyed by question id, and this repo carries two question banks:
the kiosk's own bare ids (`ask_age`) in `clinical/questions.py`, and the phone app's dotted ids
(`history.age`) in the vendored `questioning_agent` bundle. Only the first reaches `flow.screen`.
A table keyed by the second is valid Python that never fires, and nothing at runtime says so.

**A lost class body.** The first version of this feature inserted the table at column 0 inside the
`KioskFlow` class. Python ended the class there and swallowed the fourteen methods below it into
the function that followed, after its `return`. `KioskFlow.screen` stopped existing. It parsed.
"""

from __future__ import annotations

import ast
from pathlib import Path

FLOW = Path(__file__).resolve().parents[1] / "src" / "medikiosk" / "kiosk" / "flow.py"


def _module() -> ast.Module:
    return ast.parse(FLOW.read_text(encoding="utf-8"))


def _kiosk_flow_methods() -> list[str]:
    for node in _module().body:
        if isinstance(node, ast.ClassDef) and node.name == "KioskFlow":
            return [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
    raise AssertionError("KioskFlow is not a module-level class any more")


def _touch_controls() -> dict:
    for node in _module().body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "TOUCH_CONTROLS":
            return ast.literal_eval(node.value)
    raise AssertionError("TOUCH_CONTROLS is not defined at module level")


def test_kiosk_flow_still_owns_its_methods() -> None:
    """The class body is intact.

    Asserted by name rather than by count so the failure says which method went missing, and so
    adding a method does not fail the test that exists to catch losing fifteen.
    """
    methods = _kiosk_flow_methods()
    for required in ("screen", "_screen", "action", "choose_language", "set_who", "finish"):
        assert required in methods, f"KioskFlow lost {required}() — check for a dedent in the class body"


def test_no_method_is_stranded_inside_a_module_function() -> None:
    """Nothing below the class got adopted by a module-level function.

    The signature of the dedent bug: a plain function suddenly containing a dozen `self` methods
    that can never be called.
    """
    for node in _module().body:
        if isinstance(node, ast.FunctionDef):
            nested = [n for n in ast.walk(node) if isinstance(n, ast.FunctionDef) and n is not node]
            takes_self = [n.name for n in nested if n.args.args and n.args.args[0].arg == "self"]
            assert not takes_self, (
                f"{node.name}() contains methods {takes_self} — a class body probably ended early"
            )


def test_every_control_names_a_question_the_kiosk_actually_asks() -> None:
    """No dead keys.

    `registration.<key>` ids are built in `flow._screen`; clinical ids come from `QUESTIONS`.
    An id from the phone app's bundle passes every other check and simply never fires.
    """
    from medikiosk.clinical.questions import QUESTIONS

    reachable = {f"registration.{key}" for key in ("name", "age", "gender")} | set(QUESTIONS)
    for question_id in _touch_controls():
        assert question_id in reachable, (
            f"{question_id!r} is not a question this kiosk emits — the dotted ids belong to the "
            "phone app's bundle, not clinical/questions.py"
        )


def test_controls_declare_a_usable_range() -> None:
    """A stepper with a bad range is worse than a text box: it offers impossible answers, or makes
    a patient press + ninety times."""
    for question_id, control in _touch_controls().items():
        assert control["type"] in {"stepper", "scale"}, question_id
        if control["type"] != "stepper":
            continue
        low, high, step = control["min"], control["max"], control["step"]
        assert low < high, f"{question_id}: min must be below max"
        assert step > 0, f"{question_id}: step must be positive"
        initial = control.get("initial", low)
        assert low <= initial <= high, f"{question_id}: initial sits outside the range"
        presses = (high - low) / step
        assert presses <= 200, f"{question_id}: {presses:.0f} presses to cross the range"


def test_controls_do_not_duplicate_an_existing_answer_ui() -> None:
    """`ANSWER_UI` is the general mechanism and already routes severity to faces and age to bands.
    A control that shadows one of those is both redundant and usually worse for the patient."""
    from medikiosk.clinical.questions import ANSWER_UI

    for question_id in _touch_controls():
        assert question_id not in ANSWER_UI, (
            f"{question_id} already has an answer_ui ({ANSWER_UI.get(question_id)!r}); "
            "extend ANSWER_UI rather than adding a second table"
        )
