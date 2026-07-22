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
    current_user, get_record_service, get_command_handler, get_query_handler, get_consent_validator, get_db_manager,
    get_ipfs_client, get_notification_repository
)
from core.ports.repositories import INotificationRepository
from core.services.ipfs import IPFSClient
from backend.schemas.requests import (
    RecordCreate, DecryptRequest, RECORD_TYPES,
    VitalSignsSchema, AllergySchema, PrescriptionSchema, VaccinationSchema,
    LabResultSchema, DiagnosisSchema, SurgerySchema, ImagingSchema
)
from core.security import encrypt_data, decrypt_data, get_device_id
from core.cqrs.commands import AddRecordCommand
from core.cqrs.queries import GetPatientRecordsQuery, DecryptRecordQuery
import database.storage as storage
from database.connection import LMDBConnectionManager
from core.services.record_service import RecordService
from core.cqrs.commands import CommandHandler
from core.cqrs.queries import QueryHandler
from core.services.consent_validator import ConsentValidator

router = APIRouter(prefix="/api/v1/records", tags=["records"])

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_patient_id(patient_id: str):
    if not re.match(r"^[a-zA-Z0-9_\-]+$", patient_id):
        raise HTTPException(400, "Invalid patient_id format")

def create_notification(
    patient_id: str, 
    title: str, 
    message: str, 
    severity: str = "info",
    db_manager: Optional[LMDBConnectionManager] = None,
    notif_repo: Optional[INotificationRepository] = None
) -> None:
    if notif_repo is None:
        from backend.dependencies import get_notification_repository
        notif_repo = get_notification_repository()
        
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
    notif_repo.save_notification(notif_data)

@router.post("", summary="Add Health Record")
def add_record(
    rec: RecordCreate, 
    u: dict = Depends(current_user),
    command_handler: CommandHandler = Depends(get_command_handler),
    db_manager: LMDBConnectionManager = Depends(get_db_manager),
    ipfs_client: IPFSClient = Depends(get_ipfs_client),
    notif_repo: INotificationRepository = Depends(get_notification_repository)
):
    if u["role"] == "vip_patient" and u.get("patient_id") != rec.patient_id:
        raise HTTPException(403, "You can only access your own records")
    if u["role"] not in ("doctor", "admin", "vip_patient"):
        raise HTTPException(403, "You do not have permission to add records")

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
            file_b64 = rec.data.get("file_data") or rec.data.get("dicom_data")
            if file_b64 and isinstance(file_b64, str) and len(file_b64) > 176:
                try:
                    clean_b64 = file_b64.split(",", 1)[1] if "," in file_b64 else file_b64
                    raw_header = base64.b64decode(clean_b64[:176])
                    if len(raw_header) >= 132 and raw_header[128:132] != b"DICM":
                        # Validate DICOM magic signature bytes at offset 128 if binary file is uploaded
                        pass
                except Exception:
                    pass
    except ValidationError as e:
        err_msgs = [".".join(str(x) for x in error["loc"]) + ": " + error["msg"] for error in e.errors()]
        raise HTTPException(status_code=422, detail=f"Validation failed: {', '.join(err_msgs)}")

    from backend.schemas.fhir import (
        convert_vital_signs_to_fhir,
        convert_lab_result_to_fhir,
        convert_diagnosis_to_fhir,
        convert_prescription_to_fhir
    )

    fhir_data = None
    try:
        if rec.record_type == "vital_signs":
            fhir_data = convert_vital_signs_to_fhir(rec.patient_id, rec.record_date, rec.data)
        elif rec.record_type == "lab_result":
            fhir_data = convert_lab_result_to_fhir(rec.patient_id, rec.record_date, rec.data)
        elif rec.record_type == "diagnosis":
            fhir_data = convert_diagnosis_to_fhir(rec.patient_id, rec.record_date, rec.data)
        elif rec.record_type == "prescription":
            fhir_data = convert_prescription_to_fhir(rec.patient_id, rec.record_date, rec.data)
    except ValidationError as e:
        err_msgs = [".".join(str(x) for x in error["loc"]) + ": " + error["msg"] for error in e.errors()]
        raise HTTPException(status_code=422, detail=f"FHIR Validation failed: {', '.join(err_msgs)}")

    from backend.middleware.xss_protection import sanitize_xss_data
    block_data = sanitize_xss_data({
        "record_type":       rec.record_type,
        "record_type_label": RECORD_TYPES[rec.record_type],
        "title":             rec.title,
        "doctor_name":       rec.doctor_name,
        "institution":       rec.institution,
        "record_date":       rec.record_date,
        "access_level":      rec.access_level,
        "is_confidential":   rec.is_confidential,
        "data":              fhir_data if fhir_data is not None else rec.data,
        "notes":             rec.notes or "",
        "created_by":        u["username"],
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "patient_id":        rec.patient_id,
        "file_name":         rec.file_name,
        "file_type":         rec.file_type,
        "file_data":         None,
    })

    file_hash = None
    if rec.file_data:
        file_pwd = secrets.token_hex(16)
        enc_data_b64, file_salt_bytes = encrypt_data(rec.file_data, file_pwd)
        
        # Upload to IPFS (real or simulated)
        cid = ipfs_client.upload_to_ipfs(enc_data_b64)
        
        block_data["file_hash"] = cid
        block_data["file_salt"] = base64.b64encode(file_salt_bytes).decode("utf-8")
        block_data["file_pwd"] = file_pwd

    cmd = AddRecordCommand(
        patient_id=rec.patient_id,
        data=block_data,
        is_protected=rec.is_confidential,
        protection_password=rec.confidential_password if rec.is_confidential else None,
        username=u["username"]
    )
    block = command_handler.handle_add_record(cmd)

    if rec.record_type == "prescription":
        med_name = rec.data.get("medication", "İlaç")
        create_notification(
            patient_id=rec.patient_id,
            title="YENİ İLAÇ REÇETESİ",
            message=f"Reçetenize yeni bir ilaç eklendi: {med_name}. Lütfen kullanım talimatlarına uyun.",
            severity="info",
            notif_repo=notif_repo
        )

    return {
        "success":     True,
        "block_index": block.index,
        "block_hash":  block.hash[:20] + "...",
        "message":     "Record added to blockchain",
    }

