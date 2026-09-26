import os
import re
import time
import base64
import secrets
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Request, Response, Path
from pydantic import ValidationError

from backend.dependencies import (
    current_user, get_record_service, get_command_handler, get_query_handler, get_consent_validator, get_db_manager,
    get_attachment_store, get_notification_repository
)
from core.ports.repositories import INotificationRepository
from core.services.attachment_store import AttachmentStore
from backend.schemas.requests import (
    RecordCreate, DecryptRequest, CorrectionCreate, RECORD_TYPES, DATA_SCHEMAS
)
from core.security import encrypt_data, decrypt_data, get_device_id
from core.cqrs.commands import AddRecordCommand, AddCorrectionCommand
from core.cqrs.queries import GetPatientRecordsQuery, DecryptRecordQuery
import database.storage as storage
from database.connection import LMDBConnectionManager
from core.services.record_service import RecordService
from core.cqrs.commands import CommandHandler
from core.cqrs.queries import QueryHandler
from core.services.consent_validator import ConsentValidator
from core.services import access_policy

router = APIRouter(prefix="/api/v1/records", tags=["records"])

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.dual_control import dual_control_engine
from core.services.alert_service import alert_service
from backend.dependencies import _get_client_ip
from core.pseudonymization.service import project_name_for

def check_patient_id(patient_id: str):
    if not re.match(r"^[a-zA-Z0-9_\-]+$", patient_id):
        raise HTTPException(400, "Invalid patient_id format")

# The content a correction may change — the fields the record form sends.
CORRECTABLE_FIELDS = (
    "record_type", "title", "doctor_name", "institution",
    "record_date", "data", "notes",
)
# Who may see a record is not content: a correction always carries the original
# access level over, so it cannot widen (or narrow) a record's audience.
CARRIED_OVER_FIELDS = CORRECTABLE_FIELDS + ("access_level",)


# Who may see which record is decided in one place: core/services/access_policy.py.
# The helpers below only connect it to the request (the user, the consent store).

NO_CONSENT = "No active consent from this client."


def _consent_for(consent_validator: ConsentValidator, patient_id: str, username: str):
    """The `has_consent(record_type)` callable the access policy expects."""
    return lambda record_type: consent_validator.has_consent(patient_id, username, record_type)


def _require_file_access(u: dict, patient_id: str, consent_validator: ConsentValidator):
    """File level: a client opens only their own file; a practitioner only the
    file of a client who has given them some active consent. The answer is the
    same whether or not the client exists, so client IDs cannot be probed."""
    if u["role"] == "client" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    if u["role"] == "practitioner" and not consent_validator.has_any_consent(patient_id, u["username"]):
        raise HTTPException(403, NO_CONSENT)


def _can_view(u: dict, patient_id: str, record, consent_validator: ConsentValidator) -> bool:
    """Record level, for decrypted content."""
    return access_policy.can_view(u["role"], u["username"], record,
                                  _consent_for(consent_validator, patient_id, u["username"]))


def _can_view_stored(u: dict, patient_id: str, block_index: int, data,
                     consent_validator: ConsentValidator, record_service: RecordService) -> bool:
    """Record level, for a block as stored (maybe still password-protected, in
    which case its audience is read from outside the ciphertext)."""
    protected_access = (record_service.get_block_access(patient_id, block_index)
                        if isinstance(data, str) else None)
    return access_policy.can_view_stored(u["role"], u["username"], data,
                                         _consent_for(consent_validator, patient_id, u["username"]),
                                         protected_access)

# Operator roles that administer the vault but have no clinical relationship with
# the patient. None of them may read raw records on their own authority.
PRIVILEGED_NON_CLINICAL_ROLES = ("admin", "security_officer", "auditor")


