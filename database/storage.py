"""
database/storage.py — VIP Health Vault · LMDB Storage Layer v2.0
=====================================================================
Features:
  - Block storage (atomic write, sequential keys)
  - Per-patient unique encryption salt
  - Access audit log (who, when, which block)
  - User database (Argon2 hashed passwords)
  - LMDB dynamic map size management
"""

import os
import json
import time
import base64
import lmdb
import shutil
import threading
from typing import Optional, List, Dict, Any

# ──────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────
# storage.py is inside database/; parent directory = project root
_STORAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_STORAGE_DIR)
PROJECTS_DIR = os.path.join(_PROJECT_ROOT, "backend", "projects")

env_map_size = os.getenv("VHV_LMDB_MAP_SIZE")
if env_map_size:
    try:
        env_map_size_clean = env_map_size.strip().upper()
        if env_map_size_clean.endswith("G"):
            LMDB_MAP_SIZE = int(float(env_map_size_clean[:-1]) * 1024 * 1024 * 1024)
        elif env_map_size_clean.endswith("M"):
            LMDB_MAP_SIZE = int(float(env_map_size_clean[:-1]) * 1024 * 1024)
        elif env_map_size_clean.endswith("K"):
            LMDB_MAP_SIZE = int(float(env_map_size_clean[:-1]) * 1024)
        else:
            LMDB_MAP_SIZE = int(env_map_size_clean)
    except Exception:
        LMDB_MAP_SIZE = 2 * 1024 * 1024 * 1024
else:
    LMDB_MAP_SIZE = 2 * 1024 * 1024 * 1024

USERS_DB_NAME = "__users__"               # Special project name for user database


# ──────────────────────────────────────────────
# DIRECTORY HELPERS
# ──────────────────────────────────────────────

def ensure_projects_dir() -> str:
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    return PROJECTS_DIR


def get_project_path(project_name: str) -> str:
    ensure_projects_dir()
    return os.path.join(PROJECTS_DIR, project_name)


def get_db_path(project_name: str) -> str:
    project_path = get_project_path(project_name)
    os.makedirs(project_path, exist_ok=True)
    return os.path.join(project_path, "chaindata.lmdb")


def create_project(project_name: str) -> bool:
    project_path = get_project_path(project_name)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
        return True
    return False


def project_exists(project_name: str) -> bool:
    return os.path.exists(get_project_path(project_name))


def list_projects() -> List[str]:
    ensure_projects_dir()
    return [
        d for d in os.listdir(PROJECTS_DIR)
        if os.path.isdir(os.path.join(PROJECTS_DIR, d))
        and not d.startswith("__")
    ]


# ──────────────────────────────────────────────
# LMDB CORE HELPERS (Cached Environment Management)
# ──────────────────────────────────────────────

import contextvars

# Global context variables to track active LMDB transactions for Unit of Work
active_txn = contextvars.ContextVar("active_txn", default=None)
active_project = contextvars.ContextVar("active_project", default=None)

_map_sizes: Dict[str, int] = {}
_envs: Dict[str, lmdb.Environment] = {}
_env_lock = threading.Lock()

def open_db(project_name: str) -> lmdb.Environment:
    """
    Opens or retrieves a cached LMDB Environment.
    Environments are shared across threads to avoid Windows locking/sharing violations.
    """
    with _env_lock:
        if project_name not in _envs:
            path = get_db_path(project_name)
            if project_name not in _map_sizes:
                _map_sizes[project_name] = LMDB_MAP_SIZE
            
            while True:
                try:
                    _envs[project_name] = lmdb.open(path, map_size=_map_sizes[project_name], subdir=True)
                    break
                except lmdb.MapFullError:
                    _map_sizes[project_name] += 100 * 1024 * 1024  # increase map size by 100 MB
        return _envs[project_name]


def run_write_transaction(project_name: str, txn_func) -> Any:
    """
    Executes write transaction on LMDB with automatic resize support.
    If an active transaction exists in the context for this project, it is reused.
    """
    current_txn = active_txn.get()
    current_proj = active_project.get()
    
    if current_txn is not None and current_proj == project_name:
        return txn_func(current_txn)

    if project_name not in _map_sizes:
        _map_sizes[project_name] = LMDB_MAP_SIZE
    
    for attempt in range(5):
        try:
            env = open_db(project_name)
            with env.begin(write=True) as txn:
                result = txn_func(txn)
            return result
        except lmdb.MapFullError:
            # Close and remove cached environment to allow reopening with a larger map size
            with _env_lock:
                if project_name in _envs:
                    try:
                        _envs[project_name].close()
                    except Exception:
                        pass
                    del _envs[project_name]
            _map_sizes[project_name] += 100 * 1024 * 1024  # increase map size by 100 MB
    raise lmdb.MapFullError("LMDB limit reached and map size could not be increased automatically.")


def _block_key(index: int) -> bytes:
    """Sequential block key: 10 digits like '0000000001'."""
    return f"{index:010d}".encode("utf-8")


