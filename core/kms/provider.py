"""
core/kms/provider.py — Abstract Key Management Service Interface
==================================================================
Defines the contract for all KMS providers.  Every cryptographic key
operation in the vault flows through this interface so the underlying
backend can be swapped without touching business logic.

Supported backends (via concrete subclasses):
  • SoftwareKMSProvider  — local Argon2id + PBKDF2 derivation (dev / standalone)
  • CloudKMSProvider     — AWS KMS / Azure Key Vault / HashiCorp Vault (production)
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple


class KMSProvider(ABC):
    """
    Abstract base class for Key Management Service providers.

    Every concrete provider must implement:
      • derive_key     — deterministic key derivation from password + context
      • encrypt        — authenticated encryption (AES-256-GCM)
      • decrypt        — authenticated decryption
      • get_device_id  — stable, cross-platform device/environment identifier
      • get_signing_key — key material for HMAC block signatures
    """

    @abstractmethod
    def derive_key(
        self,
        password: str,
        salt: Optional[bytes] = None,
        context: Optional[str] = None,
    ) -> Tuple[bytes, bytes]:
        """
        Derive a 256-bit symmetric key from a password.

        Args:
            password: user-supplied passphrase
            salt:     optional 32-byte salt (generated if None)
            context:  optional binding context (e.g. device_id, patient_id)

        Returns:
            (raw_key_32_bytes, salt_used)
        """
        ...

    @abstractmethod
    def encrypt(
        self,
        plaintext: str,
        password: str,
        salt: Optional[bytes] = None,
    ) -> Tuple[str, bytes]:
        """
        Encrypt plaintext with AES-256-GCM.

        Returns:
            (ciphertext_base64, salt_used)
        """
        ...

    @abstractmethod
    def decrypt(
        self,
        ciphertext_b64: str,
        password: str,
        salt: bytes,
    ) -> str:
        """
        Decrypt AES-256-GCM ciphertext.

        Raises:
            ValueError on authentication failure or corrupted data.
        """
        ...

    @abstractmethod
    def get_device_id(self) -> str:
        """
        Return a stable identifier for the current device / environment.
        Must be deterministic on the same host and cross-platform
        (Windows, Linux, Docker, cloud).
        """
        ...

    @abstractmethod
    def get_signing_key(self) -> bytes:
        """
        Return the HMAC signing key used for blockchain block signatures.
        """
        ...

    # ── convenience helpers (non-abstract) ──────────────────────

    def verify_device(self, stored_device_id: str) -> bool:
        """Check whether this environment matches a stored device id."""
        return stored_device_id == self.get_device_id()
