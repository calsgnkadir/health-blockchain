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
import base64

# ── Path Configuration ───────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
from core.security import (
    verify_password, hash_password,
    get_device_id, validate_password,
    encrypt_data, decrypt_data,
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
from core.services.consent_validator import ConsentValidator
from core.cqrs.commands import (
    AddRecordCommand, AddCorrectionCommand, CreateUserCommand,
    GrantConsentCommand, RevokeConsentCommand, CommandHandler
)
from core.cqrs.queries import (
    GetPatientRecordsQuery, DecryptRecordQuery, ExportFHIRBundleQuery,
    GetNotificationsQuery, GetConsentsQuery, QueryHandler
)

user_repository = LMDBUserRepository()
block_repository = LMDBBlockRepository()
audit_repository = LMDBAuditRepository()
crypto_strategy = AESGCMStrategy()

auth_service = AuthService(user_repository)
record_service = RecordService(block_repository, crypto_strategy)
audit_service = AuditService(audit_repository, record_service)
consent_validator = ConsentValidator(block_repository)

command_handler = CommandHandler(record_service, auth_service, block_repository)
query_handler = QueryHandler(record_service, block_repository, consent_validator)


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
    from core.security import get_device_id

    # Check env vars first
    env_priv = os.getenv("VHV_JWT_PRIVATE_KEY")
    env_pub = os.getenv("VHV_JWT_PUBLIC_KEY")
    if env_priv and env_pub:
        return env_priv.strip(), env_pub.strip()

    # Get passphrase
    passphrase = os.getenv("VHV_JWT_PASSPHRASE", get_device_id()).encode("utf-8")

    if os.path.exists(_JWT_PRIVATE_KEY_FILE) and os.path.exists(_JWT_PUBLIC_KEY_FILE):
        try:
            with open(_JWT_PRIVATE_KEY_FILE, "rb") as f:
                private_data = f.read()
            # Try to load as encrypted key
            private_key = serialization.load_pem_private_key(private_data, password=passphrase)
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ).decode("utf-8")
            
            with open(_JWT_PUBLIC_KEY_FILE, "r") as f:
                public_pem = f.read()
            return private_pem, public_pem
        except Exception as e:
            print(f"[WARNING] Failed to load encrypted JWT private key: {e}. Generating new key pair.")

    # Generate keys
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    private_pem_unencrypted = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode("utf-8")

    # Encrypt for saving
    private_pem_encrypted = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase)
    )

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")

    # Save to files
    with open(_JWT_PRIVATE_KEY_FILE, "wb") as f:
        f.write(private_pem_encrypted)
    with open(_JWT_PUBLIC_KEY_FILE, "w") as f:
        f.write(public_pem)

    print("[OK] Generated new secure (encrypted) RSA key pair for JWT signing.")
    return private_pem_unencrypted, public_pem

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
    """Extracts client IP, respecting X-Forwarded-For ONLY if TRUST_PROXIES is enabled."""
    trust_proxies = os.getenv("TRUST_PROXIES", "false").lower() == "true"
    if trust_proxies:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

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
    demo_mode = os.getenv("VHV_DEMO_MODE", "false").lower() == "true"
    if env == "development" or demo_mode:
        storage.seed_default_users()
        print("[INFO] Seeding default users (Development/Demo Mode)")
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

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        import re
        if not re.match(r"^[a-zA-Z0-9_\.\-]{3,50}$", v):
            raise ValueError("Username must contain only alphanumeric characters, underscores, dots, or hyphens.")
        return v


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

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        import re
        if not re.match(r"^[a-zA-Z0-9_\.\-]{3,50}$", v):
            raise ValueError("Username must be between 3 and 50 characters and contain only alphanumeric characters, underscores, dots, or hyphens.")
        return v

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v):
        import re
        if v is not None:
            if not re.match(r"^[a-zA-Z0-9_\-]{3,50}$", v):
                raise ValueError("Patient ID must be between 3 and 50 characters and contain only alphanumeric characters, underscores, or hyphens.")
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

    cmd = CreateUserCommand(
        username=data.username,
        password=data.password,
        role=data.role,
        full_name=data.full_name,
        patient_id=data.patient_id,
        specialty=data.specialty,
        institution=data.institution,
        creator_username=u["username"]
    )
    new_user = command_handler.handle_create_user(cmd)

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

# ── HELPER FUNCTIONS ──────────────────────────────────────────────
def check_patient_id(patient_id: str):
    import re
    if not re.match(r"^[a-zA-Z0-9_\-]+$", patient_id):
        raise HTTPException(400, "Invalid patient_id format")

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


# ── CONSENT & NOTIFICATION REQUEST SCHEMAS ──────────────────────────
class ConsentGrantReq(BaseModel):
    patient_id: str
    doctor_username: str
    record_type: str
    duration_days: int

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v):
        import re
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("patient_id must contain only alphanumeric characters, underscores, and hyphens.")
        return v

    @field_validator("doctor_username")
    @classmethod
    def validate_doctor_username(cls, v):
        import re
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", v):
            raise ValueError("doctor_username must contain only alphanumeric characters, underscores, hyphens, and dots.")
        return v

    @field_validator("duration_days")
    @classmethod
    def validate_duration(cls, v):
        if v <= 0:
            raise ValueError("duration_days must be positive")
        return v

