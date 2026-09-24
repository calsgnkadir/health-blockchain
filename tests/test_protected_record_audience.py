"""
tests/test_protected_record_audience.py — who sees that a locked record exists
=============================================================================
A password-protected record's access level is inside its ciphertext. The list
used to show every such record to a practitioner holding consent for all
records, as an "ENCRYPTED RECORD" row — so the practitioner learned that the
client keeps a private journal, and when they wrote in it. The audience
(access level and author) is now stored outside the ciphertext, so a locked
client-only record is not listed for the practitioner at all, and a locked
practitioner-only note not for the client.
"""

import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from backend.schemas.requests import RECORD_TYPES
from database.sql_db import default_sql_db

CLIENT_ID = "CL-001"
PRACTITIONER = "psk.elif"
PASSWORD = "Locked@Record2026!"
SESSION_DATA = {"session_number": 5, "duration_min": 50, "session_format": "Online",
                "summary": "Locked note."}


class TestProtectedRecordAudience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default_sql_db.seed_default_users()
        cls.client = TestClient(app)
        cls.headers = {}
        for actor, (username, password) in {
            "client": ("client001", "Client@2026Secure!"),
            "practitioner": (PRACTITIONER, "Practitioner@2026!"),
        }.items():
            res = cls.client.post("/api/v1/auth/login", json={"username": username, "password": password})
            assert res.status_code == 200, res.text
            cls.headers[actor] = {"Authorization": f"Bearer {res.json()['access_token']}"}

    def setUp(self):
        os.environ["TESTING"] = "true"
        self._revoke_all()

    def tearDown(self):
        self._revoke_all()

    def _revoke_all(self):
        for record_type in ["all", *RECORD_TYPES]:
            self.client.delete(f"/api/v1/consent/{CLIENT_ID}/{PRACTITIONER}/{record_type}",
                               headers=self.headers["client"])

    def _grant(self, record_type):
        res = self.client.post("/api/v1/consent", headers=self.headers["client"], json={
            "patient_id": CLIENT_ID, "doctor_username": PRACTITIONER,
            "record_type": record_type, "duration_days": 1})
        self.assertEqual(res.status_code, 200, res.text)

    def _add_locked(self, actor, record_type, access_level, data):
        res = self.client.post("/api/v1/records", headers=self.headers[actor], json={
            "patient_id": CLIENT_ID, "record_type": record_type, "title": "Locked",
            "doctor_name": "", "institution": "", "record_date": "2026-09-01",
            "access_level": access_level, "is_confidential": True,
            "confidential_password": PASSWORD, "data": data, "notes": ""})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["block_index"]

    def _listed(self, actor):
        res = self.client.get(f"/api/v1/records/{CLIENT_ID}", headers=self.headers[actor])
        self.assertEqual(res.status_code, 200, res.text)
        return [r["block_index"] for r in res.json()["records"]]

    def _get(self, actor, path):
        return self.client.get(path, headers=self.headers[actor])

    def test_locked_client_journal_is_invisible_to_the_practitioner(self):
        idx = self._add_locked("client", "other", "private", {})
        self._grant("all")
        self.assertNotIn(idx, self._listed("practitioner"))
        self.assertEqual(self._get("practitioner", f"/api/v1/records/{CLIENT_ID}/{idx}").status_code, 404)
        self.assertEqual(self._get("practitioner", f"/api/v1/records/proof/{CLIENT_ID}/{idx}").status_code, 404)
        self.assertIn(idx, self._listed("client"))   # the client still sees their own

    def test_locked_process_note_is_invisible_to_the_client(self):
        self._grant("all")
        idx = self._add_locked("practitioner", "session_note", "practitioner_only", SESSION_DATA)
        self.assertIn(idx, self._listed("practitioner"))
        self.assertNotIn(idx, self._listed("client"))
        self.assertEqual(self._get("client", f"/api/v1/records/{CLIENT_ID}/{idx}").status_code, 404)
        self.assertEqual(self._get("client", f"/api/v1/records/proof/{CLIENT_ID}/{idx}").status_code, 404)

    def test_locked_shared_record_still_needs_consent_for_all(self):
        # Its type is still unknown until it is decrypted.
        idx = self._add_locked("client", "session_note", "doctor_shared", SESSION_DATA)
        self._grant("session_note")
        self.assertNotIn(idx, self._listed("practitioner"))
        self._grant("all")
        self.assertIn(idx, self._listed("practitioner"))


if __name__ == "__main__":
    unittest.main()
