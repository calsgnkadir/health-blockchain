"""
tests/test_lis_gateway.py — the laboratory gateway is a write path, not a public one
====================================================================================
POST /api/v1/webhooks/lis appends blocks to a patient's chain. Left open it lets
anyone reachable on the network forge clinical results in a record set the vault
presents as tamper-evident, and its patient identifier becomes a directory name
for the chain store, so an unvalidated one escapes the project directory.
"""

import os
import shutil
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from database.connection import LMDBConnectionManager
from core.pseudonymization.service import project_name_for

API_KEY = "test-lis-gateway-key"


def payload(patient_id="VIP-001", **overrides):
    body = {
        "patient_id": patient_id,
        "title": "Troponin panel",
        "doctor_name": "Dr Lab",
        "institution": "Central Laboratory",
        "test_name": "Troponin I",
        "result_value": "0.02",
        "reference_range": "0-0.4",
        "unit": "ng/mL",
        "notes": "",
    }
    body.update(overrides)
    return body


class TestLisGatewayAuthentication(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        os.environ["VHV_LIS_API_KEY"] = API_KEY
        self.client = TestClient(app)

    def tearDown(self):
        os.environ["VHV_LIS_API_KEY"] = API_KEY

    def test_submission_without_credentials_is_rejected(self):
        res = self.client.post("/api/v1/webhooks/lis", json=payload())
        self.assertEqual(res.status_code, 401)

    def test_submission_with_wrong_credentials_is_rejected(self):
        res = self.client.post("/api/v1/webhooks/lis", json=payload(),
                               headers={"X-LIS-Api-Key": "not-the-key"})
        self.assertEqual(res.status_code, 401)

    def test_gateway_fails_closed_when_unconfigured(self):
        """No key configured must mean disabled, never open."""
        os.environ["VHV_LIS_API_KEY"] = ""
        res = self.client.post("/api/v1/webhooks/lis", json=payload(),
                               headers={"X-LIS-Api-Key": "anything"})
        self.assertEqual(res.status_code, 503)

    def test_valid_submission_is_accepted(self):
        res = self.client.post("/api/v1/webhooks/lis", json=payload(),
                               headers={"X-LIS-Api-Key": API_KEY})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["success"])


class TestLisGatewayInput(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        os.environ["VHV_LIS_API_KEY"] = API_KEY
        self.client = TestClient(app)

    def _post(self, body):
        return self.client.post("/api/v1/webhooks/lis", json=body,
                                headers={"X-LIS-Api-Key": API_KEY})

    def test_patient_id_traversal_is_rejected(self):
        res = self._post(payload(patient_id="../../../escaped_chain"))
        self.assertEqual(res.status_code, 422)

    def test_patient_id_format_is_enforced(self):
        for bad in ("", "VIP", "patient_1", "VIP-1", "VIP-001; DROP TABLE users"):
            self.assertEqual(self._post(payload(patient_id=bad)).status_code, 422, bad)

    def test_submitted_text_is_stored_verbatim(self):
        """Clinical text is preserved as written; escaping happens at render."""
        res = self._post(payload(test_name="Troponin I (high-sensitivity) <5 ng/L"))
        self.assertEqual(res.status_code, 200, res.text)

        # Records are encrypted at rest, so read the decrypted view the service
        # returns — the property under test is "not HTML-escaped", not "on disk".
        from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
        from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
        from core.services.record_service import RecordService

        service = RecordService(LMDBBlockRepository(), AESGCMStrategy())
        revealed = " ".join(str(v) for v in service.get_final_data("VIP-001").values())
        self.assertIn("<5 ng/L", revealed)
        self.assertNotIn("&lt;5 ng/L", revealed)

    def test_records_are_ciphertext_on_disk(self):
        """The raw chain store must not hold plaintext clinical text."""
        self._post(payload(test_name="SECRET-MARKER-XYZ"))

        from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
        blocks = LMDBBlockRepository().load_all_blocks(project_name_for("VIP-001"))
        on_disk = " ".join(str(b.data) for b in blocks)
        self.assertNotIn("SECRET-MARKER-XYZ", on_disk)


class TestChainStorePathSafety(unittest.TestCase):
    """No caller may place a chain store outside the projects directory."""

    def setUp(self):
        self.base = os.path.join(os.path.dirname(__file__), "test_path_projects")
        self.manager = LMDBConnectionManager(self.base)

    def tearDown(self):
        self.manager.close_all()
        shutil.rmtree(self.base, ignore_errors=True)

    def test_traversing_project_names_are_refused(self):
        manager = self.manager
        for name in ("../escape", "../../escape", "patient/../..", "a/b", "..", ""):
            with self.assertRaises(ValueError, msg=name):
                manager.get_project_path(name)

    def test_ordinary_project_names_still_resolve(self):
        manager = self.manager
        path = manager.get_project_path("patient_VIP_001")
        self.assertTrue(path.endswith("patient_VIP_001"))


if __name__ == "__main__":
    unittest.main()


class TestMetadataDisclosure(unittest.TestCase):
    """Chain metadata and the liveness probe must not leak across boundaries."""

    @classmethod
    def setUpClass(cls):
        from database.sql_db import default_sql_db
        default_sql_db.seed_default_users()

    def setUp(self):
        os.environ["TESTING"] = "true"
        self.client = TestClient(app)

    def _token(self, username, password):
        res = self.client.post("/api/v1/auth/login",
                               json={"username": username, "password": password})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["access_token"]

    def test_patient_cannot_read_another_chain_status(self):
        token = self._token("vip001", "VIPPatient@2026!")
        res = self.client.get("/api/v1/blockchain/VIP-999/status",
                              headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 403)

    def test_patient_can_read_their_own_chain_status(self):
        token = self._token("vip001", "VIPPatient@2026!")
        res = self.client.get("/api/v1/blockchain/VIP-001/status",
                              headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)

    def test_health_probe_does_not_disclose_the_device_fingerprint(self):
        body = self.client.get("/api/v1/health").json()
        self.assertEqual(body["status"], "healthy")
        self.assertNotIn("device_id", body)
