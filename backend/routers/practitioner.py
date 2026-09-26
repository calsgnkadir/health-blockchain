"""
backend/routers/practitioner.py — the practitioner's own client list
====================================================================
A practitioner used to reach a client's file by typing a client ID. This
endpoint lists the clients they may actually work with, so the dashboard can
offer them instead.

A client appears here only if:
  * they have given this practitioner an active consent, or
  * this practitioner invited them (so they can see whether the client joined).

Nobody else's clients are listed. The list shows who the clients are and what
consent they gave — never record content, which still goes through the record
endpoints and the access policy (ADR-0003).
"""

from fastapi import APIRouter, Depends

from backend.dependencies import require_role, get_consent_validator
from backend.routers.onboarding import invitations_by
from core.services.consent_validator import ConsentValidator
from infrastructure.repositories.sql_repositories import SQLUserRepository

router = APIRouter(prefix="/api/v1/practitioner", tags=["practitioner"])


def clients_of(practitioner: str, consent_validator: ConsentValidator) -> list:
    """The clients this practitioner works with: those who gave them an active
    consent, and those they invited. Also the rule the appointment book uses to
    decide whom a practitioner (or their secretary) may book."""
    invited = {i["patient_id"]: i for i in invitations_by(practitioner)}

    clients = []
    for user in SQLUserRepository().load_all_users():
        if user.role != "client" or not user.patient_id or user.account_status == "DISABLED":
            continue
        consents = consent_validator.active_consents(user.patient_id, practitioner)
        invitation = invited.get(user.patient_id)
        if not consents and not invitation:
            continue   # not this practitioner's client

        if consents:
            status = "consented"
        elif invitation["status"] == "active":
            status = "waiting_for_consent"   # joined, but has not given consent yet
        else:
            status = "invited"               # has not used the invitation yet
        clients.append({
            "patient_id": user.patient_id,
            "full_name": user.full_name,
            "status": status,
            "invitation_status": invitation["status"] if invitation else None,
            "consent_types": sorted(c.get("record_type", "") for c in consents),
            # The file closes when the last consent runs out.
            "consent_expires_at": max((c.get("expiry_timestamp", 0) for c in consents), default=None),
        })

    # Clients the practitioner can open first, then by client ID.
    clients.sort(key=lambda c: (c["status"] != "consented", c["patient_id"]))
    return clients


@router.get("/clients", summary="My clients (practitioner)")
def my_clients(
    u: dict = Depends(require_role("practitioner")),
    consent_validator: ConsentValidator = Depends(get_consent_validator),
):
    return {"clients": clients_of(u["username"], consent_validator)}
