"""
tests/test_timebound_consent.py — Time-Bound Consent & RBAC Unit Tests
========================================================================
Tests for Granular Time-Bound RBAC & Audit Enforcement (Phase 4 of VIP Vault hardening).
"""

import os
import sys
import unittest
import tempfile

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.consent_validator import ConsentValidator
from core.cqrs.commands import GrantConsentCommand, RevokeConsentCommand, CommandHandler
from core.cqrs.queries import GetPatientRecordsQuery, QueryHandler
from core.services.record_service import RecordService
from core.services.auth_service import AuthService
from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository, LMDBUserRepository
from infrastructure.repositories.sql_repositories import SQLNotificationRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
import database.storage as storage


class TestTimeBoundConsent(unittest.TestCase):
    """Test time-bound consent rules, auto-expiration, and audit logging."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["TESTING"] = "true"

        # Mock DB paths
        self.block_repo = LMDBBlockRepository()
        self.user_repo = LMDBUserRepository()
        self.notif_repo = SQLNotificationRepository()
        self.crypto_strategy = AESGCMStrategy()

        self.record_service = RecordService(self.block_repo, self.crypto_strategy)
        self.auth_service = AuthService(self.user_repo)
        self.consent_validator = ConsentValidator(self.block_repo)

        self.command_handler = CommandHandler(self.record_service, self.auth_service, self.block_repo)
        self.query_handler = QueryHandler(self.record_service, self.block_repo, self.consent_validator, self.notif_repo)

        self.patient_id = f"VIP-TEST-{self._testMethodName.upper()}"
        self.doctor = "dr.smith"
        proj_name = self.record_service._get_project_name(self.patient_id)
        try:
            self.block_repo.reset_db(proj_name)
        except Exception:
            pass

    def test_grant_consent_days_active(self):
        """Consent granted for 1 day should be active immediately."""
        cmd = GrantConsentCommand(
            patient_id=self.patient_id,
            doctor_username=self.doctor,
            record_type="vital_signs",
            duration_days=1.0,
            username="vip_owner"
        )
        self.command_handler.handle_grant_consent(cmd)

        has_access = self.consent_validator.has_consent(self.patient_id, self.doctor, "vital_signs")
        self.assertTrue(has_access, "Consent granted for 1 day should be active")

    def test_grant_consent_hours_active(self):
        """Consent granted for 2 hours should be active immediately."""
        cmd = GrantConsentCommand(
            patient_id=self.patient_id,
            doctor_username=self.doctor,
            record_type="vital_signs",
            duration_days=1.0,
            duration_hours=2.0,
            username="vip_owner"
        )
        self.command_handler.handle_grant_consent(cmd)

        has_access = self.consent_validator.has_consent(self.patient_id, self.doctor, "vital_signs")
        self.assertTrue(has_access, "Consent granted for 2 hours should be active")

    def test_grant_consent_expired_denies_access(self):
        """Expired consent should deny access."""
        # Grant consent with negative hours (already expired in the past)
        cmd = GrantConsentCommand(
            patient_id=self.patient_id,
            doctor_username=self.doctor,
            record_type="lab_result",
            duration_days=1.0,
            duration_hours=-1.0,  # Expired 1 hour ago
            username="vip_owner"
        )
        self.command_handler.handle_grant_consent(cmd)

        has_access = self.consent_validator.has_consent(self.patient_id, self.doctor, "lab_result")
        self.assertFalse(has_access, "Expired consent should deny access")

    def test_revoke_consent_immediately_revokes(self):
        """Revoking consent should immediately remove access."""
        cmd_grant = GrantConsentCommand(
            patient_id=self.patient_id,
            doctor_username=self.doctor,
            record_type="prescription",
            duration_days=7.0,
            username="vip_owner"
        )
        self.command_handler.handle_grant_consent(cmd_grant)
        self.assertTrue(self.consent_validator.has_consent(self.patient_id, self.doctor, "prescription"))

        cmd_revoke = RevokeConsentCommand(
            patient_id=self.patient_id,
            doctor_username=self.doctor,
            record_type="prescription",
            username="vip_owner"
        )
        self.command_handler.handle_revoke_consent(cmd_revoke)
        self.assertFalse(self.consent_validator.has_consent(self.patient_id, self.doctor, "prescription"))

    def test_doctor_record_filtering_by_consent(self):
        """Doctor should only see records for which active consent is granted."""
        proj_name = self.record_service._get_project_name(self.patient_id)
        self.block_repo.reset_db(proj_name)

        # Add two records: one vital_signs, one lab_result
        self.record_service.add_record(
            patient_id=self.patient_id,
            data={"record_type": "vital_signs", "title": "BP Reading"},
            username="system"
        )
        self.record_service.add_record(
            patient_id=self.patient_id,
            data={"record_type": "lab_result", "title": "Blood Test"},
            username="system"
        )

        # Grant consent ONLY for vital_signs
        self.command_handler.handle_grant_consent(GrantConsentCommand(
            patient_id=self.patient_id,
            doctor_username=self.doctor,
            record_type="vital_signs",
            duration_days=1.0,
            username="vip_owner"
        ))

        query = GetPatientRecordsQuery(
            patient_id=self.patient_id,
            requester_username=self.doctor,
            requester_role="doctor",
            ignore_consent=False
        )
        records = self.query_handler.handle_get_patient_records(query)
        self.assertEqual(len(records), 1, f"Expected 1 record, got {len(records)}: {[r.get('title') for r in records]}")
        self.assertEqual(records[0]["title"], "BP Reading")

    def test_break_glass_emergency_override_logs_audit(self):
        """Break-glass emergency override logs critical audit events and notifies patient."""
        self.consent_validator.break_glass_override(
            patient_id=self.patient_id,
            doctor_username=self.doctor,
            reason="Patient in ER with acute chest pain",
            device_id="emergency-device-01"
        )

        proj_name = self.record_service._get_project_name(self.patient_id)
        access_logs = storage.load_access_logs(proj_name)
        self.assertTrue(any(entry.get("action") == "BREAK_GLASS_ACCESS" for entry in access_logs))

        audit_logs = storage.load_audit_logs(proj_name)
        self.assertTrue(any(entry.get("action") == "BREAK_GLASS_BYPASS" for entry in audit_logs))

    def test_repeated_break_glass_triggers_critical_alert(self):
        """Repeated break-glass overrides within 15 mins trigger REPEATED_BREAK_GLASS_ABUSE alert."""
        from core.services.alert_service import alert_service
        doc_user = "dr.repeated_test"

        for i in range(3):
            self.consent_validator.break_glass_override(
                patient_id=self.patient_id,
                doctor_username=doc_user,
                reason=f"Emergency override #{i+1}",
                device_id="er-terminal-01"
            )

        alerts = alert_service.get_recent_alerts(limit=10)
        repeated_alerts = [a for a in alerts if a.get("alert_type") == "REPEATED_BREAK_GLASS_ABUSE"]
        self.assertTrue(len(repeated_alerts) >= 1)
        self.assertEqual(repeated_alerts[0]["severity"], "CRITICAL")


if __name__ == "__main__":
    unittest.main()
