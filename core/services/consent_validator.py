import json
import time
import database.storage as storage
from core.ports.repositories import IBlockRepository
from core.pseudonymization.service import project_name_for

class ConsentValidator:
    def __init__(self, block_repo: IBlockRepository):
        self.block_repo = block_repo

    def _get_project_name(self, patient_id: str) -> str:
        return project_name_for(patient_id)

    def has_consent(
        self,
        patient_id: str,
        doctor_username: str,
        record_type: str,
    ) -> bool:
        """
        Checks if the doctor has an active, non-expired consent rule for the given record type.
        Supports fallback to a global 'all' record type consent.
        """
        project_name = self._get_project_name(patient_id)
        if not storage.project_exists(project_name):
            return False

        expired_detected = False
        env = storage.open_db(project_name)
        with env.begin(write=False) as txn:
            # Check specific record type consent
            key_specific = f"consent_{doctor_username}_{record_type}".encode("utf-8")
            val_spec = txn.get(key_specific)
            if val_spec:
                try:
                    data = json.loads(val_spec.decode("utf-8"))
                    expiry = data.get("expiry_timestamp", 0)
                    if time.time() < expiry:
                        return True
                    else:
                        expired_detected = True
                except Exception:
                    pass

            # Check general 'all' consent
            key_all = f"consent_{doctor_username}_all".encode("utf-8")
            val_all = txn.get(key_all)
            if val_all:
                try:
                    data = json.loads(val_all.decode("utf-8"))
                    expiry = data.get("expiry_timestamp", 0)
                    if time.time() < expiry:
                        return True
                    else:
                        expired_detected = True
                except Exception:
                    pass

        if expired_detected:
            try:
                storage.append_access_log(
                    project_name=project_name,
                    username=doctor_username,
                    action="CONSENT_EXPIRED",
                    extra={"doctor": doctor_username, "record_type": record_type}
                )
            except Exception:
                pass

        return False

    def has_any_consent(self, patient_id: str, doctor_username: str) -> bool:
        """
        Does the practitioner hold ANY unexpired consent from this client? Without
        one, the client's file is treated as if it did not exist for them.

        Matches the stored `doctor_username` exactly rather than the key prefix,
        because "consent_psk.elif_" is also a prefix of "consent_psk.elif_x_all".
        Read-only: unlike has_consent(), it never writes CONSENT_EXPIRED entries.
        """
        project_name = self._get_project_name(patient_id)
        if not storage.project_exists(project_name):
            return False

        now = time.time()
        env = storage.open_db(project_name)
        with env.begin(write=False) as txn:
            cursor = txn.cursor()
            if not cursor.set_range(b"consent_"):
                return False
            for key, value in cursor:
                if not key.startswith(b"consent_"):
                    break
                try:
                    data = json.loads(value.decode("utf-8"))
                except Exception:
                    continue
                if data.get("doctor_username") == doctor_username and now < data.get("expiry_timestamp", 0):
                    return True
        return False
