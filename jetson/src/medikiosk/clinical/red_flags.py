from medikiosk.models import PatientState, RedFlagAlert, Urgency


def evaluate_red_flags(state: PatientState) -> list[RedFlagAlert]:
    """Deterministic, auditable screening rules. No LLM may suppress these alerts."""

    alerts: list[RedFlagAlert] = []

    if state.altered_consciousness is True:
        alerts.append(
            RedFlagAlert(
                rule_id="RF_ALTERED_CONSCIOUSNESS",
                urgency=Urgency.EMERGENCY,
                message="Altered consciousness reported; alert clinical staff immediately.",
                evidence=["altered_consciousness=true"],
            )
        )

    if state.active_bleeding is True:
        alerts.append(
            RedFlagAlert(
                rule_id="RF_ACTIVE_BLEEDING",
                urgency=Urgency.EMERGENCY,
                message="Active bleeding reported; alert clinical staff immediately.",
                evidence=["active_bleeding=true"],
            )
        )

    if state.one_sided_weakness is True or state.speech_difficulty is True:
        evidence = []
        if state.one_sided_weakness is True:
            evidence.append("one_sided_weakness=true")
        if state.speech_difficulty is True:
            evidence.append("speech_difficulty=true")
        alerts.append(
            RedFlagAlert(
                rule_id="RF_POSSIBLE_STROKE",
                urgency=Urgency.EMERGENCY,
                message="Possible stroke symptom reported; alert clinical staff immediately.",
                evidence=evidence,
            )
        )

    chest_pain = state.chest_pain is True or (
        state.complaint is not None and "chest pain" in state.complaint.lower()
    )
    chest_associated = [
        name
        for name, value in (
            ("breathlessness", state.breathlessness),
            ("pain_radiation", state.pain_radiation),
            ("sweating", state.sweating),
        )
        if value is True
    ]
    if chest_pain and chest_associated:
        alerts.append(
            RedFlagAlert(
                rule_id="RF_CHEST_PAIN_ASSOCIATED",
                urgency=Urgency.EMERGENCY,
                message="Chest pain with an associated warning symptom; alert staff immediately.",
                evidence=["chest_pain=true", *[f"{name}=true" for name in chest_associated]],
            )
        )

    if state.breathlessness is True and (state.severity or 0) >= 7:
        alerts.append(
            RedFlagAlert(
                rule_id="RF_SEVERE_BREATHLESSNESS",
                urgency=Urgency.EMERGENCY,
                message="Severe breathing difficulty reported; alert clinical staff immediately.",
                evidence=["breathlessness=true", f"severity={state.severity}"],
            )
        )

    abdominal_pain = state.complaint is not None and any(
        term in state.complaint.lower() for term in ("abdominal", "stomach", "belly")
    )
    if abdominal_pain and (state.severity or 0) >= 8 and state.vomiting is True:
        alerts.append(
            RedFlagAlert(
                rule_id="RF_SEVERE_ABDOMINAL_PAIN_VOMITING",
                urgency=Urgency.URGENT,
                message="Severe abdominal pain with vomiting; request prompt clinical review.",
                evidence=["abdominal_pain=true", f"severity={state.severity}", "vomiting=true"],
            )
        )

    return _deduplicate(alerts)


def _deduplicate(alerts: list[RedFlagAlert]) -> list[RedFlagAlert]:
    seen: set[str] = set()
    result: list[RedFlagAlert] = []
    for alert in alerts:
        if alert.rule_id not in seen:
            seen.add(alert.rule_id)
            result.append(alert)
    return result
