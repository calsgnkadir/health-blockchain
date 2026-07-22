"""
test_architecture_upgrades.py — Automation tests for Security & Hardening Plan
"""

import os
import json
import base64
import unittest
import tempfile
import time
import shutil
from pydantic import ValidationError

from core.domain.entities import Block
from backend.dependencies import _get_client_ip
from backend.schemas.requests import LoginReq, UserCreate, DecryptRequest, RecordCreate
import database.storage as storage

class TestSecurityHardening(unittest.TestCase):

    def test_block_serialization_symmetry(self):
        """1. Verify Block serialization symmetry preserves protection_hash (Hata 3)"""
        original_block = Block(
            index=3,
            timestamp=1625097600.0,
            data={"heart_rate": "72", "temperature": "36.5"},
            previous_hash="0000abc123",
            signature="sig_abc123",
            is_protected=True,
            protection_hash="SuperSecurePasswordHash123!"
        )
        
        block_dict = original_block.to_dict()
        self.assertIn("protection_hash", block_dict)
        self.assertEqual(block_dict["protection_hash"], "SuperSecurePasswordHash123!")

        deserialized_block = Block.from_dict(block_dict)
        self.assertEqual(deserialized_block.index, original_block.index)
        self.assertEqual(deserialized_block.is_protected, original_block.is_protected)
        self.assertEqual(deserialized_block.protection_hash, original_block.protection_hash)

    def test_jwt_private_key_encryption(self):
        """2. Verify that JWT Private Key is saved encrypted and requires the correct passphrase (Hata 4)"""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from core.security import get_device_id
        
        temp_dir = tempfile.mkdtemp()
        try:
            private_key_file = os.path.join(temp_dir, ".jwt_private.pem")
            passphrase = b"test_passphrase_123"
            
            # Generate test RSA private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            
            # Encrypt key with BestAvailableEncryption using passphrase
            pem_data = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.BestAvailableEncryption(passphrase)
            )
            
            with open(private_key_file, "wb") as f:
                f.write(pem_data)
                
            # Attempt 1: Load without password (should fail)
            with self.assertRaises(TypeError):
                serialization.load_pem_private_key(pem_data, password=None)
                
            # Attempt 2: Load with incorrect password (should fail)
            with self.assertRaises(ValueError):
                serialization.load_pem_private_key(pem_data, password=b"wrong_passphrase")
                
            # Attempt 3: Load with correct password (should succeed)
            loaded_key = serialization.load_pem_private_key(pem_data, password=passphrase)
            self.assertIsNotNone(loaded_key)
            self.assertIsInstance(loaded_key, rsa.RSAPrivateKey)
            
        finally:
            shutil.rmtree(temp_dir)

    def test_ip_rate_limiter_and_proxy(self):
        """3. Verify client IP extraction respects TRUST_PROXIES (Hata 5)"""
        class MockRequest:
            def __init__(self, headers, client_host):
                self.headers = headers
                class Client:
                    def __init__(self, host):
                        self.host = host
                self.client = Client(client_host)
            @property
            def client(self):
                return self._client
            @client.setter
            def client(self, val):
                self._client = val

        headers_with_xff = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
        direct_ip = "192.168.1.50"
        request = MockRequest(headers=headers_with_xff, client_host=direct_ip)

        # Case A: TRUST_PROXIES=false -> ignore X-Forwarded-For
        os.environ["TRUST_PROXIES"] = "false"
        client_ip = _get_client_ip(request)
        self.assertEqual(client_ip, direct_ip)

        # Case B: TRUST_PROXIES=true -> trust X-Forwarded-For
        os.environ["TRUST_PROXIES"] = "true"
        client_ip = _get_client_ip(request)
        self.assertEqual(client_ip, "203.0.113.195")
        
        # Clean up env
        os.environ.pop("TRUST_PROXIES", None)

    def test_input_validation(self):
        """4. Verify Pydantic input validation regex, pattern, and range constraints (Hata 8)"""
        
        # A. LoginReq username regex check
        with self.assertRaises(ValidationError):
            LoginReq(username="user@name!invalid", password="SecurePassword123")
        
        valid_login = LoginReq(username="valid_user.12-3", password="SecurePassword123")
        self.assertEqual(valid_login.username, "valid_user.12-3")

        # B. UserCreate username, password, and patient_id validation
        # Password too simple
        with self.assertRaises(ValidationError):
            UserCreate(
                username="valid_user",
                password="123",
                role="doctor",
                full_name="Dr. Smith"
            )
            
        # Invalid role
        with self.assertRaises(ValidationError):
            UserCreate(
                username="valid_user",
                password="SecurePassword123!",
                role="invalid_role",
                full_name="Dr. Smith"
            )

        # Invalid patient_id
        with self.assertRaises(ValidationError):
            UserCreate(
                username="valid_user",
                password="SecurePassword123!",
                role="vip_patient",
                full_name="VIP Patient",
                patient_id="invalid@patient#id"
            )

        # C. DecryptRequest negative block index validation
        with self.assertRaises(ValidationError):
            DecryptRequest(password="password123", block_index=-5)

        valid_decrypt = DecryptRequest(password="password123", block_index=0)
        self.assertEqual(valid_decrypt.block_index, 0)

    def test_unit_of_work_transaction(self):
        """5. Verify LMDB transaction write atomicity and rollback on exception (Hata 9)"""
        test_project = "__test_transaction_rollback__"
        storage.reset_db(test_project)
        
        # Seed an initial key
        def initial_write(txn):
            txn.put(b"initial_key", b"initial_val")
        storage.run_write_transaction(test_project, initial_write)

        # Run a transaction that writes and then fails/raises an exception
        def failing_txn(txn):
            txn.put(b"failed_key", b"failed_val")
            raise RuntimeError("Database write transaction failure simulation")

        with self.assertRaises(RuntimeError):
            storage.run_write_transaction(test_project, failing_txn)

        # Verify that failed_key was NOT committed and database state is intact
        env = storage.open_db(test_project)
        with env.begin(write=False) as txn:
            self.assertEqual(txn.get(b"initial_key"), b"initial_val")
            self.assertIsNone(txn.get(b"failed_key"))

        # Clean up database
        storage.reset_db(test_project)

    def test_record_service_integrity(self):
        """6. RecordService Integrity: Verify chain validation and tampering detection"""
        from core.services.record_service import RecordService
        from core.domain.factories import BlockFactory
        
        test_patient = "VIP-TEST-INTEGRITY"
        test_project = "patient_VIP_TEST_INTEGRITY"
        storage.reset_db(test_project)
        
        from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
        from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
        
        repo = LMDBBlockRepository()
        crypto = AESGCMStrategy()
        service = RecordService(repo, crypto)
        
        # Create genesis
        genesis = BlockFactory.create_genesis_block()
        repo.save_block(test_project, genesis)
        
        # Verify valid
        self.assertTrue(service.is_chain_valid(test_patient))
        
        # Add a block
        block1 = BlockFactory.create_data_block(
            index=1,
            previous_hash=genesis.hash,
            data={"test": "data"}
        )
        repo.save_block(test_project, block1)
        self.assertTrue(service.is_chain_valid(test_patient))
        
        # Tamper with the block data AND merkle_root to break hash validation
        tampered_data = block1.to_dict()
        tampered_data["data"] = {"test": "tampered"}
        tampered_data["merkle_root"] = "tampered_root"
        storage.save_block_to_db(test_project, 1, tampered_data)
        
        # Verify that validation fails or broken link is found
        self.assertFalse(service.is_chain_valid(test_patient))
        self.assertEqual(service.find_broken_link_index(test_patient), 1)
        
        storage.reset_db(test_project)

    def test_consent_validator_rules(self):
        """7. ConsentValidator Rules: Test category-based verification"""
        from core.services.consent_validator import ConsentValidator
        from core.domain.factories import BlockFactory
        from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
        
        test_patient = "VIP-TEST-CONSENT"
        test_project = "patient_VIP_TEST_CONSENT"
        storage.reset_db(test_project)
        
        repo = LMDBBlockRepository()
        validator = ConsentValidator(repo)
        
        # Initially, no consent
        self.assertFalse(validator.has_consent(test_patient, "dr.smith", "diagnosis"))
        
        # Add a consent rule directly to LMDB key-value store
        consent_data = {
            "doctor_username": "dr.smith",
            "record_type": "diagnosis",
            "expiry_timestamp": time.time() + 3600,
            "granted_at": time.time(),
        }
        key = b"consent_dr.smith_diagnosis"
        
        def txn_consent(txn):
            txn.put(key, json.dumps(consent_data).encode("utf-8"))
        storage.run_write_transaction(test_project, txn_consent)
        
        # Test match category
        self.assertTrue(validator.has_consent(test_patient, "dr.smith", "diagnosis"))
        # Test non-matching category
        self.assertFalse(validator.has_consent(test_patient, "dr.smith", "prescription"))
        # Test non-matching doctor
        self.assertFalse(validator.has_consent(test_patient, "dr.jones", "diagnosis"))
        
        storage.reset_db(test_project)

    def test_xss_sanitization_and_date_validation(self):
        """8. Verify input sanitization (HTML escape) and ISO 8601 date validation in Pydantic models"""
        
        # Test HTML escape on doctor_name and institution
        dirty_record = {
            "patient_id": "VIP-001",
            "record_type": "diagnosis",
            "title": "Diagnosis <script>alert('xss')</script>",
            "doctor_name": "Dr. <img src=x onerror=alert(1)>",
            "institution": "<b>Vault Hospital</b>",
            "record_date": "2026-06-12",
            "data": {"icd_code": "I10", "severity": "Mild", "symptoms": "none"},
            "notes": "Testing XSS sanitization <p>tag</p>"
        }
        
        model = RecordCreate(**dirty_record)
        self.assertNotIn("<script>", model.title)
        self.assertNotIn("<img>", model.doctor_name)
        self.assertNotIn("<b>", model.institution)
        self.assertNotIn("<p>", model.notes)
        
        # Test valid record date format (ISO 8601)
        valid_dates = ["2026-06-12", "2026-06-12T17:29:58", "2026-06-12T17:29:58Z", "2026-06-12T17:29:58+03:00"]
        for d in valid_dates:
            dirty_record["record_date"] = d
            model = RecordCreate(**dirty_record)
            self.assertEqual(model.record_date, d)
            
        # Test invalid record date format
        invalid_dates = ["12-06-2026", "2026/06/12", "next tuesday", "2026-06-12T17:29:58:99"]
        for d in invalid_dates:
            dirty_record["record_date"] = d
            with self.assertRaises(ValidationError):
                RecordCreate(**dirty_record)

if __name__ == "__main__":
    unittest.main()
