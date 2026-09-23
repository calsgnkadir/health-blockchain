"""
tests/test_client_invitations.py — a practitioner invites a new client
======================================================================
The practitioner gives a name; the system picks the next free client ID,
creates a pending client account and returns a single-use invitation code.
The client redeems the code to set a password. The invitation never gives the
practitioner access: the client's file stays closed until the client consents.
"""

import os
import re
import sys
import unittest
from unittest import mock

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from backend.routers import onboarding
from database.sql_db import default_sql_db

PRACTITIONER = ("psk.elif", "Practitioner@2026!")
CLIENT_PASSWORD = "NewClient@2026Secure!"


def _delete_client(username):
    conn = default_sql_db.get_connection()
    cur = conn.cursor()
    ph = "%s" if default_sql_db.is_postgres else "?"
    try:
        cur.execute(f"DELETE FROM users WHERE username = {ph}", (username,))
        cur.execute(f"DELETE FROM enrollment_tokens WHERE username = {ph}", (username,))
        conn.commit()
    finally:
        cur.close()
        conn.close()


class TestClientInvitations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default_sql_db.seed_default_users()

    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)
        self.practitioner = self._login(*PRACTITIONER).json()["access_token"]
        self.created = []

    def tearDown(self):
        # Keep the shared dev DB clean: remove every client this test invited.
        for username in self.created:
            _delete_client(username)

    def _login(self, username, password):
        return self.client.post("/api/v1/auth/login",
                                json={"username": username, "password": password})

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def _invite(self, name="Deniz Aydın", token=None):
        res = self.client.post("/api/v1/onboarding/invite-client",
                               headers=self._auth(token or self.practitioner),
                               json={"full_name": name})
        if res.status_code == 200:
            self.created.append(res.json()["username"])
        return res

    def _redeem(self, code, password=CLIENT_PASSWORD):
        return self.client.post("/api/v1/onboarding/redeem",
                                json={"enrollment_token": code, "new_password": password})

    def _invitations(self):
        res = self.client.get("/api/v1/onboarding/invitations", headers=self._auth(self.practitioner))
        self.assertEqual(res.status_code, 200, res.text)
        return {i["patient_id"]: i for i in res.json()["invitations"]}

    def test_invite_creates_a_pending_client_with_a_new_id(self):
        res = self._invite()
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertRegex(body["patient_id"], r"^CL-[0-9]{3,}$")
        self.assertEqual(body["username"], body["patient_id"].lower())
        # Pending: the account cannot sign in before the code is used (its
        # password is random, so any guess is simply wrong).
        self.assertEqual(self._login(body["username"], CLIENT_PASSWORD).status_code, 401)

    def test_each_invitation_gets_its_own_id(self):
        first = self._invite("Client One").json()["patient_id"]
        second = self._invite("Client Two").json()["patient_id"]
        self.assertNotEqual(first, second)

    def test_an_id_with_a_leftover_chain_is_never_reused(self):
        # No account holds CL-001, but a chain for it still exists (say, a
        # deleted account). Handing out CL-001 would give the new client the
        # old client's records.
        leftover = onboarding.project_name_for("CL-001")
        repo = onboarding.SQLUserRepository()
        with mock.patch.object(repo, "load_all_users", return_value=[]), \
             mock.patch.object(repo, "user_exists", return_value=False), \
             mock.patch.object(onboarding.storage, "project_exists",
                               side_effect=lambda name: name == leftover):
            self.assertEqual(onboarding._next_client_id(repo), "CL-002")

    def test_client_redeems_the_code_and_signs_in(self):
        body = self._invite().json()
        res = self._redeem(body["invite_code"])
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["username"], body["username"])
        self.assertEqual(res.json()["invited_by"], PRACTITIONER[0])

        login = self._login(body["username"], CLIENT_PASSWORD)
        self.assertEqual(login.status_code, 200, login.text)
        me = self.client.get("/api/v1/auth/me", headers=self._auth(login.json()["access_token"])).json()
        self.assertEqual(me["role"], "client")
        self.assertEqual(me["patient_id"], body["patient_id"])

        # Single use.
        self.assertEqual(self._redeem(body["invite_code"]).status_code, 400)

    def test_invitation_gives_the_practitioner_no_access(self):
        body = self._invite().json()
        self._redeem(body["invite_code"])
        res = self.client.get(f"/api/v1/records/{body['patient_id']}", headers=self._auth(self.practitioner))
        self.assertEqual(res.status_code, 403)

    def test_invitation_list_shows_status(self):
        body = self._invite().json()
        self.assertEqual(self._invitations()[body["patient_id"]]["status"], "pending")
        self._redeem(body["invite_code"])
        self.assertEqual(self._invitations()[body["patient_id"]]["status"], "active")

    def test_renewing_replaces_the_old_code(self):
        body = self._invite().json()
        res = self.client.post(f"/api/v1/onboarding/invitations/{body['patient_id']}/renew",
                               headers=self._auth(self.practitioner))
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self._redeem(body["invite_code"]).status_code, 400)   # old code is dead
        self.assertEqual(self._redeem(res.json()["invite_code"]).status_code, 200)

    def test_cannot_renew_someone_elses_or_an_active_client(self):
        # client001 was not invited by this practitioner (and is active).
        res = self.client.post("/api/v1/onboarding/invitations/CL-001/renew",
                               headers=self._auth(self.practitioner))
        self.assertEqual(res.status_code, 404)

    def test_only_practitioners_invite(self):
        client_token = self._login("client001", "Client@2026Secure!").json()["access_token"]
        admin_token = self._login("admin", "Admin@2026Secure!").json()["access_token"]
        self.assertEqual(self._invite(token=client_token).status_code, 403)
        self.assertEqual(self._invite(token=admin_token).status_code, 403)

    def test_name_is_required(self):
        self.assertEqual(self._invite(name=" ").status_code, 422)

    def test_open_invitations_are_capped(self):
        with mock.patch.object(onboarding, "MAX_OPEN_INVITATIONS", 0):
            self.assertEqual(self._invite().status_code, 429)


if __name__ == "__main__":
    unittest.main()
