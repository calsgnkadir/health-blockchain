import os
import hmac
import hashlib
import base64
import uuid
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Device ID - Unique ID for each device
def get_device_id():
    """Creates a unique ID for each device or returns the existing one"""
    device_id_file = ".device_id"
    
    if os.path.exists(device_id_file):
        with open(device_id_file, "r") as f:
            return f.read().strip()
    else:
        # Create new device ID
        device_id = str(uuid.uuid4())
        with open(device_id_file, "w") as f:
            f.write(device_id)
        return device_id

# Private Key Management - Reads from environment variable
def get_private_key():
    """Reads private key from environment variable, creates one if not found"""
    key = os.environ.get("HEALTH_BLOCKCHAIN_KEY")
    
    if not key:
        # First use - create key and notify user
        key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        print("\n" + "="*60)
        print("⚠️  SECURITY WARNING")
        print("="*60)
        print("Private key not found. A new key has been created.")
        print("\nPlease set the following environment variable:")
        print(f"Windows PowerShell:")
        print(f'  $env:HEALTH_BLOCKCHAIN_KEY="{key}"')
        print(f"\nWindows CMD:")
        print(f'  set HEALTH_BLOCKCHAIN_KEY={key}')
        print(f"\nLinux/Mac:")
        print(f'  export HEALTH_BLOCKCHAIN_KEY="{key}"')
        print("\n⚠️  Keep this key in a SECURE location!")
        print("="*60 + "\n")
        
        # Temporarily use for this session
        os.environ["HEALTH_BLOCKCHAIN_KEY"] = key
    
    return key.encode() if isinstance(key, str) else key

# Encryption Key - Derived from Device ID and user password
def get_encryption_key(password: str = None):
    """Creates encryption key (from device ID + password)"""
    device_id = get_device_id()
    
    if password is None:
        # If no password, derive from device ID
        password = device_id
    
    # Derive key using PBKDF2
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'health_blockchain_salt',
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive((device_id + password).encode()))
    return key

# Encryption Functions
def encrypt_data(data: str, password: str = None) -> str:
    """Encrypts data using AES-256"""
    key = get_encryption_key(password)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(data.encode())
    return base64.urlsafe_b64encode(encrypted).decode()

def decrypt_data(encrypted_data: str, password: str = None) -> str:
    """Decrypts encrypted data"""
    try:
        key = get_encryption_key(password)
        fernet = Fernet(key)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        raise ValueError(f"Decryption error: {e}")

# HMAC Signature Functions (updated)
def signaturedata(message: str, device_id: str = None) -> str:
    """Creates HMAC-SHA256 signature (with device ID)"""
    if device_id is None:
        device_id = get_device_id()
    
    private_key = get_private_key()
    # Add device ID to key (device-based signature)
    combined_key = hmac.new(
        private_key,
        device_id.encode(),
        hashlib.sha256
    ).digest()
    
    signature = hmac.new(
        combined_key,
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature

def verify_message(message: str, signature: str, device_id: str = None) -> bool:
    """Verifies signature (with device ID)"""
    if device_id is None:
        device_id = get_device_id()
    
    private_key = get_private_key()
    combined_key = hmac.new(
        private_key,
        device_id.encode(),
        hashlib.sha256
    ).digest()
    
    expected = hmac.new(combined_key, message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

# Device Authentication
def verify_device_access(blockchain_device_id: str) -> bool:
    """Checks if blockchain belongs to this device"""
    current_device_id = get_device_id()
    return blockchain_device_id == current_device_id

def get_current_device_id() -> str:
    """Returns current device ID"""
    return get_device_id()
