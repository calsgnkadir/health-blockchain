import os
import re
import time
import json
import base64
import secrets
import hashlib
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request, Response, Path
from pydantic import ValidationError

from backend.dependencies import (
    current_user, record_service, command_handler, query_handler, consent_validator
)
from backend.schemas.requests import (
    RecordCreate, DecryptRequest, RECORD_TYPES,
    VitalSignsSchema, AllergySchema, PrescriptionSchema, VaccinationSchema,
    LabResultSchema, DiagnosisSchema, SurgerySchema, ImagingSchema
)
from core.security import encrypt_data, decrypt_data, get_device_id
from core.cqrs.commands import AddRecordCommand
from core.cqrs.queries import GetPatientRecordsQuery, DecryptRecordQuery
import database.storage as storage

router = APIRouter(prefix="/api/records", tags=["records"])

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_patient_id(patient_id: str):
    if not re.match(r"^[a-zA-Z0-9_\-]+$", patient_id):
        raise HTTPException(400, "Invalid patient_id format")

def create_notification(patient_id: str, title: str, message: str, severity: str = "info") -> None:
    project_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
    if not storage.project_exists(project_name):
        storage.create_project(project_name)
    
    notif_id = f"notif_{time.time_ns()}"
    notif_data = {
        "id": notif_id,
        "patient_id": patient_id,
        "title": title,
        "message": message,
        "severity": severity,
        "timestamp": time.time(),
        "read": False
    }
    
    def txn_notif(txn):
        key = f"notif_{notif_id}".encode("utf-8")
        txn.put(key, json.dumps(notif_data).encode("utf-8"))
        
    storage.run_write_transaction(project_name, txn_notif)

@router.post("", summary="Add Health Record")
def add_record(rec: RecordCreate, u: dict = Depends(current_user)):
    if u["role"] == "vip_patient" and u.get("patient_id") != rec.patient_id:
        raise HTTPException(403, "You can only access your own records")
    if u["role"] not in ("doctor", "admin", "vip_patient"):
        raise HTTPException(403, "You do not have permission to add records")

    # Dynamic clinical data validation
    try:
        if rec.record_type == "vital_signs":
            VitalSignsSchema(**rec.data)
        elif rec.record_type == "allergy":
            AllergySchema(**rec.data)
        elif rec.record_type == "prescription":
            PrescriptionSchema(**rec.data)
        elif rec.record_type == "vaccination":
            VaccinationSchema(**rec.data)
        elif rec.record_type == "lab_result":
            LabResultSchema(**rec.data)
        elif rec.record_type == "diagnosis":
            DiagnosisSchema(**rec.data)
        elif rec.record_type == "surgery":
            SurgerySchema(**rec.data)
        elif rec.record_type == "imaging":
            ImagingSchema(**rec.data)
    except ValidationError as e:
        err_msgs = [".".join(str(x) for x in error["loc"]) + ": " + error["msg"] for error in e.errors()]
        raise HTTPException(status_code=422, detail=f"Validation failed: {', '.join(err_msgs)}")

    block_data = {
        "record_type":       rec.record_type,
        "record_type_label": RECORD_TYPES[rec.record_type],
        "title":             rec.title,
        "doctor_name":       rec.doctor_name,
        "institution":       rec.institution,
        "record_date":       rec.record_date,
        "access_level":      rec.access_level,
        "is_confidential":   rec.is_confidential,
        "data":              rec.data,
        "notes":             rec.notes or "",
        "created_by":        u["username"],
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "patient_id":        rec.patient_id,
        "file_name":         rec.file_name,
        "file_type":         rec.file_type,
        "file_data":         None,
    }

    # Off-chain file storage logic
    file_hash = None
    if rec.file_data:
        OFFCHAIN_DIR = os.path.join(_PROJECT_ROOT, "backend", "offchain_storage")
        os.makedirs(OFFCHAIN_DIR, exist_ok=True)
        
        file_pwd = secrets.token_hex(16)
        enc_data_b64, file_salt_bytes = encrypt_data(rec.file_data, file_pwd)
        
        file_hash = hashlib.sha256(enc_data_b64.encode("utf-8")).hexdigest()
        
        file_path = os.path.join(OFFCHAIN_DIR, file_hash)
        with open(file_path, "w") as f:
            f.write(enc_data_b64)
            
        block_data["file_hash"] = file_hash
        block_data["file_salt"] = base64.b64encode(file_salt_bytes).decode("utf-8")
        block_data["file_pwd"] = file_pwd

    # Write block using CQRS AddRecordCommand
    cmd = AddRecordCommand(
        patient_id=rec.patient_id,
        data=block_data,
        is_protected=rec.is_confidential,
        protection_password=rec.confidential_password if rec.is_confidential else None,
        username=u["username"]
    )
    block = command_handler.handle_add_record(cmd)

    # Handle notifications for prescription
    if rec.record_type == "prescription":
        med_name = rec.data.get("medication", "İlaç")
        create_notification(
            patient_id=rec.patient_id,
            title="YENİ İLAÇ REÇETESİ",
            message=f"Reçetenize yeni bir ilaç eklendi: {med_name}. Lütfen kullanım talimatlarına uyun.",
            severity="info"
        )

    return {
        "success":     True,
        "block_index": block.index,
        "block_hash":  block.hash[:20] + "...",
        "message":     "Record added to blockchain",
    }

