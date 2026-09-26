"""
backend/routers/invoices.py — session invoices
==============================================
A practitioner or their secretary invoices a completed session; a client sees
and prints their own invoices. The rules live in core/services/invoicing.py.
Access follows the appointment book: a practitioner's book, or a client's own.
"""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import current_user
from backend.routers.appointments import _book_owner
from backend.schemas.requests import IssueInvoiceReq
from core.events.event_bus import SystemAuditEvent, event_bus
from core.security import get_device_id
from core.services import appointment_book, invoicing
from infrastructure.repositories.sql_repositories import SQLUserRepository

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])


def _money(kurus: int) -> str:
    return f"{Decimal(kurus) / 100:.2f}"


def _view(inv: dict) -> dict:
    return {
        "id": inv["id"],
        "number": inv["number"],
        "appointment_id": inv["appointment_id"],
        "patient_id": inv["patient_id"],
        "client_name": inv["client_name"],
        "practitioner_name": inv["practitioner_name"],
        "practice_name": inv["practice_name"],
        "service": invoicing.SERVICE_LINE,
        "session_date": datetime.fromtimestamp(inv["session_date"], tz=timezone.utc).isoformat(),
        "duration_min": inv["duration_min"],
        "net_amount": _money(inv["net_kurus"]),
        "vat_rate": inv["vat_rate"],
        "vat_amount": _money(inv["vat_kurus"]),
        "total_amount": _money(inv["total_kurus"]),
        "currency": "TRY",
        "issued_at": datetime.fromtimestamp(inv["issued_at"], tz=timezone.utc).isoformat(),
    }


def _may_see(u: dict, inv: dict) -> bool:
    if u["role"] == "client":
        return inv["patient_id"] == u.get("patient_id")
    return inv["practitioner_username"] == _book_owner(u)


@router.get("", summary="Invoices (own book, or a client's own)")
def list_invoices(u: dict = Depends(current_user)):
    if u["role"] == "client":
        items = invoicing.list_invoices(patient_id=u.get("patient_id"))
    else:
        items = invoicing.list_invoices(practitioner=_book_owner(u))
    return {"invoices": [_view(i) for i in items]}


@router.get("/{invoice_id}", summary="One invoice")
def get_invoice(invoice_id: str, u: dict = Depends(current_user)):
    inv = invoicing.get(invoice_id)
    if inv is None or not _may_see(u, inv):
        raise HTTPException(404, "Invoice not found")
    return {"invoice": _view(inv)}


@router.post("", summary="Invoice a completed session")
def issue_invoice(req: IssueInvoiceReq, u: dict = Depends(current_user)):
    owner = _book_owner(u)   # a practitioner or their secretary; others get 403
    appointment = appointment_book.get(req.appointment_id)
    if appointment is None or appointment["practitioner_username"] != owner:
        raise HTTPException(404, "Appointment not found")

    repo = SQLUserRepository()
    practitioner = repo.load_user(owner)
    client_name = next((c.full_name for c in repo.load_all_users()
                        if c.role == "client" and c.patient_id == appointment["patient_id"]),
                       appointment["patient_id"])
    try:
        inv = invoicing.issue(
            appointment,
            net_kurus=int(req.net_amount * 100),
            vat_rate=req.vat_rate,
            issued_by=u["username"],
            client_name=client_name,
            practitioner_name=practitioner.full_name if practitioner else owner,
            practice_name=practitioner.institution if practitioner else None,
        )
    except invoicing.InvoiceError as e:
        raise HTTPException(e.status, str(e))

    event_bus.publish(SystemAuditEvent(
        project_name="__system__", action="INVOICE_ISSUED", username=u["username"],
        device_id=get_device_id(), extra={"invoice": inv["number"], "appointment_id": inv["appointment_id"]},
    ))
    return {"invoice": _view(inv)}
