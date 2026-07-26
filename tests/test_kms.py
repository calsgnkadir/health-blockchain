"""
tests/test_kms.py — KMS Provider Unit Tests
=============================================
Tests for the KMS abstraction layer (Phase 1 of VIP Vault hardening).
"""

import os
import sys
import unittest
import tempfile
import hashlib

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.kms.provider import KMSProvider
from core.kms.software_provider import SoftwareKMSProvider
from core.kms.registry import get_kms, set_kms, reset_kms


class TestKMSProviderInterface(unittest.TestCase):
    """Verify that SoftwareKMSProvider satisfies the abstract interface."""

    def test_is_subclass_of_kms_provider(self):
        self.assertTrue(issubclass(SoftwareKMSProvider, KMSProvider))

    def test_instantiation(self):
        provider = SoftwareKMSProvider()
        self.assertIsInstance(provider, KMSProvider)


class TestSoftwareKMSDerivation(unittest.TestCase):
    """Test key derivation via SoftwareKMSProvider."""

    def setUp(self):
        # Use low iterations for fast testing
        self.kms = SoftwareKMSProvider(iterations=1000)

    def test_derive_key_returns_32_bytes(self):
        key, salt = self.kms.derive_key("test-password")
        self.assertEqual(len(key), 32)
        self.assertEqual(len(salt), 32)

    def test_derive_key_deterministic_with_same_salt(self):
        key1, salt = self.kms.derive_key("password123")
        key2, _ = self.kms.derive_key("password123", salt=salt)
        self.assertEqual(key1, key2)

    def test_derive_key_different_with_different_password(self):
        key1, salt = self.kms.derive_key("password-A")
        key2, _ = self.kms.derive_key("password-B", salt=salt)
        self.assertNotEqual(key1, key2)

    def test_derive_key_different_with_different_salt(self):
        key1, salt1 = self.kms.derive_key("same-password")
        key2, salt2 = self.kms.derive_key("same-password")
        # Random salts should differ
        self.assertNotEqual(salt1, salt2)
        self.assertNotEqual(key1, key2)

    def test_derive_key_with_context_binding(self):
        key1, salt = self.kms.derive_key("password", context="device-A")
        key2, _ = self.kms.derive_key("password", salt=salt, context="device-B")
        self.assertNotEqual(key1, key2)


class TestSoftwareKMSEncryption(unittest.TestCase):
    """Test AES-256-GCM encrypt / decrypt cycle."""

    def setUp(self):
        self.kms = SoftwareKMSProvider(iterations=1000)

    def test_encrypt_decrypt_roundtrip(self):
        original = "Top secret VIP medical record: blood type A+"
        ciphertext, salt = self.kms.encrypt(original, "vault-password")
        decrypted = self.kms.decrypt(ciphertext, "vault-password", salt)
        self.assertEqual(original, decrypted)

    def test_ciphertext_is_not_plaintext(self):
        original = "Sensitive data"
        ciphertext, _ = self.kms.encrypt(original, "password")
        self.assertNotEqual(original, ciphertext)
        self.assertNotIn("Sensitive", ciphertext)

    def test_wrong_password_raises(self):
        original = "Confidential"
        ciphertext, salt = self.kms.encrypt(original, "correct-password")
        with self.assertRaises(ValueError):
            self.kms.decrypt(ciphertext, "wrong-password", salt)

    def test_tampered_ciphertext_raises(self):
        original = "Important"
        ciphertext, salt = self.kms.encrypt(original, "password")
        tampered = ciphertext[:-4] + "XXXX"
        with self.assertRaises(ValueError):
            self.kms.decrypt(tampered, "password", salt)

    def test_empty_string_roundtrip(self):
        ciphertext, salt = self.kms.encrypt("", "password")
        decrypted = self.kms.decrypt(ciphertext, "password", salt)
        self.assertEqual("", decrypted)

    def test_unicode_roundtrip(self):
        original = "VIP hasta kaydı: 日本語テスト 🏥🔐"
        ciphertext, salt = self.kms.encrypt(original, "unicode-pass")
        decrypted = self.kms.decrypt(ciphertext, "unicode-pass", salt)
        self.assertEqual(original, decrypted)


