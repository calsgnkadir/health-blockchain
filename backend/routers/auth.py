import time
import secrets
import hashlib
import os
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.responses import JSONResponse
from backend.dependencies import (
    get_auth_service, create_token, current_user,
    get_device_id, _get_client_ip, TOKEN_HOURS,
    security_bearer, get_db_manager
)
from backend.schemas.requests import (
    LoginReq, Verify2FAReq, NonceReq, WalletLoginReq,
    SetGuardiansReq, InitiateRecoveryReq, ApproveRecoveryReq
)
from core.services.auth_service import AuthService
import core.totp as totp

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_NONCE_STORE = {}

@router.get("/nonce", summary="Generate Cryptographic Auth Nonce")
def generate_nonce():
    now = time.time()
    expired_keys = [k for k, v in _NONCE_STORE.items() if now - v["created_at"] > 600]
    for k in expired_keys:
        _NONCE_STORE.pop(k, None)

    nonce = secrets.token_hex(16)
    msg = f"Sign in to VIP Health Vault with Ethereum.\n\nNonce: {nonce}"
    _NONCE_STORE[nonce] = {
        "created_at": now,
        "message": msg
    }
    return {
        "nonce": nonce,
        "message": msg,
        "expires_in": 600
    }

@router.post("/wallet-login", summary="Sign-In with Ethereum (SIWE / Web3 Wallet Auth)")
def wallet_login(
    req: WalletLoginReq,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
):
    client_ip = _get_client_ip(request)
    
    nonce_data = _NONCE_STORE.get(req.nonce)
    if not nonce_data:
        raise HTTPException(400, "Invalid or expired authentication nonce. Please request a new nonce.")
    
    if time.time() - nonce_data["created_at"] > 600:
        _NONCE_STORE.pop(req.nonce, None)
        raise HTTPException(400, "Authentication nonce has expired.")
        
    expected_message = nonce_data["message"]
    _NONCE_STORE.pop(req.nonce, None)

    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account
        signable_msg = encode_defunct(text=expected_message)
        recovered_address = Account.recover_message(signable_msg, signature=req.signature)
        if recovered_address.lower() != req.address.lower():
            raise HTTPException(401, f"Cryptographic signature verification failed for address {req.address}")
    except ImportError:
        if not req.signature.startswith("0x") or len(req.signature) < 130:
            raise HTTPException(401, "Invalid signature format")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(401, f"Signature recovery failed: {str(e)}")

    user_entity = auth_service.authenticate_wallet(req.address, client_ip)
    if not user_entity:
        raise HTTPException(404, detail=f"No account linked to Ethereum wallet address {req.address}. Please log in with password once to link your wallet.")

    if user_entity.totp_enabled:
        if not req.code:
            return JSONResponse(
                status_code=200,
                content={"mfa_required": True}
            )
        if not user_entity.totp_secret or not totp.verify_totp(user_entity.totp_secret, req.code):
            from core.events.event_bus import event_bus, SystemAuditEvent
            event_bus.publish(SystemAuditEvent(
                project_name="__system__",
                action="LOGIN_MFA_FAILED",
                username=user_entity.username,
                device_id=get_device_id(),
                extra={"ip": client_ip, "auth_method": "wallet"},
            ))
            raise HTTPException(401, "Invalid 2FA verification code")

    auth_service.login_success(user_entity, client_ip)
    user = user_entity.to_dict()
    token = create_token(user)

    env = os.environ.get("ENVIRONMENT", "production")
    is_secure = (env == "production")
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        max_age=TOKEN_HOURS * 3600,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_HOURS * 3600,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"],
            "patient_id": user.get("patient_id"),
            "wallet_address": user.get("wallet_address"),
            "totp_enabled": bool(user.get("totp_enabled")),
        },
    }

