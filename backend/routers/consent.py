import json
import os
import re
from fastapi import APIRouter, HTTPException, Depends
from backend.dependencies import (
    user_repository, command_handler, consent_validator, current_user
)
from backend.schemas.requests import ConsentReq, BreakGlassReq
from core.cqrs.commands import GrantConsentCommand, RevokeConsentCommand
from core.security import get_device_id
import database.storage as storage

router = APIRouter(prefix="/api/consent", tags=["consent"])

def check_patient_id(patient_id: str):
    if not re.match(r"^[a-zA-Z0-9_\-]+$", patient_id):
        raise HTTPException(400, "Invalid patient_id format")

@router.get("/{patient_id}", summary="Get Patient Consent Rules")
def get_consents(patient_id: str, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    
    project_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
    if not storage.project_exists(project_name):
        return {"consents": []}
        
    env = storage.open_db(project_name)
    consents = []
    with env.begin(write=False) as txn:
        cursor = txn.cursor()
        for key, value in cursor:
            if key.startswith(b"consent_"):
                try:
                    cdata = json.loads(value.decode("utf-8"))
                    consents.append(cdata)
                except Exception:
                    continue
    return {"consents": consents}

@router.post("", summary="Grant or Update Doctor Consent")
def grant_consent(data: ConsentReq, u: dict = Depends(current_user)):
    if u["role"] == "vip_patient" and u.get("patient_id") != data.patient_id:
        raise HTTPException(403, "Access denied")
        
    doc = user_repository.load_user(data.doctor_username)
    if not doc or doc.role != "doctor":
        raise HTTPException(404, "Doctor not found")
        
    cmd = GrantConsentCommand(
        patient_id=data.patient_id,
        doctor_username=data.doctor_username,
        record_type=data.record_type,
        duration_days=data.duration_days,
        username=u["username"]
    )
    command_handler.handle_grant_consent(cmd)
    return {"success": True, "message": "Consent granted successfully"}

@router.delete("/{patient_id}/{doctor_username}/{record_type}", summary="Revoke Doctor Consent")
def revoke_consent(patient_id: str, doctor_username: str, record_type: str, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
        
    cmd = RevokeConsentCommand(
        patient_id=patient_id,
        doctor_username=doctor_username,
        record_type=record_type,
        username=u["username"]
    )
    command_handler.handle_revoke_consent(cmd)
    return {"success": True, "message": "Consent revoked successfully"}

@router.post("/{patient_id}/break-glass", summary="Break Glass Emergency Override")
def break_glass(patient_id: str, data: BreakGlassReq, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] != "doctor":
        raise HTTPException(403, "Only doctors can invoke emergency override")
        
    consent_validator.break_glass_override(
        patient_id=patient_id,
        doctor_username=u["username"],
        reason=data.reason,
        device_id=get_device_id()
    )
    return {"success": True, "message": "Emergency access granted. Audit entry logged."}
