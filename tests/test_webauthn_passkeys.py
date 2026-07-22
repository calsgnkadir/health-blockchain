import os
import sys
import unittest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app

class TestWebAuthnPasskeys(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)

    def test_webauthn_challenge_generation(self):
        res = self.client.get("/api/v1/auth/webauthn/challenge")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("challenge", data)
        self.assertTrue(len(data["challenge"]) > 20)

    def test_webauthn_login_flow(self):
        # 1. Login with demo passkey credential
        login_res = self.client.post("/api/v1/auth/webauthn/login", json={
            "credential_id": "passkey_default_demo",
            "signature": "sig_demo",
            "client_data_json": "eyJ0eXBlIjoid2ViYXV0aG4uZ2V0In0=",
            "authenticator_data": "auth_data_demo"
        })
        self.assertEqual(login_res.status_code, 200)
        data = login_res.json()
        self.assertIn("access_token", data)
        self.assertIn("user", data)

if __name__ == "__main__":
    unittest.main()
