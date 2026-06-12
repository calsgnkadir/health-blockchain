import json
import time
from typing import Any, Optional, Dict, List
from core.domain.entities import Block
from core.domain.factories import BlockFactory
from core.ports.repositories import IBlockRepository
from core.ports.cryptography import IEncryptionStrategy
from core.security import (
    verify_block_password,
    hash_block_password,
    verify_message,
    get_device_id,
)
from core.events.event_bus import event_bus, RecordAddedEvent, RecordReadEvent

class RecordService:
    def __init__(self, block_repo: IBlockRepository, crypto_strategy: IEncryptionStrategy):
        self.block_repo = block_repo
        self.crypto_strategy = crypto_strategy

    def _get_project_name(self, patient_id: str) -> str:
        return f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"

    def _get_or_create_chain(self, patient_id: str) -> List[Block]:
        project_name = self._get_project_name(patient_id)
        if not self.block_repo.project_exists(project_name):
            self.block_repo.create_project(project_name)

        chain = self.block_repo.load_all_blocks(project_name)
        if not chain:
            # Create genesis block
            genesis = BlockFactory.create_genesis_block()
            self.block_repo.reset_db(project_name)
            self.block_repo.save_block(project_name, genesis)
            chain = [genesis]
        return chain

    def get_chain(self, patient_id: str) -> List[Block]:
        return self._get_or_create_chain(patient_id)

    def add_record(
        self,
        patient_id: str,
        data: Any,
        is_protected: bool = False,
        protection_password: Optional[str] = None,
        username: str = "system",
    ) -> Block:
        project_name = self._get_project_name(patient_id)
        chain = self._get_or_create_chain(patient_id)
        last_block = chain[-1]
        index = last_block.index + 1
        previous_hash = last_block.hash

        data_to_store = data
        protection_hash = None

        if is_protected and protection_password:
            protection_hash = hash_block_password(protection_password)
            payload_str = (
                json.dumps(data, sort_keys=True, ensure_ascii=False)
                if isinstance(data, dict)
                else str(data)
            )
            patient_salt = self.block_repo.get_patient_salt(project_name)
            encrypted_str, salt = self.crypto_strategy.encrypt_data(
                payload_str, protection_password, patient_salt
            )
            data_to_store = encrypted_str
            self.block_repo.save_block_salt(project_name, index, salt)

        block = BlockFactory.create_data_block(
            index=index,
            previous_hash=previous_hash,
            data=data_to_store,
            is_protected=is_protected,
            protection_hash=protection_hash,
        )

        self.block_repo.save_block(project_name, block)

        if is_protected and protection_hash:
            self.block_repo.save_block_pwd_hash(project_name, index, protection_hash)

        # Publish decouple audit log events
        event_bus.publish(RecordAddedEvent(
            project_name=project_name,
            username=username,
            block_index=index,
            device_id=block.device_id,
            is_protected=is_protected
        ))

        # Create audit block on chain
        audit_index = index + 1
        audit_block = BlockFactory.create_audit_block(
            index=audit_index,
            previous_hash=block.hash,
            action="BLOCK_ADDED",
            username=username,
            target_block_index=index,
            extra={"is_protected": is_protected}
        )
        self.block_repo.save_block(project_name, audit_block)

        return block

    def add_correction_block(
        self,
        patient_id: str,
        block_index: int,
        corrected_data: Any,
        encryption_password: Optional[str] = None,
        username: str = "system",
    ) -> Block:
        project_name = self._get_project_name(patient_id)
        chain = self._get_or_create_chain(patient_id)
        last_block = chain[-1]
        index = last_block.index + 1
        previous_hash = last_block.hash

        data_content = corrected_data

        if encryption_password:
            payload_str = (
                json.dumps(corrected_data, sort_keys=True, ensure_ascii=False)
                if isinstance(corrected_data, dict)
                else str(corrected_data)
            )
            patient_salt = self.block_repo.get_patient_salt(project_name)
            encrypted_str, salt = self.crypto_strategy.encrypt_data(
                payload_str, encryption_password, patient_salt
            )
            data_content = encrypted_str
            self.block_repo.save_block_salt(project_name, index, salt)

        block = BlockFactory.create_correction_block(
            index=index,
            previous_hash=previous_hash,
            corrected_block_index=block_index,
            corrected_data=data_content,
            username=username,
        )

        self.block_repo.save_block(project_name, block)

        event_bus.publish(RecordReadEvent(
            project_name=project_name,
            username=username,
            block_index=index,
            device_id=block.device_id,
            action="CORRECTION_ADDED",
            extra={"correction_of": block_index}
        ))

        # Create audit block on chain
        audit_index = index + 1
        audit_block = BlockFactory.create_audit_block(
            index=audit_index,
            previous_hash=block.hash,
            action="CORRECTION_ADDED",
            username=username,
            target_block_index=index,
            extra={"correction_of": block_index}
        )
        self.block_repo.save_block(project_name, audit_block)

        return block

    def get_block_data(
        self,
        patient_id: str,
        block_index: int,
        password: Optional[str] = None,
        username: str = "anonymous",
    ) -> Any:
        project_name = self._get_project_name(patient_id)
        chain = self._get_or_create_chain(patient_id)

        block = next((b for b in chain if b.index == block_index), None)
        if not block:
            return None

        event_bus.publish(RecordReadEvent(
            project_name=project_name,
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
            action="BLOCK_READ_ATTEMPT"
        ))

        if block.is_protected:
            if not password:
                return "SECURE — password required"

            stored_hash = self.block_repo.load_block_pwd_hash(project_name, block_index)
            if not stored_hash or not verify_block_password(password, stored_hash):
                event_bus.publish(RecordReadEvent(
                    project_name=project_name,
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                    action="BLOCK_READ_FAILED",
                    extra={"reason": "WRONG_PASSWORD"}
                ))
                return "INCORRECT PASSWORD"

            salt = self.block_repo.load_block_salt(project_name, block_index)
            if not salt:
                return "Salt not found — data integrity error"

            try:
                decrypted_str = self.crypto_strategy.decrypt_data(block.data, password, salt)
            except Exception as e:
                event_bus.publish(RecordReadEvent(
                    project_name=project_name,
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                    action="BLOCK_READ_FAILED",
                    extra={"reason": f"DECRYPTION_ERROR: {str(e)}"}
                ))
                return f"DECRYPTION ERROR: {str(e)}"

            try:
                result = json.loads(decrypted_str)
            except Exception:
                result = decrypted_str

            event_bus.publish(RecordReadEvent(
                project_name=project_name,
                username=username,
                block_index=block_index,
                device_id=get_device_id(),
                action="BLOCK_READ_SUCCESS"
            ))
            return result

        # Unprotected
        event_bus.publish(RecordReadEvent(
            project_name=project_name,
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
            action="BLOCK_READ_SUCCESS"
        ))
        return block.data

    def get_final_block_data(
        self,
        patient_id: str,
        block_index: int,
        password: Optional[str] = None,
        username: str = "anonymous",
    ) -> Any:
        project_name = self._get_project_name(patient_id)
        chain = self._get_or_create_chain(patient_id)

        block = next((b for b in chain if b.index == block_index), None)
        if not block:
            return None

        # Find latest correction block if any
        correction_block = None
        for block in reversed(chain):
            if (
                isinstance(block.data, dict)
                and block.data.get("type") == "correction"
                and block.data.get("correction_of") == block_index
            ):
                correction_block = block
                break

        if not correction_block:
            return self.get_block_data(patient_id, block_index, password, username)

        event_bus.publish(RecordReadEvent(
            project_name=project_name,
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
            action="BLOCK_READ_ATTEMPT",
            extra={"correction_index": correction_block.index}
        ))

        original_block = block
        corrected_data = correction_block.data["corrected_data"]

        if original_block.is_protected:
            if not password:
                return "SECURE — password required"

            stored_hash = self.block_repo.load_block_pwd_hash(project_name, block_index)
            if not stored_hash or not verify_block_password(password, stored_hash):
                event_bus.publish(RecordReadEvent(
                    project_name=project_name,
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                    action="BLOCK_READ_FAILED",
                    extra={"reason": "WRONG_PASSWORD", "correction_index": correction_block.index}
                ))
                return "INCORRECT PASSWORD"

            salt = self.block_repo.load_block_salt(project_name, correction_block.index)
            if not salt:
                return "Salt not found — data integrity error"

            try:
                decrypted_str = self.crypto_strategy.decrypt_data(corrected_data, password, salt)
            except Exception as e:
                event_bus.publish(RecordReadEvent(
                    project_name=project_name,
                    username=username,
                    block_index=block_index,
                    device_id=get_device_id(),
                    action="BLOCK_READ_FAILED",
                    extra={"reason": f"DECRYPTION_ERROR: {str(e)}", "correction_index": correction_block.index}
                ))
                return f"DECRYPTION ERROR: {str(e)}"

            try:
                result = json.loads(decrypted_str)
            except Exception:
                result = decrypted_str

            event_bus.publish(RecordReadEvent(
                project_name=project_name,
                username=username,
                block_index=block_index,
                device_id=get_device_id(),
                action="BLOCK_READ_SUCCESS",
                extra={"correction_index": correction_block.index}
            ))
            return result

        # Unprotected block correction
        event_bus.publish(RecordReadEvent(
            project_name=project_name,
            username=username,
            block_index=block_index,
            device_id=get_device_id(),
            action="BLOCK_READ_SUCCESS",
            extra={"correction_index": correction_block.index}
        ))
        return corrected_data

    def get_final_data(self, patient_id: str) -> Dict[int, Any]:
        chain = self._get_or_create_chain(patient_id)
        result: Dict[int, Any] = {}

        for block in chain:
            if isinstance(block.data, dict) and block.data.get("type") == "correction":
                continue
            result[block.index] = block.data

        for block in chain:
            if isinstance(block.data, dict) and block.data.get("type") == "correction":
                target = block.data.get("correction_of")
                if target is not None and target in result:
                    result[target] = block.data["corrected_data"]

        return result

    def is_chain_valid(self, patient_id: str) -> bool:
        return self.find_broken_link_index(patient_id) == -1

    def find_broken_link_index(self, patient_id: str) -> int:
        chain = self._get_or_create_chain(patient_id)
        seen_nonces = set()
        for i in range(1, len(chain)):
            prev = chain[i - 1]
            curr = chain[i]

            if curr.hash != curr.create_hash():
                return i

            if curr.previous_hash != prev.hash:
                return i

            if curr.timestamp < prev.timestamp:
                return i

            nonce_key = (curr.timestamp, curr.nonce)
            if nonce_key in seen_nonces:
                return i
            seen_nonces.add(nonce_key)

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
