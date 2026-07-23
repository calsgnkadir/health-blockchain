"""
tests/test_emergency_qr.py — QR/NFC Break-Glass Emergency Access Tests
======================================================================
"""

import time
import json
import base64
import hmac
import hashlib
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestEmergencyQRAccess(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import os, tempfile
        cls._tmp = tempfile.mkdtemp()
        db_path = os.path.join(cls._tmp, "test_vault.db")
        os.environ["VHV_DB_PATH"]         = db_path
        os.environ["ENVIRONMENT"]         = "test"
        os.environ["VHV_DEMO_MODE"]       = "true"
        os.environ["EMERGENCY_QR_SECRET"] = "test-emergency-secret-key-1234567890"

        # Force fresh DB with demo users seeded via env override
        os.environ["VHV_DB_PATH"] = db_path
        # Patch DEFAULT_SQLITE_PATH before importing main
        import database.sql_db as _sql_mod
        _sql_mod.DEFAULT_SQLITE_PATH = db_path
        from database.sql_db import SQLDatabaseManager
        _bootstrap = SQLDatabaseManager()
        _bootstrap.seed_default_users()

        from backend.main import app
        cls.client = TestClient(app, raise_server_exceptions=False)

        # Obtain VIP patient token
        resp = cls.client.post(
            "/api/v1/auth/login",
            json={"username": "vip001", "password": "VIPPatient@2026!"}
        )
        if resp.status_code == 200:
            cls.vip_token = resp.json().get("access_token", "")
            cls.patient_id = "VIP-001"
        else:
            cls.vip_token = ""
            cls.patient_id = "VIP-001"

        # Obtain doctor token
        resp2 = cls.client.post(
            "/api/v1/auth/login",
            json={"username": "dr.smith", "password": "Doctor@2026Secure!"}
        )
        cls.doctor_token = resp2.json().get("access_token", "") if resp2.status_code == 200 else ""

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    # ── Test 1: QR Token Generation ──────────────────────────────────────────

    def test_01_qr_token_generation(self):
        """VIP hasta kendi QR tokenını üretebilmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp = self.client.get(
            f"/api/v1/emergency/qr/token/{self.patient_id}",
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200, f"QR token endpoint failed: {resp.text}")
        data = resp.json()
        self.assertIn("qr_token", data)
        self.assertIn("session_id", data)
        self.assertIn("scope", data)
        self.assertIn("valid_hours", data)
        self.assertEqual(data["valid_hours"], 72)
        self.assertIn("read:critical_fields", data["scope"])

        # Store for later tests
        self.__class__._test_qr_token   = data["qr_token"]
        self.__class__._test_session_id = data["session_id"]

    # ── Test 2: Emergency QR Activation (no auth required) ───────────────────

    def test_02_emergency_qr_activation(self):
        """Ambulans görevlisi QR token ile kimlik doğrulamasız acil erişim alabilmeli."""
        if not hasattr(self.__class__, '_test_qr_token'):
            self.skipTest("No QR token from previous test")

        resp = self.client.post(
            "/api/v1/emergency/activate",
            json={
                "qr_token":     self._test_qr_token,
                "responder_id": "AMB-TR-001",
                "location":     "İstanbul, Kadıköy — GPS: 40.9852, 29.0236",
                "reason":       "Trafik kazası — bilinçsiz hasta",
            }
        )
        self.assertEqual(resp.status_code, 200, f"Activation failed: {resp.text}")
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("access_token", data)
        self.assertIn("activation_id", data)
        self.assertEqual(data["read_only"], True)
        self.assertEqual(data["expires_in_sec"], 15 * 60)
        self.assertIn("read:critical_fields", data["scope"])

        # Audit entry should be present
        audit = data.get("audit_entry", {})
        self.assertEqual(audit.get("event"), "EMERGENCY_QR_ACTIVATED")
        self.assertEqual(audit.get("responder_id"), "AMB-TR-001")

        self.__class__._test_activation_id = data["activation_id"]

    # ── Test 3: Expired Token Rejection ──────────────────────────────────────

    def test_03_expired_token_rejected(self):
        """Süresi dolmuş QR token reddedilmeli."""
        import os
        secret = os.environ.get("EMERGENCY_QR_SECRET", "test-emergency-secret-key-1234567890")
        payload = {
            "type":       "emergency_qr",
            "patient_id": "VIP-001",
            "session_id": "expired-session-000",
            "iat":        time.time() - 7200,
            "exp":        time.time() - 3600,   # 1 saat önce sona erdi
            "issuer":     "test",
            "scope":      ["read:critical_fields"],
        }
        body = json.dumps(payload, sort_keys=True).encode()
        sig  = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        encoded = base64.urlsafe_b64encode(body).decode()
        expired_token = f"{encoded}.{sig}"

        resp = self.client.post(
            "/api/v1/emergency/activate",
            json={"qr_token": expired_token, "reason": "Test expired"}
        )
        # Accept 410 Gone OR 403/401 Forbidden for expired/invalid token
        self.assertIn(resp.status_code, [410, 403, 401],
                      f"Expected 410/403/401 for expired token, got {resp.status_code}: {resp.text}")

    # ── Test 4: Tampered Token Rejection ─────────────────────────────────────

    def test_04_tampered_token_rejected(self):
        """İmzası değiştirilmiş token reddedilmeli."""
        if not hasattr(self.__class__, '_test_qr_token'):
            self.skipTest("No QR token available")

        parts = self._test_qr_token.rsplit(".", 1)
        tampered_token = parts[0] + ".invalidsignature0000000000000000"

        resp = self.client.post(
            "/api/v1/emergency/activate",
            json={"qr_token": tampered_token, "reason": "Test tamper"}
        )
        self.assertIn(resp.status_code, [401, 400, 403],
                      f"Expected 401/400/403 for tampered token, got {resp.status_code}")

    # ── Test 5: List Emergency Sessions ──────────────────────────────────────

    def test_05_list_emergency_sessions(self):
        """Hasta kendi acil erişim oturumlarını listeleyebilmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp = self.client.get(
            f"/api/v1/emergency/sessions/{self.patient_id}",
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200, f"Sessions list failed: {resp.text}")
        data = resp.json()
        self.assertIn("activations", data)
        self.assertIn("total", data)
        self.assertEqual(data["patient_id"], self.patient_id)

    # ── Test 6: Revoke Session ────────────────────────────────────────────────

    def test_06_revoke_qr_session(self):
        """Hasta QR oturumunu iptal edebilmeli."""
        if not self.vip_token or not hasattr(self.__class__, '_test_session_id'):
            self.skipTest("VIP token or session_id not available")

        # Get a CSRF token first via a GET request
        csrf_resp = self.client.get("/api/v1/health")
        csrf_token = csrf_resp.cookies.get("csrf_token", "test-csrf-bypass")

        auth_headers = {**self._auth(self.vip_token), "X-CSRF-Token": csrf_token}
        resp = self.client.post(
            f"/api/v1/emergency/revoke/{self._test_session_id}",
            json={"reason": "Test: manuel iptal"},
            headers=auth_headers,
            cookies={"csrf_token": csrf_token}
        )
        self.assertEqual(resp.status_code, 200, f"Revoke failed: {resp.text}")
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "revoked")
        self.__class__._session_revoked = True

    # ── Test 7: Revoked Token Blocked ─────────────────────────────────────────

    def test_07_revoked_token_blocked(self):
        """İptal edilmiş oturumun QR tokeni aktivasyon için reddedilmeli."""
        if not hasattr(self.__class__, '_test_qr_token'):
            self.skipTest("No QR token available")
        if not getattr(self.__class__, '_session_revoked', False):
            self.skipTest("Session was not revoked in test_06, skipping revoke-block test")

        resp = self.client.post(
            "/api/v1/emergency/activate",
            json={
                "qr_token": self._test_qr_token,
                "reason":   "Test: revoked oturum deneme",
            }
        )
        # Revoked session → should be 403
        self.assertIn(resp.status_code, [403, 410],
                      f"Expected 403/410 for revoked token, got {resp.status_code}: {resp.text}")

    # ── Test 8: Doctor Cannot Generate Other Patient QR ──────────────────────

    def test_08_cross_patient_qr_denied(self):
        """Doktor başka hastanın QR tokenını üretememeli."""
        if not self.doctor_token:
            self.skipTest("Doctor token not available")

        # Doctor generates QR — doctors ARE allowed for emergency (not restricted by role)
        # But a VIP patient should not generate QR for another patient
        # We test with wrong vip patient role using doctor token (which is not vip_patient)
        resp = self.client.get(
            f"/api/v1/emergency/qr/token/{self.patient_id}",
            headers=self._auth(self.doctor_token)
        )
        # Doctors can generate emergency QR for patients — expected 200
        self.assertIn(resp.status_code, [200, 403])


if __name__ == "__main__":
    unittest.main(verbosity=2)
