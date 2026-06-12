import os
import shutil
import unittest
import sys

# Setup project root import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import LMDBConnectionManager
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository
from core.services.auth_service import AuthService
from core.domain.entities import User
from core.security import hash_password

class TestAuthService(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_projects")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_manager = LMDBConnectionManager(self.test_dir)
        self.user_repo = LMDBUserRepository(self.db_manager)
        self.auth_service = AuthService(self.user_repo)

    def tearDown(self):
        self.db_manager.close_all()
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_save_and_load_user(self):
        user = User(
            id="USR-001",
            username="test_doc",
            password_hash=hash_password("DocSecurePassword123!"),
            role="doctor",
            full_name="Dr. Test Case",
        )
        self.user_repo.save_user(user)
        loaded = self.user_repo.load_user("test_doc")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.full_name, "Dr. Test Case")

    def test_authenticate_success(self):
        user = User(
            id="USR-002",
            username="test_vip",
            password_hash=hash_password("PatientSecurePassword123!"),
            role="vip_patient",
            full_name="VIP Test Patient",
            patient_id="VIP-002"
        )
        self.user_repo.save_user(user)
        authenticated = self.auth_service.authenticate("test_vip", "PatientSecurePassword123!", "127.0.0.1")
        self.assertIsNotNone(authenticated)
        self.assertEqual(authenticated.username, "test_vip")

    def test_authenticate_failure(self):
        authenticated = self.auth_service.authenticate("unknown_user", "SomePassword123!", "127.0.0.1")
        self.assertIsNone(authenticated)