class TestSoftwareKMSDeviceId(unittest.TestCase):
    """Test device fingerprinting."""

    def setUp(self):
        self.kms = SoftwareKMSProvider()

    def test_device_id_is_string(self):
        did = self.kms.get_device_id()
        self.assertIsInstance(did, str)
        self.assertTrue(len(did) > 0)

    def test_device_id_is_stable(self):
        """Same instance returns same ID."""
        id1 = self.kms.get_device_id()
        id2 = self.kms.get_device_id()
        self.assertEqual(id1, id2)

    def test_verify_device_self(self):
        did = self.kms.get_device_id()
        self.assertTrue(self.kms.verify_device(did))

    def test_verify_device_mismatch(self):
        self.assertFalse(self.kms.verify_device("definitely-not-this-device"))


class TestSoftwareKMSSigningKey(unittest.TestCase):
    """Test signing key retrieval."""

    def setUp(self):
        self.kms = SoftwareKMSProvider()

    def test_signing_key_is_bytes(self):
        key = self.kms.get_signing_key()
        self.assertIsInstance(key, bytes)
        self.assertTrue(len(key) > 0)

    def test_signing_key_is_stable(self):
        key1 = self.kms.get_signing_key()
        key2 = self.kms.get_signing_key()
        self.assertEqual(key1, key2)


class TestKMSRegistry(unittest.TestCase):
    """Test the global KMS registry."""

    def setUp(self):
        reset_kms()

    def tearDown(self):
        reset_kms()

    def test_default_provider_is_software(self):
        os.environ.pop("KMS_PROVIDER", None)
        kms = get_kms()
        self.assertIsInstance(kms, SoftwareKMSProvider)

    def test_explicit_software_provider(self):
        os.environ["KMS_PROVIDER"] = "software"
        kms = get_kms()
        self.assertIsInstance(kms, SoftwareKMSProvider)
        os.environ.pop("KMS_PROVIDER", None)

    def test_set_kms_override(self):
        custom = SoftwareKMSProvider(iterations=100)
        set_kms(custom)
        self.assertIs(get_kms(), custom)

    def test_invalid_provider_raises(self):
        os.environ["KMS_PROVIDER"] = "nonexistent"
        with self.assertRaises(ValueError):
            get_kms()
        os.environ.pop("KMS_PROVIDER", None)


class TestBackwardCompatibility(unittest.TestCase):
    """
    Verify that core.security public API still works after KMS refactor.
    Every existing import must continue to resolve and function.
    """

    def test_get_device_id_works(self):
        from core.security import get_device_id
        did = get_device_id()
        self.assertIsInstance(did, str)
        self.assertTrue(len(did) > 0)

    def test_get_current_device_id_works(self):
        from core.security import get_current_device_id
        self.assertEqual(get_current_device_id(), get_current_device_id())

    def test_verify_device_access_works(self):
        from core.security import verify_device_access, get_device_id
        did = get_device_id()
        self.assertTrue(verify_device_access(did))

    def test_hash_verify_password(self):
        from core.security import hash_password, verify_password
        hashed = hash_password("TestPass@12345!")
        self.assertTrue(verify_password("TestPass@12345!", hashed))
        self.assertFalse(verify_password("wrong", hashed))

    def test_validate_password(self):
        from core.security import validate_password
        ok, _ = validate_password("SecurePass1!")
        self.assertTrue(ok)
        ok, msg = validate_password("short")
        self.assertFalse(ok)

    def test_encrypt_decrypt_data(self):
        from core.security import encrypt_data, decrypt_data
        ct, salt = encrypt_data("hello world", "pass")
        pt = decrypt_data(ct, "pass", salt)
        self.assertEqual(pt, "hello world")

    def test_get_encryption_key(self):
        from core.security import get_encryption_key
        key, salt = get_encryption_key("test-pass")
        self.assertEqual(len(key), 32)

    def test_signaturedata_and_verify(self):
        from core.security import signaturedata, verify_message, get_device_id
        did = get_device_id()
        sig = signaturedata("test message", did)
        self.assertTrue(verify_message("test message", sig, did))
        self.assertFalse(verify_message("tampered", sig, did))

    def test_get_private_key(self):
        from core.security import get_private_key
        key = get_private_key()
        self.assertIsInstance(key, bytes)

    def test_hash_verify_block_password(self):
        from core.security import hash_block_password, verify_block_password
        h = hash_block_password("BlockPass@2026!")
        self.assertTrue(verify_block_password("BlockPass@2026!", h))

    def test_password_policy_error_class(self):
        from core.security import PasswordPolicyError
        self.assertTrue(issubclass(PasswordPolicyError, ValueError))


if __name__ == "__main__":
    unittest.main()
