"""
backend/routers/misc.py — Miscellaneous System, Notification, & Audit Endpoints
================================================================================
Cleaned and refactored for v5.0.0 Stealth VIP Health Privacy Vault.
Removed: Appointment booking, AI Triage chatbot, and FHIR export bridges.
"""

import os
import json
import time
import secrets
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from backend.dependencies import (
    current_user, require_role, get_record_service, get_audit_service,
    get_query_handler, get_command_handler, get_db_manager, get_blockchain_notarizer,
    get_notification_repository
)
from core.ports.repositories import INotificationRepository
from backend.schemas.requests import (
    LisWebhookPayload, RECORD_TYPES, ACCESS_LEVELS
)
from backend.routers.records import create_notification, check_patient_id
from core.cqrs.queries import GetNotificationsQuery
from core.cqrs.commands import AddRecordCommand
from core.security import get_device_id
import database.storage as storage
from database.connection import LMDBConnectionManager
from core.services.record_service import RecordService
from core.services.audit_service import AuditService
from core.cqrs.commands import CommandHandler
from core.cqrs.queries import QueryHandler

router = APIRouter(prefix="/api/v1", tags=["misc"])


def is_abnormal(value_str: str, range_str: str) -> bool:
    try:
        val = float(value_str)
        if "-" in range_str:
            parts = range_str.split("-")
            low = float(parts[0].strip())
            high = float(parts[1].strip())
            return val < low or val > high
    except Exception:
        pass
    return False


# ── LIS WEBHOOK GATEWAY ────────────────────────────────────────
@router.post("/webhooks/lis", summary="LIS Hospital Webhook Gateway")
def lis_webhook(
    payload: LisWebhookPayload,
    command_handler: CommandHandler = Depends(get_command_handler),
    db_manager: LMDBConnectionManager = Depends(get_db_manager)
):
    block_data = {
        "record_type":       "lab_result",
        "record_type_label": RECORD_TYPES["lab_result"],
        "title":             payload.title,
        "doctor_name":       payload.doctor_name,
        "institution":       payload.institution,
        "record_date":       datetime.now().strftime("%Y-%m-%d"),
        "access_level":      "doctor_shared",
        "is_confidential":   False,
        "data": {
            "test_name":       payload.test_name,
            "result_value":    payload.result_value,
            "reference_range": payload.reference_range,
            "unit":            payload.unit
        },
        "notes":             f"LIS Webhook Import. {payload.notes or ''}",
        "created_by":        "LIS_GATEWAY",
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "patient_id":        payload.patient_id,
        "file_name":         None,
        "file_type":         None,
        "file_data":         None,
    }
    
    try:
        cmd = AddRecordCommand(
            patient_id=payload.patient_id,
            data=block_data,
            is_protected=False,
            protection_password=None,
            username="LIS_GATEWAY"
        )
        block = command_handler.handle_add_record(cmd)
        
        if is_abnormal(payload.result_value, payload.reference_range):
            create_notification(
                patient_id=payload.patient_id,
                title="KRİTİK LABORATUVAR SONUCU",
                message=f"Yeni gelen tahlil sonucunuzda ({payload.test_name}) referans dışı değer ({payload.result_value} {payload.unit}, Ref: {payload.reference_range}) saptandı. Lütfen hekiminize danışın.",
                severity="warning"
            )
        else:
            create_notification(
                patient_id=payload.patient_id,
                title="YENİ LABORATUVAR SONUCU",
                message=f"Tahlil sonucunuz ({payload.test_name}: {payload.result_value} {payload.unit}) sisteme yüklendi ve blockchain'e kaydedildi.",
                severity="info"
            )
            
        return {
            "success": True,
            "block_index": block.index,
            "message": "LIS laboratory block appended to blockchain successfully"
        }
    except Exception as ex:
        raise HTTPException(500, f"Failed to save webhook record to blockchain: {str(ex)}")


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
        
        # On-Chain Notarization details
        "on_chain_verified": verification["verified"],
        "on_chain_tx_hash":  verification["tx_hash"],
        "local_root":        verification["local_root"],
        "on_chain_root":     verification["on_chain_root"],
        "on_chain_reason":   verification["reason"]
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
    return {"patient_id": patient_id, "logs": logs, "source": source}


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
            {"role": "VIP", "username": "vip001", "password": "VIPPatient@2026!"}
        ]
    return {
        "environment": env,
        "demo_mode": demo_mode,
        "demo_accounts": accounts
    }