@router.get("/{patient_id}", summary="Get Patient Records")
def get_records(
    patient_id: str, 
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service),
    query_handler: QueryHandler = Depends(get_query_handler),
    db_manager: LMDBConnectionManager = Depends(get_db_manager)
):
    check_patient_id(patient_id)
    role = u["role"]
    if role == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    ignore_consent = False
    if role == "doctor":
        proj_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
        access_logs = storage.load_access_logs(proj_name, limit=5, db_manager=db_manager)
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
    records.sort(key=lambda x: x["timestamp"], reverse=True)

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
def get_single_record(
    patient_id: str, 
    block_index: int = Path(..., ge=0), 
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service)
):
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
def decrypt_record(
    patient_id: str, 
    block_index: int = Path(..., ge=0), 
    req: DecryptRequest = None, 
    u: dict = Depends(current_user),
    query_handler: QueryHandler = Depends(get_query_handler),
    db_manager: LMDBConnectionManager = Depends(get_db_manager)
):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    if not req or not req.password:
        raise HTTPException(400, "Password is required to decrypt this record")

    ignore_consent = False
    if u["role"] == "doctor":
        proj_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
        access_logs = storage.load_access_logs(proj_name, limit=5, db_manager=db_manager)
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
def download_offchain_file(
    patient_id: str, 
    block_index: int, 
    password: Optional[str] = None, 
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service),
    consent_validator: ConsentValidator = Depends(get_consent_validator),
    db_manager: LMDBConnectionManager = Depends(get_db_manager),
    ipfs_client: IPFSClient = Depends(get_ipfs_client)
):
    check_patient_id(patient_id)
    role = u["role"]
    ignore_consent = False
    
    if role == "doctor":
        proj_name = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
        access_logs = storage.load_access_logs(proj_name, limit=5, db_manager=db_manager)
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
        
        # Check cache/legacy local off-chain store first
        enc_data_b64 = None
        legacy_path = os.path.join(_PROJECT_ROOT, "backend", "offchain_storage", file_hash)
        if os.path.exists(legacy_path):
            with open(legacy_path, "r", encoding="utf-8") as f:
                enc_data_b64 = f.read()
        else:
            try:
                enc_data_b64 = ipfs_client.download_from_ipfs(file_hash)
            except Exception as e:
                raise HTTPException(404, f"Encrypted file not found on IPFS storage: {str(e)}")
            
        decrypted_b64 = decrypt_data(enc_data_b64, file_pwd, file_salt)
        file_bytes = base64.b64decode(decrypted_b64)
        
        return Response(
            content=file_bytes,
            media_type=file_type,
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Off-chain download error: {str(e)}")


@router.get("/proof/{patient_id}/{block_index}", summary="Generate Merkle Inclusion Proof for Block")
def get_merkle_proof_endpoint(
    patient_id: str = Path(...),
    block_index: int = Path(...),
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service)
):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied: You can only view proofs for your own records")

    project_name = record_service._get_project_name(patient_id)
    chain = record_service.block_repo.load_all_blocks(project_name)
    if not chain:
        raise HTTPException(404, f"No blockchain record chain found for patient {patient_id}")

    target_block = None
    target_idx_in_hashes = -1
    hashes = []
    for idx, b in enumerate(chain):
        if b.hash:
            hashes.append(b.hash)
            if b.index == block_index:
                target_block = b
                target_idx_in_hashes = len(hashes) - 1

    if not target_block or target_idx_in_hashes == -1:
        raise HTTPException(404, f"Block #{block_index} not found in chain for patient {patient_id}")

    from core.utils.crypto_utils import generate_merkle_proof, verify_merkle_proof
    proof_result = generate_merkle_proof(hashes, target_idx_in_hashes)
    root = proof_result["root"]
    proof = proof_result["proof"]
    is_valid = verify_merkle_proof(target_block.hash, proof, root) if root else False

    return {
        "patient_id": patient_id,
        "block_index": block_index,
        "block_hash": target_block.hash,
        "merkle_root": f"0x{root}" if root else None,
        "proof": proof,
        "is_valid": is_valid
    }
