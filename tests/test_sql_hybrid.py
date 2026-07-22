import os
import shutil
import unittest
import tempfile
import time
import database.sql_db as sql_db
from database.sql_db import SQLDatabaseManager
from infrastructure.repositories.sql_repositories import SQLUserRepository, SQLAppointmentRepository, SQLNotificationRepository
from core.domain.entities import User

class TestSQLHybrid(unittest.TestCase):
    def setUp(self):
        # Create a temp dir for database
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_vault.db")
        
        # Override SQLITE path and force re-initialization
        self.original_path = sql_db.DEFAULT_SQLITE_PATH
        sql_db.DEFAULT_SQLITE_PATH = self.db_path
        
        # Re-create manager for test environment
        self.db_manager = SQLDatabaseManager()
        
        # Patch the default_sql_db in sql_db and repositories modules
        self.original_manager = sql_db.default_sql_db
        sql_db.default_sql_db = self.db_manager
        
        self.user_repo = SQLUserRepository()
        self.apt_repo = SQLAppointmentRepository()
        self.notif_repo = SQLNotificationRepository()

    def tearDown(self):
        # Restore original settings
        sql_db.DEFAULT_SQLITE_PATH = self.original_path
        sql_db.default_sql_db = self.original_manager
        
        # Clean up temp dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_init(self):
        # Verify the database file is created
        self.assertTrue(os.path.exists(self.db_path))
        
        # Verify default tables can be queried
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        self.assertIn("users", tables)
        self.assertIn("appointments", tables)
        self.assertIn("notifications", tables)
        self.assertIn("blacklisted_tokens", tables)

    def test_user_repository(self):
        user = User(
            id="USR-TEST-99",
            username="dr.sqltest",
            password_hash="hashed_password",
            role="doctor",
            full_name="Dr. SQL Test",
            specialty="Pediatrics",
            institution="SQL Medical Center",
            totp_enabled=False
        )
        
        # 1. Save user
        self.user_repo.save_user(user)
        self.assertTrue(self.user_repo.user_exists("dr.sqltest"))
        
        # 2. Load user
        loaded = self.user_repo.load_user("dr.sqltest")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.full_name, "Dr. SQL Test")
        self.assertEqual(loaded.specialty, "Pediatrics")
        self.assertEqual(loaded.institution, "SQL Medical Center")
        self.assertFalse(loaded.totp_enabled)
        
        # 3. Update user
        loaded.totp_enabled = True
        loaded.specialty = "Cardiology"
        self.user_repo.save_user(loaded)
        
        updated = self.user_repo.load_user("dr.sqltest")
        self.assertTrue(updated.totp_enabled)
        self.assertEqual(updated.specialty, "Cardiology")
        
        # 4. Load all
        all_users = self.user_repo.load_all_users()
        self.assertEqual(len(all_users), 1)
        self.assertEqual(all_users[0].username, "dr.sqltest")
        
        # 5. Delete user
        deleted = self.user_repo.delete_user("dr.sqltest")
        self.assertTrue(deleted)
        self.assertFalse(self.user_repo.user_exists("dr.sqltest"))

    def test_appointment_repository(self):
        apt = {
            "id": "apt-test-111",
            "patient_id": "VIP-999",
            "doctor_name": "Dr. House",
            "department": "Diagnostic Medicine",
            "appointment_date": "2026-07-01",
            "appointment_time": "09:00",
            "status": "scheduled",
            "notes": "Lupus checkup."
        }
        
        # 1. Save
        self.apt_repo.save_appointment(apt)
        
        # 2. Load by ID
        loaded = self.apt_repo.load_appointment("apt-test-111")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["doctor_name"], "Dr. House")
        self.assertEqual(loaded["notes"], "Lupus checkup.")
        
        # 3. Load by Patient
        list_apts = self.apt_repo.load_appointments_by_patient("VIP-999")
        self.assertEqual(len(list_apts), 1)
        self.assertEqual(list_apts[0]["id"], "apt-test-111")
        
        # 4. Update
        apt["status"] = "cancelled"
        self.apt_repo.save_appointment(apt)
        updated = self.apt_repo.load_appointment("apt-test-111")
        self.assertEqual(updated["status"], "cancelled")
        
        # 5. Delete
        deleted = self.apt_repo.delete_appointment("apt-test-111")
        self.assertTrue(deleted)
        self.assertIsNone(self.apt_repo.load_appointment("apt-test-111"))

    def test_notification_repository(self):
        notif = {
            "id": "notif-test-222",
            "patient_id": "VIP-888",
            "title": "Alert Title",
            "message": "Detailed alert message",
            "severity": "warning",
            "timestamp": time.time(),
            "read": False
        }
        
        # 1. Save
        self.notif_repo.save_notification(notif)
        
        # 2. Load by Patient
        list_notifs = self.notif_repo.load_notifications_by_patient("VIP-888")
        self.assertEqual(len(list_notifs), 1)
        self.assertEqual(list_notifs[0]["id"], "notif-test-222")
        self.assertFalse(list_notifs[0]["read"])
        
        # 3. Mark as read
        marked = self.notif_repo.mark_as_read("VIP-888", "notif-test-222")
        self.assertTrue(marked)
        
        updated_notifs = self.notif_repo.load_notifications_by_patient("VIP-888")
        self.assertTrue(updated_notifs[0]["read"])

if __name__ == '__main__':
    unittest.main()
