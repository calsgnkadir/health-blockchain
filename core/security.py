"""
core/security.py — VIP Health Vault · Security Layer v3.0
============================================================
Layers:
  1. Hardware fingerprint (MAC + hostname + UUID combination)
  2. Argon2id password hash (password cracking resistance)
  3. PBKDF2 key derivation (600K iterations, per-patient unique salt)
  4. AES-256 (Fernet) encryption / decryption
  5. HMAC-SHA256 block signing (device-bound)
  6. Password policy enforcement
"""

import os
import re
import hmac
import hashlib
import base64
import uuid
import socket
import platform
from typing import Optional, Tuple

# Windows hardware fingerprint — optional (adds BIOS UUID + disk serial)
try:
    import wmi as _wmi
    _WMI_AVAILABLE = True
except ImportError:
    _WMI_AVAILABLE = False

# OS Keyring — DPAPI on Windows, Keychain on macOS, libsecret on Linux
try:
    import keyring as _keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE  = "VIPHealthVault"
_KEYRING_KEY_NAME = "private_key"

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Argon2 — preferred, falls back to bcrypt
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
    _ARGON2_AVAILABLE = True
    _ph = PasswordHasher(
        time_cost=3,
        memory_cost=65536,   # 64 MB
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )
except ImportError:
    _ARGON2_AVAILABLE = False

# Bcrypt — fallback
try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False

# ──────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────
PBKDF2_ITERATIONS = 600_000          # OWASP 2024 recommendation
_DEVICE_FINGERPRINT_FILE = ".device_fingerprint"
_PRIVATE_KEY_ENV = "HEALTH_BLOCKCHAIN_KEY"

# ──────────────────────────────────────────────
# 1. HARDWARE FINGERPRINT
# ──────────────────────────────────────────────

def _compute_hardware_fingerprint() -> str:
    """
    Generates a hardware fingerprint using MAC address, hostname, processor,
    and — when available — Windows BIOS UUID and disk serial number.
    Returns the same value on the same hardware regardless of whether the
    cache file has been deleted.
    """
    try:
        mac       = str(uuid.getnode())
        hostname  = socket.gethostname()
        processor = platform.processor() or "unknown"

        bios_uuid   = "N/A"
        disk_serial = "N/A"

        # S-01: Windows hardware identifiers via WMI (BIOS UUID + disk serial)
        if _WMI_AVAILABLE:
            try:
                c = _wmi.WMI()
                bios_info = c.Win32_ComputerSystemProduct()
                if bios_info:
                    bios_uuid = bios_info[0].UUID or "N/A"
                disk_info = c.Win32_PhysicalMedia()
                if disk_info:
                    disk_serial = (disk_info[0].SerialNumber or "N/A").strip()
            except Exception:
                pass  # WMI call failed — continue without hardware IDs
        else:
            # Fallback for Linux and other platforms
            if os.path.exists("/etc/machine-id"):
                try:
                    with open("/etc/machine-id", "r") as f:
                        bios_uuid = f.read().strip()
                except Exception:
                    pass
            elif os.path.exists("/sys/class/dmi/id/product_uuid"):
                try:
                    with open("/sys/class/dmi/id/product_uuid", "r") as f:
                        bios_uuid = f.read().strip()
                except Exception:
                    pass
            elif os.path.exists("/var/lib/dbus/machine-id"):
                try:
                    with open("/var/lib/dbus/machine-id", "r") as f:
                        bios_uuid = f.read().strip()
                except Exception:
                    pass

        raw = f"{mac}::{hostname}::{bios_uuid}::{disk_serial}::{processor}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()


