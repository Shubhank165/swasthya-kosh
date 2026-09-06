"""The slot registry, built from `clinical/questioning/slots.yaml`.

The expansion is the interesting part: `symptom_template` is written once and
becomes `<domain>.<id>` for every domain, minus whatever `skip` excludes. Ten
template slots across fourteen domains is 140 slots from ten pieces of clinical
judgement, and changing one changes all of them — which is the point. Writing
them out per domain would be the same judgement copied fourteen times, drifting
apart the first time somebody edited one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.questioning_agent.core.enums import DataType
from app.questioning_agent.core.schemas import InformationSlot


class ContentError(Exception):
    """A content file the engine refuses to load.

    Fatal rather than skipped. A slot that failed to parse is a question that is
    never asked and a hole in every case summary afterwards, and neither is
    visible at runtime.
    """


@dataclass(frozen=True, slots=True)
class Domain:
    id: str
    label_key: str
    priority: int


class SlotRegistry:
    """Every slot the case can hold, and the domains they hang off."""

    def __init__(
        self, slots: dict[str, InformationSlot], domains: dict[str, Domain]
    ) -> None:
        self._slots = slots
        self._domains = domains

    # --- reading -------------------------------------------------------------

    def __contains__(self, slot_id: object) -> bool:
        return slot_id in self._slots

    def __len__(self) -> int:
        return len(self._slots)

    def get(self, slot_id: str) -> InformationSlot | None:
        return self._slots.get(slot_id)

    def require(self, slot_id: str) -> InformationSlot:
        slot = self._slots.get(slot_id)
        if slot is None:
            raise ContentError(f"unknown slot {slot_id!r}")
        return slot

    @property
    def all(self) -> tuple[InformationSlot, ...]:
        return tuple(self._slots.values())

    @property
    def domains(self) -> tuple[Domain, ...]:
        return tuple(self._domains.values())

    def domain(self, domain_id: str) -> Domain | None:
        return self._domains.get(domain_id)

    def for_domain(self, domain_id: str) -> tuple[InformationSlot, ...]:
        return tuple(s for s in self._slots.values() if s.domain == domain_id)

    def askable(self) -> tuple[InformationSlot, ...]:
        """Slots the engine may ever ask about.

        Excludes the clinician-assessed ones. They are in the registry so the
        case summary has somewhere to put them; they are not questions.
        """
        return tuple(s for s in self._slots.values() if s.patient_observable)

    def required(self) -> tuple[InformationSlot, ...]:
        """The floor. Asked whatever the patient came in with."""
        return tuple(s for s in self._slots.values() if s.required and s.patient_observable)

    # --- loading -------------------------------------------------------------

    @classmethod
    def load(cls, directory: Path) -> SlotRegistry:
        domains = _load_domains(directory / "domains.yaml")
        slots = _load_slots(directory / "slots.yaml", domains)
        return cls(slots, domains)


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContentError(f"{path} does not exist")
    try:
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError(f"{path}: {exc}") from exc
    if not isinstance(body, dict):
        raise ContentError(f"{path}: expected a mapping at the top level")
    return body


def _load_domains(path: Path) -> dict[str, Domain]:
    body = _read(path)
    domains: dict[str, Domain] = {}
    for entry in body.get("domains") or []:
        if not isinstance(entry, dict) or not entry.get("id"):
            raise ContentError(f"{path}: a domain has no id")
        domain_id = str(entry["id"])
        if domain_id in domains:
            raise ContentError(f"{path}: domain {domain_id!r} is defined twice")
        domains[domain_id] = Domain(
            id=domain_id,
            label_key=str(entry.get("label_key") or f"domain.{domain_id}"),
            priority=int(entry.get("priority", 5)),
        )
    if not domains:
        raise ContentError(f"{path}: no domains")
    return domains


def _load_slots(path: Path, domains: dict[str, Domain]) -> dict[str, InformationSlot]:
    body = _read(path)
    slots: dict[str, InformationSlot] = {}

    def add(slot: InformationSlot) -> None:
        if slot.id in slots:
            raise ContentError(f"{path}: slot {slot.id!r} is defined twice")
        slots[slot.id] = slot

    # 1. The template, expanded across every domain.
    skip: dict[str, set[str]] = {
        str(domain): {str(s) for s in entries or []}
        for domain, entries in (body.get("skip") or {}).items()
    }
    for unknown in set(skip) - set(domains):
        raise ContentError(f"{path}: `skip` names domain {unknown!r}, which does not exist")

    template = body.get("symptom_template") or []
    for domain_id in domains:
        for entry in template:
            local = str(entry["id"])
            if local in skip.get(domain_id, set()):
                continue
            add(_slot(entry, path, slot_id=f"{domain_id}.{local}", domain=domain_id))

    # 2. What individual domains add on top.
    for domain_id, entries in (body.get("domain_slots") or {}).items():
        if domain_id not in domains:
            raise ContentError(f"{path}: domain_slots names {domain_id!r}, which does not exist")
        for entry in entries or []:
            add(
                _slot(
                    entry,
                    path,
                    slot_id=f"{domain_id}.{entry['id']}",
                    domain=str(domain_id),
                )
            )

    # 3. The flat sections. Their ids are already fully qualified, and the
    #    domain is the prefix — `general`, `ayush`, `assessment`.
    for section, observable in (
        ("general", True),
        ("ayush", True),
        ("clinician_assessed", False),
    ):
        for entry in body.get(section) or []:
            slot_id = str(entry["id"])
            if "." not in slot_id:
                raise ContentError(f"{path}: {section} slot {slot_id!r} needs a domain prefix")
            add(
                _slot(
                    entry,
                    path,
                    slot_id=slot_id,
                    domain=slot_id.split(".", 1)[0],
                    patient_observable=observable,
                )
            )

    if not slots:
        raise ContentError(f"{path}: no slots")
    return slots


def _slot(
    entry: Any,
    path: Path,
    *,
    slot_id: str,
    domain: str,
    patient_observable: bool = True,
) -> InformationSlot:
    if not isinstance(entry, dict):
        raise ContentError(f"{path}: {slot_id} is not a mapping")
    try:
        data_type = DataType(str(entry["data_type"]))
    except (KeyError, ValueError) as exc:
        raise ContentError(f"{path}: {slot_id} has no usable data_type") from exc

    try:
        return InformationSlot(
            id=slot_id,
            domain=domain,
            description=str(entry["description"]),
            data_type=data_type,
            patient_observable=patient_observable,
            priority=int(entry.get("priority", 5)),
            applicable_domains=(domain,),
            required=bool(entry.get("required", False)),
            allowed_values=tuple(str(v) for v in entry.get("allowed_values") or ()),
        )
    except Exception as exc:  # pydantic validation, KeyError on description
        raise ContentError(f"{path}: {slot_id}: {exc}") from exc


__all__ = ["ContentError", "Domain", "SlotRegistry"]
