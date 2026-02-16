
import time
import json
import hashlib
from typing import Optional

from core.security import signaturedata, verify_message, encrypt_data, decrypt_data
import database.storage as storage

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
        hash_val: Optional[str] = None # Added optional hash_val for loading
    ):
        self.index = index
        self.timestamp = timestamp
        self.data = data
        self.previous_hash = previous_hash
        self.is_protected = is_protected
        self.protection_password = protection_password
        self.signature = signature
        
        # Calculate or set hash
        if hash_val:
            self.hash = hash_val
        else:
            self.hash = self.create_hash()

    def create_hash(self) -> str:
        """Creates SHA256 hash from block fields."""
        data_text = (
            json.dumps(self.data, sort_keys=True)
            if isinstance(self.data, dict)
            else str(self.data)
        )

        full_string = f"{self.index}{self.timestamp}{data_text}{self.previous_hash}"
        return hashlib.sha256(full_string.encode()).hexdigest()

    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "signature": self.signature,
            "is_protected": self.is_protected,
            "protection_password": self.protection_password,
        }

# ---------------------------------------------------------
# BLOCKCHAIN
# ---------------------------------------------------------
class Blockchain:
    """Enterprise-grade blockchain using LMDB storage."""

    def __init__(self, project_name: str):
        self.chain: list[Block] = []
        self.project_name = project_name
        
        # Try to load existing chain
        loaded_blocks = self.load_chain_from_db()
        if loaded_blocks:
            self.chain = loaded_blocks
            print(f"✔ LMDB: Blockchain initialized with {len(self.chain)} blocks.")
        else:
            print("⚠ New Chain: Creating Genesis Block.")
            self.create_genesis_block()

    # -----------------------------------------------------
    # GENESIS BLOCK
    # -----------------------------------------------------
    def create_genesis_block(self):
        # Reset DB just in case
        storage.reset_db(self.project_name)
        
        ts = time.time()
        sig = signaturedata(f"0|{ts}|Genesis Block|0")
        block = Block(0, ts, "Genesis Block", "0", sig)
        self.chain.append(block)
        self.save_block(block) # Commit to LMDB

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

        # Encrypt data if needed BEFORE signing
        data_to_store = data
        protection_hash = None
        
        if is_protected and protection_password:
            protection_hash = hashlib.sha256(protection_password.encode()).hexdigest()
            # Encrypt payload
            payload_str = (
                json.dumps(data, sort_keys=True)
                if isinstance(data, dict)
                else str(data)
            )
            data_to_store = encrypt_data(payload_str, protection_password)

        # Sign the stored data
        stored_data_text = (
            json.dumps(data_to_store, sort_keys=True)
            if isinstance(data_to_store, dict)
            else str(data_to_store)
        )
        msg = f"{index}|{ts}|{stored_data_text}|{prev_hash}"
        signature = signaturedata(msg)

        block = Block(
            index=index,
            timestamp=ts,
            data=data_to_store,
            previous_hash=prev_hash,
            signature=signature,
            is_protected=is_protected,
            protection_password=protection_hash,
        )

        self.chain.append(block)
        self.save_block(block) # Immediate persist

    # -----------------------------------------------------
    # ADD CORRECTION BLOCK
    # -----------------------------------------------------
    def add_correction_block(self, block_index: int, corrected_data, encryption_password: Optional[str] = None):
        """Append-only correction."""
        data_content = corrected_data
        
        if encryption_password:
             payload_str = (
                json.dumps(corrected_data, sort_keys=True)
                if isinstance(corrected_data, dict)
                else str(corrected_data)
            )
             data_content = encrypt_data(payload_str, encryption_password)

        correction_info = {
            "correction_of": block_index,
            "corrected_data": data_content,
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
        self.save_block(block) # Immediate persist
        print(f"✔ Correction block committed via LMDB transaction.")

    # -----------------------------------------------------
    # READ / RETRIEVE
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
            
            # Decrypt
            try:
                decrypted_str = decrypt_data(block.data, password)
                try:
                    return json.loads(decrypted_str)
                except:
                    return decrypted_str
            except Exception as e:
                return f"❌ DECRYPTION FAILED: {str(e)}"

        return block.data

    def get_final_data(self) -> dict:
        result = {}
        # Base blocks
        for block in self.chain:
            if isinstance(block.data, dict) and "correction_of" in block.data:
                continue
            result[block.index] = block.data
        # Corrections
        for block in self.chain:
            if isinstance(block.data, dict) and "correction_of" in block.data:
                target = block.data["correction_of"]
                if target in result:
                     result[target] = block.data["corrected_data"]
        return result

    # -----------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------
    def is_valid(self) -> bool:
        """Verify hash integrity and signatures."""
        for prev, curr in zip(self.chain, self.chain[1:]):
            if curr.hash != curr.create_hash():
                return False
            if curr.previous_hash != prev.hash:
                return False

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
    # LMDB PERSISTENCE
    # -----------------------------------------------------
    def save_block(self, block):
        """Saves a SINGLE block to LMDB (Atomic Write)."""
        storage.save_block_to_db(self.project_name, block.index, block.to_dict())
        # No need to dump whole chain anymore! Huge win.

    def save_chain(self):
        """Deprecated: LMDB saves incrementally. This is kept for compatibility."""
        pass 

    def load_chain_from_db(self):
        """Loads all blocks from LMDB."""
        raw_blocks = storage.load_all_blocks(self.project_name)
        if not raw_blocks:
            return None
            
        blocks = []
        for b in raw_blocks:
            block = Block(
                index=b["index"],
                timestamp=b["timestamp"],
                data=b["data"],
                previous_hash=b["previous_hash"],
                signature=b["signature"],
                is_protected=b.get("is_protected", False),
                protection_password=b.get("protection_password"),
                hash_val=b.get("hash")
            )
            blocks.append(block)
        return blocks
        
    @staticmethod
    def load_chain(project_name: str):
        # Factory method pattern
        return Blockchain(project_name)
