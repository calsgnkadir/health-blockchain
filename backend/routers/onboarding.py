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

A practitioner brings in their own clients the same way, through an invitation:

  invite-client (practitioner)        →  new CL-### client, PENDING + invite code
  redeem        (client)              →  as above; the client then grants
                                         consent themselves — an invitation
                                         never gives the practitioner access.
"""

import hashlib
import re
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.dependencies import require_role
from backend.schemas.requests import ProvisionAccountReq, RedeemEnrollmentReq, InviteClientReq
from core.pseudonymization.service import project_name_for
from core.domain.entities import User
from core.events.event_bus import event_bus, SystemAuditEvent
from core.security import get_device_id, hash_password, validate_password
from database.sql_db import get_sql_db
import database.storage as storage
from infrastructure.repositories.sql_repositories import SQLUserRepository, _to_placeholder

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])

# How long a provisioned holder has to redeem their token (out-of-band delivery).
_TOKEN_TTL_SECONDS = 72 * 3600


# A practitioner may hold at most this many unredeemed invitations, so a stolen
# practitioner account cannot fill the user table with pending clients.
MAX_OPEN_INVITATIONS = 20


def _hash_token(token: str) -> str:
    """Only the hash of the enrollment token is stored, never the token itself."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _issue_token(cur, username: str, created_by: str):
    """Store a new single-use token for `username`; return (token, expires_at).
    The caller commits."""
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + _TOKEN_TTL_SECONDS
    cur.execute(
        _to_placeholder(
            "INSERT INTO enrollment_tokens "
            "(token_hash, username, expires_at, used, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (_hash_token(token), username, expires_at, False, created_by, now),
    )
    return token, expires_at


def _col(row, name: str, index: int):
    """Read a column from a SQLite row or a PostgreSQL tuple alike."""
    try:
        return row[name]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _next_client_id(repo: SQLUserRepository) -> str:
    """The next free CL-### number. A number is free only if no account has it
    AND no chain exists for it: a chain left behind by an old or erased client
    must never be handed to a new person."""
    numbers = [
        int(user.patient_id[3:]) for user in repo.load_all_users()
        if user.patient_id and re.fullmatch(r"CL-[0-9]{3,}", user.patient_id)
    ]
    n = max(numbers, default=0) + 1
    while True:
        patient_id = f"CL-{n:03d}"
        if (not storage.project_exists(project_name_for(patient_id))
                and not repo.user_exists(patient_id.lower())):
            return patient_id
        n += 1


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

    db = get_sql_db()
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        token, expires_at = _issue_token(cur, req.username, u["username"])
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


# ── CLIENT INVITATIONS (practitioner) ─────────────────────────
def _open_invitations(cur, practitioner: str) -> int:
    cur.execute(
        _to_placeholder(
            "SELECT COUNT(*) FROM enrollment_tokens "
            "WHERE created_by = ? AND used = ? AND expires_at > ?"
        ),
        (practitioner, False, time.time()),
    )
    return cur.fetchone()[0]


@router.post("/invite-client", summary="Invite a new client (practitioner)")
def invite_client(
    req: InviteClientReq,
    u: dict = Depends(require_role("practitioner")),
):
    """Create a pending client account with the next free client ID and return a
    single-use invitation code. The practitioner hands the code to the client in
    person; the client sets their own password with it."""
    repo = SQLUserRepository()
    db = get_sql_db()
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        if _open_invitations(cur, u["username"]) >= MAX_OPEN_INVITATIONS:
            raise HTTPException(429, "Too many open invitations. Wait for some to be used or to expire.")

        patient_id = _next_client_id(repo)
        username = patient_id.lower()
        repo.save_user(User(
            id=f"USR-{uuid.uuid4().hex[:12].upper()}",
            username=username,
            # A random password nobody holds; login is refused while PENDING anyway.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role="client",
            full_name=req.full_name,
            specialty=None,
            institution=None,
            patient_id=patient_id,
            clearance=None,
            totp_secret=None,
            totp_enabled=False,
            account_status="PENDING_ONBOARDING",
        ))
        token, expires_at = _issue_token(cur, username, u["username"])
        conn.commit()
    finally:
        cur.close()
        conn.close()

    # The audit trail names the client by ID only, not by their real name.
    event_bus.publish(SystemAuditEvent(
        project_name="__system__",
        action="CLIENT_INVITED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"patient_id": patient_id},
    ))

    return {
        "success": True,
        "patient_id": patient_id,
        "username": username,
        # Shown once. Only its hash is stored, so it cannot be looked up later.
        "invite_code": token,
        "expires_at": expires_at,
    }


def invitations_by(practitioner: str) -> list:
    """The clients this practitioner has invited, newest first, with the
    invitation's status: pending, expired, or active (the client joined)."""
    db = get_sql_db()
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _to_placeholder(
                "SELECT u.patient_id, u.full_name, u.account_status, "
                "MAX(t.expires_at), MAX(t.created_at) "
                "FROM enrollment_tokens t JOIN users u ON u.username = t.username "
                "WHERE t.created_by = ? AND u.role = ? "
                "GROUP BY u.patient_id, u.full_name, u.account_status "
                "ORDER BY MAX(t.created_at) DESC"
            ),
            (practitioner, "client"),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    now = time.time()
    invitations = []
    for row in rows:
        account_status, expires_at = row[2], float(row[3])
        if account_status == "ACTIVE_ENROLLED":
            status = "active"
        elif now > expires_at:
            status = "expired"
        else:
            status = "pending"
        invitations.append({
            "patient_id": row[0],
            "full_name": row[1],
            "status": status,
            "expires_at": expires_at,
            "invited_at": float(row[4]),
        })
    return invitations


@router.get("/invitations", summary="My client invitations (practitioner)")
def list_invitations(u: dict = Depends(require_role("practitioner"))):
    """Only their own: a practitioner learns nothing here about anyone else's
    clients."""
    return {"invitations": invitations_by(u["username"])}


@router.post("/invitations/{patient_id}/renew", summary="Issue a new invitation code (practitioner)")
def renew_invitation(patient_id: str, u: dict = Depends(require_role("practitioner"))):
    """A code lasts 72 hours. If it expired (or was lost) before the client used
    it, the practitioner who invited them can issue a new one; the old codes stop
    working."""
    if not re.fullmatch(r"CL-[0-9]{3,}", patient_id):
        raise HTTPException(400, "Invalid client ID")
    username = patient_id.lower()
    not_found = HTTPException(404, "No pending invitation for this client")

    repo = SQLUserRepository()
    user = repo.load_user(username)
    if not user or user.role != "client" or user.account_status != "PENDING_ONBOARDING":
        raise not_found

    db = get_sql_db()
    conn = db.get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _to_placeholder("SELECT COUNT(*) FROM enrollment_tokens WHERE username = ? AND created_by = ?"),
            (username, u["username"]),
        )
        if cur.fetchone()[0] == 0:
            raise not_found   # someone else's client: answer as if it did not exist
        cur.execute(
            _to_placeholder("UPDATE enrollment_tokens SET used = ? WHERE username = ?"),
            (True, username),
        )
        token, expires_at = _issue_token(cur, username, u["username"])
        conn.commit()
    finally:
        cur.close()
        conn.close()

    event_bus.publish(SystemAuditEvent(
        project_name="__system__",
        action="CLIENT_INVITATION_RENEWED",
        username=u["username"],
        device_id=get_device_id(),
        extra={"patient_id": patient_id},
    ))
    return {"success": True, "patient_id": patient_id, "username": username,
            "invite_code": token, "expires_at": expires_at}


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
                "SELECT username, expires_at, used, created_by FROM enrollment_tokens WHERE token_hash = ?"
            ),
            (token_hash,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(400, "Invalid or unknown enrollment token")
        username, expires_at, used, created_by = (
            _col(row, "username", 0), _col(row, "expires_at", 1),
            _col(row, "used", 2), _col(row, "created_by", 3))

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

        # A client invited by a practitioner is told who invited them, so they
        # know whom to give consent to. Nothing is granted automatically.
        inviter = repo.load_user(created_by) if user.role == "client" else None
        invited_by = inviter.username if inviter and inviter.role == "practitioner" else None

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
        "invited_by": invited_by,
        "message": "Account activated. You can now sign in and enrol your passkey.",
    }
