import os
import sys
import unittest
import shutil
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from backend.dependencies import get_db_manager, current_user
from infrastructure.repositories.sql_repositories import SQLUserRepository
from core.domain.entities import User
from core.security import hash_password

class TestPhase3Advanced(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        self.user_repo = SQLUserRepository()

        self.test_user = User(
            id="USR-P3-01",
            username="p3_user",
            password_hash=hash_password("PassPhase3!"),
            role="vip_patient",
            full_name="Phase 3 User",
            patient_id="VIP-333",
            wallet_address="0x1111111111111111111111111111111111111111"
        )
        self.user_repo.save_user(self.test_user)

        app.dependency_overrides[current_user] = lambda: self.test_user.to_dict()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_w3c_did_document(self):
        res = self.client.get("/api/v1/auth/did/p3_user")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["id"].startswith("did:vhv:"))
        self.assertEqual(data["controller"], "did:vhv:p3_user")
        self.assertIn("verificationMethod", data)

    def test_w3c_verifiable_credential(self):
        res = self.client.get("/api/v1/auth/vc/p3_user")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("VerifiableCredential", data["type"])
        self.assertEqual(data["credentialSubject"]["username"], "p3_user")
        self.assertIn("proof", data)

    def test_social_recovery_workflow(self):
        # 1. Configure Guardians
        g_payload = {"guardians": ["guardian1@test.com", "guardian2@test.com", "guardian3@test.com"]}
        res = self.client.post("/api/v1/auth/recovery/guardians", json=g_payload)
        self.assertEqual(res.status_code, 200)

        # 2. Initiate Recovery
        init_payload = {
            "username": "p3_user",
            "new_wallet_address": "0x9999999999999999999999999999999999999999"
        }
        res_init = self.client.post("/api/v1/auth/recovery/initiate", json=init_payload)
        self.assertEqual(res_init.status_code, 200)
        rec_id = res_init.json()["recovery_id"]

        # 3. Guardian 1 Approves
        appr1 = {"recovery_id": rec_id, "guardian_identifier": "guardian1@test.com"}
        res_appr1 = self.client.post("/api/v1/auth/recovery/approve", json=appr1)
        self.assertEqual(res_appr1.status_code, 200)
        self.assertEqual(res_appr1.json()["status"], "pending")

        # 4. Guardian 2 Approves (Threshold = 2 reached!)
        appr2 = {"recovery_id": rec_id, "guardian_identifier": "guardian2@test.com"}
        res_appr2 = self.client.post("/api/v1/auth/recovery/approve", json=appr2)
        self.assertEqual(res_appr2.status_code, 200)
        self.assertEqual(res_appr2.json()["status"], "executed")

        # Verify wallet address updated to new address
        updated_user = self.user_repo.load_user("p3_user")
        self.assertEqual(updated_user.wallet_address, "0x9999999999999999999999999999999999999999")

if __name__ == "__main__":
    unittest.main()
