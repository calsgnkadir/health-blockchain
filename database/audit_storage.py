"""
database/audit_storage.py — Access and system audit logging persistence layer
"""

import hashlib
import json
import time
from typing import Optional, List
from database.connection import LMDBConnectionManager


def _access_entry_hash(entry: dict) -> str:
    """
    SHA-256 over the entry's content (every field except ``hash`` itself).

    ``prev_hash`` is part of the content, so each entry commits to its
    predecessor — the property that makes deleting or altering any past access
    event detectable.
    """
    material = json.dumps(
        {k: v for k, v in entry.items() if k != "hash"},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def append_access_log(
    project_name: str,
    username: str,
    action: str,
    device_id: Optional[str] = None,
    extra: Optional[dict] = None,
    db_manager: Optional[LMDBConnectionManager] = None,
) -> None:
    """
    Append a hash-linked access event.

    Who read (or attempted to read) a VIP record is exactly the claim this vault
    must be able to defend, so the access log is not a flat, deletable table: each
    entry carries a sequence number and the hash of the previous entry, forming a
    tamper-evident ledger verifiable via ``verify_access_log_integrity``. Reads are
    frequent, so this lives beside the clinical chain rather than adding a block
    per read to it.
    """
    from database.storage import default_db_manager
    manager = db_manager or default_db_manager

    def txn_block(txn):
        head_key = f"meta_access_head_{project_name}".encode("utf-8")
        seq_key = f"meta_access_seq_{project_name}".encode("utf-8")
        prev_hash = (txn.get(head_key) or b"").decode("utf-8")
        seq = int((txn.get(seq_key) or b"0").decode("utf-8")) + 1

        entry = {
            "seq": seq,
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "action": action,
            "username": username,
            "device_id": device_id or "unknown",
            "prev_hash": prev_hash,
            **(extra or {}),
        }
        entry["hash"] = _access_entry_hash(entry)

        # Key on the monotonic sequence number, not a wall-clock timestamp: two
        # events in the same clock tick would otherwise share a key and the second
        # would silently overwrite the first — a lost access-log entry. `seq` is
        # unique and monotonic, so keys never collide and sort chronologically.
        key = f"access_log_{project_name}_{seq:020d}".encode("utf-8")
        txn.put(key, json.dumps(entry, ensure_ascii=False).encode("utf-8"))
        txn.put(head_key, entry["hash"].encode("utf-8"))
        txn.put(seq_key, str(seq).encode("utf-8"))

    manager.run_write_transaction(project_name, txn_block)


def verify_access_log_integrity(
    project_name: str,
    db_manager: Optional[LMDBConnectionManager] = None,
) -> dict:
    """
    Walk the access ledger in sequence and confirm the hash chain is intact.

    Returns ``{"valid", "count", "broken_at"}``. A deleted, reordered or altered
    entry breaks either the sequence linkage or a recomputed hash and is reported
    by its sequence number.
    """
    from database.storage import default_db_manager
    manager = db_manager or default_db_manager
    if not manager.project_exists(project_name):
        return {"valid": True, "count": 0, "broken_at": None}

    env = manager.open_db(project_name)
    entries = []
    with env.begin(write=False) as txn:
        prefix = f"access_log_{project_name}_".encode("utf-8")
        for key, value in txn.cursor():
            if key.startswith(prefix):
                try:
                    entries.append(json.loads(value.decode("utf-8")))
                except Exception:
                    continue

    # Legacy (pre-chaining) entries have no seq/hash; verification applies once
    # the ledger is chained, which every fresh deployment is from the first write.
    chained = [e for e in entries if "hash" in e and "seq" in e]
    chained.sort(key=lambda e: e.get("seq", 0))

    prev = ""
    for e in chained:
        if e.get("prev_hash", "") != prev:
            return {"valid": False, "count": len(chained), "broken_at": e.get("seq")}
        if _access_entry_hash(e) != e.get("hash"):
            return {"valid": False, "count": len(chained), "broken_at": e.get("seq")}
        prev = e["hash"]

    return {"valid": True, "count": len(chained), "broken_at": None}


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
