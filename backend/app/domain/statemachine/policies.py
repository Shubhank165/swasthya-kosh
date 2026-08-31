"""Selection policy — the small set of knobs the state machine is allowed to have.

Everything here is configuration a hospital can set. None of it is a decision a
model gets to make at runtime, and none of it can cause a required field to be
skipped: `max_optional_fields` bounds optional questions only, and there is
deliberately no "stop after N questions" that could end an incomplete history.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    """How the engine chooses the next question."""

    #: Ask non-required pathway fields once every required field is settled.
    ask_optional_fields: bool = True
    #: Upper bound on optional questions per session. Required fields ignore it.
    max_optional_fields: int = 12
    #: Ask the Ayurveda module when the intake enables it.
    ayurveda_module_enabled: bool = True
    #: Ask review-of-systems groups declared by the active pathway.
    review_of_systems_enabled: bool = True
    #: Re-confirm prior-record facts rather than asking open questions about them.
    confirm_prior_records: bool = True
    #: Prompt for documents even when the patient brought none.
    always_offer_documents: bool = True
    #: Languages the kiosk renders. First entry is the fallback.
    supported_languages: tuple[str, ...] = field(default_factory=lambda: ("en", "hi"))

    def fallback_language(self) -> str:
        return self.supported_languages[0] if self.supported_languages else "en"

    def resolve_language(self, requested: str | None) -> str:
        """Closest supported language to the one requested."""
        if requested is None:
            return self.fallback_language()
        if requested in self.supported_languages:
            return requested
        base = requested.split("-")[0]
        for supported in self.supported_languages:
            if supported.split("-")[0] == base:
                return supported
        return self.fallback_language()


DEFAULT_POLICY = SelectionPolicy()
