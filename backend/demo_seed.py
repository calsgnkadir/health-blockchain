"""
backend/demo_seed.py — Demonstration file for the bundled demo client
====================================================================
A freshly cloned vault starts with an empty chain, so every screen renders as an
empty state — the running application looks broken rather than idle.

This module writes a small, clinically coherent therapy file for the demo client
(a CBT course for anxiety) so a first run shows the system doing its job. It only
ever runs alongside the demo accounts (development or VHV_DEMO_MODE), and only
when the client has no records yet, so it can never touch a real deployment or
overwrite a real chain.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import List

DEMO_PATIENT_ID = "VIP-001"
DEMO_DOCTOR = "dr.smith"

# Documented in the README and shown on the login screen's demo panel.
DEMO_RECORD_PASSWORD = "DemoRecord@2026!"

_DOCTOR_NAME = "Uzm. Psk. Elif Yılmaz"
_INSTITUTION = "Mahrem Psychology Practice"


def _day(offset: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=offset)).strftime("%Y-%m-%d")


def _record(record_type: str, title: str, data: dict, days_ago: int,
            access_level: str = "doctor_shared", notes: str = "") -> dict:
    from backend.schemas.requests import RECORD_TYPES
    return {
        "record_type":       record_type,
        "record_type_label": RECORD_TYPES[record_type],
        "title":             title,
        "doctor_name":       _DOCTOR_NAME,
        "institution":       _INSTITUTION,
        "record_date":       _day(days_ago),
        "access_level":      access_level,
        "is_confidential":   False,
        "data":              data,
        "notes":             notes,
        "created_by":        DEMO_DOCTOR,
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "patient_id":        DEMO_PATIENT_ID,
        "file_name":         None,
        "file_type":         None,
        "file_data":         None,
    }


def _demo_chart() -> List[dict]:
    """Five weeks of a CBT course for anxiety. The GAD-7 score (max 21) falls
    from 16 to 7, so the file shows the therapy working."""
    return [
        _record("consent_form", "KVKK explicit consent & therapy agreement", {
            "form_type": "KVKK explicit consent + therapy agreement",
            "signed_date": _day(35),
        }, days_ago=35),

        _record("assessment", "Intake GAD-7", {
            "instrument": "GAD-7", "score": "16", "max_score": "21",
            "interpretation": "Severe anxiety",
        }, days_ago=35, notes="Frequent panic episodes on the morning commute."),

        _record("treatment_plan", "CBT plan for panic and generalised anxiety", {
            "goals": "Fewer panic episodes; commute to work without avoidance",
            "approach": "Cognitive Behavioural Therapy (CBT)",
            "planned_sessions": "12",
        }, days_ago=34),

        _record("session_note", "Session 1 — psychoeducation", {
            "session_number": "1", "duration_min": "50", "session_format": "In-person",
            "summary": "Explained the anxiety cycle; practised paced breathing.",
        }, days_ago=28),

        _record("homework", "Daily thought record", {
            "task": "Write down 3 anxious thoughts a day and the evidence for and against each.",
            "due_date": _day(21),
        }, days_ago=28),

        _record("session_note", "Session 2 — cognitive restructuring", {
            "session_number": "2", "duration_min": "50", "session_format": "In-person",
            "summary": "Reviewed the thought record; challenged catastrophic predictions.",
        }, days_ago=21),

        _record("assessment", "Follow-up GAD-7", {
            "instrument": "GAD-7", "score": "11", "max_score": "21",
            "interpretation": "Moderate anxiety",
        }, days_ago=14),

        _record("session_note", "Session 3 — graded exposure", {
            "session_number": "3", "duration_min": "50", "session_format": "Online",
            "summary": "Built an exposure ladder for the commute; first step agreed.",
        }, days_ago=14),

        _record("assessment", "Follow-up GAD-7", {
            "instrument": "GAD-7", "score": "7", "max_score": "21",
            "interpretation": "Mild anxiety",
        }, days_ago=1, notes="Responding well to therapy."),
    ]


def _confidential_record() -> dict:
    # A process note: the therapist's own reflections, encrypted with an extra
    # password on top of the at-rest encryption.
    record = _record("session_note", "Confidential process note", {
        "session_number": "3", "duration_min": "50", "session_format": "Online",
        "summary": "Therapist reflections on transference; not for the client file.",
    }, days_ago=14, access_level="private")
    record["is_confidential"] = True
    return record


def seed_demo_chart() -> bool:
    """Writes the demo chart once. Safe to call on every startup."""
    from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
    from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
    from core.services.record_service import RecordService
    from core.cqrs.commands import AddRecordCommand, CommandHandler, GrantConsentCommand

    block_repo = LMDBBlockRepository()
    record_service = RecordService(block_repo, AESGCMStrategy())
    project_name = record_service._get_project_name(DEMO_PATIENT_ID)

    existing = [
        b for b in block_repo.load_all_blocks(project_name)
        if b.index > 0 and not (isinstance(b.data, dict) and b.data.get("type") == "audit")
    ]
    if existing:
        return False  # a chart is already present — never write over it

    handler = CommandHandler(record_service, None, block_repo)

    for record in _demo_chart():
        handler.handle_add_record(AddRecordCommand(
            patient_id=DEMO_PATIENT_ID, data=record,
            is_protected=False, protection_password=None, username=DEMO_DOCTOR,
        ))

    handler.handle_add_record(AddRecordCommand(
        patient_id=DEMO_PATIENT_ID, data=_confidential_record(),
        is_protected=True, protection_password=DEMO_RECORD_PASSWORD, username=DEMO_DOCTOR,
    ))

    # Without a consent grant the demo doctor signs in to an empty chart, which
    # looks like a bug rather than the access control working.
    handler.handle_grant_consent(GrantConsentCommand(
        patient_id=DEMO_PATIENT_ID, doctor_username=DEMO_DOCTOR,
        record_type="all", duration_days=90, duration_hours=None,
        username="vip001",
    ))
    return True


def seed_demo_chart_if_enabled() -> bool:
    """Seeds only in the same conditions that create the demo accounts."""
    env = os.environ.get("ENVIRONMENT", "production")
    demo_mode = os.getenv("VHV_DEMO_MODE", "false").lower() == "true"
    if env != "development" and not demo_mode:
        return False
    return seed_demo_chart()
