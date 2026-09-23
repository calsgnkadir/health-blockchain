import json
from datetime import datetime, timezone
from typing import Any, Optional, List
from core.ports.repositories import IBlockRepository, INotificationRepository
from core.services.record_service import RecordService
from core.services.consent_validator import ConsentValidator
import database.storage as storage

class GetPatientRecordsQuery:
    def __init__(self, patient_id: str, requester_username: str, requester_role: str):
        self.patient_id = patient_id
        self.requester_username = requester_username
        self.requester_role = requester_role

class DecryptRecordQuery:
    def __init__(self, patient_id: str, block_index: int, password: Optional[str], requester_username: str, requester_role: str):
        self.patient_id = patient_id
        self.block_index = block_index
        self.password = password
        self.requester_username = requester_username
        self.requester_role = requester_role

class GetNotificationsQuery:
    def __init__(self, patient_id: str, username: str):
        self.patient_id = patient_id
        self.username = username

class GetConsentsQuery:
    def __init__(self, patient_id: str):
        self.patient_id = patient_id


class QueryHandler:
    def __init__(
        self,
        record_service: RecordService,
        block_repo: IBlockRepository,
        consent_validator: ConsentValidator,
        notif_repo: INotificationRepository,
    ):
        self.record_service = record_service
        self.block_repo = block_repo
        self.consent_validator = consent_validator
        self.notif_repo = notif_repo

    def handle_get_patient_records(self, query: GetPatientRecordsQuery) -> List[dict]:
        patient_id = query.patient_id
        role = query.requester_role
        username = query.requester_username

        # Get records chain
        chain = self.record_service.get_chain(patient_id)
        final_data = self.record_service.get_final_data(patient_id)
        corrections = self.record_service.get_corrections_index(patient_id)
        records = []

        for block in chain:
            if block.index == 0:
                continue  # Skip Genesis block
            data = final_data.get(block.index)
            if data is None:
                continue

            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    pass

            if isinstance(data, dict) and data.get("type") == "audit":
                continue

            # A practitioner sees a record only with the client's consent for its
            # type (or for all records). Records without consent are left out of
            # the list entirely rather than shown as locked entries.
            if role == "practitioner":
                rec_type = data.get("record_type", "other") if isinstance(data, dict) else "other"
                if not self.consent_validator.has_consent(patient_id, username, rec_type):
                    continue

            # Client-only ("private") records are never shown to a practitioner.
            if role == "practitioner" and isinstance(data, dict) and data.get("access_level") == "private":
                continue

            entry = {
                "block_index":    block.index,
                "timestamp":      block.timestamp,
                "timestamp_iso":  datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat(),
                "is_protected":   block.is_protected,
                "is_correction":  isinstance(data, dict) and data.get("type") == "correction",
                "is_corrected":   block.index in corrections,
                "correction":     corrections.get(block.index),
                "hash_preview":   block.hash[:24] + "...",
                "prev_hash_preview": block.previous_hash[:24] + "..." if block.previous_hash else "N/A",
                "merkle_root_preview": block.merkle_root[:24] + "..." if block.merkle_root else "N/A",
                "signature_preview":   block.signature[:24] + "..." if block.signature else "N/A",
                "device_id":      block.device_id[:16] + "..." if block.device_id else None,
            }

            if block.is_protected:
                entry["title"]        = "ENCRYPTED RECORD"
                entry["record_type"]  = "protected"
                entry["data"]         = None
                entry["file_name"]    = None
                entry["file_type"]    = None
                entry["file_data"]    = None
            elif isinstance(data, dict):
                entry["title"]        = data.get("title", "Untitled")
                entry["record_type"]  = data.get("record_type", "other")
                entry["record_type_label"] = data.get("record_type_label", "")
                entry["access_level"] = data.get("access_level", "")
                entry["doctor_name"]  = data.get("doctor_name", "")
                entry["institution"]  = data.get("institution", "")
                entry["record_date"]  = data.get("record_date", "")
                entry["data"]         = data.get("data", {})
                entry["notes"]        = data.get("notes", "")
                entry["created_by"]   = data.get("created_by", "")
                entry["file_name"]    = data.get("file_name")
                entry["file_type"]    = data.get("file_type")
                entry["file_data"]    = data.get("file_data")
                entry["file_hash"]    = data.get("file_hash")  # For off-chain files

            records.append(entry)

        return records

    def handle_decrypt_record(self, query: DecryptRecordQuery) -> Any:
        is_practitioner = query.requester_role == "practitioner"
        if is_practitioner:
            chain = self.record_service.get_chain(query.patient_id)
            if not any(b.index == query.block_index for b in chain):
                return "Record not found"
            # An encrypted record's type is only known after decryption, so a
            # practitioner needs consent for all records before we even try.
            if not self.consent_validator.has_consent(query.patient_id, query.requester_username, "all"):
                return "SECURE — 'All Records' client consent is required to decrypt encrypted blocks."

        data = self.record_service.get_final_block_data(
            patient_id=query.patient_id,
            block_index=query.block_index,
            password=query.password,
            username=query.requester_username
        )
        # Same rule as the record list: a client-only record stays hidden from a
        # practitioner, even one holding its password.
        if is_practitioner and isinstance(data, dict) and data.get("access_level") == "private":
            return "SECURE — this record is visible to the client only."
        return data

    def handle_get_notifications(self, query: GetNotificationsQuery) -> List[dict]:
        return self.notif_repo.load_notifications_by_patient(query.patient_id)

    def handle_get_consents(self, query: GetConsentsQuery) -> List[dict]:
        project_name = self.record_service._get_project_name(query.patient_id)
        if not storage.project_exists(project_name):
            return []

        env = storage.open_db(project_name)
        consents = []
        with env.begin(write=False) as txn:
            cursor = txn.cursor()
            for key, value in cursor:
                if key.startswith(b"consent_"):
                    try:
                        data = json.loads(value.decode("utf-8"))
                        consents.append(data)
                    except Exception:
                        continue
        return consents
