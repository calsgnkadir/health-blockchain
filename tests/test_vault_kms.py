"""
tests/test_vault_kms.py — externally-held signing key via Vault Transit
=======================================================================
The Vault provider computes every MAC by calling Vault's /transit/hmac endpoint,
so the signing key never enters this process. These tests run against a fake Vault
HTTP endpoint (no live server): they prove the remote-MAC path signs and verifies,
that the provider never needs local key material, and that a broken Vault fails
closed rather than silently signing with a local key.
"""

import base64
import hashlib
import hmac
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.kms.vault_provider import VaultTransitKMSProvider, VaultKMSError

# The "key" only the fake Vault knows — it stands in for key material held inside
# Vault. The provider under test never sees it.
_FAKE_VAULT_KEY = b"fake-vault-transit-root-key-do-not-leak"


def _fake_vault_hmac(message: bytes) -> bytes:
    return hmac.new(_FAKE_VAULT_KEY, message, hashlib.sha256).digest()


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _make_fake_urlopen(recorder=None):
    def fake_urlopen(req, timeout=None):
        if recorder is not None:
            recorder["url"] = req.full_url
            recorder["token"] = req.headers.get("X-vault-token")
        body = json.loads(req.data.decode("utf-8"))
        message = base64.b64decode(body["input"])
        digest = _fake_vault_hmac(message)
        payload = {"data": {"hmac": "vault:v1:" + base64.b64encode(digest).decode("ascii")}}
        return _FakeResponse(json.dumps(payload).encode("utf-8"))
    return fake_urlopen


class TestVaultTransitKMS(unittest.TestCase):
    def _provider(self):
        return VaultTransitKMSProvider(
            addr="https://vault.internal:8200", token="s.faketoken", key_name="vhv-signing"
        )

    def test_requires_addr_and_token(self):
        with self.assertRaises(VaultKMSError):
            VaultTransitKMSProvider(addr="", token="t")
        with self.assertRaises(VaultKMSError):
            VaultTransitKMSProvider(addr="https://vault:8200", token="")

    def test_mac_is_computed_by_vault(self):
        rec = {}
        with mock.patch("urllib.request.urlopen", _make_fake_urlopen(rec)):
            out = self._provider().mac(b"block-hash-payload")
        self.assertEqual(out, _fake_vault_hmac(b"block-hash-payload"))
        self.assertEqual(rec["url"], "https://vault.internal:8200/v1/transit/hmac/vhv-signing/sha2-256")
        self.assertEqual(rec["token"], "s.faketoken")

    def test_signing_key_is_never_exposed(self):
        with self.assertRaises(NotImplementedError):
            self._provider().get_signing_key()

    def test_sign_and_verify_roundtrip_through_vault(self):
        from core.kms.registry import set_kms, reset_kms
        from core.security import signaturedata, verify_message
        provider = self._provider()
        try:
            with mock.patch("urllib.request.urlopen", _make_fake_urlopen()):
                set_kms(provider)
                sig = signaturedata("attestation-message")
                self.assertTrue(verify_message("attestation-message", sig))
                self.assertFalse(verify_message("tampered-message", sig))
        finally:
            reset_kms()

    def test_fails_closed_when_vault_unreachable(self):
        import urllib.error
        from core.kms.registry import set_kms, reset_kms
        from core.security import signaturedata

        def boom(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        provider = self._provider()
        with mock.patch("urllib.request.urlopen", boom):
            with self.assertRaises(VaultKMSError):
                provider.mac(b"x")
            try:
                set_kms(provider)
                # No silent local fallback: signing must raise, not succeed.
                with self.assertRaises(VaultKMSError):
                    signaturedata("m")
            finally:
                reset_kms()


if __name__ == "__main__":
    unittest.main()