class BreakGlassReq(BaseModel):
    reason: str


# ── HEALTH RECORD SCHEMAS & VALIDATIONS ────────────────────────────
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

    @field_validator("patient_id")
    @classmethod
    def validate_patient_id(cls, v):
        import re
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("patient_id must contain only alphanumeric characters, underscores, and hyphens.")
        return v

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
            max_len = int(2 * 1024 * 1024 * 4 / 3)
            if len(v) > max_len:
                raise ValueError("Attachment size exceeds the 2MB limit")
        return v

class DecryptRequest(BaseModel):
    password: str
    block_index: int

    @field_validator("block_index")
    @classmethod
    def validate_block_index(cls, v):
        if v < 0:
            raise ValueError("block_index must be a non-negative integer.")
        return v


# ── HEALTH RECORD ENDPOINTS ────────────────────────────────────────
@app.post("/api/records", summary="Add Health Record")
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
        raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")

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
        
        import hashlib
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


@app.get("/api/records/{patient_id}", summary="Get Patient Records")
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


from fastapi import Path

@app.get("/api/records/{patient_id}/{block_index}", summary="Get Single Record")
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


@app.post("/api/records/{patient_id}/{block_index}/decrypt", summary="Decrypt Encrypted Record")
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


# ── OFF-CHAIN FILE DOWNLOAD ENDPOINT ────────────────────────────────
@app.get("/api/records/offchain/download/{patient_id}/{block_index}", summary="Download Off-chain File")
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


# ── PATIENT CONSENT ENDPOINTS ───────────────────────────────────────
@app.get("/api/consent/{patient_id}", summary="Get Patient Consent Rules")
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

@app.post("/api/consent", summary="Grant or Update Doctor Consent")
def grant_consent(data: ConsentGrantReq, u: dict = Depends(current_user)):
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

@app.delete("/api/consent/{patient_id}/{doctor_username}/{record_type}", summary="Revoke Doctor Consent")
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

@app.post("/api/consent/{patient_id}/break-glass", summary="Break Glass Emergency Override")
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


# ── SMART NOTIFICATION ENDPOINTS ──────────────────────────────────
@app.get("/api/notifications/{patient_id}", summary="Get Patient Notifications")
def get_notifications(patient_id: str, u: dict = Depends(current_user)):
    check_patient_id(patient_id)
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
        
    query = GetNotificationsQuery(patient_id=patient_id, username=u["username"])
    notifs = query_handler.handle_get_notifications(query)
    return {"notifications": notifs}

@app.post("/api/notifications/{patient_id}/{notif_id}/read", summary="Mark Notification as Read")
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


@app.get("/api/config", summary="Dynamic Configuration and Demo mode")
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

# ── Phase 4 Integrations Schemas & Routes ────────────────────────────────

class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_name: str
    department: str
    appointment_date: str
    appointment_time: str
    notes: Optional[str] = ""

class TriageRequest(BaseModel):
    symptoms: str
    duration_days: int

class LisWebhookPayload(BaseModel):
    patient_id: str
    doctor_name: str
    institution: str
    title: str
    test_name: str
    result_value: str
    reference_range: str
    unit: str
    notes: Optional[str] = ""

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

@app.get("/api/appointments/{patient_id}", summary="Get Patient Appointments")
def get_appointments(patient_id: str, u: dict = Depends(current_user)):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    return [apt for apt in appointments_db if apt["patient_id"] == patient_id]

@app.post("/api/appointments", summary="Create Appointment")
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

@app.delete("/api/appointments/{appointment_id}", summary="Cancel Appointment")
def cancel_appointment(appointment_id: str, u: dict = Depends(current_user)):
    apt = next((a for a in appointments_db if a["id"] == appointment_id), None)
    if not apt:
        raise HTTPException(404, "Appointment not found")
        
    if u["role"] == "vip_patient" and u.get("patient_id") != apt["patient_id"]:
        raise HTTPException(403, "Access denied")
        
    appointments_db.remove(apt)
    return {"success": True, "message": "Appointment cancelled successfully"}

@app.post("/api/ai/triage", summary="AI Medical Triage Chatbot")
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

@app.get("/api/enabiz/fhir/export/{patient_id}", summary="FHIR e-Nabiz Export Bridge")
def fhir_export(patient_id: str, u: dict = Depends(current_user)):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
        
    query = ExportFHIRBundleQuery(
        patient_id=patient_id,
        requester_username=u["username"],
        requester_role=u["role"]
    )
    return query_handler.handle_export_fhir_bundle(query)

@app.post("/api/webhooks/lis", summary="LIS Hospital Webhook Gateway")
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
        # Route via CQRS for transactional safety
        cmd = AddRecordCommand(
            patient_id=payload.patient_id,
            data=block_data,
            is_protected=False,
            protection_password=None,
            username="LIS_GATEWAY"
        )
        block = command_handler.handle_add_record(cmd)
        
        # Check if value is abnormal and trigger warning notification
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
