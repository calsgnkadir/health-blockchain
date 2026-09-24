"""
tests/test_practitioner_clients.py — the practitioner's client list
===================================================================
GET /api/v1/practitioner/clients lists only the clients a practitioner may
work with: those who gave them consent, and those they invited. Nobody else.
"""

import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from backend.schemas.requests import RECORD_TYPES
from database.sql_db import default_sql_db
from tests.test_client_invitations import _delete_client

CLIENT_ID = "CL-001"
PRACTITIONER = "psk.elif"
NEW_CLIENT_PASSWORD = "NewClient@2026Secure!"


class TestPractitionerClients(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default_sql_db.seed_default_users()

    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)
        self.practitioner = self._token(PRACTITIONER, "Practitioner@2026!")
        self.client001 = self._token("client001", "Client@2026Secure!")
        self.created = []
        self._revoke_all(CLIENT_ID, self.client001)

    def tearDown(self):
        self._revoke_all(CLIENT_ID, self.client001)
        for username in self.created:
            _delete_client(username)

    def _token(self, username, password):
        res = self.client.post("/api/v1/auth/login", json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["access_token"]

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _revoke_all(self, patient_id, client_token):
        for record_type in ["all", *RECORD_TYPES]:
            self.client.delete(f"/api/v1/consent/{patient_id}/{PRACTITIONER}/{record_type}",
                               headers=self._auth(client_token))

    def _grant(self, patient_id, client_token, record_type):
        res = self.client.post("/api/v1/consent", headers=self._auth(client_token), json={
            "patient_id": patient_id, "doctor_username": PRACTITIONER,
            "record_type": record_type, "duration_days": 1})
        self.assertEqual(res.status_code, 200, res.text)

    def _clients(self):
        res = self.client.get("/api/v1/practitioner/clients", headers=self._auth(self.practitioner))
        self.assertEqual(res.status_code, 200, res.text)
        return {c["patient_id"]: c for c in res.json()["clients"]}

    def test_client_without_consent_is_not_listed(self):
        self.assertNotIn(CLIENT_ID, self._clients())

    def test_consenting_client_is_listed_with_the_consent(self):
        self._grant(CLIENT_ID, self.client001, "session_note")
        self._grant(CLIENT_ID, self.client001, "assessment")
        entry = self._clients()[CLIENT_ID]
        self.assertEqual(entry["status"], "consented")
        self.assertEqual(entry["full_name"], "Ahmet Karataş")
        self.assertEqual(entry["consent_types"], ["assessment", "session_note"])
        self.assertIsNotNone(entry["consent_expires_at"])

    def test_invited_client_moves_from_invited_to_consented(self):
        res = self.client.post("/api/v1/onboarding/invite-client", headers=self._auth(self.practitioner),
                               json={"full_name": "Deniz Aydın"})
        self.assertEqual(res.status_code, 200, res.text)
        invite = res.json()
        self.created.append(invite["username"])
        pid = invite["patient_id"]
        self.assertEqual(self._clients()[pid]["status"], "invited")

        self.client.post("/api/v1/onboarding/redeem", json={
            "enrollment_token": invite["invite_code"], "new_password": NEW_CLIENT_PASSWORD})
        self.assertEqual(self._clients()[pid]["status"], "waiting_for_consent")

        new_client = self._token(invite["username"], NEW_CLIENT_PASSWORD)
        self._grant(pid, new_client, "all")
        entry = self._clients()[pid]
        self.assertEqual(entry["status"], "consented")
        self.assertEqual(entry["consent_types"], ["all"])

    def test_only_practitioners(self):
        res = self.client.get("/api/v1/practitioner/clients", headers=self._auth(self.client001))
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