@router.post("/wallet-link", summary="Link Web3 Wallet Address to Current Account")
def wallet_link(
    req: WalletLoginReq,
    request: Request,
    u: dict = Depends(current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    from core.domain.entities import User
    user_entity = User.from_dict(u)
    
    nonce_data = _NONCE_STORE.get(req.nonce)
    if not nonce_data:
        raise HTTPException(400, "Invalid or expired nonce.")
    
    expected_message = nonce_data["message"]
    _NONCE_STORE.pop(req.nonce, None)

    try:
        from eth_account.messages import encode_defunct
        from eth_account import Account
        signable_msg = encode_defunct(text=expected_message)
        recovered_address = Account.recover_message(signable_msg, signature=req.signature)
        if recovered_address.lower() != req.address.lower():
            raise HTTPException(401, "Signature verification failed.")
    except ImportError:
        pass
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(401, f"Signature recovery failed: {str(e)}")

    auth_service.link_wallet(user_entity, req.address)
    return {"success": True, "message": f"Successfully linked wallet {req.address} to account {user_entity.username}"}

@router.post("/login", summary="User Login")
def login(
    req: LoginReq, 
    request: Request, 
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
):
    client_ip = _get_client_ip(request)

    user_entity = auth_service.authenticate(req.username, req.password, client_ip)
    if not user_entity:
        raise HTTPException(401, "Incorrect username or password")

    if user_entity.totp_enabled:
        if not req.code:
            return JSONResponse(
                status_code=200,
                content={"mfa_required": True}
            )
        if not user_entity.totp_secret or not totp.verify_totp(user_entity.totp_secret, req.code):
            from core.events.event_bus import event_bus, SystemAuditEvent
            event_bus.publish(SystemAuditEvent(
                project_name="__system__",
                action="LOGIN_MFA_FAILED",
                username=req.username,
                device_id=get_device_id(),
                extra={"ip": client_ip},
            ))
            raise HTTPException(401, "Invalid 2FA verification code")

    auth_service.login_success(user_entity, client_ip)
    user = user_entity.to_dict()
    token = create_token(user)

    env = os.environ.get("ENVIRONMENT", "production")
    is_secure = (env == "production")
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        max_age=TOKEN_HOURS * 3600,
    )

    return {
        "access_token": token,
        "token_type":   "bearer",
        "expires_in":   TOKEN_HOURS * 3600,
        "user": {
            "id":         user["id"],
            "username":   user["username"],
            "role":       user["role"],
            "full_name":  user["full_name"],
            "patient_id": user.get("patient_id"),
            "totp_enabled": bool(user.get("totp_enabled")),
        },
    }

@router.get("/me", summary="Current User Info")
def me(u: dict = Depends(current_user)):
    return {
        "id":         u["id"],
        "username":   u["username"],
        "role":       u["role"],
        "full_name":  u["full_name"],
        "patient_id": u.get("patient_id"),
        "totp_enabled": bool(u.get("totp_enabled")),
    }

@router.post("/logout", summary="User Logout")
def logout(
    response: Response,
    request: Request,
    creds = Depends(security_bearer),
    db_manager = Depends(get_db_manager)
):
    import jwt
    import database.storage as storage
    from backend.dependencies import JWT_PUBLIC_KEY, ALGORITHM
    
    token = request.cookies.get("access_token")
    if not token and creds:
        token = creds.credentials
        
    if token:
        try:
            payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=[ALGORITHM])
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                storage.blacklist_token(jti, exp, db_manager)
                storage.clean_expired_blacklisted_tokens(db_manager)
        except Exception:
            pass

    response.delete_cookie("access_token")
    return {"success": True, "message": "Logged out successfully"}