def _enforce_privileged_dual_control(request: Request, u: dict, patient_id: str):
    if u.get("role") in PRIVILEGED_NON_CLINICAL_ROLES:
        dc_token = request.headers.get("X-Dual-Control-Token") or request.query_params.get("dual_control_token")
        if not dc_token or not dual_control_engine.is_dual_control_approved(dc_token, patient_id):
            client_ip = _get_client_ip(request)
            alert_service.raise_alert(
                alert_type="DUAL_CONTROL_VIOLATION_BLOCKED",
                severity="CRITICAL",
                title=f"Admin Dual-Control Access Blocked for {patient_id}",
                description=f"Admin {u.get('username')} attempted unauthorized raw record access to client {patient_id} without an active Security Officer co-signed token.",
                username=u.get("username"),
                client_ip=client_ip,
                extra={"patient_id": patient_id, "token_provided": dc_token}
            )
            raise HTTPException(
                status_code=403,
                detail=f"Dual-Control Policy Violation: privileged operators cannot view or decrypt client records without an active co-signed token for patient {patient_id}. Open Dual-Control Access to request one."
            )

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
    attachments: AttachmentStore = Depends(get_attachment_store),
    notif_repo: INotificationRepository = Depends(get_notification_repository),
    consent_validator: ConsentValidator = Depends(get_consent_validator)
):
    if u["role"] == "client" and u.get("patient_id") != rec.patient_id:
        raise HTTPException(403, "You can only access your own records")
    if u["role"] not in ("practitioner", "admin", "client"):
        raise HTTPException(403, "You do not have permission to add records")

    # Writing needs the same consent as reading: a practitioner used to be able
    # to add records to any client's file, consent or not.
    allowed_levels = access_policy.CREATABLE_LEVELS.get(u["role"])
    if allowed_levels is not None and rec.access_level not in allowed_levels:
        raise HTTPException(403, "You cannot create a record with this access level")
    if not access_policy.can_create(u["role"], rec.access_level, rec.record_type,
                                    _consent_for(consent_validator, rec.patient_id, u["username"])):
        raise HTTPException(403, "Client consent is required to add this type of record")

    # Check the type-specific `data` fields. Free-form types have no schema.
    schema = DATA_SCHEMAS.get(rec.record_type)
    try:
        if schema:
            schema(**rec.data)
    except ValidationError as e:
        err_msgs = [".".join(str(x) for x in error["loc"]) + ": " + error["msg"] for error in e.errors()]
        raise HTTPException(status_code=422, detail=f"Validation failed: {', '.join(err_msgs)}")

    # Stored verbatim; the client escapes at render. See sanitize_html().
    block_data = ({
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
    })

    if rec.file_data:
        file_pwd = secrets.token_hex(16)
        enc_data_b64, file_salt_bytes = encrypt_data(rec.file_data, file_pwd)

        # Store the (already-encrypted) blob in the encrypted attachment store.
        ref = attachments.put(enc_data_b64)

        block_data["file_hash"] = ref
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

    if rec.record_type == "homework":
        # Notifications live in the SQL store in plaintext, so they must never
        # carry clinical detail (e.g. what the homework is about) — that would
        # leak data the chain took care to encrypt. Point the client at their
        # records instead of repeating the content.
        create_notification(
            patient_id=rec.patient_id,
            title="YENİ ÖDEV",
            message="Uzmanınız sizinle yeni bir ödev paylaştı. Ayrıntılar için kayıtlarınıza bakın.",
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
    request: Request,
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service),
    query_handler: QueryHandler = Depends(get_query_handler),
    db_manager: LMDBConnectionManager = Depends(get_db_manager),
    consent_validator: ConsentValidator = Depends(get_consent_validator)
):
    check_patient_id(patient_id)
    _enforce_privileged_dual_control(request, u, patient_id)
    _require_file_access(u, patient_id, consent_validator)
    role = u["role"]

    query = GetPatientRecordsQuery(
        patient_id=patient_id,
        requester_username=u["username"],
        requester_role=role,
    )
    records = query_handler.handle_get_patient_records(query)
    records.sort(key=lambda x: x["timestamp"], reverse=True)

    from core.events.event_bus import SystemAuditEvent, event_bus
    proj_name = record_service._get_project_name(patient_id)
    event_bus.publish(SystemAuditEvent(
        project_name=proj_name,
        action="RECORDS_VIEWED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"record_count": len(records)}
    ))

    # A patient viewing their own chart is not "access" worth surfacing to them;
    # a clinician or operator reading it is exactly what the transparency ledger
    # exists to record, so that lands in the tamper-evident access log.
    if not (u["role"] == "client" and u.get("patient_id") == patient_id):
        storage.append_access_log(
            project_name=proj_name,
            username=u["username"],
            action="RECORDS_VIEWED",
            device_id=get_device_id(),
            extra={"role": u["role"], "record_count": len(records),
                   "client_ip": _get_client_ip(request)},
            db_manager=db_manager,
        )

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
    request: Request,
    block_index: int = Path(..., ge=0),
    version: str = "current",
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service),
    consent_validator: ConsentValidator = Depends(get_consent_validator)
):
    # This endpoint used to check only that a client stayed in their own file:
    # any practitioner could read any client's unprotected records, with or
    # without consent, by walking block numbers (an IDOR). It now applies the
    # same policy as the record list.
    check_patient_id(patient_id)
    _enforce_privileged_dual_control(request, u, patient_id)
    _require_file_access(u, patient_id, consent_validator)

    # A record the user may not see gets the same answer as one that does not
    # exist, just as the list leaves it out rather than showing it locked.
    not_found = HTTPException(404, "Block not found")
    chain = record_service.get_chain(patient_id)
    block = next((b for b in chain if b.index == block_index), None)
    if block is None:
        raise not_found

    if block.is_protected:
        if not _can_view_stored(u, patient_id, block_index, block.data, consent_validator, record_service):
            raise not_found
        return {
            "block_index": block_index,
            "is_protected": True,
            "data": "ENCRYPTED — use POST /decrypt with the correct password",
        }

    # version=original returns the pre-correction content; the original block is
    # never modified, so both versions remain readable. Both are checked, though
    # a correction carries the original's access level over.
    original = record_service.get_original_block_data(patient_id, block_index)
    if not _can_view_stored(u, patient_id, block_index, original, consent_validator, record_service):
        raise not_found
    if version == "original":
        data = original
    else:
        data = record_service.get_final_block_data(patient_id, block_index, password=None, username=u["username"])
        if not _can_view_stored(u, patient_id, block_index, data, consent_validator, record_service):
            raise not_found
    return {"block_index": block_index, "is_protected": False, "version": version, "data": data}

