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

    def test_submitted_markup_is_neutralised(self):
        res = self._post(payload(test_name="<img src=x onerror=alert(1)>"))
        self.assertEqual(res.status_code, 200, res.text)
        # The stored value must not still be live markup.
        from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
        blocks = LMDBBlockRepository().load_all_blocks("patient_VIP_001")
        stored = " ".join(str(b.data) for b in blocks)
        self.assertNotIn("<img src=x onerror=", stored)


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



if __name__ == "__main__":
    unittest.main()
