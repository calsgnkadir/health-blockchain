"""
backend/routers/onboarding.py — out-of-band account provisioning & enrollment
=============================================================================
No real account should exist that a person self-registered. Accounts are
*provisioned* by a privileged operator once identity has been vetted out of band,
and stay inactive until the holder redeems a single-use enrollment token that was
also delivered out of band (in person / sealed channel — the system never emails
it). Only then does the account become ``ACTIVE_ENROLLED`` and able to log in.

  provision (admin/security officer)  →  PENDING_ONBOARDING + one-time token
  redeem    (holder, token-gated)     →  sets password, ACTIVE_ENROLLED
  login                               →  refused unless ACTIVE_ENROLLED
"""

import hashlib
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.dependencies import require_role
from backend.schemas.requests import ProvisionAccountReq, RedeemEnrollmentReq
from core.domain.entities import User
from core.events.event_bus import event_bus, SystemAuditEvent
from core.security import get_device_id, hash_password, validate_password
from database.sql_db import get_sql_db
from infrastructure.repositories.sql_repositories import SQLUserRepository, _to_placeholder

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

# How long a provisioned holder has to redeem their token (out-of-band delivery).
_TOKEN_TTL_SECONDS = 72 * 3600


def _hash_token(token: str) -> str:
    """Only the hash of the enrollment token is stored, never the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/provision", summary="Provision a vetted account (out-of-band)")
def provision_account(
    req: ProvisionAccountReq,
    request: Request,
    u: dict = Depends(require_role("admin", "security_officer")),
):
    repo = SQLUserRepository()
    if repo.user_exists(req.username):
        raise HTTPException(409, "A user with this username already exists")

    # Locked account: a random password nobody holds. It is PENDING until the
    # holder redeems their token, and login is refused in the meantime.
    user = User(
        id=f"USR-{uuid.uuid4().hex[:12].upper()}",
        username=req.username,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=req.role,
        full_name=req.full_name,
        specialty=req.specialty,
        institution=req.institution,
        patient_id=req.patient_id,
        clearance=req.clearance,
        totp_secret=None,
        totp_enabled=False,
        account_status="PENDING_ONBOARDING",
    )
    repo.save_user(user)

    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + _TOKEN_TTL_SECONDS

    db = get_sql_db()
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _to_placeholder(
                "INSERT INTO enrollment_tokens "
                "(token_hash, username, expires_at, used, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (_hash_token(token), req.username, expires_at, False, u["username"], now),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    event_bus.publish(SystemAuditEvent(
        project_name="__system__",
        action="ACCOUNT_PROVISIONED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"provisioned": req.username, "role": req.role},
    ))

    return {
        "success": True,
        "username": req.username,
        "account_status": "PENDING_ONBOARDING",
        # Deliver this out of band. It is single-use, expires, and is stored only
        # as a hash — it cannot be recovered from the system afterwards.
        "enrollment_token": token,
        "expires_at": expires_at,
        "message": "Deliver the enrollment token to the account holder out of band.",
    }


@router.post("/redeem", summary="Redeem an enrollment token and activate the account")
def redeem_enrollment(req: RedeemEnrollmentReq, request: Request):
    valid, msg = validate_password(req.new_password)
    if not valid:
        raise HTTPException(422, msg)

    token_hash = _hash_token(req.enrollment_token)

    db = get_sql_db()
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _to_placeholder(
                "SELECT username, expires_at, used FROM enrollment_tokens WHERE token_hash = ?"
            ),
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(400, "Invalid or unknown enrollment token")
        try:
            username, expires_at, used = row["username"], row["expires_at"], row["used"]
        except Exception:
            username, expires_at, used = row[0], row[1], row[2]

        if used:
            raise HTTPException(400, "This enrollment token has already been used")
        if time.time() > float(expires_at):
            raise HTTPException(400, "This enrollment token has expired")

        repo = SQLUserRepository()
        user = repo.load_user(username)
        if not user:
            raise HTTPException(400, "The account for this token no longer exists")

        user.password_hash = hash_password(req.new_password)
        user.account_status = "ACTIVE_ENROLLED"
        repo.save_user(user)

        cur.execute(
            _to_placeholder("UPDATE enrollment_tokens SET used = ? WHERE token_hash = ?"),
            (True, token_hash),
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()

    event_bus.publish(SystemAuditEvent(
        project_name="__system__",
        action="ACCOUNT_ENROLLED",
        username=username,
        device_id=get_device_id(),
        extra={},
    ))

    return {
        "success": True,
        "username": username,
        "account_status": "ACTIVE_ENROLLED",
        "message": "Account activated. You can now sign in and enrol your passkey.",
    }
