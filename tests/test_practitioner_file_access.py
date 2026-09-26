"""
tests/test_practitioner_file_access.py — file-level and record-level access
===========================================================================
The API side of core/services/access_policy.py (ADR-0003):

  * GET /records/{client}/{block} used to check nothing for a practitioner, so
    any practitioner could read any client's unprotected records by walking
    block numbers, with no consent at all (an IDOR);
  * a practitioner could add records to any client's file without consent;
  * chain status and notifications were open to any practitioner;
  * a new level, "practitioner_only", is for the practitioner's own process
    notes: the author sees it, the client does not.
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
UNKNOWN_CLIENT_ID = "CL-9999"
PRACTITIONER = "psk.elif"
ACCOUNTS = {
    "client": ("client001", "Client@2026Secure!"),
    "practitioner": (PRACTITIONER, "Practitioner@2026!"),
}
PROFILE_DATA = {"presenting_problem": "Panic on the commute"}
SESSION_DATA = {"session_number": 4, "duration_min": 50, "session_format": "Online",
                "summary": "Reviewed the exposure ladder."}


class TestPractitionerFileAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default_sql_db.seed_default_users()
        cls.client = TestClient(app)
        cls.headers = {}
        for actor, (username, password) in ACCOUNTS.items():
            res = cls.client.post("/api/v1/auth/login",
                                  json={"username": username, "password": password})
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

    def _add(self, actor="client", record_type="client_profile", access_level="doctor_shared",
             data=PROFILE_DATA):
        return self.client.post("/api/v1/records", headers=self.headers[actor], json={
            "patient_id": CLIENT_ID, "record_type": record_type, "title": "File access test",
            "doctor_name": "Uzm. Psk. Elif Yilmaz", "institution": "Mahrem",
            "record_date": "2026-09-01", "access_level": access_level,
            "data": data, "notes": "",
        })

    def _added(self, *args, **kwargs):
        res = self._add(*args, **kwargs)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["block_index"]

    def _get(self, path, actor="practitioner"):
        return self.client.get(path, headers=self.headers[actor])

    # ── the IDOR ───────────────────────────────────────────────
    def test_single_record_needs_consent(self):
        idx = self._added(record_type="client_profile")
        path = f"/api/v1/records/{CLIENT_ID}/{idx}"
        self.assertEqual(self._get(path).status_code, 403)
        self.assertEqual(self._get(path + "?version=original").status_code, 403)

    def test_single_record_needs_consent_for_its_own_type(self):
        idx = self._added(record_type="client_profile")
        self._grant("homework")
        path = f"/api/v1/records/{CLIENT_ID}/{idx}"
        self.assertEqual(self._get(path).status_code, 404)
        self.assertEqual(self._get(path + "?version=original").status_code, 404)
        self._grant("client_profile")
        res = self._get(path)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["data"]["record_type"], "client_profile")

    def test_client_only_record_is_hidden_from_single_record_endpoint(self):
        idx = self._added(record_type="other", access_level="private", data={})
        self._grant("all")
        self.assertEqual(self._get(f"/api/v1/records/{CLIENT_ID}/{idx}").status_code, 404)

    def test_bookkeeping_blocks_are_hidden_from_practitioner(self):
        self._grant("all")
        self.assertEqual(self._get(f"/api/v1/records/{CLIENT_ID}/0").status_code, 404)

    # ── file level ─────────────────────────────────────────────
    def test_file_is_closed_without_any_consent(self):
        idx = self._added()
        for path in (f"/api/v1/records/{CLIENT_ID}",
                     f"/api/v1/blockchain/{CLIENT_ID}/status",
                     f"/api/v1/records/proof/{CLIENT_ID}/{idx}"):
            with self.subTest(path=path):
                self.assertEqual(self._get(path).status_code, 403)
        self._grant("client_profile")
        for path in (f"/api/v1/records/{CLIENT_ID}",
                     f"/api/v1/blockchain/{CLIENT_ID}/status",
                     f"/api/v1/records/proof/{CLIENT_ID}/{idx}"):
            with self.subTest(path=path):
                self.assertEqual(self._get(path).status_code, 200)

    def test_unknown_client_looks_the_same_as_a_client_without_consent(self):
        known = self._get(f"/api/v1/records/{CLIENT_ID}")
        unknown = self._get(f"/api/v1/records/{UNKNOWN_CLIENT_ID}")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json(), unknown.json())

    def test_notifications_are_for_the_client_only(self):
        self._grant("all")
        self.assertEqual(self._get(f"/api/v1/notifications/{CLIENT_ID}").status_code, 403)
        self.assertEqual(self._get(f"/api/v1/notifications/{CLIENT_ID}", actor="client").status_code, 200)

    # ── writing ────────────────────────────────────────────────
    def test_practitioner_needs_consent_to_add_a_record(self):
        res = self._add("practitioner", "session_note", data=SESSION_DATA)
        self.assertEqual(res.status_code, 403, res.text)
        self._grant("client_profile")            # consent for another type is not enough
        res = self._add("practitioner", "session_note", data=SESSION_DATA)
        self.assertEqual(res.status_code, 403, res.text)
        self._grant("session_note")
        res = self._add("practitioner", "session_note", data=SESSION_DATA)
        self.assertEqual(res.status_code, 200, res.text)

    def test_roles_may_only_use_their_own_access_levels(self):
        self._grant("all")
        self.assertEqual(self._add("client", access_level="practitioner_only").status_code, 403)
        self.assertEqual(self._add("practitioner", access_level="private").status_code, 403)

    def test_correction_cannot_move_a_record_to_a_type_without_consent(self):
        idx = self._added(record_type="client_profile")
        self._grant("client_profile")
        res = self.client.post(
            f"/api/v1/records/{CLIENT_ID}/{idx}/correct", headers=self.headers["practitioner"],
            json={"reason": "Wrong type", "corrected_data": {
                "record_type": "session_note", "data": SESSION_DATA}})
        self.assertEqual(res.status_code, 403, res.text)

    # ── practitioner-only notes ────────────────────────────────
    def test_practitioner_only_note_is_seen_by_its_author_not_the_client(self):
        self._grant("all")
        idx = self._added("practitioner", "session_note", "practitioner_only", SESSION_DATA)

        listed = [r["block_index"] for r in self._get(f"/api/v1/records/{CLIENT_ID}").json()["records"]]
        self.assertIn(idx, listed)
        self.assertEqual(self._get(f"/api/v1/records/{CLIENT_ID}/{idx}").status_code, 200)

        listed = [r["block_index"] for r in
                  self._get(f"/api/v1/records/{CLIENT_ID}", actor="client").json()["records"]]
        self.assertNotIn(idx, listed)
        self.assertEqual(self._get(f"/api/v1/records/{CLIENT_ID}/{idx}", actor="client").status_code, 404)

    def test_client_cannot_correct_a_practitioner_only_note(self):
        self._grant("all")
        idx = self._added("practitioner", "session_note", "practitioner_only", SESSION_DATA)
        res = self.client.post(
            f"/api/v1/records/{CLIENT_ID}/{idx}/correct", headers=self.headers["client"],
            json={"reason": "Curious", "corrected_data": {"title": "Overwritten"}})
        self.assertEqual(res.status_code, 403, res.text)

    def test_revoking_consent_closes_the_practitioners_own_notes_too(self):
        self._grant("all")
        idx = self._added("practitioner", "session_note", "practitioner_only", SESSION_DATA)
        self._revoke_all()
        self.assertEqual(self._get(f"/api/v1/records/{CLIENT_ID}/{idx}").status_code, 403)


    # ── session transcripts ────────────────────────────────────
    def test_a_transcript_is_always_practitioner_only(self):
        self._grant("all")
        transcript = {"session_number": 3, "transcript": "T: ...\nC: ..."}
        shared = self._add("practitioner", "session_transcript", "doctor_shared", transcript)
        self.assertEqual(shared.status_code, 422, shared.text)
        idx = self._added("practitioner", "session_transcript", "practitioner_only", transcript)
        listed = [r["block_index"] for r in
                  self._get(f"/api/v1/records/{CLIENT_ID}", actor="client").json()["records"]]
        self.assertNotIn(idx, listed)

    def test_a_client_cannot_write_a_transcript(self):
        transcript = {"session_number": 3, "transcript": "My own version"}
        for level in ("doctor_shared", "private", "practitioner_only"):
            with self.subTest(level=level):
                self.assertIn(self._add("client", "session_transcript", level, transcript).status_code,
                              (403, 422))


if __name__ == "__main__":
    unittest.main()
