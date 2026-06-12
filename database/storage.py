"""
database/storage.py — VIP Health Vault · LMDB Storage Layer v3.0
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
from typing import Optional, List, Dict, Any

from database.connection import LMDBConnectionManager, active_txn, active_project


# ──────────────────────────────────────────────
# CONSTANTS & SETUP
# ──────────────────────────────────────────────
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

USERS_DB_NAME = "__users__"

# Default instance for process-wide usage and backward compatibility
default_db_manager = LMDBConnectionManager(PROJECTS_DIR, LMDB_MAP_SIZE)

# ──────────────────────────────────────────────
# BACKWARD COMPATIBLE DELEGATES
# ──────────────────────────────────────────────

def ensure_projects_dir() -> str:
    return default_db_manager.ensure_projects_dir()

def get_project_path(project_name: str) -> str:
    return default_db_manager.get_project_path(project_name)

def get_db_path(project_name: str) -> str:
    return default_db_manager.get_db_path(project_name)

def create_project(project_name: str) -> bool:
    return default_db_manager.create_project(project_name)

def project_exists(project_name: str) -> bool:
    return default_db_manager.project_exists(project_name)

def list_projects() -> List[str]:
    return default_db_manager.list_projects()

def open_db(project_name: str) -> lmdb.Environment:
    return default_db_manager.open_db(project_name)

def run_write_transaction(project_name: str, txn_func) -> Any:
    return default_db_manager.run_write_transaction(project_name, txn_func)

def _block_key(index: int) -> bytes:
    return f"{index:010d}".encode("utf-8")

# ──────────────────────────────────────────────
# BLOCK OPERATIONS
# ──────────────────────────────────────────────

def save_block_to_db(project_name: str, index: int, block_data: dict, db_manager: Optional[LMDBConnectionManager] = None) -> None:
    manager = db_manager or default_db_manager
    def txn_block(txn):
        key = _block_key(index)
        value = json.dumps(block_data, ensure_ascii=False).encode("utf-8")
        txn.put(key, value)
        txn.put(b"meta_last_index", str(index).encode("utf-8"))
    manager.run_write_transaction(project_name, txn_block)


def load_all_blocks(project_name: str, db_manager: Optional[LMDBConnectionManager] = None) -> List[dict]:
    manager = db_manager or default_db_manager
    if not manager.project_exists(project_name):
        return []

    env = manager.open_db(project_name)
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


def reset_db(project_name: str, db_manager: Optional[LMDBConnectionManager] = None) -> None:
    manager = db_manager or default_db_manager
    manager.close_db(project_name)
    path = manager.get_db_path(project_name)
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
        except Exception as e:
            print(f"DB reset error: {e}")


# ──────────────────────────────────────────────
# PER-PATIENT ENCRYPTION SALT MANAGEMENT
# ──────────────────────────────────────────────

def save_patient_salt(project_name: str, salt: bytes, db_manager: Optional[LMDBConnectionManager] = None) -> None:
    manager = db_manager or default_db_manager
    def txn_block(txn):
        key = f"meta_salt_{project_name}".encode("utf-8")
        txn.put(key, base64.urlsafe_b64encode(salt))
    manager.run_write_transaction(project_name, txn_block)


def get_patient_salt(project_name: str, db_manager: Optional[LMDBConnectionManager] = None) -> bytes:
    manager = db_manager or default_db_manager
    env = manager.open_db(project_name)
    with env.begin(write=False) as txn:
        key = f"meta_salt_{project_name}".encode("utf-8")
        val = txn.get(key)
        if val:
            return base64.urlsafe_b64decode(val)

    salt = os.urandom(32)
    save_patient_salt(project_name, salt, manager)
    return salt


def save_block_salt(project_name: str, block_index: int, salt: bytes, db_manager: Optional[LMDBConnectionManager] = None) -> None:
    manager = db_manager or default_db_manager
    def txn_block(txn):
        key = f"salt_{block_index:010d}".encode("utf-8")
        txn.put(key, base64.urlsafe_b64encode(salt))
    manager.run_write_transaction(project_name, txn_block)


def load_block_salt(project_name: str, block_index: int, db_manager: Optional[LMDBConnectionManager] = None) -> Optional[bytes]:
    manager = db_manager or default_db_manager
    env = manager.open_db(project_name)
    with env.begin(write=False) as txn:
        key = f"salt_{block_index:010d}".encode("utf-8")
        value = txn.get(key)
        if value:
            return base64.urlsafe_b64decode(value)
        return None


def save_block_pwd_hash(project_name: str, block_index: int, pwd_hash: str, db_manager: Optional[LMDBConnectionManager] = None) -> None:
    manager = db_manager or default_db_manager
    def txn_block(txn):
        key = f"pwd_hash_{block_index:010d}".encode("utf-8")
        txn.put(key, pwd_hash.encode("utf-8"))
    manager.run_write_transaction(project_name, txn_block)


def load_block_pwd_hash(project_name: str, block_index: int, db_manager: Optional[LMDBConnectionManager] = None) -> Optional[str]:
    manager = db_manager or default_db_manager
    env = manager.open_db(project_name)
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
    db_manager: Optional[LMDBConnectionManager] = None,
) -> None:
    manager = db_manager or default_db_manager
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
    manager.run_write_transaction(project_name, txn_block)


def load_access_logs(project_name: str, limit: int = 100, db_manager: Optional[LMDBConnectionManager] = None) -> List[dict]:
    manager = db_manager or default_db_manager
    if not manager.project_exists(project_name):
        return []

    env = manager.open_db(project_name)
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
    db_manager: Optional[LMDBConnectionManager] = None,
) -> None:
    manager = db_manager or default_db_manager
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
    manager.run_write_transaction(project_name, txn_block)


def load_audit_logs(project_name: str, limit: int = 100, db_manager: Optional[LMDBConnectionManager] = None) -> List[dict]:
    manager = db_manager or default_db_manager
    if not manager.project_exists(project_name):
        return []

    env = manager.open_db(project_name)
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

def _ensure_users_db(db_manager: LMDBConnectionManager) -> None:
    db_manager.create_project(USERS_DB_NAME)


def save_user(user_data: dict, db_manager: Optional[LMDBConnectionManager] = None) -> None:
    manager = db_manager or default_db_manager
    _ensure_users_db(manager)
    def txn_block(txn):
        key = f"user_{user_data['username']}".encode("utf-8")
        txn.put(key, json.dumps(user_data, ensure_ascii=False).encode("utf-8"))
    manager.run_write_transaction(USERS_DB_NAME, txn_block)


def load_user(username: str, db_manager: Optional[LMDBConnectionManager] = None) -> Optional[dict]:
    manager = db_manager or default_db_manager
    _ensure_users_db(manager)
    env = manager.open_db(USERS_DB_NAME)
    with env.begin(write=False) as txn:
        key = f"user_{username}".encode("utf-8")
        value = txn.get(key)
        if value:
            return json.loads(value.decode("utf-8"))
        return None


def load_all_users(db_manager: Optional[LMDBConnectionManager] = None) -> List[dict]:
    manager = db_manager or default_db_manager
    _ensure_users_db(manager)
    env = manager.open_db(USERS_DB_NAME)
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


def user_exists(username: str, db_manager: Optional[LMDBConnectionManager] = None) -> bool:
    return load_user(username, db_manager) is not None


def delete_user(username: str, db_manager: Optional[LMDBConnectionManager] = None) -> bool:
    manager = db_manager or default_db_manager
    _ensure_users_db(manager)
    def txn_block(txn):
        key = f"user_{username}".encode("utf-8")
        return txn.delete(key)
    return manager.run_write_transaction(USERS_DB_NAME, txn_block)


# ──────────────────────────────────────────────
# DEFAULT USERS SEEDING — First Run
# ──────────────────────────────────────────────

def seed_default_users(db_manager: Optional[LMDBConnectionManager] = None) -> None:
    from core.security import hash_password

    manager = db_manager or default_db_manager
    if load_all_users(manager):
        return

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
        save_user(user, manager)

    print("[OK] Default users seeded into LMDB successfully.")
