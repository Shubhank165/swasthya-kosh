"""The hospital picker — 2/3 §5 screen 2, §12.

**Unauthenticated.** It is the list a patient chooses from before they have
anything to authenticate as, and it holds no patient data: a hospital's name,
location, timezone and department list are what a signboard outside the building
already says.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import HospitalRepoDep
from app.schemas.api import DepartmentOut, HospitalListResponse, HospitalOut

router = APIRouter(prefix="/hospitals", tags=["hospitals"])

#: Department codes are stored as slugs. Rendering them is the app's job in
#: every language it speaks, so what travels is the code plus a plain English
#: display for a client that has no string for it yet — never a translation
#: invented here.
#: Every entry carries a gloss where the bare name would not be enough, and
#: none where it already is. Three-with-help and one-without reads as
#: unfinished, and the one left bare is the one a patient who does not know the
#: word most needs help with.
#:
#: General specialties, named as the board outside the OPD names them. A patient
#: is looking for the word that matches the sign they walked past, so the codes
#: are slugs of the English specialty rather than anything a clinician would
#: only recognise in a textbook.
_DISPLAY = {
    "general_medicine": "General Medicine",
    "orthopaedics": "Orthopaedics (bones and joints)",
    "paediatrics": "Paediatrics (children)",
    "ent": "ENT (ear, nose and throat)",
    "obstetrics_gynaecology": "Obstetrics and Gynaecology",
    "dermatology": "Dermatology (skin)",
    "ophthalmology": "Ophthalmology (eyes)",
    "cardiology": "Cardiology (heart)",
    # Not a department a patient recognises — an escape hatch for one who does
    # not know where to go, which is what this code has always been. Named as
    # what it is: a bare "General" sitting next to "General Medicine" gives a
    # patient two options that read almost identically, and the patient who
    # cannot tell them apart is the one who most needed guiding.
    #
    # The code stays `general` rather than becoming `unsure`: it is what every
    # stored intake is already filed under and what the app and kiosk both
    # send. The similarity to `general_medicine` is a reader's problem, not a
    # patient's, and this comment is the fix for it.
    "general": "Not sure — the staff will guide me",
}


@router.get(
    "",
    response_model=HospitalListResponse,
    summary="Hospitals a patient can submit an intake to",
)
async def hospitals(repository: HospitalRepoDep) -> HospitalListResponse:
    """Active hospitals only.

    A deactivated hospital stays in the database — its intakes and reports must
    remain readable — but it is not offered to a patient about to travel there.
    """
    rows = await repository.all()
    return HospitalListResponse(
        hospitals=[
            HospitalOut(
                hospital_id=row.id,
                display_name=row.display_name,
                location=row.location,
                timezone=row.timezone,
                default_language=row.default_language,
                departments=[
                    DepartmentOut(code=code, display=_DISPLAY.get(code, code))
                    for code in (row.departments or [])
                ],
            )
            for row in rows
            if row.active
        ]
    )