# ──────────────────────────────────────────────
# BLOCK OPERATIONS
# ──────────────────────────────────────────────

def save_block_to_db(project_name: str, index: int, block_data: dict) -> None:
    """Writes a single block atomically to LMDB."""
    def txn_block(txn):
        key = _block_key(index)
        value = json.dumps(block_data, ensure_ascii=False).encode("utf-8")
        txn.put(key, value)
        txn.put(b"meta_last_index", str(index).encode("utf-8"))
    run_write_transaction(project_name, txn_block)


def load_all_blocks(project_name: str) -> List[dict]:
    """Loads all blocks sequentially."""
    if not project_exists(project_name):
        return []

    env = open_db(project_name)
    blocks = []
    with env.begin(write=False) as txn:
        cursor = txn.cursor()
        for key, value in cursor:
            if (
                key.startswith(b"meta_")
                or key.startswith(b"salt_")
                or key.startswith(b"audit_")
                or key.startswith(b"user_")
                or key.startswith(b"access_log_")
                or key.startswith(b"pwd_hash_")
                or key.startswith(b"consent_")
                or key.startswith(b"notif_")
            ):
                continue
            try:
                block_data = json.loads(value.decode("utf-8"))
                blocks.append(block_data)
            except Exception:
                continue
    return blocks


def reset_db(project_name: str) -> None:
    """Resets the database (called before Genesis block)."""
    with _env_lock:
        if project_name in _envs:
            try:
                _envs[project_name].close()
            except Exception:
                pass
            del _envs[project_name]
    path = get_db_path(project_name)
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
        except Exception as e:
            print(f"DB reset error: {e}")


# ──────────────────────────────────────────────
# PER-PATIENT ENCRYPTION SALT MANAGEMENT
# ──────────────────────────────────────────────

def save_patient_salt(project_name: str, salt: bytes) -> None:
    """Saves patient-specific (per-patient) salt to LMDB (meta_salt_<patient_id>)."""
    def txn_block(txn):
        key = f"meta_salt_{project_name}".encode("utf-8")
        txn.put(key, base64.urlsafe_b64encode(salt))
    run_write_transaction(project_name, txn_block)


def get_patient_salt(project_name: str) -> bytes:
    """
    Returns patient-specific (per-patient) salt.
    Generates a new one if missing and stores with meta_salt_<patient_id> key.
    """
    env = open_db(project_name)
    with env.begin(write=False) as txn:
        key = f"meta_salt_{project_name}".encode("utf-8")
        val = txn.get(key)
        if val:
            return base64.urlsafe_b64decode(val)

    # If missing, generate and save
    salt = os.urandom(32)
    save_patient_salt(project_name, salt)
    return salt


def save_block_salt(project_name: str, block_index: int, salt: bytes) -> None:
    """Saves a block's encryption salt to LMDB."""
    def txn_block(txn):
        key = f"salt_{block_index:010d}".encode("utf-8")
        txn.put(key, base64.urlsafe_b64encode(salt))
    run_write_transaction(project_name, txn_block)


def load_block_salt(project_name: str, block_index: int) -> Optional[bytes]:
    """Reads a block's encryption salt from LMDB."""
    env = open_db(project_name)
    with env.begin(write=False) as txn:
        key = f"salt_{block_index:010d}".encode("utf-8")
        value = txn.get(key)
        if value:
            return base64.urlsafe_b64decode(value)
        return None


def save_block_pwd_hash(project_name: str, block_index: int, pwd_hash: str) -> None:
    """Writes the saved block's password hash (Argon2) to LMDB under a separate key."""
    def txn_block(txn):
        key = f"pwd_hash_{block_index:010d}".encode("utf-8")
        txn.put(key, pwd_hash.encode("utf-8"))
    run_write_transaction(project_name, txn_block)


def load_block_pwd_hash(project_name: str, block_index: int) -> Optional[str]:
    """Reads the block's password hash from LMDB."""
    env = open_db(project_name)
    with env.begin(write=False) as txn:
        key = f"pwd_hash_{block_index:010d}".encode("utf-8")
        val = txn.get(key)
        if val:
            return val.decode("utf-8")
        return None


# ──────────────────────────────────────────────
# ACCESS LOG TABLE (access_log_<patient_id>)
# ──────────────────────────────────────────────

