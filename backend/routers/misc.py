import os
import json
import time
import secrets
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from backend.dependencies import (
    current_user, require_role, record_service, audit_service,
    query_handler, command_handler
)
from backend.schemas.requests import (
    AppointmentCreate, TriageRequest, LisWebhookPayload,
    RECORD_TYPES, ACCESS_LEVELS
)
from backend.routers.records import create_notification, check_patient_id
from core.cqrs.queries import ExportFHIRBundleQuery, GetNotificationsQuery
from core.cqrs.commands import AddRecordCommand
from core.security import get_device_id
import database.storage as storage

router = APIRouter(tags=["misc"])

# Global mock DB for appointments
appointments_db = [
    {
        "id": "apt001",
        "patient_id": "VIP-001",
        "doctor_name": "Prof. Dr. Ahmet Yilmaz",
        "department": "Cardiology",
        "appointment_date": "2026-06-12",
        "appointment_time": "10:30",
        "status": "scheduled",
        "notes": "Routine cardiology follow-up."
    },
    {
        "id": "apt002",
        "patient_id": "VIP-001",
        "doctor_name": "Dr. Sarah Smith",
        "department": "Neurology",
        "appointment_date": "2026-06-15",
        "appointment_time": "14:00",
        "status": "scheduled",
        "notes": "Migraine progress review."
    }
]

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

# ── APPOINTMENT ENDPOINTS ──────────────────────────────────────
@router.get("/api/appointments/{patient_id}", summary="Get Patient Appointments")
def get_appointments(patient_id: str, u: dict = Depends(current_user)):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    return [apt for apt in appointments_db if apt["patient_id"] == patient_id]

@router.post("/api/appointments", summary="Create Appointment")
def create_appointment(req: AppointmentCreate, u: dict = Depends(current_user)):
    if u["role"] == "vip_patient" and u.get("patient_id") != req.patient_id:
        raise HTTPException(403, "Access denied")
    
    new_apt = {
        "id": f"apt{secrets.token_hex(4)}",
        "patient_id": req.patient_id,
        "doctor_name": req.doctor_name,
        "department": req.department,
        "appointment_date": req.appointment_date,
        "appointment_time": req.appointment_time,
        "status": "scheduled",
        "notes": req.notes or ""
    }
    appointments_db.append(new_apt)
    
    # Trigger smart notification
    try:
        create_notification(
            patient_id=req.patient_id,
            title="RANDEVU OLUŞTURULDU",
            message=f"Hekim {req.doctor_name} ({req.department}) ile {req.appointment_date} günü saat {req.appointment_time} için randevunuz başarıyla oluşturuldu.",
            severity="info"
        )
    except Exception as ex:
        print(f"[WARNING] Failed to trigger appointment notification: {ex}")
        
    return {"success": True, "appointment": new_apt}

@router.delete("/api/appointments/{appointment_id}", summary="Cancel Appointment")
def cancel_appointment(appointment_id: str, u: dict = Depends(current_user)):
    apt = next((a for a in appointments_db if a["id"] == appointment_id), None)
    if not apt:
        raise HTTPException(404, "Appointment not found")
        
    if u["role"] == "vip_patient" and u.get("patient_id") != apt["patient_id"]:
        raise HTTPException(403, "Access denied")
        
    appointments_db.remove(apt)
    return {"success": True, "message": "Appointment cancelled successfully"}

# ── AI MEDICAL TRIAGE ──────────────────────────────────────────
@router.post("/api/ai/triage", summary="AI Medical Triage Chatbot")
def ai_triage(req: TriageRequest):
    symptoms_lower = req.symptoms.lower()
    
    if any(kw in symptoms_lower for kw in ["chest pain", "breath", "stroke", "paralysis", "speech", "heart attack", "unconscious", "head injury"]):
        level = "red"
        status = "URGENT / EMERGENCY"
        recommendation = "Please seek immediate medical attention at the nearest emergency department or call emergency services (112)."
        reason = "Symptoms indicate a potential life-threatening emergency."
    elif any(kw in symptoms_lower for kw in ["fever", "severe pain", "fracture", "blood", "vomiting", "infection", "migraine", "abdominal pain"]):
        level = "orange"
        status = "CLINIC APPOINTMENT"
        recommendation = "We recommend booking a consultation with your physician or visiting an outpatient clinic within 24 hours."
        reason = "Symptoms warrant physical clinical examination and potential diagnostics."
    else:
        level = "green"
        status = "SELF-CARE / MONITOR"
        recommendation = "Monitor your symptoms closely. Ensure adequate rest, hydration, and consult a doctor if condition worsens."
        reason = "Mild symptom classification. Supportive self-care is appropriate."
        
    return {
        "status": status,
        "level": level,
        "recommendation": recommendation,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
        "disclaimer": "Disclaimer: This AI Triage is for informational purposes only. It is not a substitute for professional medical advice."
    }