@router.post("/{patient_id}/{block_index}/decrypt", summary="Decrypt Encrypted Record")
def decrypt_record(
    patient_id: str,
    request: Request,
    block_index: int = Path(..., ge=0),
    req: DecryptRequest = None,
    u: dict = Depends(current_user),
    query_handler: QueryHandler = Depends(get_query_handler),
    db_manager: LMDBConnectionManager = Depends(get_db_manager),
    consent_validator: ConsentValidator = Depends(get_consent_validator)
):
    check_patient_id(patient_id)
    _enforce_privileged_dual_control(request, u, patient_id)
    _require_file_access(u, patient_id, consent_validator)

    if not req or not req.password:
        raise HTTPException(400, "Password is required to decrypt this record")

    query = DecryptRecordQuery(
        patient_id=patient_id,
        block_index=block_index,
        password=req.password,
        requester_username=u["username"],
        requester_role=u["role"],
    )
    data = query_handler.handle_decrypt_record(query)

    if isinstance(data, str) and ("INCORRECT" in data or "SECURE" in data or "ERROR" in data):
        raise HTTPException(403, "Incorrect password — decryption failed")

    # Record immutable audit access log
    proj_name = project_name_for(patient_id)
    storage.append_access_log(
        project_name=proj_name,
        username=u["username"],
        action="RECORD_DECRYPTED",
        device_id=get_device_id(),
        extra={
            "block_index": block_index,
            "role": u["role"],
            "client_ip": _get_client_ip(request)
        },
        db_manager=db_manager
    )

    from core.events.event_bus import SystemAuditEvent, event_bus
    event_bus.publish(SystemAuditEvent(
        project_name=proj_name,
        action="RECORD_DECRYPTED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"block_index": block_index, "role": u["role"]}
    ))

    return {"block_index": block_index, "data": data}