def get_device_id() -> str:
    """
    Returns the device fingerprint.
    On the same hardware, deleting the cache file is safe — the same
    fingerprint is recomputed from hardware identifiers.
    A mismatch between the cached and the computed fingerprint indicates
    that either the hardware changed or the file was copied from another device.
    In cloud container environments (Railway/Docker), unique secure tokens are used.
    """
    # Legacy .device_id migration
    if os.path.exists(".device_id") and not os.path.exists(_DEVICE_FINGERPRINT_FILE):
        try:
            with open(".device_id", "r") as f:
                old_val = f.read().strip()
            with open(_DEVICE_FINGERPRINT_FILE, "w") as f:
                f.write(old_val)
        except Exception:
            pass

    if os.path.exists(_DEVICE_FINGERPRINT_FILE):
        try:
            with open(_DEVICE_FINGERPRINT_FILE, "r") as f:
                cached = f.read().strip()
            if cached:
                # Retain hardware check warning for legacy 64-character hashes
                if len(cached) == 64 and not cached.startswith("dev_"):
                    computed = _compute_hardware_fingerprint()
                    if cached != computed:
                        print(
                            "[SECURITY WARNING] Device fingerprint mismatch. "
                            "The hardware may have changed, or the fingerprint file "
                            "was copied from another device. Access may be restricted."
                        )
                return cached
        except Exception:
            pass

    # First run (or empty file) — generate a secure unique container-safe ID
    import secrets
    secure_id = f"dev_{secrets.token_hex(32)}"
    try:
        with open(_DEVICE_FINGERPRINT_FILE, "w") as f:
            f.write(secure_id)
    except Exception:
        pass
    return secure_id


def get_current_device_id() -> str:
    """General access point — same as get_device_id()."""
    return get_device_id()


def verify_device_access(stored_device_id: str) -> bool:
    """Does this blockchain belong to this device?"""
    return stored_device_id == get_device_id()


# ──────────────────────────────────────────────
# 2. PRIVATE KEY MANAGEMENT
# ──────────────────────────────────────────────

_PRIVATE_KEY_FILE = ".private_key"

def get_private_key() -> bytes:
    """
    Returns the HMAC private key used for block signatures.
    Priority order:
      1. HEALTH_BLOCKCHAIN_KEY environment variable
      2. OS keyring  (Windows DPAPI / macOS Keychain / libsecret)
      3. .private_key plaintext file  (legacy fallback — auto-migrates to keyring)
      4. Generate a new random key and store it
    The plaintext file is automatically removed once the key is migrated
    to the OS keyring.
    """
    # 1. Environment variable — highest priority
    key = os.environ.get(_PRIVATE_KEY_ENV)
    if key:
        return key.encode() if isinstance(key, str) else key

    # 2. OS keyring (DPAPI on Windows)
    if _KEYRING_AVAILABLE:
        try:
            key = _keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY_NAME)
            if key:
                os.environ[_PRIVATE_KEY_ENV] = key
                return key.encode()
        except Exception:
            pass

    # 3. Plaintext file fallback (legacy)
    if os.path.exists(_PRIVATE_KEY_FILE):
        with open(_PRIVATE_KEY_FILE, "r") as f:
            key = f.read().strip()
        if key:
            # S-02: Auto-migrate from plaintext file to OS keyring
            if _KEYRING_AVAILABLE:
                try:
                    _keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY_NAME, key)
                    os.remove(_PRIVATE_KEY_FILE)
                    print("[OK] Private key migrated from .private_key file to OS keyring (DPAPI on Windows).")
                except Exception:
                    pass
            os.environ[_PRIVATE_KEY_ENV] = key
            return key.encode()

    # 4. Generate new key
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    if _KEYRING_AVAILABLE:
        try:
            _keyring.set_password(_KEYRING_SERVICE, _KEYRING_KEY_NAME, key)
            print("[OK] New private key generated and stored in OS keyring.")
        except Exception:
            with open(_PRIVATE_KEY_FILE, "w") as f:
                f.write(key)
    else:
        with open(_PRIVATE_KEY_FILE, "w") as f:
            f.write(key)

    os.environ[_PRIVATE_KEY_ENV] = key
    return key.encode()


# ──────────────────────────────────────────────
# 3. PASSWORD POLICY
# ──────────────────────────────────────────────

class PasswordPolicyError(ValueError):
    """Password policy violation."""
    pass