# ── FHIR EXPORT ───────────────────────────────────────────────
@router.get("/api/enabiz/fhir/export/{patient_id}", summary="FHIR e-Nabiz Export Bridge")
def fhir_export(patient_id: str, u: dict = Depends(current_user)):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
        
    query = ExportFHIRBundleQuery(
        patient_id=patient_id,
        requester_username=u["username"],
        requester_role=u["role"]
    )
    return query_handler.handle_export_fhir_bundle(query)

# ── LIS WEBHOOK GATEWAY ────────────────────────────────────────
@router.post("/api/webhooks/lis", summary="LIS Hospital Webhook Gateway")
def lis_webhook(payload: LisWebhookPayload):
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
@router.get("/api/notifications/{patient_id}", summary="Get Patient Notifications")
def get_notifications(patient_id: str, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
        
    query = GetNotificationsQuery(patient_id=patient_id, username=u["username"])
    notifs = query_handler.handle_get_notifications(query)
    return {"notifications": notifs}

@router.post("/api/notifications/{patient_id}/{notif_id}/read", summary="Mark Notification as Read")
def mark_notification_read(patient_id: str, notif_id: str, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
        
    project_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
    
    def txn_read(txn):
        key = f"notif_{notif_id}".encode("utf-8")
        val = txn.get(key)
        if val:
            data = json.loads(val.decode("utf-8"))
            data["read"] = True
            txn.put(key, json.dumps(data).encode("utf-8"))
            return True
        return False
        
    success = storage.run_write_transaction(project_name, txn_read)
    if not success:
        raise HTTPException(404, "Notification not found")
    return {"success": True}

# ── BLOCKCHAIN STATUS / EXPLORER ──────────────────────────────
@router.get("/api/blockchain/{patient_id}/status", summary="Chain Status")
def chain_status(patient_id: str, u: dict = Depends(current_user)):
    chain = record_service.get_chain(patient_id)
    brk = record_service.find_broken_link_index(patient_id)
    return {
        "patient_id":   patient_id,
        "chain_length": len(chain),
        "is_valid":     brk == -1,
        "broken_at":    brk if brk != -1 else None,
        "device_id":    get_device_id()[:16] + "...",
    }

@router.get("/api/blockchain/{patient_id}/audit", summary="Access History")
def audit_log(
    patient_id: str,
    limit: int = 50,
    source: str = "db",
    u: dict = Depends(require_role("admin", "auditor")),
):
    logs = audit_service.get_audit_logs(patient_id, limit, source)
    return {"patient_id": patient_id, "logs": logs, "source": source}

@router.get("/api/blockchain/{patient_id}/access-logs", summary="Patient Access Log")
def get_access_logs(
    patient_id: str,
    limit: int = 100,
    source: str = "db",
    u: dict = Depends(require_role("admin", "auditor", "vip_patient"))
):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    logs = audit_service.get_access_logs(patient_id, limit, source)
    return {"patient_id": patient_id, "logs": logs, "source": source}

# ── SYSTEM / CONFIG ───────────────────────────────────────────
@router.get("/api/record-types", summary="Record Types")
def record_types():
    return {
        "types":         [{"value": k, "label": v} for k, v in RECORD_TYPES.items()],
        "access_levels": [{"value": k, "label": v} for k, v in ACCESS_LEVELS.items()],
    }

@router.get("/api/system/status", summary="System Status")
def system_status(u: dict = Depends(require_role("admin"))):
    projects = storage.list_projects()
    return {
        "status":       "operational",
        "version":      "3.0.0",
        "device_id":    get_device_id()[:16] + "...",
        "projects":     len(projects),
        "patient_ids":  projects,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }

@router.get("/api/system/config", summary="Public System Configuration")
def get_system_config():
    return {
        "environment": os.environ.get("ENVIRONMENT", "production"),
    }

@router.get("/api/config", summary="Dynamic Configuration and Demo mode")
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
