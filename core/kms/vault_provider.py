"""
core/kms/vault_provider.py — HashiCorp Vault Transit KMS provider
=================================================================
Holds the vault's signing key in HashiCorp Vault's Transit secrets engine so the
key never enters this process. Every key-using operation the application needs is
a MAC over some context (block signatures, the notarizer anchor, and the at-rest
key derivation all go through ``KMSProvider.mac``), so this provider implements
``mac`` by calling Vault's ``/v1/transit/hmac/:key/sha2-256`` endpoint — Vault
computes the HMAC inside its own boundary and returns only the result.

This closes the "a rogue admin has both the database and the key" gap: an operator
with the ``projects/`` store and this host still cannot forge a signature or derive
an at-rest key, because the root key lives in Vault under a separate token/policy.

Local AES-at-rest and password operations (``encrypt`` / ``decrypt`` /
``derive_key``) and the device id are delegated to a composed software provider.
They never touch the root key — they operate on the *derived* scoped secret that
``derive_rest_secret`` obtains through ``mac`` — so delegating them locally is safe.

Configuration (environment):
  • VAULT_ADDR             — e.g. https://vault.internal:8200
  • VAULT_TOKEN            — a token whose policy allows transit/hmac on the key
  • VHV_KMS_TRANSIT_KEY    — transit key name (default "vhv-signing")
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple

from core.kms.provider import KMSProvider
from core.kms.software_provider import SoftwareKMSProvider


class VaultKMSError(Exception):
    """Raised when a Vault Transit operation fails. Never falls back to a local key."""


def _require_http_url(url: str) -> str:
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise VaultKMSError(
            f"VAULT_ADDR must be an http(s) URL, got {scheme or 'no'} scheme: {url!r}"
        )
    return url


class VaultTransitKMSProvider(KMSProvider):
    """Signing key held in Vault Transit; the key never reaches this process."""

    def __init__(
        self,
        addr: Optional[str] = None,
        token: Optional[str] = None,
        key_name: Optional[str] = None,
        timeout: float = 5.0,
    ):
        addr = (addr if addr is not None else os.getenv("VAULT_ADDR", "")).rstrip("/")
        if not addr:
            raise VaultKMSError("VAULT_ADDR is required for the Vault Transit KMS provider")
        self._addr = _require_http_url(addr)

        self._token = token if token is not None else os.getenv("VAULT_TOKEN", "")
        if not self._token:
            raise VaultKMSError("VAULT_TOKEN is required for the Vault Transit KMS provider")

        self._key = key_name or os.getenv("VHV_KMS_TRANSIT_KEY", "vhv-signing")
        self._timeout = timeout
        # Local provider for AES/password/device operations only — never the root key.
        self._local = SoftwareKMSProvider()

    # ── the one key-using primitive, performed inside Vault ──────────────
    def mac(self, message: bytes) -> bytes:
        url = f"{self._addr}/v1/transit/hmac/{self._key}/sha2-256"
        body = json.dumps(
            {"input": base64.b64encode(message).decode("ascii")}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"X-Vault-Token": self._token, "Content-Type": "application/json"},
        )
        try:
            # Scheme restricted to http(s) by _require_http_url in __init__.
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # nosec B310
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            # Fail closed: a broken Vault must stop signing, never sign locally.
            raise VaultKMSError(f"Vault Transit hmac call failed: {e}")

        hmac_str = payload.get("data", {}).get("hmac", "")
        # Vault returns "vault:v1:<base64>"; take the trailing base64 payload.
        prefix, _, encoded = hmac_str.rpartition(":")
        if not prefix or not encoded:
            raise VaultKMSError(f"Unexpected Vault hmac response: {hmac_str!r}")
        try:
            return base64.b64decode(encoded)
        except Exception:
            raise VaultKMSError(f"Vault hmac payload is not valid base64: {encoded!r}")

    def get_signing_key(self) -> bytes:
        raise NotImplementedError(
            "The signing key is held in Vault Transit and never leaves it; use mac()."
        )

    # ── local delegations (operate on derived secrets, not the root key) ──
    def derive_key(
        self, password: str, salt: Optional[bytes] = None, context: Optional[str] = None
    ) -> Tuple[bytes, bytes]:
        return self._local.derive_key(password, salt, context)

    def encrypt(
        self, plaintext: str, password: str, salt: Optional[bytes] = None
    ) -> Tuple[str, bytes]:
        return self._local.encrypt(plaintext, password, salt)

    def decrypt(self, ciphertext_b64: str, password: str, salt: bytes) -> str:
        return self._local.decrypt(ciphertext_b64, password, salt)

    def get_device_id(self) -> str:
        return self._local.get_device_id()
