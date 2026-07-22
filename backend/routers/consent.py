import json
import os
import re
from fastapi import APIRouter, HTTPException, Depends
from backend.dependencies import (
    get_user_repository, get_command_handler, get_consent_validator, current_user, get_db_manager
)
from backend.schemas.requests import ConsentReq, BreakGlassReq
from core.cqrs.commands import GrantConsentCommand, RevokeConsentCommand
from core.security import get_device_id
import database.storage as storage
from database.connection import LMDBConnectionManager
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository
from core.cqrs.commands import CommandHandler
from core.services.consent_validator import ConsentValidator

router = APIRouter(prefix="/api/v1/consent", tags=["consent"])

def check_patient_id(patient_id: str):
    if not re.match(r"^[a-zA-Z0-9_\-]+$", patient_id):
        raise HTTPException(400, "Invalid patient_id format")

@router.get("/{patient_id}", summary="Get Patient Consent Rules")
def get_consents(
    patient_id: str, 
    u: dict = Depends(current_user),
    db_manager: LMDBConnectionManager = Depends(get_db_manager)
):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    
    project_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
    if not db_manager.project_exists(project_name):
        return {"consents": []}
        
    env = db_manager.open_db(project_name)
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
def grant_consent(
    data: ConsentReq, 
    u: dict = Depends(current_user),
    user_repository: LMDBUserRepository = Depends(get_user_repository),
    command_handler: CommandHandler = Depends(get_command_handler)
):
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
def revoke_consent(
    patient_id: str, 
    doctor_username: str, 
    record_type: str, 
    u: dict = Depends(current_user),
    command_handler: CommandHandler = Depends(get_command_handler)
):
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
def break_glass(
    patient_id: str, 
    data: BreakGlassReq, 
    u: dict = Depends(current_user),
    consent_validator: ConsentValidator = Depends(get_consent_validator)
):
    check_patient_id(patient_id)
    if u["role"] != "doctor":
        raise HTTPException(403, "Only doctors can invoke emergency override")
        
    from backend.middleware.xss_protection import strip_dangerous_xss_tags
    clean_reason = strip_dangerous_xss_tags(data.reason)
    consent_validator.break_glass_override(
        patient_id=patient_id,
        doctor_username=u["username"],
        reason=clean_reason,
        device_id=get_device_id()
    )
    return {"success": True, "message": "Emergency access granted. Audit entry logged."}
