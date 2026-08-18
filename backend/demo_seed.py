"""
backend/demo_seed.py — Demonstration chart for the bundled VIP patient
=====================================================================
A freshly cloned vault starts with an empty chain, so the dashboard, the vital
sign trends, the allergy banner, the vaccine passport and the medication list all
render as empty states — the running application looks broken rather than idle.

This module writes a small, clinically coherent chart for the demo patient so a
first run shows the system doing its job. It only ever runs alongside the demo
accounts (development or VHV_DEMO_MODE), and only when the patient has no records
yet, so it can never touch a real deployment or overwrite a real chain.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import List

DEMO_PATIENT_ID = "VIP-001"
DEMO_DOCTOR = "dr.smith"

# Documented in the README and shown on the login screen's demo panel.
DEMO_RECORD_PASSWORD = "DemoRecord@2026!"

_DOCTOR_NAME = "Prof. Dr. James Smith"
_INSTITUTION = "VIP Medical Center"


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
    """Four weeks of a plausible cardiology follow-up."""
    return [
        _record("vital_signs", "Routine vitals — week 1", {
            "blood_pressure": "148/94", "heart_rate": "88",
            "temperature": "36.7", "oxygen_sat": "97",
        }, days_ago=21),

        _record("allergy", "Penicillin allergy", {
            "allergen": "Penicillin", "reaction": "Anaphylaxis",
            "severity": "Severe", "onset_date": "2019-05-02",
        }, days_ago=20, notes="Documented after an emergency admission in 2019."),

        _record("lab_result", "Lipid panel", {
            "test_name": "LDL cholesterol", "result_value": "168",
            "reference_range": "0-130", "unit": "mg/dL",
        }, days_ago=18, notes="Above reference range; statin therapy discussed."),

        _record("diagnosis", "Essential hypertension", {
            "icd_code": "I10", "severity": "Moderate",
            "symptoms": "Morning headaches, occasional dizziness",
        }, days_ago=14),

        _record("prescription", "Ramipril 5 mg", {
            "medication": "Ramipril", "dose": "5 mg",
            "frequency": "1x daily (morning)", "duration": "90",
        }, days_ago=14, notes="Review blood pressure at the next visit."),

        _record("vital_signs", "Follow-up vitals — week 3", {
            "blood_pressure": "138/88", "heart_rate": "79",
            "temperature": "36.5", "oxygen_sat": "98",
        }, days_ago=7),

        _record("vaccination", "Influenza vaccination", {
            "vaccine_name": "Influenza (quadrivalent)", "lot_number": "FLU-2026-0442",
            "dose_number": "1", "next_dose": _day(-365),
        }, days_ago=5),

        _record("vital_signs", "Follow-up vitals — week 4", {
            "blood_pressure": "129/82", "heart_rate": "74",
            "temperature": "36.6", "oxygen_sat": "98",
        }, days_ago=1, notes="Responding well to therapy."),
    ]


def _confidential_record() -> dict:
    record = _record("psychology", "Confidential consultation note", {
        "summary": "Stress management consultation",
        "clinician": "Dr. Elif Aydın",
    }, days_ago=10, access_level="private")
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
