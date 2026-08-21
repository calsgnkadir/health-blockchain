"""
core/kms/registry.py — KMS Provider Registry (Singleton)
==========================================================
Central access point for the active KMS provider.  All modules in the
codebase should call ``get_kms()`` instead of directly instantiating
providers or calling raw crypto functions.

Configuration:
  • KMS_PROVIDER env var:  "software" (default) | "aws" | "vault"
"""

import os
from typing import Optional

from core.kms.provider import KMSProvider
from core.kms.software_provider import SoftwareKMSProvider

_active_provider: Optional[KMSProvider] = None


def get_kms() -> KMSProvider:
    """
    Return the globally-configured KMS provider.
    Lazily initialized on first call based on KMS_PROVIDER env var.
    """
    global _active_provider
    if _active_provider is not None:
        return _active_provider

    provider_name = os.environ.get("KMS_PROVIDER", "software").lower()

    if provider_name == "software":
        _active_provider = SoftwareKMSProvider()
    elif provider_name == "vault":
        # Externally-held signing key: the root key stays in HashiCorp Vault's
        # Transit engine and never enters this process (see vault_provider).
        from core.kms.vault_provider import VaultTransitKMSProvider
        _active_provider = VaultTransitKMSProvider()
    elif provider_name == "aws":
        from core.kms.cloud_stub import get_cloud_provider
        _active_provider = get_cloud_provider(provider_name)
    else:
        raise ValueError(
            f"Unknown KMS_PROVIDER='{provider_name}'. "
            f"Supported: software, aws, vault"
        )

    return _active_provider


def set_kms(provider: KMSProvider) -> None:
    """
    Override the active KMS provider (useful for testing).
    """
    global _active_provider
    _active_provider = provider


def reset_kms() -> None:
    """
    Reset the provider so the next get_kms() call re-initializes.
    """
    global _active_provider
    _active_provider = None
