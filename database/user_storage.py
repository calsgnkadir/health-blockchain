"""
database/user_storage.py — User management LMDB persistence layer
"""

import json
from typing import Optional, List
from database.connection import LMDBConnectionManager

USERS_DB_NAME = "__users__"

def _ensure_users_db(db_manager: LMDBConnectionManager) -> None:
    db_manager.create_project(USERS_DB_NAME)


def save_user(user_data: dict, db_manager: LMDBConnectionManager) -> None:
    _ensure_users_db(db_manager)
    def txn_block(txn):
        key = f"user_{user_data['username']}".encode("utf-8")
        txn.put(key, json.dumps(user_data, ensure_ascii=False).encode("utf-8"))
    db_manager.run_write_transaction(USERS_DB_NAME, txn_block)


def load_user(username: str, db_manager: LMDBConnectionManager) -> Optional[dict]:
    _ensure_users_db(db_manager)
    env = db_manager.open_db(USERS_DB_NAME)
    with env.begin(write=False) as txn:
        key = f"user_{username}".encode("utf-8")
        value = txn.get(key)
        if value:
            return json.loads(value.decode("utf-8"))
        return None


def load_all_users(db_manager: LMDBConnectionManager) -> List[dict]:
    _ensure_users_db(db_manager)
    env = db_manager.open_db(USERS_DB_NAME)
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


def user_exists(username: str, db_manager: LMDBConnectionManager) -> bool:
    return load_user(username, db_manager) is not None


def delete_user(username: str, db_manager: LMDBConnectionManager) -> bool:
    _ensure_users_db(db_manager)
    def txn_block(txn):
        key = f"user_{username}".encode("utf-8")
        return txn.delete(key)
    return db_manager.run_write_transaction(USERS_DB_NAME, txn_block)


def seed_default_users(db_manager: LMDBConnectionManager) -> None:
    from core.security import hash_password

    if load_all_users(db_manager):
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
            "full_name": "Ahmet Karataş",
            "patient_id": "VIP-001",
            "clearance": "TOP_SECRET",
            "totp_secret": None,
            "totp_enabled": False,
        },
    ]

    for user in defaults:
        save_user(user, db_manager)

    print("[OK] Default users seeded into LMDB successfully.")
