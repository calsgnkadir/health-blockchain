"""
core/blockchain.py — VIP Health Vault · Blockchain Core v3.0
==================================================================
Security layers:
  1. SHA-256 hash chain (immutable history)
  2. HMAC-SHA256 device signature (prevent fake block additions)
  3. AES-256 block encryption + unique per-block salt
  4. Nonce + timestamp → replay attack prevention
  5. Every access is recorded as an audit log block on the blockchain
"""

import time
import json
import hashlib
import os
import secrets
from typing import Optional, List, Dict, Any

from core.security import (
    signaturedata, verify_message,
    encrypt_data, decrypt_data,
    hash_block_password, verify_block_password,
    get_device_id,
)
import database.storage as storage


# ──────────────────────────────────────────────
# MERKLE TREE CALCULATOR
# ──────────────────────────────────────────────

def calculate_merkle_root(data: Any) -> str:
    """
    Computes Merkle Root hash based on leaf data elements.
    """
    if data is None:
        return hashlib.sha256(b"").hexdigest()
        
    leaves = []
    if isinstance(data, dict):
        # Sort keys to guarantee hash consistency
        for k in sorted(data.keys()):
            val = data[k]
            val_str = json.dumps(val, sort_keys=True, ensure_ascii=False)
            leaf_hash = hashlib.sha256(f"{k}:{val_str}".encode("utf-8")).hexdigest()
            leaves.append(leaf_hash)
    elif isinstance(data, list):
        for item in data:
            item_str = json.dumps(item, sort_keys=True, ensure_ascii=False)
            leaf_hash = hashlib.sha256(item_str.encode("utf-8")).hexdigest()
            leaves.append(leaf_hash)
    else:
        # Single data value (str, int, etc.)
        leaf_hash = hashlib.sha256(str(data).encode("utf-8")).hexdigest()
        leaves.append(leaf_hash)
        
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
        
    # Compute Merkle Tree upwards
    nodes = leaves
    while len(nodes) > 1:
        temp_nodes = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i+1] if i+1 < len(nodes) else left
            combined = hashlib.sha256((left + right).encode("utf-8")).hexdigest()
            temp_nodes.append(combined)
        nodes = temp_nodes
        
    return nodes[0]


# ──────────────────────────────────────────────
# BLOCK
# ──────────────────────────────────────────────

class Block:
    """Represents a single immutable record in the blockchain."""

    def __init__(
        self,
        index: int,
        timestamp: float,
        data: Any,
        previous_hash: str,
        signature: str,
        is_protected: bool = False,
        protection_password: Optional[str] = None,  # Argon2 hash
        nonce: Optional[str] = None,
        device_id: Optional[str] = None,
        hash_val: Optional[str] = None,
        merkle_root: Optional[str] = None,
    ):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.is_protected = is_protected
        self.protection_password = protection_password   # Argon2 hash (stored separately)
        self.nonce = nonce or secrets.token_hex(16)      # Replay attack prevention
        self.device_id = device_id or get_device_id()
        self.signature = signature
        
        if hash_val is not None or index == 0:
            self.merkle_root = merkle_root
        else:
            self.merkle_root = merkle_root or calculate_merkle_root(data)

        if hash_val:
            self.hash = hash_val
        else:
            self.hash = self.create_hash()

    def create_hash(self) -> str:
        """SHA-256 hash: index + timestamp + merkle_root/data + previous_hash + nonce."""
        # Backward compatibility: use legacy hashing if merkle_root is missing
        if not hasattr(self, 'merkle_root') or self.merkle_root is None:
            data_text = (
                json.dumps(self.data, sort_keys=True, ensure_ascii=False)
                if isinstance(self.data, dict)
                else str(self.data)
            )
            full_string = (
                f"{self.index}{self.timestamp}{data_text}"
                f"{self.previous_hash}{self.nonce}"
            )
        else:
            full_string = (
                f"{self.index}{self.timestamp}{self.merkle_root}"
                f"{self.previous_hash}{self.nonce}"
            )
        return hashlib.sha256(full_string.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "signature": self.signature,
            "is_protected": self.is_protected,
            # protection_password is removed (stored separately in LMDB)
            "nonce": self.nonce,
            "device_id": self.device_id,
            "merkle_root": self.merkle_root,
        }


# ──────────────────────────────────────────────
# BLOCKCHAIN
# ──────────────────────────────────────────────

