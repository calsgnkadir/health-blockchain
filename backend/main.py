"""
backend/main.py — VIP Health Vault · Backend API v3.0
======================================================
Security features:
  - JWT token authentication (required env secret)
  - LMDB-based Argon2 hashed user database
  - Role-based access control (RBAC)
  - Rate limiting (brute-force prevention)
  - Hardware device fingerprint verification
  - Audit logs for every transaction
  - CORS restriction

Running:
  uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Depends, Request, status, Cookie, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator, ValidationError
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import jwt
import json
import os
import sys
import time
import threading
import secrets

# ── Path Configuration ───────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.blockchain import Blockchain
from core.security import (
    verify_password, hash_password,
    get_device_id, validate_password,
)
import database.storage as storage
import core.totp as totp

# Clean Architecture Dependency Injection
from core.domain.entities import User, Block
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository, LMDBBlockRepository, LMDBAuditRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
from core.services.auth_service import AuthService
from core.services.record_service import RecordService
from core.services.audit_service import AuditService

user_repository = LMDBUserRepository()
block_repository = LMDBBlockRepository()
audit_repository = LMDBAuditRepository()
crypto_strategy = AESGCMStrategy()

auth_service = AuthService(user_repository)
record_service = RecordService(block_repository, crypto_strategy)
audit_service = AuditService(audit_repository, record_service)


# ── Application ─────────────────────────────────────────────────
app = FastAPI(
    title="VIP Health Vault API",
    version="3.0.0",
    description="Blockchain-based VIP health record system",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)

@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    # Only enforce CSRF for API state-changing routes
    path = request.url.path
    if (
        request.method in ("GET", "HEAD", "OPTIONS")
        or not path.startswith("/api/")
        or path == "/api/auth/login"
    ):
        response = await call_next(request)
        # Ensure csrf_token cookie is present for the client to read
        if not request.cookies.get("csrf_token"):
            env = os.environ.get("ENVIRONMENT", "production")
            is_secure = (env == "production")
            response.set_cookie(
                "csrf_token",
                secrets.token_hex(32),
                samesite="strict",
                secure=is_secure,
                httponly=False  # Must be readable by JavaScript
            )
        return response

    # Unsafe requests (POST, PUT, DELETE) on API paths
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_header = request.headers.get("x-csrf-token")

    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        return JSONResponse(
            status_code=403,
            content={"detail": "CSRF token validation failed — missing or mismatched token"}
        )

    return await call_next(request)

# ── JWT RSA Key Configuration ──────────────────────────────
_JWT_PRIVATE_KEY_FILE = os.path.join(os.path.dirname(__file__), ".jwt_private.pem")
_JWT_PUBLIC_KEY_FILE = os.path.join(os.path.dirname(__file__), ".jwt_public.pem")

def _load_or_generate_jwt_rsa_keys() -> tuple[str, str]:
    """Loads RSA private and public keys, generating them if they do not exist."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    if os.path.exists(_JWT_PRIVATE_KEY_FILE) and os.path.exists(_JWT_PUBLIC_KEY_FILE):
        with open(_JWT_PRIVATE_KEY_FILE, "r") as f:
            private_pem = f.read()
        with open(_JWT_PUBLIC_KEY_FILE, "r") as f:
            public_pem = f.read()
        return private_pem, public_pem

    # Generate keys
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode("utf-8")

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")

    # Save to files
    with open(_JWT_PRIVATE_KEY_FILE, "w") as f:
        f.write(private_pem)
    with open(_JWT_PUBLIC_KEY_FILE, "w") as f:
        f.write(public_pem)

    print("[OK] Generated new RSA key pair for JWT signing.")
    return private_pem, public_pem

JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = _load_or_generate_jwt_rsa_keys()
ALGORITHM = "RS256"
TOKEN_HOURS = 8   # 8 hours

security_bearer = HTTPBearer(auto_error=False)

# ── Rate Limiting ─────────────────────────────────────────────
_login_attempts: Dict[str, List[float]] = defaultdict(list)
_rate_lock = threading.Lock()
RATE_LIMIT_WINDOW = 60   # seconds
RATE_LIMIT_MAX = 5       # max 5 login attempts per minute

def _check_rate_limit(ip: str) -> bool:
    """Returns True if allowed, False if rate limit exceeded."""
    now = time.time()
    with _rate_lock:
        attempts = _login_attempts[ip]
        # Clear attempts outside the time window
        _login_attempts[ip] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
        if len(_login_attempts[ip]) >= RATE_LIMIT_MAX:
            return False
        _login_attempts[ip].append(now)
        return True

