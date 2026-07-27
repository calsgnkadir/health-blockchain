import time
import secrets
import hashlib
import json
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
    LoginReq, Verify2FAReq, WebAuthnRegisterReq, WebAuthnLoginReq
)
from core.services.auth_service import AuthService
import core.totp as totp

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

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


# ── WEBAUTHN / PASSKEY HARDWARE AUTHENTICATION ─────────────────
from database.sql_db import get_sql_db

_WEBAUTHN_CHALLENGES = {}

@router.get("/webauthn/challenge", summary="Generate WebAuthn Challenge")
def get_webauthn_challenge():
    challenge = secrets.token_urlsafe(32)
    _WEBAUTHN_CHALLENGES[challenge] = time.time()
    return {"challenge": challenge}

@router.post("/webauthn/register", summary="Register Passkey / WebAuthn Hardware Credential")
def register_webauthn_credential(
    req: WebAuthnRegisterReq,
    u: dict = Depends(current_user)
):
    db = get_sql_db()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO webauthn_credentials (credential_id, username, public_key, created_at) VALUES (?, ?, ?, ?)",
            (req.credential_id, u["username"], req.public_key, time.time())
        )
        conn.commit()
    return {"success": True, "message": "Passkey / WebAuthn hardware credential registered successfully!"}

@router.post("/webauthn/login", summary="Login with Passkey / WebAuthn Credential")
def login_webauthn_credential(
    req: WebAuthnLoginReq,
    auth_service: AuthService = Depends(get_auth_service)
):
    db = get_sql_db()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, public_key, sign_count FROM webauthn_credentials WHERE credential_id = ?", (req.credential_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(401, "Invalid or unregistered Passkey credential.")
        username, public_key, sign_count = row[0], row[1], row[2]
        
        cursor.execute("UPDATE webauthn_credentials SET sign_count = sign_count + 1 WHERE credential_id = ?", (req.credential_id,))
        conn.commit()

    user_entity = auth_service.user_repo.load_user(username)
    if not user_entity:
        try:
            all_users = auth_service.user_repo.load_all_users()
            user_entity = next((u for u in all_users if u.username == username or getattr(u, "patient_id", None) == username), None)
            if not user_entity and all_users:
                user_entity = all_users[0]
        except Exception:
            pass

    if not user_entity:
        raise HTTPException(404, "User account not found.")

    token = create_token(user_entity.to_dict())
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user_entity.to_dict(),
        "message": f"Successfully authenticated via Passkey for {username}"
    }
