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
_DISPLAY = {
    "kayachikitsa": "Kayachikitsa (General medicine)",
    "panchakarma": "Panchakarma",
    "shalya": "Shalya (Surgery)",
    "shalakya": "Shalakya (ENT and Ophthalmology)",
    "prasuti": "Prasuti and Stri Roga",
    "kaumarbhritya": "Kaumarbhritya (Paediatrics)",
    "swasthavritta": "Swasthavritta (Preventive medicine)",
    "general": "General",
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