@router.post("/{patient_id}/{block_index}/correct", summary="Correct a Record (append-only)")
def correct_record(
    patient_id: str,
    request: Request,
    block_index: int = Path(..., ge=1),
    req: CorrectionCreate = None,
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service),
    command_handler: CommandHandler = Depends(get_command_handler),
    consent_validator: ConsentValidator = Depends(get_consent_validator),
    db_manager: LMDBConnectionManager = Depends(get_db_manager),
):
    """
    Append a correction. The original block is never modified — a client record
    is not overwritten, it is superseded by a correction, and both remain on the
    chain. The same access gates as reading apply, since correcting requires
    seeing the record first.
    """
    check_patient_id(patient_id)
    _enforce_privileged_dual_control(request, u, patient_id)
    _require_file_access(u, patient_id, consent_validator)
    if u["role"] not in ("practitioner", "admin", "client"):
        raise HTTPException(403, "You do not have permission to correct records")
    if not req or not isinstance(req.corrected_data, dict) or not req.corrected_data:
        raise HTTPException(400, "corrected_data (the superseding record) is required")

    original = record_service.get_block_data(patient_id, block_index, username=u["username"])
    if original is None:
        raise HTTPException(404, "Record not found")
    if isinstance(original, str):
        # Password-protected records need their password to read and re-seal;
        # correcting them is out of scope for this flow.
        raise HTTPException(400, "Password-protected records cannot be corrected here")
    if not isinstance(original, dict) or original.get("type") in ("audit", "correction"):
        raise HTTPException(400, "Only clinical records can be corrected")

    rec_type = original.get("record_type", "other")

    # Correcting requires the same access as reading the record — for every role
    # now, so a client cannot correct a practitioner's own process note either.
    if not _can_view(u, patient_id, original, consent_validator):
        raise HTTPException(403, "Client consent is required to correct this record")

    # A correction must pass the same checks as a new record: this endpoint used
    # to store corrected_data as-is, so any record_type, any data shape and any
    # extra key went straight onto the chain. Fields the client leaves out are
    # taken from the original; keys outside CORRECTABLE_FIELDS are dropped.
    merged = {k: original[k] for k in CARRIED_OVER_FIELDS if original.get(k) is not None}
    merged.update({k: v for k, v in req.corrected_data.items() if k in CORRECTABLE_FIELDS})
    merged.setdefault("record_type", rec_type)
    try:
        checked = RecordCreate(patient_id=patient_id, **merged)
        schema = DATA_SCHEMAS.get(checked.record_type)
        if schema:
            schema(**checked.data)
    except ValidationError as e:
        err_msgs = [".".join(str(x) for x in err["loc"]) + ": " + err["msg"] for err in e.errors()]
        raise HTTPException(status_code=422, detail=f"Validation failed: {', '.join(err_msgs)}")

    # The corrected version is a new record too: changing its type must not move
    # it to a type the practitioner holds no consent for.
    if not access_policy.can_create(u["role"], checked.access_level, checked.record_type,
                                    _consent_for(consent_validator, patient_id, u["username"])):
        raise HTTPException(403, "Client consent is required to correct this record")

    corrected = checked.model_dump(include=set(CARRIED_OVER_FIELDS))
    corrected["record_type_label"] = RECORD_TYPES[checked.record_type]
    corrected["patient_id"] = patient_id
    corrected["created_by"] = u["username"]
    corrected["created_at"] = datetime.now(timezone.utc).isoformat()

    cmd = AddCorrectionCommand(
        patient_id=patient_id,
        block_index=block_index,
        corrected_data=corrected,
        username=u["username"],
        reason=req.reason,
    )
    correction_block = command_handler.handle_add_correction(cmd)

    storage.append_access_log(
        project_name=project_name_for(patient_id),
        username=u["username"],
        action="RECORD_CORRECTED",
        device_id=get_device_id(),
        extra={"block_index": block_index, "correction_index": correction_block.index,
               "reason": req.reason, "client_ip": _get_client_ip(request)},
        db_manager=db_manager,
    )

    return {
        "success": True,
        "corrected_block_index": block_index,
        "correction_block_index": correction_block.index,
        "message": "Correction appended. The original record remains on the chain.",
    }


@router.get("/offchain/download/{patient_id}/{block_index}", summary="Download Off-chain File")
def download_offchain_file(
    patient_id: str,
    block_index: int,
    request: Request,
    password: Optional[str] = None,
    u: dict = Depends(current_user),
    record_service: RecordService = Depends(get_record_service),
    consent_validator: ConsentValidator = Depends(get_consent_validator),
    db_manager: LMDBConnectionManager = Depends(get_db_manager),
    attachments: AttachmentStore = Depends(get_attachment_store)
):
    check_patient_id(patient_id)
    _enforce_privileged_dual_control(request, u, patient_id)
    _require_file_access(u, patient_id, consent_validator)
    denied = HTTPException(403, "Access denied: client consent is required to download this file.")

    # Checked BEFORE decrypting. This used to accept consent for *any* type, so
    # consent for one kind of record opened the attachments of every other kind.
    # An encrypted record's type is unknown until it is decrypted, so it needs
    # consent for all records — otherwise a practitioner without consent could
    # still use this endpoint to test passwords ("wrong password" vs "denied").
    meta = record_service.get_block_data(patient_id, block_index, username=u["username"])
    if meta is None:
        raise HTTPException(404, "Record not found")
    if not _can_view_stored(u, patient_id, block_index, meta, consent_validator, record_service):
        raise denied

    try:
        data = record_service.get_final_block_data(patient_id, block_index, password=password, username=u["username"])
        if isinstance(data, str) and ("SECURE" in data or "INCORRECT" in data or "ERROR" in data):
            raise HTTPException(400, f"Decryption failed: {data}")

        # Checked again AFTER decrypting, when the real access level is known.
        if not _can_view(u, patient_id, data, consent_validator):
            raise denied
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
                enc_data_b64 = attachments.get(file_hash)
            except Exception as e:
                raise HTTPException(404, f"Encrypted attachment not found: {str(e)}")

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
    record_service: RecordService = Depends(get_record_service),
    consent_validator: ConsentValidator = Depends(get_consent_validator)
):
    # A proof holds no record content, but it confirms that a block exists and
    # when the chain last changed — so it follows the same rules as reading.
    check_patient_id(patient_id)
    _require_file_access(u, patient_id, consent_validator)
    if u["role"] in ("practitioner", "client"):
        stored = record_service.get_final_block_data(patient_id, block_index, password=None, username=u["username"])
        if stored is None or not _can_view_stored(u, patient_id, block_index, stored, consent_validator, record_service):
            raise HTTPException(404, f"Block #{block_index} not found in chain for patient {patient_id}")

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
