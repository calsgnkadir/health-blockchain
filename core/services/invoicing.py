"""
core/services/invoicing.py — invoices for completed sessions
============================================================
One invoice per completed appointment, numbered per practitioner and year
(2026-0001, 2026-0002, ...). What an invoice says is fixed when it is issued:
names are copied in, and it is never edited afterwards.

What an invoice deliberately does not hold:
  * anything clinical — the service line is a fixed text, there is no free-text
    field, so a diagnosis or a note cannot end up on a document that leaves the
    practice;
  * payment state — Mahrem issues invoices, it does not track payments.

Money is integer kuruş (1 TRY = 100 kuruş). Floats never touch an amount.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from database.sql_db import get_sql_db
from infrastructure.repositories.sql_repositories import _to_placeholder

VAT_RATES = (0, 1, 10, 20)                 # the Turkish VAT rates, in percent
MAX_NET_KURUS = 1_000_000 * 100            # 1,000,000 TRY for one session is surely a typo
SERVICE_LINE = "Psychological counselling session"
TURKEY = timezone(timedelta(hours=3))      # invoice years follow the practice's calendar

_COLUMNS = ("id", "number", "invoice_year", "sequence", "appointment_id", "practitioner_username",
            "patient_id", "client_name", "practitioner_name", "practice_name", "session_date",
            "duration_min", "net_kurus", "vat_rate", "vat_kurus", "total_kurus", "issued_by", "issued_at")
_SELECT = ("SELECT id, number, invoice_year, sequence, appointment_id, practitioner_username, "
           "patient_id, client_name, practitioner_name, practice_name, session_date, duration_min, "
           "net_kurus, vat_rate, vat_kurus, total_kurus, issued_by, issued_at FROM invoices")
_INSERT = ("INSERT INTO invoices (id, number, invoice_year, sequence, appointment_id, "
           "practitioner_username, patient_id, client_name, practitioner_name, practice_name, "
           "session_date, duration_min, net_kurus, vat_rate, vat_kurus, total_kurus, issued_by, issued_at) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")


class InvoiceError(ValueError):
    """A request invoicing refuses; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _run(sql: str, params: tuple = (), fetch: str = "") -> list:
    db = get_sql_db()
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(_to_placeholder(sql), params)
        rows = cur.fetchall() if fetch == "all" else ([cur.fetchone()] if fetch == "one" else [])
        conn.commit()
        return rows
    finally:
        cur.close()
        conn.close()


def _row(row) -> Optional[dict]:
    return {col: row[i] for i, col in enumerate(_COLUMNS)} if row else None


def vat_of(net_kurus: int, vat_rate: int) -> int:
    """VAT in kuruş, rounded half up, in integers only."""
    return (net_kurus * vat_rate + 50) // 100


# ── Reading ───────────────────────────────────────────────────
def get(invoice_id: str) -> Optional[dict]:
    rows = _run(_SELECT + " WHERE id = ?", (invoice_id,), fetch="one")
    return _row(rows[0]) if rows else None


def for_appointment(appointment_id: str) -> Optional[dict]:
    rows = _run(_SELECT + " WHERE appointment_id = ?", (appointment_id,), fetch="one")
    return _row(rows[0]) if rows else None


def list_invoices(*, practitioner: Optional[str] = None, patient_id: Optional[str] = None) -> list:
    """One practitioner's invoices or one client's — never unscoped."""
    if not practitioner and not patient_id:
        raise ValueError("an invoice list must be scoped to a practitioner or a client")
    rows = _run(_SELECT + " WHERE (? IS NULL OR practitioner_username = ?) AND (? IS NULL OR patient_id = ?)"
                " ORDER BY issued_at DESC",
                (practitioner, practitioner, patient_id, patient_id), fetch="all")
    return [_row(r) for r in rows]


# ── Issuing ───────────────────────────────────────────────────
def issue(appointment: dict, *, net_kurus: int, vat_rate: int, issued_by: str,
          client_name: str, practitioner_name: str, practice_name: Optional[str]) -> dict:
    if appointment["status"] != "completed":
        raise InvoiceError("Only a completed session can be invoiced", status=409)
    if for_appointment(appointment["id"]):
        raise InvoiceError("This session has already been invoiced", status=409)
    if vat_rate not in VAT_RATES:
        raise InvoiceError(f"VAT rate must be one of {VAT_RATES}")
    if not 0 < net_kurus <= MAX_NET_KURUS:
        raise InvoiceError("The amount must be above zero and at most 1,000,000 TRY")

    now = time.time()
    year = datetime.fromtimestamp(now, tz=TURKEY).year
    practitioner = appointment["practitioner_username"]
    rows = _run("SELECT MAX(sequence) FROM invoices WHERE practitioner_username = ? AND invoice_year = ?",
                (practitioner, year), fetch="one")
    sequence = ((rows[0][0] if rows and rows[0] else None) or 0) + 1
    vat_kurus = vat_of(net_kurus, vat_rate)
    invoice_id = f"INV-{uuid.uuid4().hex[:12].upper()}"
    # The UNIQUE constraints (appointment; practitioner + year + sequence) are
    # the last line of defence against a double invoice or a reused number.
    _run(_INSERT, (invoice_id, f"{year}-{sequence:04d}", year, sequence, appointment["id"],
                   practitioner, appointment["patient_id"], client_name, practitioner_name, practice_name,
                   appointment["starts_at"], appointment["duration_min"], net_kurus, vat_rate,
                   vat_kurus, net_kurus + vat_kurus, issued_by, now))
    return get(invoice_id)
