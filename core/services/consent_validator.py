import json
import time
from typing import Optional
from collections import defaultdict
import database.storage as storage
from core.ports.repositories import IBlockRepository
from core.pseudonymization.service import project_name_for

class ConsentValidator:
    def __init__(self, block_repo: IBlockRepository):
        self.block_repo = block_repo
        self._break_glass_history = defaultdict(list)

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

        # Raise Critical Security Alert
        try:
            from core.services.alert_service import alert_service
            alert_service.raise_alert(
                alert_type="BREAK_GLASS_BYPASS",
                severity="CRITICAL",
                title=f"Emergency Break-Glass Access Invoked by {doctor_username}",
                description=f"Doctor {doctor_username} triggered emergency break-glass override for patient {patient_id}. Reason: {reason}",
                client_ip="internal"
            )

            # Check for Repeated Break-Glass Anomaly Pattern (3+ overrides in 15 minutes)
            now = time.time()
            window = 900  # 15 minutes
            recent_invocations = [t for t in self._break_glass_history[doctor_username] if now - t <= window]
            recent_invocations.append(now)
            self._break_glass_history[doctor_username] = recent_invocations

            if len(recent_invocations) >= 3:
                alert_service.raise_alert(
                    alert_type="REPEATED_BREAK_GLASS_ABUSE",
                    severity="CRITICAL",
                    title=f"CRITICAL ANOMALY: Repeated Break-Glass Overrides by Dr. {doctor_username}",
                    description=f"Doctor {doctor_username} triggered {len(recent_invocations)} emergency break-glass overrides within 15 minutes. Potential insider policy abuse or coercion.",
                    client_ip="internal"
                )
        except Exception:
            pass

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
