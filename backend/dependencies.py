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
from database.connection import LMDBConnectionManager
from infrastructure.repositories.lmdb_repositories import LMDBUserRepository, LMDBBlockRepository, LMDBAuditRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
from core.services.auth_service import AuthService
from core.services.record_service import RecordService
from core.services.audit_service import AuditService
from core.services.consent_validator import ConsentValidator
from core.cqrs.commands import CommandHandler
from core.cqrs.queries import QueryHandler

def get_db_manager() -> LMDBConnectionManager:
    from database.storage import default_db_manager
    return default_db_manager

def get_user_repository(db_manager: LMDBConnectionManager = Depends(get_db_manager)) -> LMDBUserRepository:
    return LMDBUserRepository(db_manager)

def get_block_repository(db_manager: LMDBConnectionManager = Depends(get_db_manager)) -> LMDBBlockRepository:
    return LMDBBlockRepository(db_manager)

def get_audit_repository(db_manager: LMDBConnectionManager = Depends(get_db_manager)) -> LMDBAuditRepository:
    return LMDBAuditRepository(db_manager)

def get_crypto_strategy() -> AESGCMStrategy:
    return AESGCMStrategy()

def get_auth_service(user_repo: LMDBUserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(user_repo)

def get_record_service(
    block_repo: LMDBBlockRepository = Depends(get_block_repository),
    crypto_strat: AESGCMStrategy = Depends(get_crypto_strategy)
) -> RecordService:
    return RecordService(block_repo, crypto_strat)

def get_audit_service(
    audit_repo: LMDBAuditRepository = Depends(get_audit_repository),
    record_serv: RecordService = Depends(get_record_service)
) -> AuditService:
    return AuditService(audit_repo, record_serv)

def get_consent_validator(block_repo: LMDBBlockRepository = Depends(get_block_repository)) -> ConsentValidator:
    return ConsentValidator(block_repo)

def get_command_handler(
    record_serv: RecordService = Depends(get_record_service),
    auth_serv: AuthService = Depends(get_auth_service),
    block_repo: LMDBBlockRepository = Depends(get_block_repository)
) -> CommandHandler:
    return CommandHandler(record_serv, auth_serv, block_repo)

def get_query_handler(
    record_serv: RecordService = Depends(get_record_service),
    block_repo: LMDBBlockRepository = Depends(get_block_repository),
    consent_val: ConsentValidator = Depends(get_consent_validator)
) -> QueryHandler:
    return QueryHandler(record_serv, block_repo, consent_val)

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
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    user_repo: LMDBUserRepository = Depends(get_user_repository)
) -> dict:
    token = access_token
    if not token and creds:
        token = creds.credentials

    if not token:
        raise HTTPException(401, "Not authenticated — access token is missing")

    try:
        payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = user_repo.load_user(username)
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
