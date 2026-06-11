import json
import time
from typing import Optional
import database.storage as storage
from core.ports.repositories import IBlockRepository

class ConsentValidator:
    def __init__(self, block_repo: IBlockRepository):
        self.block_repo = block_repo

    def _get_project_name(self, patient_id: str) -> str:
        return f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"

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

        env = storage.open_db(project_name)
        with env.begin(write=False) as txn:
            # Check specific record type consent
            key_specific = f"consent_{doctor_username}_{record_type}".encode("utf-8")
            val_spec = txn.get(key_specific)
            if val_spec:
                try:
                    data = json.loads(val_spec.decode("utf-8"))
                    if time.time() < data.get("expiry_timestamp", 0):
                        return True
                except Exception:
                    pass

            # Check general 'all' consent
            key_all = f"consent_{doctor_username}_all".encode("utf-8")
            val_all = txn.get(key_all)
            if val_all:
                try:
                    data = json.loads(val_all.decode("utf-8"))
                    if time.time() < data.get("expiry_timestamp", 0):
                        return True
                except Exception:
                    pass

        return False

    def break_glass_override(
        self,
        patient_id: str,
        doctor_username: str,
        reason: str,
        device_id: Optional[str] = None,
    ) -> None:
        """
        Overrides consent checks in an emergency situation.
        Creates an immutable audit and access entry logging the bypass event.
        """
        project_name = self._get_project_name(patient_id)
        
        # Log to LMDB Access Logs
        storage.append_access_log(
            project_name=project_name,
            username=doctor_username,
            action="BREAK_GLASS_ACCESS",
            device_id=device_id or "unknown",
            extra={"reason": reason, "severity": "CRITICAL"}
        )

        # Log to LMDB System Audit Log
        storage.append_audit_log(
            project_name=project_name,
            action="BREAK_GLASS_BYPASS",
            username=doctor_username,
            device_id=device_id or "unknown",
            extra={"reason": reason, "patient_id": patient_id}
        )

        # Create high-priority notification for the patient
        notif_id = f"notif_{time.time_ns()}"
        notif_data = {
            "id": notif_id,
            "patient_id": patient_id,
            "title": "ACİL DURUM ERİŞİMİ TETİKLENDİ (BREAK GLASS)",
            "message": f"Dr. {doctor_username} acil durum yetkisi kullanarak kayıtlarınıza erişti. Gerekçe: {reason}",
            "severity": "high",
            "timestamp": time.time(),
            "read": False
        }
        
        def txn_notif(txn):
            key = f"notif_{notif_id}".encode("utf-8")
            txn.put(key, json.dumps(notif_data).encode("utf-8"))

        storage.run_write_transaction(project_name, txn_notif)