@router.get("/{patient_id}", summary="Get Patient Records")
def get_records(patient_id: str, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    role = u["role"]
    if role == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    # Enforce consent validation for doctors
    ignore_consent = False
    if role == "doctor":
        proj_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
        access_logs = storage.load_access_logs(proj_name, limit=5)
        for log in access_logs:
            if log.get("action") == "BREAK_GLASS_ACCESS" and log.get("username") == u["username"]:
                if time.time() - log.get("timestamp", 0) < 900:  # 15 mins window
                    ignore_consent = True
                    break

    query = GetPatientRecordsQuery(
        patient_id=patient_id,
        requester_username=u["username"],
        requester_role=role,
        ignore_consent=ignore_consent
    )
    records = query_handler.handle_get_patient_records(query)
    
    # Sort records by timestamp descending
    records.sort(key=lambda x: x["timestamp"], reverse=True)

    # Publish access viewed event
    from core.events.event_bus import SystemAuditEvent, event_bus
    event_bus.publish(SystemAuditEvent(
        project_name=record_service._get_project_name(patient_id),
        action="RECORDS_VIEWED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"record_count": len(records)}
    ))

    chain = record_service.get_chain(patient_id)
    return {
        "patient_id":   patient_id,
        "total_blocks": len(chain),
        "records":      records,
        "chain_valid":  record_service.is_chain_valid(patient_id),
    }

@router.get("/{patient_id}/{block_index}", summary="Get Single Record")
def get_single_record(patient_id: str, block_index: int = Path(..., ge=0), u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    chain = record_service.get_chain(patient_id)
    block = next((b for b in chain if b.index == block_index), None)
    if block is None:
        raise HTTPException(404, "Block not found")

    if block.is_protected:
        return {
            "block_index": block_index,
            "is_protected": True,
            "data": "ENCRYPTED — use POST /decrypt with the correct password",
        }

    data = record_service.get_final_block_data(patient_id, block_index, password=None, username=u["username"])
    return {"block_index": block_index, "is_protected": False, "data": data}

@router.post("/{patient_id}/{block_index}/decrypt", summary="Decrypt Encrypted Record")
def decrypt_record(patient_id: str, block_index: int = Path(..., ge=0), req: DecryptRequest = None, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    if not req or not req.password:
        raise HTTPException(400, "Password is required to decrypt this record")

    # Enforce consent validation for doctors
    ignore_consent = False
    if u["role"] == "doctor":
        proj_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
        access_logs = storage.load_access_logs(proj_name, limit=5)
        for log in access_logs:
            if log.get("action") == "BREAK_GLASS_ACCESS" and log.get("username") == u["username"]:
                if time.time() - log.get("timestamp", 0) < 900:  # 15 mins window
                    ignore_consent = True
                    break

    query = DecryptRecordQuery(
        patient_id=patient_id,
        block_index=block_index,
        password=req.password,
        requester_username=u["username"],
        requester_role=u["role"],
        ignore_consent=ignore_consent
    )
    data = query_handler.handle_decrypt_record(query)

    if isinstance(data, str) and ("INCORRECT" in data or "SECURE" in data or "ERROR" in data):
        raise HTTPException(403, "Incorrect password — decryption failed")

    return {"block_index": block_index, "data": data}

@router.get("/offchain/download/{patient_id}/{block_index}", summary="Download Off-chain File")
def download_offchain_file(patient_id: str, block_index: int, password: Optional[str] = None, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    role = u["role"]
    ignore_consent = False
    
    if role == "doctor":
        proj_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
        access_logs = storage.load_access_logs(proj_name, limit=5)
        for log in access_logs:
            if log.get("action") == "BREAK_GLASS_ACCESS" and log.get("username") == u["username"]:
                if time.time() - log.get("timestamp", 0) < 900:
                    ignore_consent = True
                    break
        if not ignore_consent:
            has_any = (
                consent_validator.has_consent(patient_id, u["username"], "all")
                or consent_validator.has_consent(patient_id, u["username"], "imaging")
                or consent_validator.has_consent(patient_id, u["username"], "lab_result")
            )
            if not has_any:
                raise HTTPException(403, "Access denied: Patient consent is required to download this file.")
                
    if role == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
        
    try:
        data = record_service.get_final_block_data(patient_id, block_index, password=password, username=u["username"])
        if isinstance(data, str) and ("SECURE" in data or "INCORRECT" in data or "ERROR" in data):
            raise HTTPException(400, f"Decryption failed: {data}")
            
        if not isinstance(data, dict) or not data.get("file_hash"):
            raise HTTPException(404, "File not found or not stored off-chain")
            
        file_hash = data["file_hash"]
        file_salt = base64.b64decode(data["file_salt"])
        file_pwd = data["file_pwd"]
        file_name = data.get("file_name", "download")
        file_type = data.get("file_type", "application/octet-stream")
        
        OFFCHAIN_DIR = os.path.join(_PROJECT_ROOT, "backend", "offchain_storage")
        file_path = os.path.join(OFFCHAIN_DIR, file_hash)
        
        if not os.path.exists(file_path):
            raise HTTPException(404, "Encrypted file not found on off-chain storage")
            
        with open(file_path, "r") as f:
            enc_data_b64 = f.read()
            
        decrypted_b64 = decrypt_data(enc_data_b64, file_pwd, file_salt)
        file_bytes = base64.b64decode(decrypted_b64)
        
        return Response(
            content=file_bytes,
            media_type=file_type,
            headers={
                "Content-Disposition": f"attachment; filename={file_name}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to download off-chain file: {str(e)}")