def append_access_log(
    project_name: str,
    username: str,
    action: str,
    device_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Appends an access log entry for a specific patient.
    Key format: access_log_<project_name>_<timestamp_ns>
    """
    def txn_block(txn):
        ts_ns = time.time_ns()
        key = f"access_log_{project_name}_{ts_ns:020d}".encode("utf-8")
        entry = {
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "action": action,
            "username": username,
            "device_id": device_id or "unknown",
            **(extra or {}),
        }
        txn.put(key, json.dumps(entry, ensure_ascii=False).encode("utf-8"))
    run_write_transaction(project_name, txn_block)


def load_access_logs(project_name: str, limit: int = 100) -> List[dict]:
    """Returns the last 'limit' access logs (newest to oldest)."""
    if not project_exists(project_name):
        return []

    env = open_db(project_name)
    logs = []
    with env.begin(write=False) as txn:
        cursor = txn.cursor()
        prefix = f"access_log_{project_name}_".encode("utf-8")
        for key, value in cursor:
            if key.startswith(prefix):
                try:
                    log = json.loads(value.decode("utf-8"))
                    logs.append(log)
                except Exception:
                    continue
        logs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return logs[:limit]


# ──────────────────────────────────────────────
# ACCESS AUDIT LOG
# ──────────────────────────────────────────────

def append_audit_log(
    project_name: str,
    action: str,
    username: str,
    block_index: Optional[int] = None,
    device_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Creates an audit entry. Every entry is stored with a timestamp in LMDB.
    Format: audit_<timestamp_ns> → JSON
    """
    def txn_block(txn):
        ts_ns = time.time_ns()
        key = f"audit_{ts_ns:020d}".encode("utf-8")
        entry = {
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "action": action,
            "username": username,
            "block_index": block_index,
            "device_id": device_id,
            **(extra or {}),
        }
        txn.put(key, json.dumps(entry, ensure_ascii=False).encode("utf-8"))
    run_write_transaction(project_name, txn_block)


def load_audit_logs(project_name: str, limit: int = 100) -> List[dict]:
    """Returns the last 'limit' audit logs (newest to oldest)."""
    if not project_exists(project_name):
        return []

    env = open_db(project_name)
    logs = []
    with env.begin(write=False) as txn:
        cursor = txn.cursor()
        all_audit = []
        for key, value in cursor:
            if key.startswith(b"audit_"):
                try:
                    log = json.loads(value.decode("utf-8"))
                    all_audit.append(log)
                except Exception:
                    continue
        all_audit.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        logs = all_audit[:limit]
    return logs


# ──────────────────────────────────────────────
# USER DATABASE (Argon2 hashed)
# ──────────────────────────────────────────────

def _ensure_users_db() -> None:
    create_project(USERS_DB_NAME)


def save_user(user_data: dict) -> None:
    """
    Saves user to LMDB.
    user_data: {username, password_hash, role, full_name, patient_id, ...}
    """
    _ensure_users_db()
    def txn_block(txn):
        key = f"user_{user_data['username']}".encode("utf-8")
        txn.put(key, json.dumps(user_data, ensure_ascii=False).encode("utf-8"))
    run_write_transaction(USERS_DB_NAME, txn_block)


def load_user(username: str) -> Optional[dict]:
    """Loads user by username."""
    _ensure_users_db()
    env = open_db(USERS_DB_NAME)
    with env.begin(write=False) as txn:
        key = f"user_{username}".encode("utf-8")
        value = txn.get(key)
        if value:
            return json.loads(value.decode("utf-8"))
        return None


def load_all_users() -> List[dict]:
    """Returns all users."""
    _ensure_users_db()
    env = open_db(USERS_DB_NAME)
    users = []
    with env.begin(write=False) as txn:
        cursor = txn.cursor()
        for key, value in cursor:
            if key.startswith(b"user_"):
                try:
                    users.append(json.loads(value.decode("utf-8")))
                except Exception:
                    continue
    return users


def user_exists(username: str) -> bool:
    return load_user(username) is not None


def delete_user(username: str) -> bool:
    _ensure_users_db()
    def txn_block(txn):
        key = f"user_{username}".encode("utf-8")
        return txn.delete(key)
    return run_write_transaction(USERS_DB_NAME, txn_block)


# ──────────────────────────────────────────────
# DEFAULT USERS SEEDING — First Run
# ──────────────────────────────────────────────

def seed_default_users() -> None:
    """
    Seeds default users if the user database is empty.
    In production, these default passwords must be changed!
    """
    from core.security import hash_password

    if load_all_users():
        return   # Users already exist

    defaults = [
        {
            "id": "USR-ADMIN-001",
            "username": "admin",
            "password_hash": hash_password("Admin@2026Secure!"),
            "role": "admin",
            "full_name": "System Administrator",
            "patient_id": None,
            "totp_secret": None,
            "totp_enabled": False,
        },
        {
            "id": "USR-DOC-001",
            "username": "dr.smith",
            "password_hash": hash_password("Doctor@2026Secure!"),
            "role": "doctor",
            "full_name": "Prof. Dr. James Smith",
            "specialty": "Cardiology",
            "institution": "VIP Medical Center",
            "patient_id": None,
            "totp_secret": None,
            "totp_enabled": False,
        },
        {
            "id": "USR-VIP-001",
            "username": "vip001",
            "password_hash": hash_password("VIPPatient@2026!"),
            "role": "vip_patient",
            "full_name": "VIP Patient — [CONFIDENTIAL]",
            "patient_id": "VIP-001",
            "clearance": "TOP_SECRET",
            "totp_secret": None,
            "totp_enabled": False,
        },
    ]

    for user in defaults:
        save_user(user)

    print("[OK] Default users seeded into LMDB successfully.")
