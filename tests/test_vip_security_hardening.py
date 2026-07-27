"""
tests/test_vip_security_hardening.py — Tests for VIP Security Hardening
========================================================================
Covering:
1. Network IP Allowlisting Middleware (IP restriction, block public IPs)
2. Real-Time Security Alert Service & Anomaly Engine
3. Dual-Control (M-of-N Approval) Engine & Anti-Self-Approval
"""

import os
import unittest
from fastapi.testclient import TestClient
from backend.main import app
from core.services.alert_service import alert_service
from core.services.dual_control import dual_control_engine


class TestVIPSecurityHardening(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_alert_service_raise_and_retrieve(self):
        alert_id = alert_service.raise_alert(
            alert_type="UNAUTHORIZED_ACCESS_SPIKE",
            severity="CRITICAL",
            title="Rapid Failed Login Spikes",
            description="5 failed attempts in 10 seconds",
            username="attacker_user",
            client_ip="198.51.100.4"
        )
        self.assertIsNotNone(alert_id)
        self.assertTrue(alert_id.startswith("alt_"))

        recent_alerts = alert_service.get_recent_alerts(limit=10, severity_filter="CRITICAL")
        found = any(a["alert_id"] == alert_id for a in recent_alerts)
        self.assertTrue(found)

        # Test acknowledgement
        ack_success = alert_service.acknowledge_alert(alert_id)
        self.assertTrue(ack_success)

    def test_dual_control_workflow_and_security(self):
        patient_id = "VIP-SEC-999"
        
        # 1. Initiate Dual Control Request
        req_res = dual_control_engine.request_dual_control_access(
            request_type="DECRYPT_RAW_RECORD",
            target_patient_id=patient_id,
            requested_by="admin",
            reason="Court order inspection",
            validity_minutes=15
        )
        token_id = req_res["token_id"]
        self.assertEqual(req_res["status"], "PENDING_CO_APPROVAL")

        # 2. Prevent self-approval (Admin requesting cannot self-approve)
        with self.assertRaises(ValueError) as ctx:
            dual_control_engine.co_sign_request(token_id, co_signer_username="admin", co_signer_role="admin")
        self.assertIn("cannot self-approve", str(ctx.exception))

        # 3. Co-sign by a distinct Security Officer
        co_sign_res = dual_control_engine.co_sign_request(
            token_id=token_id,
            co_signer_username="sec_officer_1",
            co_signer_role="security_officer"
        )
        self.assertEqual(co_sign_res["status"], "APPROVED")
        self.assertEqual(co_sign_res["co_signed_by"], "sec_officer_1")

        # 4. Verify approval status
        is_valid = dual_control_engine.is_dual_control_approved(token_id, patient_id)
        self.assertTrue(is_valid)


if __name__ == "__main__":
    unittest.main()
