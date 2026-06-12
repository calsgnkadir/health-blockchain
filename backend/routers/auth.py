import os
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.responses import JSONResponse
from backend.dependencies import (
    auth_service, create_token, current_user,
    get_device_id, _get_client_ip, TOKEN_HOURS
)
from backend.schemas.requests import LoginReq, Verify2FAReq
import core.totp as totp

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login", summary="User Login")
async def login(req: LoginReq, request: Request, response: Response):
    client_ip = _get_client_ip(request)

    # Note: Rate limiting is handled in RateLimiterMiddleware

    user_entity = auth_service.authenticate(req.username, req.password, client_ip)
    if not user_entity:
        raise HTTPException(401, "Incorrect username or password")

    # Check if TOTP 2FA is enabled
    if user_entity.totp_enabled:
        if not req.code:
            return JSONResponse(
                status_code=200,
                content={"mfa_required": True}
            )
        # Verify 2FA code
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
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"success": True, "message": "Logged out successfully"}

@router.post("/2fa/setup", summary="Setup 2FA TOTP")
def setup_2fa(u: dict = Depends(current_user)):
    """Generates a temporary secret and QR code for the user to register in their app."""
    from core.domain.entities import User
    user_entity = User.from_dict(u)
    res = auth_service.setup_2fa(user_entity)
    return res

@router.post("/2fa/enable", summary="Verify and Enable 2FA")
def enable_2fa(req: Verify2FAReq, u: dict = Depends(current_user)):
    """Verifies the code and enables 2FA for the user."""
    from core.domain.entities import User
    user_entity = User.from_dict(u)
    if not user_entity.totp_secret:
        raise HTTPException(400, "2FA setup has not been initiated. Call /api/auth/2fa/setup first.")
    
    if auth_service.enable_2fa(user_entity, req.code):
        return {"success": True, "message": "Two-factor authentication enabled successfully"}
    else:
        raise HTTPException(400, "Invalid verification code. Please check your app and try again.")

@router.post("/2fa/disable", summary="Disable 2FA")
def disable_2fa(req: Verify2FAReq, u: dict = Depends(current_user)):
    """Verifies the code and disables 2FA for the user."""
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
