# healthchain.py
import os
import time
import json
import hashlib
from typing import Optional

from security import signaturedata, verify_message

# Optional project manager support
try:
    from project_manager import get_blockchain_file
except ImportError:
    get_blockchain_file = None


# ---------------------------------------------------------
# BLOCK
# ---------------------------------------------------------
class Block:
    """Represents a single block in the blockchain."""

    def __init__(
        self,
        index: int,
        timestamp: float,
        data,
        previous_hash: str,
        signature: str,
        is_protected: bool = False,
        protection_password: Optional[str] = None,
    ):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.is_protected = is_protected
        self.protection_password = protection_password  # Already hashed
        self.hash = self.create_hash()
        self.signature = signature

    def create_hash(self) -> str:
        """Creates SHA256 hash from block fields."""
        data_text = (
            json.dumps(self.data, sort_keys=True)
            if isinstance(self.data, dict)
            else str(self.data)
        )

        full_string = f"{self.index}{self.timestamp}{data_text}{self.previous_hash}"
        return hashlib.sha256(full_string.encode()).hexdigest()


# ---------------------------------------------------------
# BLOCKCHAIN
# ---------------------------------------------------------
class Blockchain:
    """Basic blockchain with correction blocks and protected blocks."""

    def __init__(self, project_name: Optional[str] = None, **_):
        self.chain: list[Block] = []
        self.project_name = project_name
        self.encryption_password = None  # kept only for compatibility
        self.create_genesis_block()

    # -----------------------------------------------------
    # GENESIS BLOCK
    # -----------------------------------------------------
    def create_genesis_block(self):
        ts = time.time()
        sig = signaturedata(f"0|{ts}|Genesis Block|0")
        block = Block(0, ts, "Genesis Block", "0", sig)
        self.chain.append(block)

    # -----------------------------------------------------
    # ADD NORMAL BLOCK
    # -----------------------------------------------------
    def add_block(
        self,
        data,
        is_protected: bool = False,
        protection_password: Optional[str] = None,
    ):
        last = self.chain[-1]
        index = last.index + 1
        ts = time.time()
        prev_hash = last.hash

        # Sign message
        data_text = (
            json.dumps(data, sort_keys=True)
            if isinstance(data, dict)
            else str(data)
        )

        msg = f"{index}|{ts}|{data_text}|{prev_hash}"
        signature = signaturedata(msg)

        # Hash password if protection is enabled
        protection_hash = None
        if is_protected and protection_password:
            protection_hash = hashlib.sha256(protection_password.encode()).hexdigest()

        block = Block(
            index=index,
            timestamp=ts,
            data=data,
            previous_hash=prev_hash,
            signature=signature,
            is_protected=is_protected,
            protection_password=protection_hash,
        )

        self.chain.append(block)

    # -----------------------------------------------------
    # READ BLOCK DATA (PASSWORD CHECK IF PROTECTED)
    # -----------------------------------------------------
    def get_block_data(self, block_index: int, password: Optional[str] = None):
        if block_index < 0 or block_index >= len(self.chain):
            return None

        block = self.chain[block_index]

        if block.is_protected:
            if not password:
                return "🔒 PROTECTED — password required"
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if password_hash != block.protection_password:
                return "❌ INCORRECT PASSWORD"

        return block.data

    # -----------------------------------------------------
    # ADD CORRECTION BLOCK
    # -----------------------------------------------------
    def add_correction_block(self, block_index: int, corrected_data):
        """
        Adds a correction block which overrides the data of an earlier block.
        """
        correction_info = {
            "correction_of": block_index,
            "corrected_data": corrected_data,
            "note": "Correction block for a previous entry.",
        }

        last = self.chain[-1]
        index = last.index + 1
        ts = time.time()
        prev_hash = last.hash

        data_string = json.dumps(correction_info, sort_keys=True)
        msg = f"{index}|{ts}|{data_string}|{prev_hash}"
        signature = signaturedata(msg)

        block = Block(
            index=index,
            timestamp=ts,
            data=correction_info,
            previous_hash=prev_hash,
            signature=signature,
        )

        self.chain.append(block)
        print(f"✔ Correction block added for block #{block_index}")

    # -----------------------------------------------------
    # FINAL DATA (AFTER CORRECTIONS)
    # -----------------------------------------------------
    def get_final_data(self) -> dict:
        result = {}

        # First: add all normal blocks
        for block in self.chain:
            if isinstance(block.data, dict) and "correction_of" in block.data:
                continue
            result[block.index] = block.data

        # Second: apply corrections
        for block in self.chain:
            if isinstance(block.data, dict) and "correction_of" in block.data:
                target = block.data["correction_of"]
                result[target] = block.data["corrected_data"]

        return result

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------
    def is_valid(self) -> bool:
        """Verify hash integrity and signatures."""
        for prev, curr in zip(self.chain, self.chain[1:]):

            # Hash check
            if curr.hash != curr.create_hash():
                return False

            # Previous hash check
            if curr.previous_hash != prev.hash:
                return False

            # Signature verification
            data_text = (
                json.dumps(curr.data, sort_keys=True)
                if isinstance(curr.data, dict)
                else str(curr.data)
            )
            msg = f"{curr.index}|{curr.timestamp}|{data_text}|{curr.previous_hash}"

            if not verify_message(msg, curr.signature):
                return False

        return True

    # -----------------------------------------------------
    # DEFAULT SAVE PATH
    # -----------------------------------------------------
    def _default_filename(self):
        if self.project_name and get_blockchain_file:
            return get_blockchain_file(self.project_name)
        return "current_chain.json"

    # -----------------------------------------------------
    # SAVE BLOCKCHAIN
    # -----------------------------------------------------
    def save_chain(self, filename: Optional[str] = None, encrypted: bool = False):
        if filename is None:
            filename = self._default_filename()

        export = [
            {
                "index": b.index,
                "timestamp": b.timestamp,
                "data": b.data,
                "previous_hash": b.previous_hash,
                "hash": b.hash,
                "signature": b.signature,
                "is_protected": b.is_protected,
                "protection_password": b.protection_password,
            }
            for b in self.chain
        ]

        # Ensure directory exists
        folder = os.path.dirname(filename)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=4)

        print(f"💾 Blockchain saved to {filename}")

    # -----------------------------------------------------
    # LOAD BLOCKCHAIN
    # -----------------------------------------------------
    @staticmethod
    def load_chain(
        filename: Optional[str] = None,
        encryption_password: Optional[str] = None,
        project_name: Optional[str] = None,
    ):
        if filename is None and project_name and get_blockchain_file:
            filename = get_blockchain_file(project_name)

        if not filename:
            return None

        try:
            with open(filename, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            print("❌ File not found.")
            return None
        except json.JSONDecodeError:
            print("❌ Invalid JSON file.")
            return None

        # Support both formats:
        if isinstance(raw, dict) and "blocks" in raw:
            blocks_data = raw["blocks"]
        elif isinstance(raw, list):
            blocks_data = raw
        else:
            print("❌ Unsupported blockchain format.")
            return None

        bc = Blockchain(project_name=project_name)
        bc.chain = []

        for b in blocks_data:
            block = Block(
                index=b["index"],
                timestamp=b["timestamp"],
                data=b["data"],
                previous_hash=b["previous_hash"],
                signature=b["signature"],
                is_protected=b.get("is_protected", False),
                protection_password=b.get("protection_password"),
            )
            bc.chain.append(block)

        print(f"✔ Loaded blockchain from {filename}")
        return bc


