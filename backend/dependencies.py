import os
import sys
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# Path Configuration
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.security import (
    get_device_id,
)
import database.storage as storage

# Clean Architecture Dependency Injection
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository, LMDBBlockRepository, LMDBAuditRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
from core.services.auth_service import AuthService
from core.services.record_service import RecordService
from core.services.audit_service import AuditService
from core.services.consent_validator import ConsentValidator
from core.cqrs.commands import CommandHandler
from core.cqrs.queries import QueryHandler

user_repository = LMDBUserRepository()
block_repository = LMDBBlockRepository()
audit_repository = LMDBAuditRepository()
crypto_strategy = AESGCMStrategy()

auth_service = AuthService(user_repository)
record_service = RecordService(block_repository, crypto_strategy)
audit_service = AuditService(audit_repository, record_service)
consent_validator = ConsentValidator(block_repository)

command_handler = CommandHandler(record_service, auth_service, block_repository)
query_handler = QueryHandler(record_service, block_repository, consent_validator)

# ── JWT RSA Key Configuration ──────────────────────────────
_JWT_PRIVATE_KEY_FILE = os.path.join(os.path.dirname(__file__), ".jwt_private.pem")
_JWT_PUBLIC_KEY_FILE = os.path.join(os.path.dirname(__file__), ".jwt_public.pem")

def _load_or_generate_jwt_rsa_keys() -> tuple[str, str]:
    """Loads RSA private and public keys, generating them if they do not exist."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Check env vars first
    env_priv = os.getenv("VHV_JWT_PRIVATE_KEY")
    env_pub = os.getenv("VHV_JWT_PUBLIC_KEY")
    if env_priv and env_pub:
        return env_priv.strip(), env_pub.strip()

    # Get passphrase
    passphrase = os.getenv("VHV_JWT_PASSPHRASE", get_device_id()).encode("utf-8")

    if os.path.exists(_JWT_PRIVATE_KEY_FILE) and os.path.exists(_JWT_PUBLIC_KEY_FILE):
        try:
            with open(_JWT_PRIVATE_KEY_FILE, "rb") as f:
                private_data = f.read()
            # Try to load as encrypted key
            private_key = serialization.load_pem_private_key(private_data, password=passphrase)
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ).decode("utf-8")
            
            with open(_JWT_PUBLIC_KEY_FILE, "r") as f:
                public_pem = f.read()
            return private_pem, public_pem
        except Exception as e:
            print(f"[WARNING] Failed to load encrypted JWT private key: {e}. Generating new key pair.")

    # Generate keys
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    private_pem_unencrypted = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode("utf-8")

    # Encrypt for saving
    private_pem_encrypted = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase)
    )

    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")

    # Save to files
    with open(_JWT_PRIVATE_KEY_FILE, "wb") as f:
        f.write(private_pem_encrypted)
    with open(_JWT_PUBLIC_KEY_FILE, "w") as f:
        f.write(public_pem)

    print("[OK] Generated new secure (encrypted) RSA key pair for JWT signing.")
    return private_pem_unencrypted, public_pem

JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = _load_or_generate_jwt_rsa_keys()
ALGORITHM = "RS256"
TOKEN_HOURS = 8   # 8 hours

security_bearer = HTTPBearer(auto_error=False)

def create_token(user: dict) -> str:
    payload = {
        "sub":      user["username"],
        "role":     user["role"],
        "user_id":  user["id"],
        "exp":      datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS),
        "iat":      datetime.now(timezone.utc),
        "device":   get_device_id()[:16],
    }
    return jwt.encode(payload, JWT_PRIVATE_KEY, algorithm=ALGORITHM)

def current_user(
    access_token: Optional[str] = Cookie(None),
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> dict:
    token = access_token
    if not token and creds:
        token = creds.credentials

    if not token:
        raise HTTPException(401, "Not authenticated — access token is missing")

    try:
        payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = user_repository.load_user(username)
        if not user:
            raise HTTPException(401, "Invalid token — user not found")
        return user.to_dict()
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

def require_role(*roles: str):
    """Dependency factory to enforce specific roles."""
    def dependency(u: dict = Depends(current_user)) -> dict:
        if u["role"] not in roles:
            raise HTTPException(403, f"Unauthorized action. Required roles: {roles}")
        return u
    return dependency

def _get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For ONLY if TRUST_PROXIES is enabled."""
    trust_proxies = os.getenv("TRUST_PROXIES", "false").lower() == "true"
    if trust_proxies:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
