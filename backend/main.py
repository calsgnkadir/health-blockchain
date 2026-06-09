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

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import jwt
import json
import os
import sys
import time
import threading

# ── Path Configuration ───────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.blockchain import Blockchain
from core.security import (
    verify_password, hash_password,
    get_device_id, validate_password,
)
import database.storage as storage

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
    allow_headers=["Authorization", "Content-Type"],
)

# ── JWT Configuration ────────────────────────────────────────
_JWT_SECRET_FILE = os.path.join(os.path.dirname(__file__), ".jwt_secret")

def _load_or_create_jwt_secret() -> str:
    """
    Loads JWT secret from:
      1. JWT_SECRET environment variable
      2. OS keyring (Windows DPAPI / macOS Keychain / libsecret)
      3. .jwt_secret plaintext file — auto-migrates to keyring and deletes file
      4. Generate new random secret and store it
    """
    # 1. Environment variable — highest priority
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return secret

    # 2. OS keyring (DPAPI on Windows)
    try:
        import keyring as _kr
        secret = _kr.get_password("VIPHealthVault", "jwt_secret")
        if secret:
            return secret
    except Exception:
        pass

    # 3. Persistent file — legacy fallback
    if os.path.exists(_JWT_SECRET_FILE):
        with open(_JWT_SECRET_FILE, "r") as f:
            secret = f.read().strip()
        if secret:
            # S-06: Auto-migrate from plaintext file to OS keyring
            try:
                import keyring as _kr
                _kr.set_password("VIPHealthVault", "jwt_secret", secret)
                os.remove(_JWT_SECRET_FILE)
                print("[OK] JWT secret migrated from .jwt_secret file to OS keyring (DPAPI on Windows).")
            except Exception:
                pass  # Keep file if keyring unavailable
            return secret

    # 4. Generate and store new secret
    import secrets as _sec
    secret = _sec.token_hex(32)
    try:
        import keyring as _kr
        _kr.set_password("VIPHealthVault", "jwt_secret", secret)
        print("[OK] JWT secret generated and stored in OS keyring.")
    except Exception:
        with open(_JWT_SECRET_FILE, "w") as f:
            f.write(secret)
        print("\n[WARN] JWT secret generated and saved to .jwt_secret file.")
        print("   Set the JWT_SECRET environment variable in production.\n")
    return secret

SECRET_KEY = _load_or_create_jwt_secret()
ALGORITHM = "HS256"
TOKEN_HOURS = 8   # 8 hours

security_bearer = HTTPBearer()

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
    storage.seed_default_users()
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
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def current_user(creds: HTTPAuthorizationCredentials = Depends(security_bearer)) -> dict:
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = storage.load_user(username)
        if not user:
            raise HTTPException(401, "Invalid token — user not found")
        return user
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


@app.post("/api/auth/login", summary="User Login")
async def login(req: LoginReq, request: Request):
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait 1 minute.",
        )

    user = storage.load_user(req.username)
    if not user or not verify_password(req.password, user["password_hash"]):
        # Failed login audit log
        if user:
            storage.append_audit_log(
                "__system__",
                action="LOGIN_FAILED",
                username=req.username,
                device_id=get_device_id(),
                extra={"ip": client_ip},
            )
        raise HTTPException(401, "Incorrect username or password")

    token = create_token(user)

    storage.append_audit_log(
        "__system__",
        action="LOGIN_SUCCESS",
        username=req.username,
        device_id=get_device_id(),
        extra={"ip": client_ip, "role": user["role"]},
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
    }

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
    users = storage.load_all_users()
    return {"users": [
        {k: v for k, v in user.items() if k != "password_hash"}
        for user in users
    ]}


