"""
tests/test_record_access_rules.py — one access rule for every record endpoint
=============================================================================
The record list (core/cqrs/queries.py) has always applied this rule to a
practitioner: never a client-only ("private") record, and otherwise only with
the client's consent for that record's type (or for all records). The
endpoints that touch a single record did not all apply it:

  * downloading an attachment accepted consent for *any* type, so consent for
    one kind of record opened the attachments of every other kind;
  * a practitioner could correct a client-only record;
  * a correction could change a record's access level, i.e. who may see it;
  * a practitioner holding the password could decrypt a client-only record.

Each test below pins one of those.
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
ACCOUNTS = {
    "client": ("client001", "Client@2026Secure!"),
    "practitioner": (PRACTITIONER, "Practitioner@2026!"),
}
ASSESSMENT_DATA = {"instrument": "GAD-7", "score": 7, "max_score": 21,
                   "interpretation": "Mild anxiety"}


class TestRecordAccessRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default_sql_db.seed_default_users()

    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)
        # Start every test with no consent for the practitioner at all.
        for record_type in ["all", *RECORD_TYPES]:
            self.client.delete(f"/api/v1/consent/{CLIENT_ID}/{PRACTITIONER}/{record_type}",
                               headers=self._headers("client"))

    def _headers(self, actor):
        username, password = ACCOUNTS[actor]
        res = self.client.post("/api/v1/auth/login",
                               json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200, res.text)
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    def _grant(self, record_type):
        res = self.client.post("/api/v1/consent", headers=self._headers("client"), json={
            "patient_id": CLIENT_ID, "doctor_username": PRACTITIONER,
            "record_type": record_type, "duration_days": 1})
        self.assertEqual(res.status_code, 200, res.text)

    def _add(self, record_type="assessment", access_level="doctor_shared",
             data=ASSESSMENT_DATA, with_file=False, password=None):
        body = {
            "patient_id": CLIENT_ID, "record_type": record_type, "title": "Access rule test",
            "doctor_name": "Uzm. Psk. Elif Yilmaz", "institution": "Mahrem",
            "record_date": "2026-09-01", "access_level": access_level,
            "is_confidential": bool(password), "confidential_password": password,
            "data": data, "notes": "",
        }
        if with_file:
            body.update(file_name="note.txt", file_type="text/plain", file_data="aGVsbG8=")
        res = self.client.post("/api/v1/records", headers=self._headers("client"), json=body)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["block_index"]

    def _download(self, idx, actor="practitioner"):
        return self.client.get(f"/api/v1/records/offchain/download/{CLIENT_ID}/{idx}",
                               headers=self._headers(actor))

    def test_attachment_needs_consent_for_its_own_record_type(self):
        idx = self._add("assessment", with_file=True)
        self._grant("document")          # consent for a different type
        self.assertEqual(self._download(idx).status_code, 403)
        self._grant("assessment")        # consent for this record's type
        self.assertEqual(self._download(idx).status_code, 200)

    def test_client_only_attachment_is_never_given_to_a_practitioner(self):
        idx = self._add("document", access_level="private", data={}, with_file=True)
        self._grant("all")
        self.assertEqual(self._download(idx).status_code, 403)
        self.assertEqual(self._download(idx, actor="client").status_code, 200)

    def test_practitioner_cannot_correct_a_client_only_record(self):
        idx = self._add("document", access_level="private", data={})
        self._grant("all")
        res = self.client.post(
            f"/api/v1/records/{CLIENT_ID}/{idx}/correct", headers=self._headers("practitioner"),
            json={"reason": "Tidy up", "corrected_data": {"title": "Overwritten"}})
        self.assertEqual(res.status_code, 403, res.text)

    def test_a_correction_cannot_change_who_sees_the_record(self):
        idx = self._add("document", access_level="private", data={})
        res = self.client.post(
            f"/api/v1/records/{CLIENT_ID}/{idx}/correct", headers=self._headers("client"),
            json={"reason": "Typo", "corrected_data": {
                "title": "Fixed title", "access_level": "doctor_shared"}})
        self.assertEqual(res.status_code, 200, res.text)
        current = self.client.get(f"/api/v1/records/{CLIENT_ID}/{idx}?version=current",
                                  headers=self._headers("client")).json()["data"]
        self.assertEqual(current["title"], "Fixed title")
        self.assertEqual(current["access_level"], "private")

    def test_password_does_not_open_a_client_only_record_for_a_practitioner(self):
        idx = self._add("document", access_level="private", data={},
                        password="ClientOnly@2026!")
        self._grant("all")
        res = self.client.post(f"/api/v1/records/{CLIENT_ID}/{idx}/decrypt",
                               headers=self._headers("practitioner"),
                               json={"password": "ClientOnly@2026!"})
        self.assertEqual(res.status_code, 403, res.text)


if __name__ == "__main__":
    unittest.main()
