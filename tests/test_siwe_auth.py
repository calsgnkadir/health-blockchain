import os
import sys
import unittest
import shutil
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from backend.dependencies import get_db_manager
from database.connection import LMDBConnectionManager
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository
from core.domain.entities import User
from core.security import hash_password

class TestSIWEAuth(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_projects_siwe")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_manager = LMDBConnectionManager(self.test_dir)
        self.user_repo = LMDBUserRepository(self.db_manager)

        self.test_user = User(
            id="USR-SIWE-01",
            username="crypto_patient",
            password_hash=hash_password("CryptoPass123!"),
            role="vip_patient",
            full_name="Crypto Patient",
            patient_id="VIP-777",
            wallet_address="0x1234567890123456789012345678901234567890"
        )
        self.user_repo.save_user(self.test_user)

        import database.storage as storage
        self.original_default_db = storage.default_db_manager
        storage.default_db_manager = self.db_manager

        app.dependency_overrides[get_db_manager] = lambda: self.db_manager
        self.client = TestClient(app)

    def tearDown(self):
        import database.storage as storage
        storage.default_db_manager = self.original_default_db
        app.dependency_overrides.clear()
        self.db_manager.close_all()
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_generate_nonce(self):
        res = self.client.get("/api/v1/auth/nonce")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("nonce", data)
        self.assertIn("message", data)
        self.assertEqual(len(data["nonce"]), 32)
        self.assertIn(data["nonce"], data["message"])

    def test_wallet_login_invalid_nonce(self):
        payload = {
            "address": "0x1234567890123456789012345678901234567890",
            "signature": "0x" + "00" * 65,
            "nonce": "invalid_nonce_12345"
        }
        res = self.client.post("/api/v1/auth/wallet-login", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Invalid or expired", res.json()["detail"])

if __name__ == "__main__":
    unittest.main()
