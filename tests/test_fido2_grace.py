"""
tests/test_fido2_grace.py — MANDATORY_FIDO2 must not deadlock a fresh account
=============================================================================
Enforcing "must have a passkey" by refusing every password login would lock out a
fresh account: a passkey can only be enrolled after logging in. So an account with
no passkey gets a one-time enrolment grace — it logs in and the response flags that
a passkey must be enrolled now, instead of a 403 that can never be cleared.
"""

import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from database.sql_db import default_sql_db


class TestFido2EnrollmentGrace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default_sql_db.seed_default_users()

    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)
        self._saved = os.environ.get("MANDATORY_FIDO2")
        # Ensure the account has no passkey so the grace path is exercised.
        conn = default_sql_db.get_connection()
        cur = conn.cursor()
        ph = "%s" if default_sql_db.is_postgres else "?"
        try:
            cur.execute(f"DELETE FROM webauthn_credentials WHERE username = {ph}", ("client001",))
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("MANDATORY_FIDO2", None)
        else:
            os.environ["MANDATORY_FIDO2"] = self._saved

    def _login(self):
        return self.client.post("/api/v1/auth/login",
                                json={"username": "client001", "password": "Client@2026Secure!"})

    def test_fresh_account_can_log_in_and_is_told_to_enrol(self):
        os.environ["MANDATORY_FIDO2"] = "true"
        res = self._login()
        self.assertEqual(res.status_code, 200, res.text)   # not a 403 deadlock
        body = res.json()
        self.assertIn("access_token", body)
        self.assertTrue(body.get("passkey_enrollment_required"))

    def test_flag_is_false_when_policy_is_off(self):
        os.environ["MANDATORY_FIDO2"] = "false"
        res = self._login()
        self.assertEqual(res.status_code, 200, res.text)
        self.assertFalse(res.json().get("passkey_enrollment_required"))


if __name__ == "__main__":
    unittest.main()
