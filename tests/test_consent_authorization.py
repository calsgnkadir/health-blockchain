"""
tests/test_consent_authorization.py — Consent is the patient's decision alone
=============================================================================
Guards the authorization boundary around /api/v1/consent:

* A practitioner must not be able to grant themselves access to a chart, nor
  revoke a permission the patient set — that would make the consent model
  decorative and let a doctor silently bypass Break-Glass auditing.
* An administrator must not be able to do it either, since that would route
  around the Dual-Control policy keeping admins out of raw records.
"""

import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from database.sql_db import default_sql_db

PATIENT_ID = "VIP-001"
DOCTOR = "dr.smith"

ACCOUNTS = {
    "patient": ("vip001", "VIPPatient@2026!"),
    "doctor": (DOCTOR, "Doctor@2026Secure!"),
    "admin": ("admin", "Admin@2026Secure!"),
}


class TestConsentAuthorization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The demo accounts are normally seeded by the app startup event, which the
        # bare TestClient does not run.
        default_sql_db.seed_default_users()

    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)

    def _headers(self, actor: str):
        username, password = ACCOUNTS[actor]
        res = self.client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        self.assertEqual(res.status_code, 200, res.text)
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    def _grant(self, actor: str, record_type: str = "all"):
        return self.client.post(
            "/api/v1/consent",
            headers=self._headers(actor),
            json={
                "patient_id": PATIENT_ID,
                "doctor_username": DOCTOR,
                "record_type": record_type,
                "duration_days": 30,
            },
        )

    def _revoke(self, actor: str, record_type: str = "all"):
        return self.client.delete(
            f"/api/v1/consent/{PATIENT_ID}/{DOCTOR}/{record_type}",
            headers=self._headers(actor),
        )

    def test_patient_can_grant_and_revoke_own_consent(self):
        self.assertEqual(self._grant("patient", "lab_result").status_code, 200)
        self.assertEqual(self._revoke("patient", "lab_result").status_code, 200)

    def test_doctor_cannot_grant_consent_to_themselves(self):
        res = self._grant("doctor")
        self.assertEqual(res.status_code, 403)
        self.assertIn("Consent Policy Violation", res.json()["detail"])

    def test_doctor_cannot_revoke_patient_consent(self):
        self.assertEqual(self._grant("patient", "imaging").status_code, 200)
        self.assertEqual(self._revoke("doctor", "imaging").status_code, 403)
        # The patient's decision must survive the attempt.
        consents = self.client.get(
            f"/api/v1/consent/{PATIENT_ID}", headers=self._headers("patient")
        ).json()["consents"]
        self.assertTrue(
            any(c["doctor_username"] == DOCTOR and c["record_type"] == "imaging" for c in consents)
        )
        self._revoke("patient", "imaging")

    def test_admin_cannot_grant_consent(self):
        self.assertEqual(self._grant("admin").status_code, 403)

    def test_admin_cannot_revoke_consent(self):
        self.assertEqual(self._revoke("admin").status_code, 403)

    def test_doctor_only_sees_permissions_granted_to_them(self):
        self.assertEqual(self._grant("patient", "diagnosis").status_code, 200)
        visible = self.client.get(
            f"/api/v1/consent/{PATIENT_ID}", headers=self._headers("doctor")
        ).json()["consents"]
        self.assertTrue(all(c["doctor_username"] == DOCTOR for c in visible))
        self._revoke("patient", "diagnosis")


if __name__ == "__main__":
    unittest.main()
