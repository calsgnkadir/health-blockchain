"""
core/kms/cloud_stub.py — Cloud KMS Provider Stubs
===================================================
Integration stubs for production-grade key management services.
Each stub raises NotImplementedError with clear guidance on what
needs to be configured for production deployment.

Supported targets:
  • AWS KMS           — envelope encryption with CMK
  • Azure Key Vault   — managed HSM-backed keys
  • HashiCorp Vault   — Transit secrets engine
"""

import os
from typing import Optional, Tuple

from core.kms.provider import KMSProvider


class AWSKMSProvider(KMSProvider):
    """
    AWS KMS integration stub.

    Production setup requires:
      - AWS_KMS_KEY_ID environment variable (CMK ARN)
      - boto3 SDK installed
      - IAM role with kms:Encrypt, kms:Decrypt, kms:GenerateDataKey
    """

    def __init__(self):
        self._key_id = os.environ.get("AWS_KMS_KEY_ID")
        if not self._key_id:
            raise EnvironmentError(
                "AWS_KMS_KEY_ID environment variable is required. "
                "Set it to the ARN of your Customer Master Key."
            )

    def derive_key(self, password: str, salt: Optional[bytes] = None,
                   context: Optional[str] = None) -> Tuple[bytes, bytes]:
        raise NotImplementedError(
            "AWS KMS derive_key: Use boto3 kms.generate_data_key_without_plaintext() "
            "with encryption context for password-independent key derivation."
        )

    def encrypt(self, plaintext: str, password: str,
                salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        raise NotImplementedError(
            "AWS KMS encrypt: Use boto3 kms.encrypt() with the CMK ARN. "
            "For large payloads, use envelope encryption via generate_data_key()."
        )

    def decrypt(self, ciphertext_b64: str, password: str,
                salt: bytes) -> str:
        raise NotImplementedError(
            "AWS KMS decrypt: Use boto3 kms.decrypt() with the CMK ARN."
        )

    def get_device_id(self) -> str:
        # In AWS, use instance identity document or ECS task metadata
        return os.environ.get("AWS_INSTANCE_ID", f"aws-{os.environ.get('HOSTNAME', 'unknown')}")

    def get_signing_key(self) -> bytes:
        raise NotImplementedError(
            "AWS KMS get_signing_key: Use kms.sign() with an asymmetric CMK "
            "or retrieve a data key via generate_data_key()."
        )


class HashiCorpVaultProvider(KMSProvider):
    """
    HashiCorp Vault Transit Engine integration stub.

    Production setup requires:
      - VAULT_ADDR environment variable (e.g. https://vault.example.com:8200)
      - VAULT_TOKEN or VAULT_ROLE_ID + VAULT_SECRET_ID for AppRole auth
      - hvac Python SDK installed
      - Transit secrets engine enabled with a named key
    """

    def __init__(self):
        self._addr = os.environ.get("VAULT_ADDR")
        if not self._addr:
            raise EnvironmentError(
                "VAULT_ADDR environment variable is required. "
                "Set it to your Vault server address."
            )

    def derive_key(self, password: str, salt: Optional[bytes] = None,
                   context: Optional[str] = None) -> Tuple[bytes, bytes]:
        raise NotImplementedError(
            "Vault derive_key: Use Transit engine's /transit/datakey/plaintext/:name "
            "endpoint to generate a data encryption key."
        )

    def encrypt(self, plaintext: str, password: str,
                salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        raise NotImplementedError(
            "Vault encrypt: Use Transit engine's /transit/encrypt/:name endpoint."
        )

    def decrypt(self, ciphertext_b64: str, password: str,
                salt: bytes) -> str:
        raise NotImplementedError(
            "Vault decrypt: Use Transit engine's /transit/decrypt/:name endpoint."
        )

    def get_device_id(self) -> str:
        return os.environ.get("VAULT_CLIENT_ID", f"vault-{os.environ.get('HOSTNAME', 'unknown')}")

    def get_signing_key(self) -> bytes:
        raise NotImplementedError(
            "Vault get_signing_key: Use Transit engine's /transit/sign/:name endpoint "
            "for HMAC operations."
        )


def get_cloud_provider(provider_name: str) -> KMSProvider:
    """
    Factory function to instantiate cloud KMS providers.

    Args:
        provider_name: "aws" | "vault" | "azure"

    Returns:
        Configured KMSProvider instance.
    """
    providers = {
        "aws": AWSKMSProvider,
        "vault": HashiCorpVaultProvider,
    }
    cls = providers.get(provider_name.lower())
    if cls is None:
        raise ValueError(
            f"Unknown cloud KMS provider: '{provider_name}'. "
            f"Supported: {list(providers.keys())}"
        )
    return cls()