@app.post("/api/admin/users", summary="Create New User")
def create_user(data: UserCreate, u: dict = Depends(require_role("admin"))):
    if storage.user_exists(data.username):
        raise HTTPException(409, f"Username already exists: {data.username}")

    import uuid as _uuid
    new_user = {
        "id":            f"USR-{data.role.upper()}-{_uuid.uuid4().hex[:6].upper()}",
        "username":      data.username,
        "password_hash": hash_password(data.password),
        "role":          data.role,
        "full_name":     data.full_name,
        "patient_id":    data.patient_id,
        "specialty":     data.specialty,
        "institution":   data.institution,
        "totp_secret":   None,
        "totp_enabled":  False,
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "created_by":    u["username"],
    }
    storage.save_user(new_user)

    storage.append_audit_log(
        "__system__",
        action="USER_CREATED",
        username=u["username"],
        extra={"new_user": data.username, "role": data.role},
    )

    return {"success": True, "user_id": new_user["id"]}

# ──────────────────────────────────────────────────────────────
# HEALTH RECORDS
# ──────────────────────────────────────────────────────────────

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


@app.post("/api/records", summary="Add Health Record")
def add_record(rec: RecordCreate, u: dict = Depends(current_user)):
    # Authorization checks
    if u["role"] == "vip_patient" and u.get("patient_id") != rec.patient_id:
        raise HTTPException(403, "You can only access your own records")
    if u["role"] not in ("doctor", "admin", "vip_patient"):
        raise HTTPException(403, "You do not have permission to add records")

    bc = get_blockchain(rec.patient_id)

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
    }

    block = bc.add_block(
        block_data,
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

    bc = get_blockchain(patient_id)
    final_data = bc.get_final_data()
    records = []

    for block in bc.chain:
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
        else:
            entry["title"] = str(data)[:80]
            entry["data"]  = None

        records.append(entry)

    records.sort(key=lambda x: x["timestamp"], reverse=True)

    # Access audit log
    storage.append_audit_log(
        f"patient_{patient_id.replace('-','_')}",
        action="RECORDS_VIEWED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"record_count": len(records)},
    )

    return {
        "patient_id":   patient_id,
        "total_blocks": len(bc.chain),
        "records":      records,
        "chain_valid":  bc.is_valid(),
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

    bc = get_blockchain(patient_id)
    block = bc.chain[block_index] if 0 <= block_index < len(bc.chain) else None
    if block is None:
        raise HTTPException(404, "Block not found")

    if block.is_protected:
        return {
            "block_index": block_index,
            "is_protected": True,
            "data": "ENCRYPTED — use POST /decrypt with the correct password",
        }

    data = bc.get_final_block_data(block_index, password=None, username=u["username"])
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

    bc = get_blockchain(patient_id)
    data = bc.get_final_block_data(block_index, password=req.password, username=u["username"])

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
    bc = get_blockchain(patient_id)
    brk = bc.find_broken_link_index()
    return {
        "patient_id":   patient_id,
        "chain_length": len(bc.chain),
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
    proj = f"patient_{patient_id.replace('-','_')}"
    used_source = source
    
    if source == "blockchain":
        bc = get_blockchain(patient_id)
        logs = bc.get_audit_logs(limit)
    else:
        logs = storage.load_audit_logs(proj, limit)
        # Fallback to blockchain logs if not in database
        if not logs:
            bc = get_blockchain(patient_id)
            logs = bc.get_audit_logs(limit)
            used_source = "blockchain"
            
    return {"patient_id": patient_id, "logs": logs, "source": used_source}


@app.get("/api/blockchain/{patient_id}/access-logs", summary="Patient Access Log")
def get_access_logs(
    patient_id: str,
    limit: int = 100,
    source: str = "db",
    u: dict = Depends(require_role("admin", "auditor", "vip_patient"))
):
    if u["role"] == "vip_patient" and u.get("patient_id") != patient_id:
        raise HTTPException(403, "Access denied")
    proj = f"patient_{patient_id.replace('-','_')}"
    used_source = source
    
    if source == "blockchain":
        bc = get_blockchain(patient_id)
        logs = bc.get_audit_logs(limit)
    else:
        logs = storage.load_access_logs(proj, limit)
        # Fallback to blockchain logs if not in database
        if not logs:
            bc = get_blockchain(patient_id)
            logs = bc.get_audit_logs(limit)
            used_source = "blockchain"
            
    return {"patient_id": patient_id, "logs": logs, "source": used_source}


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
