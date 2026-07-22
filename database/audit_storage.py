"""
database/audit_storage.py — Access and system audit logging persistence layer
"""

import json
import time
from typing import Optional, List
from database.connection import LMDBConnectionManager
from core.security import get_device_id

def append_access_log(
    project_name: str,
    username: str,
    action: str,
    device_id: Optional[str] = None,
    extra: Optional[dict] = None,
    db_manager: Optional[LMDBConnectionManager] = None,
) -> None:
    from database.storage import default_db_manager
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
    from database.storage import default_db_manager
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


def append_audit_log(
    project_name: str,
    action: str,
    username: str,
    block_index: Optional[int] = None,
    device_id: Optional[str] = None,
    extra: Optional[dict] = None,
    db_manager: Optional[LMDBConnectionManager] = None,
) -> None:
    from database.storage import default_db_manager
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
    from database.storage import default_db_manager
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
