import os
import sys
import unittest
import shutil
from fastapi.testclient import TestClient

# Setup project root import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from backend.dependencies import get_db_manager, current_user
from database.connection import LMDBConnectionManager
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository
from core.domain.entities import User
from core.security import hash_password

class TestAPIRecordsFHIR(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_projects_api_rec")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_manager = LMDBConnectionManager(self.test_dir)
        self.user_repo = LMDBUserRepository(self.db_manager)

        # Seed test user
        self.test_user = User(
            id="USR-T01",
            username="test_patient",
            password_hash=hash_password("PatientPassword123!"),
            role="vip_patient",
            full_name="VIP Patient Test",
            patient_id="VIP-099",
        )
        self.user_repo.save_user(self.test_user)

        # Override dependencies
        import database.storage as storage
        self.original_default_db_manager = storage.default_db_manager
        storage.default_db_manager = self.db_manager

        app.dependency_overrides[get_db_manager] = lambda: self.db_manager
        app.dependency_overrides[current_user] = lambda: self.test_user.to_dict()

        self.client = TestClient(app)

    def tearDown(self):
        import database.storage as storage
        storage.default_db_manager = self.original_default_db_manager

        app.dependency_overrides.clear()
        self.db_manager.close_all()
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_add_vital_signs_record_saves_fhir(self):
        payload = {
            "patient_id": "VIP-099",
            "record_type": "vital_signs",
            "title": "Daily Vitals Check",
            "doctor_name": "Dr. Test APIRecords",
            "institution": "Test General Hospital",
            "record_date": "2026-06-22",
            "access_level": "doctor_shared",
            "is_confidential": False,
            "data": {
                "blood_pressure": "120/80",
                "heart_rate": 75,
                "temperature": 36.6,
                "oxygen_sat": 99
            },
            "notes": "Patient is resting"
        }

        # Get CSRF token first
        self.client.get("/api/v1/records/VIP-099")
        csrf_token = self.client.cookies.get("csrf_token")
        headers = {"x-csrf-token": csrf_token}

        # Add record
        r_add = self.client.post("/api/v1/records", json=payload, headers=headers)
        self.assertEqual(r_add.status_code, 200)
        self.assertTrue(r_add.json()["success"])

        # Fetch records
        r_get = self.client.get("/api/v1/records/VIP-099")
        self.assertEqual(r_get.status_code, 200)
        records = r_get.json()["records"]
        self.assertEqual(len(records), 1)

        # Check if the data is saved in FHIR format
        record_data = records[0]["data"]
        self.assertEqual(record_data["resourceType"], "Observation")
        self.assertEqual(record_data["status"], "final")
        self.assertEqual(record_data["category"][0]["coding"][0]["code"], "vital-signs")
        self.assertEqual(record_data["code"]["coding"][0]["code"], "85353-1")

        # Check components
        components = record_data["component"]
        systolic = next(c for c in components if c["code"]["coding"][0]["code"] == "8480-6")
        self.assertEqual(systolic["valueQuantity"]["value"], 120.0)

    def test_add_prescription_record_saves_fhir(self):
        payload = {
            "patient_id": "VIP-099",
            "record_type": "prescription",
            "title": "Anti-hypertensive Rx",
            "doctor_name": "Dr. Test APIRecords",
            "institution": "Test General Hospital",
            "record_date": "2026-06-22",
            "access_level": "doctor_shared",
            "is_confidential": False,
            "data": {
                "medication": "Lisinopril 10mg",
                "dose": "1 tablet",
                "frequency": "Daily",
                "duration": 30
            },
            "notes": "Take in the morning"
        }

        # Get CSRF token first
        self.client.get("/api/v1/records/VIP-099")
        csrf_token = self.client.cookies.get("csrf_token")
        headers = {"x-csrf-token": csrf_token}

        # Add record
        r_add = self.client.post("/api/v1/records", json=payload, headers=headers)
        self.assertEqual(r_add.status_code, 200)

        # Fetch records
        r_get = self.client.get("/api/v1/records/VIP-099")
        self.assertEqual(r_get.status_code, 200)
        records = r_get.json()["records"]
        
        # We have two records now (vital signs from previous or since it's same patient, wait setUp/tearDown resets DB per test)
        self.assertEqual(len(records), 1)
        record_data = records[0]["data"]
        
        self.assertEqual(record_data["resourceType"], "MedicationRequest")
        self.assertEqual(record_data["status"], "active")
        self.assertEqual(record_data["medicationCodeableConcept"]["text"], "Lisinopril 10mg")
        self.assertEqual(record_data["dosageInstruction"][0]["timing"]["repeat"]["duration"], 30.0)