@router.post("/2fa/setup", summary="Setup 2FA TOTP")
def setup_2fa(
    u: dict = Depends(current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    from core.domain.entities import User
    user_entity = User.from_dict(u)
    res = auth_service.setup_2fa(user_entity)
    return res

@router.post("/2fa/enable", summary="Verify and Enable 2FA")
def enable_2fa(
    req: Verify2FAReq, 
    u: dict = Depends(current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    from core.domain.entities import User
    user_entity = User.from_dict(u)
    if not user_entity.totp_secret:
        raise HTTPException(400, "2FA setup has not been initiated. Call /api/v1/auth/2fa/setup first.")
    
    if auth_service.enable_2fa(user_entity, req.code):
        return {"success": True, "message": "Two-factor authentication enabled successfully"}
    else:
        raise HTTPException(400, "Invalid verification code. Please check your app and try again.")

@router.post("/2fa/disable", summary="Disable 2FA")
def disable_2fa(
    req: Verify2FAReq, 
    u: dict = Depends(current_user),
    auth_service: AuthService = Depends(get_auth_service)
):
    from core.domain.entities import User
    user_entity = User.from_dict(u)
    if not user_entity.totp_enabled:
        raise HTTPException(400, "2FA is not enabled for this account.")
        
    if not user_entity.totp_secret:
        raise HTTPException(500, "Database inconsistency: enabled 2FA but missing secret.")
        
    if auth_service.disable_2fa(user_entity, req.code):
        return {"success": True, "message": "Two-factor authentication disabled successfully"}
    else:
        raise HTTPException(400, "Invalid verification code. Disable failed.")


# ── PHASE 3: SOCIAL RECOVERY & W3C DECENTRALIZED IDENTITY (DID / VC) ──
_GUARDIANS_STORE = {}
_RECOVERY_REQUESTS = {}

@router.post("/recovery/guardians", summary="Set Account Social Recovery Guardians")
def set_guardians(
    req: SetGuardiansReq,
    u: dict = Depends(current_user)
):
    username = u["username"]
    _GUARDIANS_STORE[username] = [g.strip().lower() for g in req.guardians]
    return {
        "success": True,
        "message": f"Successfully configured {len(req.guardians)} guardians for user {username}.",
        "guardians": _GUARDIANS_STORE[username]
    }

@router.post("/recovery/initiate", summary="Initiate Social Recovery Request")
def initiate_recovery(
    req: InitiateRecoveryReq,
    auth_service: AuthService = Depends(get_auth_service)
):
    user_entity = auth_service.user_repo.load_user(req.username)
    if not user_entity:
        raise HTTPException(404, "User account not found.")

    guardians = _GUARDIANS_STORE.get(req.username, [])
    if not guardians:
        raise HTTPException(400, "No guardians configured for this account.")

    recovery_id = f"rec_{secrets.token_hex(12)}"
    _RECOVERY_REQUESTS[recovery_id] = {
        "recovery_id": recovery_id,
        "username": req.username,
        "new_wallet_address": req.new_wallet_address,
        "guardians": guardians,
        "approvals": set(),
        "created_at": time.time(),
        "status": "pending"
    }

    return {
        "success": True,
        "recovery_id": recovery_id,
        "message": f"Recovery initiated for {req.username}. Requires {len(guardians) // 2 + 1} guardian approvals.",
        "threshold": len(guardians) // 2 + 1
    }

@router.post("/recovery/approve", summary="Approve Social Recovery Request (Guardian)")
def approve_recovery(
    req: ApproveRecoveryReq,
    auth_service: AuthService = Depends(get_auth_service)
):
    rec = _RECOVERY_REQUESTS.get(req.recovery_id)
    if not rec:
        raise HTTPException(404, "Recovery request not found or expired.")

    if time.time() - rec["created_at"] > 86400:
        _RECOVERY_REQUESTS.pop(req.recovery_id, None)
        raise HTTPException(400, "Recovery request has expired.")

    guardian_clean = req.guardian_identifier.strip().lower()
    if guardian_clean not in rec["guardians"]:
        raise HTTPException(403, f"{req.guardian_identifier} is not an authorized guardian for this recovery request.")

    rec["approvals"].add(guardian_clean)
    threshold = len(rec["guardians"]) // 2 + 1

    if len(rec["approvals"]) >= threshold and rec["status"] == "pending":
        rec["status"] = "executed"
        user_entity = auth_service.user_repo.load_user(rec["username"])
        if user_entity:
            auth_service.link_wallet(user_entity, rec["new_wallet_address"])

        return {
            "success": True,
            "status": "executed",
            "message": f"Threshold reached ({len(rec['approvals'])}/{threshold}). Account access successfully recovered to {rec['new_wallet_address']}!"
        }

    return {
        "success": True,
        "status": "pending",
        "approvals_count": len(rec["approvals"]),
        "threshold": threshold,
        "message": f"Approval recorded ({len(rec['approvals'])}/{threshold}). Waiting for remaining guardian signatures."
    }

@router.get("/did/{identifier}", summary="Get W3C Decentralized Identity (DID) Document")
def get_did_document(
    identifier: str,
    auth_service: AuthService = Depends(get_auth_service)
):
    user_entity = auth_service.user_repo.load_user(identifier)
    if not user_entity:
        user_dict = {"id": identifier, "username": identifier, "role": "patient", "wallet_address": "0x0000"}
    else:
        user_dict = user_entity.to_dict()

    did_id = f"did:vhv:{hashlib.sha256(user_dict['username'].encode()).hexdigest()[:16]}"
    wallet_addr = user_dict.get("wallet_address") or "0x0000000000000000000000000000000000000000"

    return {
        "@context": ["https://www.w3.org/ns/did/v1"],
        "id": did_id,
        "controller": f"did:vhv:{user_dict['username']}",
        "verificationMethod": [{
            "id": f"{did_id}#key-1",
            "type": "EcdsaSecp256k1VerificationKey2019",
            "controller": f"did:vhv:{user_dict['username']}",
            "blockchainAccountId": f"eip155:1:{wallet_addr}"
        }],
        "authentication": [f"{did_id}#key-1"],
        "service": [{
            "id": f"{did_id}#health-vault",
            "type": "VIPHealthVaultEncryptedStorage",
            "serviceEndpoint": f"https://vault.healthchain.org/api/v1/records/{user_dict.get('patient_id') or user_dict['username']}"
        }]
    }

@router.get("/vc/{identifier}", summary="Issue W3C Verifiable Credential")
def get_verifiable_credential(
    identifier: str,
    auth_service: AuthService = Depends(get_auth_service)
):
    user_entity = auth_service.user_repo.load_user(identifier)
    if not user_entity:
        raise HTTPException(404, "User not found.")

    u = user_entity.to_dict()
    import uuid
    did_id = f"did:vhv:{hashlib.sha256(u['username'].encode()).hexdigest()[:16]}"

    vc_payload = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://schema.org"
        ],
        "id": f"urn:uuid:{uuid.uuid4()}",
        "type": ["VerifiableCredential", "HealthVaultMedicalCredential"],
        "issuer": "did:vhv:issuer:authority_health_core",
        "issuanceDate": datetime.now(timezone.utc).isoformat(),
        "credentialSubject": {
            "id": did_id,
            "username": u["username"],
            "role": u["role"],
            "full_name": u["full_name"],
            "patient_id": u.get("patient_id"),
            "institution": u.get("institution") or "Connected Vitals Network",
            "specialty": u.get("specialty")
        },
        "proof": {
            "type": "Ed25519Signature2020",
            "created": datetime.now(timezone.utc).isoformat(),
            "proofPurpose": "assertionMethod",
            "verificationMethod": "did:vhv:issuer:authority_health_core#key-1",
            "jws": f"eyJhbGciOiJFZERTQSI...{secrets.token_hex(16)}"
        }
    }

    return vc_payload
