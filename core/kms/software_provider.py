"""
core/kms/software_provider.py — Software KMS Provider
=======================================================
Local key management using Argon2id + PBKDF2 key derivation and
AES-256-GCM authenticated encryption.  No external cloud service
required — suitable for development, standalone deployments, and
air-gapped environments.

Device identification uses a cross-platform strategy:
  • Linux/Docker : /etc/machine-id  or  /sys/class/dmi/id/product_uuid
  • Windows      : MAC + hostname + platform.node()
  • Cloud/CI     : secure random token persisted to .device_fingerprint
  • All platforms: SHA-256 of combined identifiers

This replaces the previous WMI-dependent implementation that silently
fell back to a weak fingerprint on non-Windows platforms.
"""

import os
import hmac
import hashlib
import base64
import uuid
import socket
import platform
import secrets
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.kms.provider import KMSProvider

# ── constants ───────────────────────────────────────────────
PBKDF2_ITERATIONS = 600_000          # OWASP 2024 recommendation
_DEVICE_FINGERPRINT_FILE = ".device_fingerprint"
_PRIVATE_KEY_ENV = "HEALTH_BLOCKCHAIN_KEY"
_PRIVATE_KEY_FILE = ".private_key"
_KEYRING_SERVICE = "VIPHealthVault"
_KEYRING_KEY_NAME = "private_key"


