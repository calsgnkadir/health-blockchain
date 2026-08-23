import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from core.utils.crypto_utils import calculate_merkle_root

@dataclass
class User:
    id: str
    username: str
    password_hash: str
    role: str
    full_name: str
    patient_id: Optional[str] = None
    totp_secret: Optional[str] = None
    totp_enabled: bool = False
    specialty: Optional[str] = None
    institution: Optional[str] = None
    clearance: Optional[str] = None
    account_status: str = "ACTIVE_ENROLLED"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role,
            "full_name": self.full_name,
            "patient_id": self.patient_id,
            "totp_secret": self.totp_secret,
            "totp_enabled": self.totp_enabled,
            "specialty": self.specialty,
            "institution": self.institution,
            "clearance": self.clearance,
            "account_status": self.account_status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            id=data["id"],
            username=data["username"],
            password_hash=data["password_hash"],
            role=data["role"],
            full_name=data["full_name"],
            patient_id=data.get("patient_id"),
            totp_secret=data.get("totp_secret"),
            totp_enabled=data.get("totp_enabled", False),
            specialty=data.get("specialty"),
            institution=data.get("institution"),
            clearance=data.get("clearance"),
            account_status=data.get("account_status", "ACTIVE_ENROLLED"),
        )


@dataclass
class HealthRecord:
    patient_id: str
    record_type: str
    title: str
    doctor_name: str
    institution: str
    record_date: str
    access_level: str = "doctor_shared"
    is_confidential: bool = False
    data: Dict[str, Any] = field(default_factory=dict)
    notes: Optional[str] = ""

    def to_dict(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "record_type": self.record_type,
            "title": self.title,
            "doctor_name": self.doctor_name,
            "institution": self.institution,
            "record_date": self.record_date,
            "access_level": self.access_level,
            "is_confidential": self.is_confidential,
            "data": self.data,
            "notes": self.notes,
        }




@dataclass
class Block:
    """
    One block on a patient's append-only, tamper-evident chain.

    Three distinct digests, easily confused — this is the exact structure of the
    hash chain (see ``RecordService.find_broken_link_index`` for the verifier):

      • ``merkle_root`` — SHA-256 Merkle root over this block's ``data`` (the
        already-AES-encrypted payload). Covers *content*.
      • ``hash``        — SHA-256 over this block's fields
        (``index|timestamp|merkle_root|previous_hash|nonce|metadata``). This is
        the block's own identity digest.
      • ``previous_hash`` — the **previous block's ``hash``**. This is what links
        the chain: block N's ``previous_hash`` must equal block N-1's ``hash``.
      • ``signature``   — HMAC-SHA256 (KMS-keyed) over
        ``index|timestamp|merkle_root|previous_hash|nonce``. Authenticity: only the
        signing-key holder could have produced it. Independent of ``hash``.

    So integrity is a hash chain (``previous_hash`` → prior ``hash``) and
    authenticity is a separate keyed signature; the verifier checks both.
    """
    index: int
    timestamp: float
    data: Any
    previous_hash: str          # == the previous block's `hash` (chain link)
    signature: str              # HMAC-SHA256 over the signed fields (authenticity)
    is_protected: bool = False
    protection_hash: Optional[str] = None
    nonce: Optional[str] = None
    device_id: Optional[str] = None
    hash: Optional[str] = None          # this block's own SHA-256 identity digest
    merkle_root: Optional[str] = None   # Merkle root over `data` (content digest)

    def __post_init__(self):
        if not self.merkle_root and self.index != 0:
            self.merkle_root = calculate_merkle_root(self.data)
        if not self.hash:
            self.hash = self.create_hash()

    def create_hash(self) -> str:
        """SHA-256 hash of the block's fields."""
        prot_hash_str = str(self.protection_hash) if self.protection_hash else ""
        device_id_str = str(self.device_id) if self.device_id else ""
        is_prot_str = "1" if self.is_protected else "0"

        metadata_suffix = f"{is_prot_str}{prot_hash_str}{device_id_str}"

        if not self.merkle_root:
            data_text = (
                json.dumps(self.data, sort_keys=True, ensure_ascii=False)
                if isinstance(self.data, dict)
                else str(self.data)
            )
            full_string = (
                f"{self.index}{self.timestamp}{data_text}"
                f"{self.previous_hash}{self.nonce}{metadata_suffix}"
            )
        else:
            full_string = (
                f"{self.index}{self.timestamp}{self.merkle_root}"
                f"{self.previous_hash}{self.nonce}{metadata_suffix}"
            )
        return hashlib.sha256(full_string.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "signature": self.signature,
            "is_protected": self.is_protected,
            "nonce": self.nonce,
            "device_id": self.device_id,
            "hash": self.hash,
            "merkle_root": self.merkle_root,
            "protection_hash": self.protection_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(
            index=data["index"],
            timestamp=data["timestamp"],
            data=data["data"],
            previous_hash=data["previous_hash"],
            signature=data["signature"],
            is_protected=data.get("is_protected", False),
            protection_hash=data.get("protection_hash") or data.get("protection_password"),
            nonce=data.get("nonce"),
            device_id=data.get("device_id"),
            hash=data.get("hash"),
            merkle_root=data.get("merkle_root"),
        )