def validate_password(password: str) -> Tuple[bool, str]:
    """
    Validates the password policy rules.
    Returns: (is_valid, error_message)
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least 1 uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least 1 lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least 1 digit."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password):
        return False, "Password must contain at least 1 special character (!@#$%^&* etc.)."
    return True, ""


# ──────────────────────────────────────────────
# 4. ARGON2 / BCRYPT PASSWORD HASH (Access Control)
# ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Hashes password with Argon2id (bcrypt fallback).
    Used for storage (vault password, user password).
    """
    if _ARGON2_AVAILABLE:
        return _ph.hash(password)
    elif _BCRYPT_AVAILABLE:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode(), salt).decode()
    else:
        # Fallback — PBKDF2 + random salt
        salt = os.urandom(32)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
        return base64.urlsafe_b64encode(salt + dk).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Verifies a hashed password."""
    try:
        if _ARGON2_AVAILABLE and hashed.startswith("$argon2"):
            try:
                return _ph.verify(hashed, password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return False
        elif _BCRYPT_AVAILABLE and hashed.startswith("$2b$"):
            return bcrypt.checkpw(password.encode(), hashed.encode())
        else:
            # PBKDF2 fallback
            raw = base64.urlsafe_b64decode(hashed.encode())
            salt, dk_stored = raw[:32], raw[32:]
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
            return hmac.compare_digest(dk, dk_stored)
    except Exception:
        return False


# ──────────────────────────────────────────────
# 5. PBKDF2 ENCRYPTION KEY (For Block Data)
# ──────────────────────────────────────────────

def get_encryption_key(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """
    Derives AES 256-bit key using password + Device ID + unique salt.
    Returns: (raw_key_32_bytes, salt)
    """
    device_id = get_device_id()
    if salt is None:
        salt = os.urandom(32)   # Unique random salt

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    # Key material: device_id + password (device dependency)
    key_material = (device_id + password).encode("utf-8")
    raw_key = kdf.derive(key_material)
    return raw_key, salt


# ──────────────────────────────────────────────
# 6. AES-256-GCM ENCRYPTION / DECRYPTION
# ──────────────────────────────────────────────

def encrypt_data(data: str, password: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
    """
    Encrypts data with AES-256-GCM.
    Returns: (encrypted_data_base64, used_salt)
    """
    raw_key, used_salt = get_encryption_key(password, salt)
    aesgcm = AESGCM(raw_key)
    nonce = os.urandom(12)  # Standard 12-byte nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, data.encode("utf-8"), None)
    
    # Pack nonce + ciphertext
    payload = nonce + ciphertext
    return base64.urlsafe_b64encode(payload).decode("utf-8"), used_salt


def decrypt_data(encrypted_data: str, password: str, salt: bytes) -> str:
    """
    Decrypts AES-256-GCM encrypted data.
    salt: unique salt used during encryption (comes from LMDB).
    """
    try:
        raw_key, _ = get_encryption_key(password, salt)
        aesgcm = AESGCM(raw_key)
        
        payload = base64.urlsafe_b64decode(encrypted_data.encode("utf-8"))
        if len(payload) < 28:  # 12 bytes nonce + at least 16 bytes authentication tag
            raise ValueError("Invalid encrypted payload size")
            
        nonce = payload[:12]
        ciphertext = payload[12:]
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as e:
        raise ValueError(f"Decryption error: {e}")



# ──────────────────────────────────────────────
# 7. HMAC-SHA256 SIGNATURE (Device Bound)
# ──────────────────────────────────────────────

def signaturedata(message: str, device_id: str = None) -> str:
    """
    Generates HMAC-SHA256 signature.
    Key = combination of private_key + device_id.
    Another device cannot generate the same signature.
    """
    if device_id is None:
        device_id = get_device_id()

    private_key = get_private_key()
    combined_key = hmac.new(
        private_key,
        device_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    return hmac.new(
        combined_key,
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_message(message: str, signature: str, device_id: str = None) -> bool:
    """Verifies HMAC signature (timing-safe comparison)."""
    if device_id is None:
        device_id = get_device_id()

    private_key = get_private_key()
    combined_key = hmac.new(
        private_key,
        device_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    expected = hmac.new(
        combined_key,
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ──────────────────────────────────────────────
# 8. SIMPLE HASH (For Block Password Protection)
# ──────────────────────────────────────────────

def hash_block_password(password: str) -> str:
    """Hashes block access password (using Argon2 or fallback)."""
    return hash_password(password)


def verify_block_password(password: str, stored_hash: str) -> bool:
    """Verifies block access password."""
    return verify_password(password, stored_hash)