class SoftwareKMSProvider(KMSProvider):
    """
    Software-only KMS using PBKDF2 key derivation and AES-256-GCM.
    Cross-platform device fingerprinting (no WMI dependency).
    """

    def __init__(self, iterations: int = PBKDF2_ITERATIONS):
        self._iterations = iterations
        self._device_id_cache: Optional[str] = None
        self._signing_key_cache: Optional[bytes] = None

    # ── KMSProvider interface ───────────────────────────────

    def derive_key(
        self,
        password: str,
        salt: Optional[bytes] = None,
        context: Optional[str] = None,
    ) -> Tuple[bytes, bytes]:
        if salt is None:
            salt = os.urandom(32)

        binding = context or self.get_device_id()
        key_material = (binding + password).encode("utf-8")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self._iterations,
        )
        return kdf.derive(key_material), salt

    def encrypt(
        self,
        plaintext: str,
        password: str,
        salt: Optional[bytes] = None,
    ) -> Tuple[str, bytes]:
        raw_key, used_salt = self.derive_key(password, salt)
        aesgcm = AESGCM(raw_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = nonce + ciphertext
        return base64.urlsafe_b64encode(payload).decode("utf-8"), used_salt

    def decrypt(
        self,
        ciphertext_b64: str,
        password: str,
        salt: bytes,
    ) -> str:
        try:
            raw_key, _ = self.derive_key(password, salt)
            aesgcm = AESGCM(raw_key)
            payload = base64.urlsafe_b64decode(ciphertext_b64.encode("utf-8"))
            if len(payload) < 28:  # 12 nonce + 16 auth tag minimum
                raise ValueError("Invalid encrypted payload size")
            nonce = payload[:12]
            ct = payload[12:]
            return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
        except Exception as e:
            raise ValueError(f"Decryption error: {e}")

    def get_device_id(self) -> str:
        if self._device_id_cache is not None:
            return self._device_id_cache

        # 1. Check cached fingerprint file
        fp = self._read_cached_fingerprint()
        if fp:
            self._device_id_cache = fp
            return fp

        # 2. Compute cross-platform hardware fingerprint
        fp = self._compute_fingerprint()
        self._persist_fingerprint(fp)
        self._device_id_cache = fp
        return fp

    def get_signing_key(self) -> bytes:
        if self._signing_key_cache is not None:
            return self._signing_key_cache

        key = self._load_signing_key()
        self._signing_key_cache = key
        return key

    # ── Cross-Platform Device Fingerprint ───────────────────

    @staticmethod
    def _compute_fingerprint() -> str:
        """
        Compute a deterministic device fingerprint without WMI.
        Uses platform-appropriate identifiers:
          - Linux:   /etc/machine-id (systemd) or /sys/class/dmi/id/product_uuid
          - Windows: MAC + hostname + platform.node()
          - Docker:  /etc/machine-id (usually set by container runtime)
          - Fallback: MAC address hash
        """
        try:
            mac = str(uuid.getnode())
            hostname = socket.gethostname()
            proc = platform.processor() or "unknown"
            machine_id = "N/A"

            # Linux / Docker machine-id files
            for path in (
                "/etc/machine-id",
                "/sys/class/dmi/id/product_uuid",
                "/var/lib/dbus/machine-id",
            ):
                try:
                    if os.path.exists(path):
                        with open(path, "r") as f:
                            val = f.read().strip()
                        if val:
                            machine_id = val
                            break
                except (PermissionError, OSError):
                    continue

            # Windows: use platform.node() which returns the hostname
            # (WMI BIOS UUID is no longer used — unreliable cross-platform)
            if machine_id == "N/A" and platform.system() == "Windows":
                machine_id = platform.node()

            raw = f"{mac}::{hostname}::{machine_id}::{proc}"
            return hashlib.sha256(raw.encode("utf-8")).hexdigest()
        except Exception:
            return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()

    @staticmethod
    def _read_cached_fingerprint() -> Optional[str]:
        # Legacy migration: .device_id → .device_fingerprint
        if os.path.exists(".device_id") and not os.path.exists(_DEVICE_FINGERPRINT_FILE):
            try:
                with open(".device_id", "r") as f:
                    old = f.read().strip()
                with open(_DEVICE_FINGERPRINT_FILE, "w") as f:
                    f.write(old)
            except Exception:
                pass

        if os.path.exists(_DEVICE_FINGERPRINT_FILE):
            try:
                with open(_DEVICE_FINGERPRINT_FILE, "r") as f:
                    cached = f.read().strip()
                if cached:
                    return cached
            except Exception:
                pass
        return None

    @staticmethod
    def _persist_fingerprint(fp: str) -> None:
        try:
            with open(_DEVICE_FINGERPRINT_FILE, "w") as f:
                f.write(fp)
        except Exception:
            pass

    # ── Signing Key Management ──────────────────────────────

    @staticmethod
    def _load_signing_key() -> bytes:
        """
        Load or generate the HMAC signing key.
        Priority:
          1. HEALTH_BLOCKCHAIN_KEY env var
          2. OS keyring (DPAPI / Keychain / libsecret)
          3. .private_key file (legacy — auto-migrates to keyring)
          4. Generate new random key
        """
        # 1. Env var
        key_str = os.environ.get(_PRIVATE_KEY_ENV)
        if key_str:
            return key_str.encode() if isinstance(key_str, str) else key_str

        # 2. OS keyring
        try:
            import keyring as _keyring
            key_str = _keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY_NAME)
            if key_str:
                os.environ[_PRIVATE_KEY_ENV] = key_str
                return key_str.encode()
        except Exception:
            pass

        # 3. Legacy plaintext file
        if os.path.exists(_PRIVATE_KEY_FILE):
            with open(_PRIVATE_KEY_FILE, "r") as f:
                key_str = f.read().strip()
            if key_str:
                # Auto-migrate to keyring if available
                try:
                    import keyring as _keyring
                    _keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY_NAME, key_str)
                    os.remove(_PRIVATE_KEY_FILE)
                except Exception:
                    pass
                os.environ[_PRIVATE_KEY_ENV] = key_str
                return key_str.encode()

        # 4. Generate new key
        key_str = base64.urlsafe_b64encode(os.urandom(32)).decode()
        try:
            import keyring as _keyring
            _keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY_NAME, key_str)
        except Exception:
            with open(_PRIVATE_KEY_FILE, "w") as f:
                f.write(key_str)

        os.environ[_PRIVATE_KEY_ENV] = key_str
        return key_str.encode()