def _get_client_ip(request: Request) -> str:
    """Extracts client IP from X-Forwarded-For if behind a proxy, otherwise client host."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ── Blockchain Cache ──────────────────────────────────────────
_blockchains: Dict[str, Blockchain] = {}
_bc_lock = threading.Lock()

def get_blockchain(patient_id: str) -> Blockchain:
    with _bc_lock:
        if patient_id not in _blockchains:
            proj = f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"
            if not storage.project_exists(proj):
                storage.create_project(proj)
            _blockchains[patient_id] = Blockchain(proj)
        return _blockchains[patient_id]

# ── Health Record Categories ────────────────────────────────
RECORD_TYPES = {
    "diagnosis":     "Diagnosis",
    "lab_result":    "Lab Result",
    "prescription":  "Prescription",
    "surgery":       "Surgery",
    "vaccination":   "Vaccination",
    "imaging":       "Imaging (MRI/CT/X-Ray)",
    "vital_signs":   "Vital Signs",
    "allergy":       "Allergy",
    "psychology":    "Psychology",
    "genetic":       "Genetics",
    "emergency":     "Emergency",
    "other":         "Other",
}

ACCESS_LEVELS = {
    "private":        "Patient Only",
    "doctor_shared":  "Patient + Doctor",
    "emergency":      "Emergency Access",
    "admin_only":     "Administrator Only",
}

# ── Default User Seed ──────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """Initialize user database on startup."""
    env = os.environ.get("ENVIRONMENT", "production")
    if env == "development":
        storage.seed_default_users()
        print("[INFO] Seeding default users (Development Mode)")
    else:
        print("[INFO] Production Mode — Skipping default user seeding")
    print(f"[OK] VIP Health Vault API v3.0 ready - Device: {get_device_id()[:16]}...")

# ──────────────────────────────────────────────────────────────
# AUTH HELPERS
# ──────────────────────────────────────────────────────────────

def create_token(user: dict) -> str:
    payload = {
        "sub":      user["username"],
        "role":     user["role"],
        "user_id":  user["id"],
        "exp":      datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
        "iat":      datetime.now(timezone.utc),
        "device":   get_device_id()[:16],
    }
    return jwt.encode(payload, JWT_PRIVATE_KEY, algorithm=ALGORITHM)
def current_user(
    access_token: Optional[str] = Cookie(None),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> dict:
    token = access_token
    if not token and creds:
        token = creds.credentials

    if not token:
        raise HTTPException(401, "Not authenticated — access token is missing")

    try:
        payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = user_repository.load_user(username)
        if not user:
            raise HTTPException(401, "Invalid token — user not found")
        return user.to_dict()
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")


def require_role(*roles: str):
    """Dependency factory to enforce specific roles."""
    def dependency(u: dict = Depends(current_user)) -> dict:
        if u["role"] not in roles:
            raise HTTPException(403, f"Unauthorized action. Required roles: {roles}")
        return u
    return dependency

# ──────────────────────────────────────────────────────────────
# AUTH ENDPOINTS
# ──────────────────────────────────────────────────────────────

class LoginReq(BaseModel):
    username: str
    password: str
    code: Optional[str] = None


@app.post("/api/auth/login", summary="User Login")
async def login(req: LoginReq, request: Request, response: Response):
    client_ip = _get_client_ip(request)

    # Rate limiting
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait 1 minute.",
        )

    user_entity = auth_service.authenticate(req.username, req.password, client_ip)
    if not user_entity:
        raise HTTPException(401, "Incorrect username or password")

    # Check if TOTP 2FA is enabled
    if user_entity.totp_enabled:
        if not req.code:
            return JSONResponse(
                status_code=200,
                content={"mfa_required": True}
            )
        # Verify 2FA code
        if not user_entity.totp_secret or not totp.verify_totp(user_entity.totp_secret, req.code):
            from core.events.event_bus import event_bus, SystemAuditEvent
            event_bus.publish(SystemAuditEvent(
                project_name="__system__",
                action="LOGIN_MFA_FAILED",
                username=req.username,
                device_id=get_device_id(),
                extra={"ip": client_ip},
            ))
            raise HTTPException(401, "Invalid 2FA verification code")

    auth_service.login_success(user_entity, client_ip)
    user = user_entity.to_dict()
    token = create_token(user)

    env = os.environ.get("ENVIRONMENT", "production")
    is_secure = (env == "production")
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        max_age=TOKEN_HOURS * 3600,
    )

    return {
        "access_token": token,
        "token_type":   "bearer",
        "expires_in":   TOKEN_HOURS * 3600,
        "user": {
            "id":         user["id"],
            "username":   user["username"],
            "role":       user["role"],
            "full_name":  user["full_name"],
            "patient_id": user.get("patient_id"),
            "totp_enabled": bool(user.get("totp_enabled")),
        },
    }



@app.get("/api/auth/me", summary="Current User Info")
def me(u: dict = Depends(current_user)):
    return {
        "id":         u["id"],
        "username":   u["username"],
        "role":       u["role"],
        "full_name":  u["full_name"],
        "patient_id": u.get("patient_id"),
        "totp_enabled": bool(u.get("totp_enabled")),
    }

@app.post("/api/auth/logout", summary="User Logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"success": True, "message": "Logged out successfully"}

class Verify2FAReq(BaseModel):
    code: str

@app.post("/api/auth/2fa/setup", summary="Setup 2FA TOTP")
def setup_2fa(u: dict = Depends(current_user)):
    """Generates a temporary secret and QR code for the user to register in their app."""
    user_entity = User.from_dict(u)
    res = auth_service.setup_2fa(user_entity)
    return res

@app.post("/api/auth/2fa/enable", summary="Verify and Enable 2FA")
def enable_2fa(req: Verify2FAReq, u: dict = Depends(current_user)):
    """Verifies the code and enables 2FA for the user."""
    user_entity = User.from_dict(u)
    if not user_entity.totp_secret:
        raise HTTPException(400, "2FA setup has not been initiated. Call /api/auth/2fa/setup first.")
    
    if auth_service.enable_2fa(user_entity, req.code):
        return {"success": True, "message": "Two-factor authentication enabled successfully"}
    else:
        raise HTTPException(400, "Invalid verification code. Please check your app and try again.")

@app.post("/api/auth/2fa/disable", summary="Disable 2FA")
def disable_2fa(req: Verify2FAReq, u: dict = Depends(current_user)):
    """Verifies the code and disables 2FA for the user."""
    user_entity = User.from_dict(u)
    if not user_entity.totp_enabled:
        raise HTTPException(400, "2FA is not enabled for this account.")
        
    if not user_entity.totp_secret:
        raise HTTPException(500, "Database inconsistency: enabled 2FA but missing secret.")
        
    if auth_service.disable_2fa(user_entity, req.code):
        return {"success": True, "message": "Two-factor authentication disabled successfully"}
    else:
        raise HTTPException(400, "Invalid verification code. Disable failed.")


# ──────────────────────────────────────────────────────────────
# USER MANAGEMENT (Admin Only)
# ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    full_name: str
    patient_id: Optional[str] = None
    specialty: Optional[str] = None
    institution: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        valid, msg = validate_password(v)
        if not valid:
            raise ValueError(msg)
        return v

    @field_validator("role")
    @classmethod
    def valid_role(cls, v):
        allowed = {"admin", "doctor", "vip_patient", "nurse", "auditor"}
        if v not in allowed:
            raise ValueError(f"Invalid role. Allowed roles: {allowed}")
        return v


@app.get("/api/admin/users", summary="All Users")
def list_users(u: dict = Depends(require_role("admin"))):
    users = user_repository.load_all_users()
    return {"users": [
        {k: v for k, v in user.to_dict().items() if k not in ("password_hash", "totp_secret")}
        for user in users
    ]}


@app.post("/api/admin/users", summary="Create New User")
def create_user(data: UserCreate, u: dict = Depends(require_role("admin"))):
    if user_repository.user_exists(data.username):
        raise HTTPException(409, f"Username already exists: {data.username}")

    new_user = auth_service.create_user(
        username=data.username,
        password=data.password,
        role=data.role,
        full_name=data.full_name,
        patient_id=data.patient_id,
        specialty=data.specialty,
        institution=data.institution,
        creator_username=u["username"]
    )

    return {"success": True, "user_id": new_user.id}

# ──────────────────────────────────────────────────────────────
# HEALTH RECORDS
# ──────────────────────────────────────────────────────────────

class VitalSignsSchema(BaseModel):
    blood_pressure: str
    heart_rate: int
    temperature: float
    oxygen_sat: int

    @field_validator("heart_rate")
    @classmethod
    def check_heart_rate(cls, v):
        if not (1 <= v <= 300):
            raise ValueError("Heart rate must be between 1 and 300 bpm")
        return v

    @field_validator("temperature")
    @classmethod
    def check_temp(cls, v):
        if not (30.0 <= v <= 45.0):
            raise ValueError("Temperature must be between 30.0°C and 45.0°C")
        return v

    @field_validator("oxygen_sat")
    @classmethod
    def check_spo2(cls, v):
        if not (0 <= v <= 100):
            raise ValueError("SpO2 oxygen saturation must be between 0% and 100%")
        return v

class AllergySchema(BaseModel):
    allergen: str
    reaction: str
    severity: str
    onset_date: str

    @field_validator("severity")
    @classmethod
    def check_severity(cls, v):
        allowed = {"Mild", "Moderate", "Severe"}
        if v not in allowed:
            raise ValueError(f"Severity must be one of {allowed}")
        return v

class PrescriptionSchema(BaseModel):
    medication: str
    dose: str
    frequency: str
    duration: int

    @field_validator("duration")
    @classmethod
    def check_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be a positive number of days")
        return v

class VaccinationSchema(BaseModel):
    vaccine_name: str
    lot_number: str
    dose_number: int
    next_dose: Optional[str] = None

    @field_validator("dose_number")
    @classmethod
    def check_dose(cls, v):
        if v <= 0:
            raise ValueError("Dose number must be a positive integer")
        return v

class LabResultSchema(BaseModel):
    test_name: str
    result_value: str
    reference_range: str
    unit: str

class DiagnosisSchema(BaseModel):
    icd_code: str
    severity: str
    symptoms: str

class SurgerySchema(BaseModel):
    procedure: str
    anesthesia: str
    duration_min: int
    outcome: str

    @field_validator("duration_min")
    @classmethod
    def check_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be a positive number of minutes")
        return v

class ImagingSchema(BaseModel):
    modality: str
    body_part: str
    findings: str
    radiologist: str

class RecordCreate(BaseModel):
    patient_id:      str
    record_type:     str
    title:           str
    doctor_name:     str
    institution:     str
    record_date:     str
    access_level:    str = "doctor_shared"
    is_confidential: bool = False
    confidential_password: Optional[str] = None
    data:            Dict[str, Any]
    notes:           Optional[str] = None
    file_name:       Optional[str] = None
    file_type:       Optional[str] = None
    file_data:       Optional[str] = None

    @field_validator("record_type")
    @classmethod
    def valid_record_type(cls, v):
        if v not in RECORD_TYPES:
            raise ValueError(f"Invalid record type: {v}")
        return v

    @field_validator("access_level")
    @classmethod
    def valid_access_level(cls, v):
        if v not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access level: {v}")
        return v

    @field_validator("file_data")
    @classmethod
    def file_data_size(cls, v):
        if v is not None:
            # 2MB binary is approximately 2.7MB base64 encoded
            max_len = int(2 * 1024 * 1024 * 4 / 3)
            if len(v) > max_len:
                raise ValueError("Attachment size exceeds the 2MB limit")
        return v

@app.post("/api/records", summary="Add Health Record")
def add_record(rec: RecordCreate, u: dict = Depends(current_user)):
    # Authorization checks
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
        err_msgs = []
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            err_msgs.append(f"{loc}: {error['msg']}")
        raise HTTPException(
            status_code=422,
            detail=f"Validation failed: {', '.join(err_msgs)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Validation error: {str(e)}"
        )

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
        "file_data":         rec.file_data,
    }

    block = record_service.add_record(
        patient_id=rec.patient_id,
        data=block_data,
        is_protected=rec.is_confidential,
        protection_password=rec.confidential_password if rec.is_confidential else None,
        username=u["username"],
    )

    return {
        "success":     True,
        "block_index": block.index,
        "block_hash":  block.hash[:20] + "...",
        "message":     "Record added to blockchain",
    }


@app.get("/api/records/{patient_id}", summary="Get Patient Records")
def get_records(patient_id: str, u: dict = Depends(current_user)):
    role = u["role"]

    # Authorization checks
    if role == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    chain = record_service.get_chain(patient_id)
    final_data = record_service.get_final_data(patient_id)
    records = []

    for block in chain:
        if block.index == 0:
            continue  # Skip Genesis block
        data = final_data.get(block.index)
        if data is None:
            continue

        # Do not show audit blocks as medical records
        if isinstance(data, dict) and data.get("type") == "audit":
            continue

        # Doctors cannot see private records
        if role == "doctor" and isinstance(data, dict) and data.get("access_level") == "private":
            continue

        entry = {
            "block_index":    block.index,
            "timestamp":      block.timestamp,
            "timestamp_iso":  datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat(),
            "is_protected":   block.is_protected,
            "is_correction":  isinstance(data, dict) and data.get("type") == "correction",
            "hash_preview":   block.hash[:24] + "...",
            "device_id":      block.device_id[:16] + "..." if block.device_id else None,
        }

        if block.is_protected:
            entry["title"]        = "ENCRYPTED VIP RECORD"
            entry["record_type"]  = "protected"
            entry["data"]         = None
            entry["file_name"]    = None
            entry["file_type"]    = None
            entry["file_data"]    = None
        elif isinstance(data, dict):
            entry["title"]        = data.get("title", "Untitled")
            entry["record_type"]  = data.get("record_type", "other")
            entry["record_type_label"] = data.get("record_type_label", "")
            entry["access_level"] = data.get("access_level", "")
            entry["doctor_name"]  = data.get("doctor_name", "")
            entry["institution"]  = data.get("institution", "")
            entry["record_date"]  = data.get("record_date", "")
            entry["data"]         = data.get("data", {})
            entry["notes"]        = data.get("notes", "")
            entry["file_name"]    = data.get("file_name")
            entry["file_type"]    = data.get("file_type")
            entry["file_data"]    = data.get("file_data")
        else:
            entry["title"] = str(data)[:80]
            entry["data"]  = None

        records.append(entry)

    records.sort(key=lambda x: x["timestamp"], reverse=True)

    # Access audit log
    from core.events.event_bus import SystemAuditEvent, event_bus
    event_bus.publish(SystemAuditEvent(
        project_name=record_service._get_project_name(patient_id),
        action="RECORDS_VIEWED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"record_count": len(records)}
    ))

    return {
        "patient_id":   patient_id,
        "total_blocks": len(chain),
        "records":      records,
        "chain_valid":  record_service.is_chain_valid(patient_id),
    }


@app.get("/api/records/{patient_id}/{block_index}", summary="Get Single Record (Public)")
def get_single_record(
    patient_id: str,
    block_index: int,
    u: dict = Depends(current_user),
):
    """Returns metadata for a single block. Encrypted blocks return a placeholder — use POST /decrypt."""
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    chain = record_service.get_chain(patient_id)
    block = chain[block_index] if 0 <= block_index < len(chain) else None
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


class DecryptRequest(BaseModel):
    password: str


@app.post("/api/records/{patient_id}/{block_index}/decrypt", summary="Decrypt Encrypted Record")
def decrypt_record(
    patient_id: str,
    block_index: int,
    req: DecryptRequest,
    u: dict = Depends(current_user),
):
    """
    Decrypts a confidential block using the provided password.
    Password is sent in the request body — never in the URL.
    """
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")

    if not req.password:
        raise HTTPException(400, "Password is required to decrypt this record")

    data = record_service.get_final_block_data(patient_id, block_index, password=req.password, username=u["username"])

    if isinstance(data, str) and (
        "INCORRECT" in data or "SECURE" in data or "ERROR" in data
    ):
        raise HTTPException(403, "Incorrect password — decryption failed")

    return {"block_index": block_index, "data": data}


# ──────────────────────────────────────────────────────────────
# BLOCKCHAIN STATUS / EXPLORER
# ──────────────────────────────────────────────────────────────

@app.get("/api/blockchain/{patient_id}/status", summary="Chain Status")
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


@app.get("/api/blockchain/{patient_id}/audit", summary="Access History")
def audit_log(
    patient_id: str,
    limit: int = 50,
    source: str = "db",
    u: dict = Depends(require_role("admin", "auditor")),
):
    logs = audit_service.get_audit_logs(patient_id, limit, source)
    return {"patient_id": patient_id, "logs": logs, "source": source}


@app.get("/api/blockchain/{patient_id}/access-logs", summary="Patient Access Log")
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



@app.get("/api/record-types", summary="Record Types")
def record_types():
    return {
        "types":         [{"value": k, "label": v} for k, v in RECORD_TYPES.items()],
        "access_levels": [{"value": k, "label": v} for k, v in ACCESS_LEVELS.items()],
    }


@app.get("/api/system/status", summary="System Status")
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


@app.get("/api/system/config", summary="Public System Configuration")
def get_system_config():
    return {
        "environment": os.environ.get("ENVIRONMENT", "production"),
    }

# ──────────────────────────────────────────────────────────────
# FRONTEND SERVER
# ──────────────────────────────────────────────────────────────
STATIC = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC):
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    async def frontend_root():
        return FileResponse(os.path.join(STATIC, "index.html"))

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend_spa(path: str = ""):
        # Skip API paths
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(os.path.join(STATIC, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
