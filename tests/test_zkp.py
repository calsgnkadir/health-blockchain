"""
tests/test_zkp.py — Zero-Knowledge Proof (ZKP) Selective Disclosure Tests
=========================================================================
7 test cases covering:
  1. Pedersen commitment creation (hiding property)
  2. ZKP proof generation and verification (completeness)
  3. Tampered proof rejection (soundness)
  4. Wrong claim label rejection
  5. API: commitment endpoint (VIP patient creates commitment)
  6. API: verify endpoint (no auth required, zero-knowledge)
  7. API: commitments list endpoint
"""
import os
import sys
import json
import time
import unittest
import tempfile

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.zkp.pedersen import PedersenZKP, ZKPCommitment, _field_to_int


class TestZKPEngine(unittest.TestCase):
    """Unit tests for the pure-Python ZKP engine."""

    def setUp(self):
        self.zkp = PedersenZKP()

    def test_01_commitment_creation(self):
        """Pedersen commitment'i deterministic olmayan rastgele r ile oluşturmalı (hiding property)."""
        comm1 = self.zkp.commit("VIP-001", "has_allergy", "Penisilin")
        comm2 = self.zkp.commit("VIP-001", "has_allergy", "Penisilin")
        self.assertTrue(comm1.commitment_hex.startswith("0x"), "Commitment should be a hex string")
        # Hiding: same claim but different random r → different commitment
        self.assertNotEqual(comm1.commitment_hex, comm2.commitment_hex, "Commitments should differ due to random blinding")
        # Deterministic value_int
        self.assertEqual(comm1.value_int, comm2.value_int, "value_int must be deterministic for same claim")

    def test_02_proof_generation_and_verification(self):
        """Geçerli bir commitment için üretilen ZKP kanıtı doğrulanabilmeli (completeness)."""
        comm = self.zkp.commit("VIP-001", "has_blood_type", "A+")
        proof = self.zkp.prove(comm)
        self.assertIsNotNone(proof.proof_id)
        self.assertTrue(proof.R_hex.startswith("0x"))
        self.assertIsInstance(proof.s_int, int)
        is_valid = self.zkp.verify_proof(proof)
        self.assertTrue(is_valid, "Valid proof should verify successfully")

    def test_03_tampered_proof_rejected(self):
        """Manipüle edilmiş (yanlış s_int) kanıt reddedilmeli (soundness)."""
        comm = self.zkp.commit("VIP-001", "has_vaccination", "Covid-19")
        proof = self.zkp.prove(comm)
        proof.s_int += 1  # Tamper: breaks the Schnorr equation
        is_valid = self.zkp.verify_proof(proof)
        self.assertFalse(is_valid, "Tampered proof should be rejected")

    def test_04_wrong_claim_label_rejected(self):
        """Yanlış claim_label ile doğrulama başarısız olmalı."""
        comm = self.zkp.commit("VIP-001", "has_allergy", "Penisilin")
        proof = self.zkp.prove(comm)
        is_valid = self.zkp.verify_proof(proof, claim_type="has_allergy", claim_label="Aspirin")
        self.assertFalse(is_valid, "Proof with wrong label should not verify")


class TestZKPAPI(unittest.TestCase):
    """Integration tests for ZKP API endpoints."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        db_path = os.path.join(cls._tmp, "test_zkp_vault.db")

        os.environ["TESTING"] = "true"
        os.environ["ENVIRONMENT"] = "test"
        os.environ["VHV_DEMO_MODE"] = "true"

        import database.sql_db as _sql_mod
        _sql_mod.DEFAULT_SQLITE_PATH = db_path
        from database.sql_db import SQLDatabaseManager
        _bootstrap = SQLDatabaseManager()
        _bootstrap.seed_default_users()
        _sql_mod.default_sql_db = _bootstrap
        import infrastructure.repositories.sql_repositories as _sql_repo_mod
        _sql_repo_mod.default_sql_db = _bootstrap

        from backend.main import app
        from fastapi.testclient import TestClient
        cls.client = TestClient(app, raise_server_exceptions=False)

        # Login VIP patient with correct seeded password
        resp = cls.client.post("/api/v1/auth/login", json={"username": "vip001", "password": "VIPPatient@2026!"})
        cls.vip_token = resp.json().get("access_token", "") if resp.status_code == 200 else ""

        # Login doctor
        resp2 = cls.client.post("/api/v1/auth/login", json={"username": "dr.smith", "password": "Doctor@2026Secure!"})
        cls.doc_token = resp2.json().get("access_token", "") if resp2.status_code == 200 else ""

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_05_create_commitment_endpoint(self):
        """VIP hasta commitment olusturabilmeli ve yanit dogru alanlari icermeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp = self.client.post(
            "/api/v1/zkp/commitment/VIP-001",
            json={"claim_type": "has_allergy", "claim_label": "Penisilin"},
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200, f"Commitment creation failed: {resp.text}")
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("commitment", data)
        self.assertIn("commitment_hex", data["commitment"])
        self.assertIn("secret", data)
        self.assertIn("randomness_hex", data["secret"])
        self.assertIn("proof", data)

        # Store for subsequent tests
        TestZKPAPI._last_proof = data["proof"]
        TestZKPAPI._last_commitment = data["commitment"]

    def test_06_verify_endpoint_no_auth(self):
        """Kanit dogrulama endpoint'i kimlik dogrulama olmadan calisabilmeli."""
        # First create a commitment
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp = self.client.post(
            "/api/v1/zkp/commitment/VIP-001",
            json={"claim_type": "has_blood_type", "claim_label": "A+"},
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200)
        proof = resp.json()["proof"]
        commitment = resp.json()["commitment"]

        # Verify WITHOUT any auth token
        verify_resp = self.client.post(
            "/api/v1/zkp/verify",
            json={
                "commitment_hex": commitment["commitment_hex"],
                "R_hex": proof["R_hex"],
                "s_int": proof["s_int"],
                "challenge_hex": proof["challenge_hex"],
                "claim_type": commitment["claim_type"],
                "claim_label": commitment["claim_label"],
                "patient_id": "VIP-001",
            }
        )
        self.assertEqual(verify_resp.status_code, 200, f"Verify failed: {verify_resp.text}")
        result = verify_resp.json()
        self.assertTrue(result["verified"], f"Proof should be valid, got: {result}")
        self.assertFalse(result["raw_data_exposed"])

    def test_07_list_commitments_endpoint(self):
        """VIP hasta kendi commitment listesini gorebilmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp = self.client.get(
            "/api/v1/zkp/commitments/VIP-001",
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200, f"List failed: {resp.text}")
        data = resp.json()
        self.assertEqual(data["patient_id"], "VIP-001")
        self.assertIn("commitments", data)
        self.assertIn("supported_claim_types", data)
        # After test_05 and test_06, we should have at least 2 commitments
        self.assertGreaterEqual(data["total"], 2, "Should have at least 2 commitments from previous tests")


if __name__ == "__main__":
    unittest.main()
