"""
backend/routers/misc.py — Miscellaneous System, Notification, & Audit Endpoints
================================================================================
Cleaned and refactored for v5.0.0 Stealth VIP Health Privacy Vault.
Removed: Appointment booking, AI Triage chatbot, and FHIR export bridges.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from backend.dependencies import (
    current_user, require_role, get_record_service, get_audit_service,
    get_query_handler, get_db_manager, get_blockchain_notarizer,
    get_notification_repository
)
from core.ports.repositories import INotificationRepository
from backend.schemas.requests import (
    RECORD_TYPES, ACCESS_LEVELS
)
from backend.routers.records import check_patient_id
from core.cqrs.queries import GetNotificationsQuery
from core.security import get_device_id
from database.connection import LMDBConnectionManager
from core.services.record_service import RecordService
from core.services.audit_service import AuditService
from core.cqrs.queries import QueryHandler

router = APIRouter(prefix="/api/v1", tags=["misc"])


# ── SMART NOTIFICATIONS ───────────────────────────────────────
@router.get("/notifications/{patient_id}", summary="Get Patient Notifications")
def get_notifications(
    patient_id: str,
    u: dict = Depends(current_user),
    query_handler: QueryHandler = Depends(get_query_handler)
):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    query = GetNotificationsQuery(patient_id=patient_id, username=u["username"])
    notifs = query_handler.handle_get_notifications(query)
    return {"notifications": notifs}


@router.post("/notifications/{patient_id}/{notif_id}/read", summary="Mark Notification as Read")
def mark_notification_read(
    patient_id: str,
    notif_id: str,
    u: dict = Depends(current_user),
    notif_repo: INotificationRepository = Depends(get_notification_repository)
):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    success = notif_repo.mark_as_read(patient_id, notif_id)
    if not success:
        raise HTTPException(404, "Notification not found")
    return {"success": True}


# ── LOCAL HASH-CHAIN STATUS & AUDIT LOGS ──────────────────────
@router.get("/blockchain/{patient_id}/status", summary="Chain Status")
def chain_status(
    patient_id: str,
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service),
    notarizer = Depends(get_blockchain_notarizer)
):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        # Chain length and Merkle root disclose that a person is a patient here and
        # how much of a record they have - metadata this vault exists to conceal.
        raise HTTPException(403, "Access denied")

    chain = record_service.get_chain(patient_id)
    brk = record_service.find_broken_link_index(patient_id)

    # Run on-chain verification
    verification = notarizer.verify_on_chain(patient_id)

    return {
        "patient_id":   patient_id,
        "chain_length": len(chain),
        "is_valid":     brk == -1,
        "broken_at":    brk if brk != -1 else None,
        "device_id":    get_device_id()[:16] + "...",

        # Local anchor details (ADR-0001). The anchor is an HMAC-SHA256 signature
        # of the Merkle root under the server's KMS key — a real, verifiable
        # commitment, not a public-chain transaction. The UI labels it as a local
        # signed anchor rather than implying any on-chain settlement.
        "is_locally_anchored": True,
        "anchor_verified":     verification["verified"],
        "anchor_signature":    verification["tx_hash"],
        "local_root":          verification["local_root"],
        "anchored_root":       verification["on_chain_root"],
        "anchor_reason":       verification["reason"]
    }


@router.get("/blockchain/{patient_id}/audit", summary="Access History")
def audit_log(
    patient_id: str,
    limit: int = 50,
    source: str = "db",
    u: dict = Depends(require_role("admin", "auditor")),
    audit_service: AuditService = Depends(get_audit_service)
):
    logs = audit_service.get_audit_logs(patient_id, limit, source)
    return {"patient_id": patient_id, "logs": logs, "source": source}


@router.get("/blockchain/{patient_id}/access-logs", summary="Patient Access Log")
def get_access_logs(
    patient_id: str,
    limit: int = 100,
    source: str = "db",
    u: dict = Depends(require_role("admin", "auditor", "vip_patient")),
    audit_service: AuditService = Depends(get_audit_service)
):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    logs = audit_service.get_access_logs(patient_id, limit, source)
    integrity = audit_service.verify_access_integrity(patient_id)
    return {"patient_id": patient_id, "logs": logs, "source": source, "integrity": integrity}


# ── SYSTEM / CONFIG ───────────────────────────────────────────
@router.get("/record-types", summary="Record Types")
def record_types():
    return {
        "types":         [{"value": k, "label": v} for k, v in RECORD_TYPES.items()],
        "access_levels": [{"value": k, "label": v} for k, v in ACCESS_LEVELS.items()],
    }


@router.get("/system/status", summary="System Status")
def system_status(
    u: dict = Depends(require_role("admin")),
    db_manager: LMDBConnectionManager = Depends(get_db_manager)
):
    projects = db_manager.list_projects()
    return {
        "status":       "operational",
        "version":      "5.0.0",
        "device_id":    get_device_id()[:16] + "...",
        "projects":     len(projects),
        "patient_ids":  projects,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/config", summary="Public System Configuration")
def get_system_config():
    return {
        "environment": os.environ.get("ENVIRONMENT", "production"),
    }


@router.get("/config", summary="Dynamic Configuration")
def get_config():
    demo_mode = os.getenv("VHV_DEMO_MODE", "false").lower() == "true"
    env = os.environ.get("ENVIRONMENT", "production")
    if env == "development":
        demo_mode = True

    accounts = []
    if demo_mode:
        accounts = [
            {"role": "ADMIN", "username": "admin", "password": "Admin@2026Secure!"},
            {"role": "DOCTOR", "username": "dr.smith", "password": "Doctor@2026Secure!"},
            {"role": "VIP", "username": "vip001", "password": "VIPPatient@2026!"},
            {"role": "SECOFF", "username": "sec.officer", "password": "SecOfficer@2026!"}
        ]
    return {
        "environment": env,
        "demo_mode": demo_mode,
        "demo_accounts": accounts
    }