class Blockchain:
    """
    VIP Health Chain — Immutable, Encrypted, Device-Bound.
    Each block:
      - Linked to the previous block via SHA-256
      - Carries a hardware-bound HMAC-SHA256 signature
      - Contains optional AES-256 encrypted payload
      - Protected against replay attacks via a unique nonce
    """

    def __init__(self, project_name: str):
        self.project_name = project_name
        self.chain: List[Block] = []

        loaded = self._load_from_db()
        if loaded:
            self.chain = loaded
            print(f"[OK] Blockchain loaded: {len(self.chain)} blocks ({project_name})")
        else:
            print(f"[INFO] New chain: Genesis block being created ({project_name})")
            self._create_genesis_block()

    # ─────────────────────────────────────────
    # GENESIS BLOCK
    # ─────────────────────────────────────────

    def _create_genesis_block(self) -> None:
        storage.reset_db(self.project_name)
        ts = time.time()
        nonce = secrets.token_hex(16)
        device = get_device_id()
        msg = f"0|{ts}|Genesis Block|0|{nonce}"
        sig = signaturedata(msg)

        genesis = Block(
            index=0,
            timestamp=ts,
            data={
                "type": "genesis",
                "message": "VIP Health Vault — Genesis Block",
                "created_by": "system",
                "device_id": device,
            },
            previous_hash="0",
            signature=sig,
            nonce=nonce,
            device_id=device,
        )
        self.chain.append(genesis)
        self._persist(genesis)

    # ─────────────────────────────────────────
    # ADD BLOCK
    # ─────────────────────────────────────────

    def add_block(
        self,
        data: Any,
        is_protected: bool = False,
        protection_password: Optional[str] = None,
        username: str = "system",
    ) -> Block:
        """
        Adds a new health record block.
        AES-256 + unique salt is used for encrypted blocks.
        """
        last = self.chain[-1]
        index = last.index + 1
        ts = time.time()
        prev_hash = last.hash
        nonce = secrets.token_hex(16)
        device = get_device_id()

        data_to_store = data
        protection_hash = None

        if is_protected and protection_password:
            # Argon2 password hash
            protection_hash = hash_block_password(protection_password)

            payload_str = (
                json.dumps(data, sort_keys=True, ensure_ascii=False)
                if isinstance(data, dict)
                else str(data)
            )
            patient_salt = storage.get_patient_salt(self.project_name)
            encrypted_str, salt = encrypt_data(payload_str, protection_password, patient_salt)
            data_to_store = encrypted_str

            # Store block salt separately in LMDB
            storage.save_block_salt(self.project_name, index, salt)

        # Compute Merkle Root
        merkle_root = calculate_merkle_root(data_to_store)

        # Signing: index|ts|merkle_root|prev_hash|nonce
        msg = f"{index}|{ts}|{merkle_root}|{prev_hash}|{nonce}"
        signature = signaturedata(msg)

        block = Block(
            index=index,
            timestamp=ts,
            data=data_to_store,
            previous_hash=prev_hash,
            signature=signature,
            is_protected=is_protected,
            protection_password=protection_hash,
            nonce=nonce,
            device_id=device,
            merkle_root=merkle_root,
        )

        self.chain.append(block)
        self._persist(block)

        # Store password hash separately
        if is_protected and protection_hash:
            storage.save_block_pwd_hash(self.project_name, index, protection_hash)

        # Audit logging and Cryptographic Access Log
        storage.append_audit_log(
            self.project_name,
            action="BLOCK_ADDED",
            username=username,
            block_index=index,
            device_id=device,
            extra={"is_protected": is_protected},
        )
        storage.append_access_log(
            self.project_name,
            username=username,
            action="BLOCK_ADDED",
            device_id=device,
            extra={"block_index": index, "is_protected": is_protected},
        )
        self.add_audit_block(
            action="BLOCK_ADDED",
            username=username,
            target_block_index=index,
            extra={"is_protected": is_protected}
        )

        return block

    # ─────────────────────────────────────────
    # CORRECTION BLOCK (Append-Only)
    # ─────────────────────────────────────────

    def add_correction_block(
        self,
        block_index: int,
        corrected_data: Any,
        encryption_password: Optional[str] = None,
        username: str = "system",
    ) -> Block:
        """
        Appends a correction block representing an updated version of a previous block.
        Preserves complete history on the chain.
        """
        data_content = corrected_data

        if encryption_password:
            payload_str = (
                json.dumps(corrected_data, sort_keys=True, ensure_ascii=False)
                if isinstance(corrected_data, dict)
                else str(corrected_data)
            )
            last_real_index = self.chain[-1].index + 1
            patient_salt = storage.get_patient_salt(self.project_name)
            encrypted_str, salt = encrypt_data(payload_str, encryption_password, patient_salt)
            data_content = encrypted_str
            # Save salt to correction block index (next index)
            storage.save_block_salt(self.project_name, last_real_index, salt)

        correction_info = {
            "type": "correction",
            "correction_of": block_index,
            "corrected_data": data_content,
            "note": "Correction block — does not overwrite the previous record.",
            "corrected_by": username,
        }

        last = self.chain[-1]
        index = last.index + 1
        ts = time.time()
        prev_hash = last.hash
        nonce = secrets.token_hex(16)
        device = get_device_id()

        # Compute Merkle Root
        merkle_root = calculate_merkle_root(correction_info)

        # Signing: index|ts|merkle_root|prev_hash|nonce
        msg = f"{index}|{ts}|{merkle_root}|{prev_hash}|{nonce}"
        signature = signaturedata(msg)

        block = Block(
            index=index,
            timestamp=ts,
            data=correction_info,
            previous_hash=prev_hash,
            signature=signature,
            nonce=nonce,
            device_id=device,
            merkle_root=merkle_root,
        )

        self.chain.append(block)
        self._persist(block)

        storage.append_audit_log(
            self.project_name,
            action="CORRECTION_ADDED",
            username=username,
            block_index=index,
            device_id=device,
            extra={"correction_of": block_index},
        )
        storage.append_access_log(
            self.project_name,
            username=username,
            action="CORRECTION_ADDED",
            device_id=device,
            extra={"block_index": index, "correction_of": block_index},
        )
        self.add_audit_block(
            action="CORRECTION_ADDED",
            username=username,
            target_block_index=index,
            extra={"correction_of": block_index}
        )

        print(f"[OK] Correction block added for #{block_index} (new block #{index})")
        return block

    # ─────────────────────────────────────────
    # CRYPTOGRAPHIC ACCESS LOG (Audit Block)
    # ─────────────────────────────────────────

    def add_audit_block(
        self,
        action: str,
        username: str,
        target_block_index: Optional[int] = None,
        extra: Optional[dict] = None,
    ) -> Block:
        """Stores system access and audit events as blocks on the blockchain."""
        last = self.chain[-1]
        index = last.index + 1
        ts = time.time()
        prev_hash = last.hash
        nonce = secrets.token_hex(16)
        device = get_device_id()

        audit_data = {
            "type": "audit",
            "action": action,
            "username": username,
            "target_block_index": target_block_index,
            "device_id": device,
            **(extra or {})
        }

        # Compute Merkle Root
        merkle_root = calculate_merkle_root(audit_data)

        # Signing: index|ts|merkle_root|prev_hash|nonce
        msg = f"{index}|{ts}|{merkle_root}|{prev_hash}|{nonce}"
        signature = signaturedata(msg)

        block = Block(
            index=index,
            timestamp=ts,
            data=audit_data,
            previous_hash=prev_hash,
            signature=signature,
            is_protected=False,
            nonce=nonce,
            device_id=device,
            merkle_root=merkle_root,
        )

        self.chain.append(block)
        self._persist(block)
        return block

    # ─────────────────────────────────────────
    # READ BLOCK DATA (with Audit Logging)
    # ─────────────────────────────────────────

    def get_block_data(
        self,
        block_index: int,
        password: Optional[str] = None,
        username: str = "anonymous",
    ) -> Any:
        """
        Returns block data.
        Decrypts with password + unique salt for encrypted blocks.
        Every access is recorded to the audit logs.
        """
        if block_index < 0 or block_index >= len(self.chain):
            return None

        block = self.chain[block_index]

        # Audit log — access attempt (LMDB only)
        storage.append_audit_log(
            self.project_name,
            action="BLOCK_READ_ATTEMPT",
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
        )
        storage.append_access_log(
            self.project_name,
            username=username,
            action="BLOCK_READ_ATTEMPT",
            device_id=get_device_id(),
            extra={"block_index": block_index},
        )

        if block.is_protected:
            if not password:
                return "SECURE — password required"

            # Argon2 password verification
            if not verify_block_password(password, block.protection_password):
                storage.append_audit_log(
                    self.project_name,
                    action="BLOCK_READ_FAILED",
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                    extra={"reason": "WRONG_PASSWORD"},
                )
                storage.append_access_log(
                    self.project_name,
                    username=username,
                    action="BLOCK_READ_FAILED",
                    device_id=get_device_id(),
                    extra={"block_index": block_index, "reason": "WRONG_PASSWORD"},
                )
                return "INCORRECT PASSWORD"

            # Retrieve salt from LMDB
            salt = storage.load_block_salt(self.project_name, block_index)
            if not salt:
                return "Salt not found — data integrity error"

            try:
                decrypted_str = decrypt_data(block.data, password, salt)
                try:
                    result = json.loads(decrypted_str)
                except Exception:
                    result = decrypted_str

                storage.append_audit_log(
                    self.project_name,
                    action="BLOCK_READ_SUCCESS",
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                )
                storage.append_access_log(
                    self.project_name,
                    username=username,
                    action="BLOCK_READ_SUCCESS",
                    device_id=get_device_id(),
                    extra={"block_index": block_index},
                )
                return result

            except Exception as e:
                return f"DECRYPTION ERROR: {str(e)}"

        # Unprotected block
        storage.append_audit_log(
            self.project_name,
            action="BLOCK_READ_SUCCESS",
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
        )
        storage.append_access_log(
            self.project_name,
            username=username,
            action="BLOCK_READ_SUCCESS",
            device_id=get_device_id(),
            extra={"block_index": block_index},
        )
        return block.data

    # ─────────────────────────────────────────
    # READ FINAL BLOCK DATA (Corrections & Decryption)
    # ─────────────────────────────────────────

    def get_final_block_data(
        self,
        block_index: int,
        password: Optional[str] = None,
        username: str = "anonymous",
    ) -> Any:
        """
        Returns the final block data with corrections applied.
        Decrypts if encrypted.
        """
        if block_index < 0 or block_index >= len(self.chain):
            return None

        # Find if there is a correction block (take the latest correction)
        correction_block = None
        for block in reversed(self.chain):
            if (
                isinstance(block.data, dict)
                and block.data.get("type") == "correction"
                and block.data.get("correction_of") == block_index
            ):
                correction_block = block
                break

        # If no correction block, call standard get_block_data
        if not correction_block:
            return self.get_block_data(block_index, password, username)

        # Audit log — access attempt (LMDB only)
        storage.append_audit_log(
            self.project_name,
            action="BLOCK_READ_ATTEMPT",
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
            extra={"correction_index": correction_block.index},
        )
        storage.append_access_log(
            self.project_name,
            username=username,
            action="BLOCK_READ_ATTEMPT",
            device_id=get_device_id(),
            extra={"block_index": block_index, "correction_index": correction_block.index},
        )

        original_block = self.chain[block_index]
        corrected_data = correction_block.data["corrected_data"]

        if original_block.is_protected:
            if not password:
                return "SECURE — password required"

            # Argon2 password verification (against original block hash)
            if not verify_block_password(password, original_block.protection_password):
                storage.append_audit_log(
                    self.project_name,
                    action="BLOCK_READ_FAILED",
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                    extra={"reason": "WRONG_PASSWORD", "correction_index": correction_block.index},
                )
                storage.append_access_log(
                    self.project_name,
                    username=username,
                    action="BLOCK_READ_FAILED",
                    device_id=get_device_id(),
                    extra={"block_index": block_index, "reason": "WRONG_PASSWORD", "correction_index": correction_block.index},
                )
                return "INCORRECT PASSWORD"

            # Retrieve salt from LMDB (associated with the correction block index)
            salt = storage.load_block_salt(self.project_name, correction_block.index)
            if not salt:
                return "Salt not found — data integrity error"

            try:
                decrypted_str = decrypt_data(corrected_data, password, salt)
                try:
                    result = json.loads(decrypted_str)
                except Exception:
                    result = decrypted_str

                storage.append_audit_log(
                    self.project_name,
                    action="BLOCK_READ_SUCCESS",
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                    extra={"correction_index": correction_block.index},
                )
                storage.append_access_log(
                    self.project_name,
                    username=username,
                    action="BLOCK_READ_SUCCESS",
                    device_id=get_device_id(),
                    extra={"block_index": block_index, "correction_index": correction_block.index},
                )
                return result

            except Exception as e:
                return f"DECRYPTION ERROR: {str(e)}"

        # Unprotected block correction
        storage.append_audit_log(
            self.project_name,
            action="BLOCK_READ_SUCCESS",
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
            extra={"correction_index": correction_block.index},
        )
        storage.append_access_log(
            self.project_name,
            username=username,
            action="BLOCK_READ_SUCCESS",
            device_id=get_device_id(),
            extra={"block_index": block_index, "correction_index": correction_block.index},
        )
        return corrected_data

    # ─────────────────────────────────────────
    # FINAL STATE (Corrections Applied)
    # ─────────────────────────────────────────

    def get_final_data(self) -> Dict[int, Any]:
        """
        Returns the final state of all blocks.
        Correction blocks override legacy block data.
        """
        result: Dict[int, Any] = {}

        for block in self.chain:
            if isinstance(block.data, dict) and block.data.get("type") == "correction":
                continue
            result[block.index] = block.data

        for block in self.chain:
            if isinstance(block.data, dict) and block.data.get("type") == "correction":
                target = block.data.get("correction_of")
                if target is not None and target in result:
                    result[target] = block.data["corrected_data"]

        return result

    # ─────────────────────────────────────────
    # VALIDATION
    # ─────────────────────────────────────────

    def is_valid(self) -> bool:
        """Hash integrity + signature verification."""
        return self.find_broken_link_index() == -1

    def find_broken_link_index(self) -> int:
        """
        Returns the index of the first broken link.
        Returns -1 if the chain is valid.
        """
        seen_nonces = set()
        for i in range(1, len(self.chain)):
            prev = self.chain[i - 1]
            curr = self.chain[i]

            # Hash consistency check
            if curr.hash != curr.create_hash():
                return i

            # Previous hash chain check
            if curr.previous_hash != prev.hash:
                return i

            # Timestamp must be monotonically increasing (Monotonic timestamp check)
            if curr.timestamp < prev.timestamp:
                return i

            # Nonce must be unique (timestamp + nonce pairing replay attack protection)
            nonce_key = (curr.timestamp, curr.nonce)
            if nonce_key in seen_nonces:
                return i
            seen_nonces.add(nonce_key)

            # Signature verification
            if curr.merkle_root is not None:
                msg = f"{curr.index}|{curr.timestamp}|{curr.merkle_root}|{curr.previous_hash}|{curr.nonce}"
            else:
                data_text = (
                    json.dumps(curr.data, sort_keys=True, ensure_ascii=False)
                    if isinstance(curr.data, dict)
                    else str(curr.data)
                )
                msg = f"{curr.index}|{curr.timestamp}|{data_text}|{curr.previous_hash}|{curr.nonce}"
            
            if not verify_message(msg, curr.signature, curr.device_id):
                return i

        return -1

    # ─────────────────────────────────────────
    # LMDB PERSISTENCE
    # ─────────────────────────────────────────

    def _persist(self, block: Block) -> None:
        """Writes a single block atomically to LMDB."""
        storage.save_block_to_db(self.project_name, block.index, block.to_dict())

    def save_block(self, block: Block) -> None:
        """For UI compatibility — same as _persist()."""
        self._persist(block)

    def save_chain(self) -> None:
        """Legacy API compatibility — LMDB already writes incrementally."""
        pass

    def _load_from_db(self) -> Optional[List[Block]]:
        raw_blocks = storage.load_all_blocks(self.project_name)
        if not raw_blocks:
            return None

        blocks = []
        for b in raw_blocks:
            pwd_hash = None
            if b.get("is_protected", False):
                pwd_hash = storage.load_block_pwd_hash(self.project_name, b["index"])

            block = Block(
                index=b["index"],
                timestamp=b["timestamp"],
                data=b["data"],
                previous_hash=b["previous_hash"],
                signature=b["signature"],
                is_protected=b.get("is_protected", False),
                protection_password=pwd_hash,
                nonce=b.get("nonce", secrets.token_hex(16)),
                device_id=b.get("device_id", get_device_id()),
                hash_val=b.get("hash"),
                merkle_root=b.get("merkle_root"),
            )
            blocks.append(block)
        return blocks

    @staticmethod
    def load_chain(project_name: str) -> "Blockchain":
        return Blockchain(project_name)

    # ─────────────────────────────────────────
    # AUDIT LOG ACCESS
    # ─────────────────────────────────────────

    def get_audit_logs(self, limit: int = 50) -> List[dict]:
        return storage.load_audit_logs(self.project_name, limit)
