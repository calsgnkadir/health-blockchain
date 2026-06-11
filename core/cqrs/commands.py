import json
from typing import Any, Optional, Dict, List
from core.domain.entities import User, Block
from core.ports.repositories import IBlockRepository
from infrastructure.repositories.lmdb_unit_of_work import LMDBUnitOfWork
from core.services.record_service import RecordService
from core.services.auth_service import AuthService
import database.storage as storage

class AddRecordCommand:
    def __init__(
        self,
        patient_id: str,
        data: Any,
        is_protected: bool = False,
        protection_password: Optional[str] = None,
        username: str = "system",
    ):
        self.patient_id = patient_id
        self.data = data
        self.is_protected = is_protected
        self.protection_password = protection_password
        self.username = username

class AddCorrectionCommand:
    def __init__(
        self,
        patient_id: str,
        block_index: int,
        corrected_data: Any,
        encryption_password: Optional[str] = None,
        username: str = "system",
    ):
        self.patient_id = patient_id
        self.block_index = block_index
        self.corrected_data = corrected_data
        self.encryption_password = encryption_password
        self.username = username

class CreateUserCommand:
    def __init__(
        self,
        username: str,
        password: str,
        role: str,
        full_name: str,
        patient_id: Optional[str] = None,
        specialty: Optional[str] = None,
        institution: Optional[str] = None,
        creator_username: str = "system",
    ):
        self.username = username
        self.password = password
        self.role = role
        self.full_name = full_name
        self.patient_id = patient_id
        self.specialty = specialty
        self.institution = institution
        self.creator_username = creator_username

class GrantConsentCommand:
    def __init__(
        self,
        patient_id: str,
        doctor_username: str,
        record_type: str,
        duration_days: int,
        username: str,
    ):
        self.patient_id = patient_id
        self.doctor_username = doctor_username
        self.record_type = record_type
        self.duration_days = duration_days
        self.username = username

class RevokeConsentCommand:
    def __init__(
        self,
        patient_id: str,
        doctor_username: str,
        record_type: str,
        username: str,
    ):
        self.patient_id = patient_id
        self.doctor_username = doctor_username
        self.record_type = record_type
        self.username = username


class CommandHandler:
    def __init__(
        self,
        record_service: RecordService,
        auth_service: AuthService,
        block_repo: IBlockRepository,
    ):
        self.record_service = record_service
        self.auth_service = auth_service
        self.block_repo = block_repo

    def handle_add_record(self, cmd: AddRecordCommand) -> Block:
        project_name = self.record_service._get_project_name(cmd.patient_id)
        with LMDBUnitOfWork(project_name):
            return self.record_service.add_record(
                patient_id=cmd.patient_id,
                data=cmd.data,
                is_protected=cmd.is_protected,
                protection_password=cmd.protection_password,
                username=cmd.username,
            )

    def handle_add_correction(self, cmd: AddCorrectionCommand) -> Block:
        project_name = self.record_service._get_project_name(cmd.patient_id)
        with LMDBUnitOfWork(project_name):
            return self.record_service.add_correction_block(
                patient_id=cmd.patient_id,
                block_index=cmd.block_index,
                corrected_data=cmd.corrected_data,
                encryption_password=cmd.encryption_password,
                username=cmd.username,
            )

    def handle_create_user(self, cmd: CreateUserCommand) -> User:
        with LMDBUnitOfWork("__users__"):
            return self.auth_service.create_user(
                username=cmd.username,
                password=cmd.password,
                role=cmd.role,
                full_name=cmd.full_name,
                patient_id=cmd.patient_id,
                specialty=cmd.specialty,
                institution=cmd.institution,
                creator_username=cmd.creator_username,
            )

    def handle_grant_consent(self, cmd: GrantConsentCommand) -> None:
        import time
        project_name = self.record_service._get_project_name(cmd.patient_id)
        expiry_ts = time.time() + (cmd.duration_days * 86400)
        consent_data = {
            "doctor_username": cmd.doctor_username,
            "record_type": cmd.record_type,
            "expiry_timestamp": expiry_ts,
            "granted_at": time.time(),
        }
        key = f"consent_{cmd.doctor_username}_{cmd.record_type}".encode("utf-8")
        
        def txn_consent(txn):
            txn.put(key, json.dumps(consent_data).encode("utf-8"))
        
        with LMDBUnitOfWork(project_name):
            storage.run_write_transaction(project_name, txn_consent)
            storage.append_access_log(
                project_name=project_name,
                username=cmd.username,
                action="CONSENT_GRANTED",
                extra={"doctor": cmd.doctor_username, "record_type": cmd.record_type, "days": cmd.duration_days}
            )

    def handle_revoke_consent(self, cmd: RevokeConsentCommand) -> None:
        project_name = self.record_service._get_project_name(cmd.patient_id)
        key = f"consent_{cmd.doctor_username}_{cmd.record_type}".encode("utf-8")
        
        def txn_revoke(txn):
            txn.delete(key)
            
        with LMDBUnitOfWork(project_name):
            storage.run_write_transaction(project_name, txn_revoke)
            storage.append_access_log(
                project_name=project_name,
                username=cmd.username,
                action="CONSENT_REVOKED",
                extra={"doctor": cmd.doctor_username, "record_type": cmd.record_type}
            )
