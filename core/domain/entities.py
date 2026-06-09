from dataclasses import dataclass, field
from typing import Optional, Dict, Any

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


import hashlib
import json

def calculate_merkle_root(data: Any) -> str:
    """
    Computes Merkle Root hash based on leaf data elements.
    """
    if data is None:
        return hashlib.sha256(b"").hexdigest()
        
    leaves = []
    if isinstance(data, dict):
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
        leaf_hash = hashlib.sha256(str(data).encode("utf-8")).hexdigest()
        leaves.append(leaf_hash)
        
    if not leaves:
        return hashlib.sha256(b"").hexdigest()
        
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


@dataclass
class Block:
    index: int
    timestamp: float
    data: Any
    previous_hash: str
    signature: str
    is_protected: bool = False
    protection_password: Optional[str] = None
    nonce: Optional[str] = None
    device_id: Optional[str] = None
    hash: Optional[str] = None
    merkle_root: Optional[str] = None

    def __post_init__(self):
        if not self.merkle_root and self.index != 0:
            self.merkle_root = calculate_merkle_root(self.data)
        if not self.hash:
            self.hash = self.create_hash()

    def create_hash(self) -> str:
        """SHA-256 hash of the block's fields."""
        if not self.merkle_root:
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
            "signature": self.signature,
            "is_protected": self.is_protected,
            "nonce": self.nonce,
            "device_id": self.device_id,
            "hash": self.hash,
            "merkle_root": self.merkle_root,
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
            protection_password=data.get("protection_password"),
            nonce=data.get("nonce"),
            device_id=data.get("device_id"),
            hash=data.get("hash"),
            merkle_root=data.get("merkle_root"),
        )

