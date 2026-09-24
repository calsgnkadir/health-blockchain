"""
core/services/access_policy.py — who may see and write a client's records
=========================================================================
One policy, used by every endpoint that reads or writes a record. It used to be
re-implemented per endpoint, and the copies drifted apart: the record list hid
records the single-record endpoint still returned (see ADR-0003).

The rules, in plain words:

  File level  — a practitioner with no active consent from a client does not
                see that client's file at all: not its records, not its chain
                status, not even whether it exists.
  Record level — every record carries an access level:
      "doctor_shared"      client + practitioner   (the default)
      "private"            client only             (e.g. a personal journal)
      "practitioner_only"  the practitioner who wrote it only (a process note)
                and a practitioner additionally needs consent for the record's
                type (or for all records).

Administrators, auditors and security officers are not decided here: they may
read a client's records only with a dual-control co-signature, enforced by the
routers before this policy is consulted.

Everything here is a pure function of its arguments — `has_consent` is passed
in as a callable — so the policy can be tested without a database.
"""

from typing import Callable, Optional

SHARED = "doctor_shared"
CLIENT_ONLY = "private"
PRACTITIONER_ONLY = "practitioner_only"

KNOWN_LEVELS = {SHARED, CLIENT_ONLY, PRACTITIONER_ONLY}

# Which access levels each role may give a record it creates. A client cannot
# write a note hidden from themselves, nor a practitioner one hidden from
# themselves.
CREATABLE_LEVELS = {
    "client":       {SHARED, CLIENT_ONLY},
    "practitioner": {SHARED, PRACTITIONER_ONLY},
}

HasConsent = Callable[[str], bool]   # record_type -> does the practitioner hold consent?


def can_view(role: str, username: str, record: Optional[dict], has_consent: HasConsent) -> bool:
    """May this user see this (decrypted) record? The caller has already
    checked that a client is looking at their own file."""
    if not isinstance(record, dict):
        return False
    level = record.get("access_level", SHARED)
    if level not in KNOWN_LEVELS and role in ("client", "practitioner"):
        # An access level this policy does not know (e.g. the old "admin_only")
        # is never read as "shared": unknown means closed.
        return False

    if role == "client":
        return level != PRACTITIONER_ONLY

    if role == "practitioner":
        if level == CLIENT_ONLY:
            return False
        if level == PRACTITIONER_ONLY and record.get("created_by") != username:
            return False
        return has_consent(record.get("record_type", "other"))

    # admin / auditor / security_officer: gated by dual-control upstream.
    return True


def can_create(role: str, access_level: str, record_type: str, has_consent: HasConsent) -> bool:
    """May this user add a record with this access level and type?"""
    allowed = CREATABLE_LEVELS.get(role)
    if allowed is not None and access_level not in allowed:
        return False
    if role == "practitioner":
        # Writing into a client's file needs the same consent as reading it.
        return has_consent(record_type)
    return True


# Blocks that keep the chain working but are not records a person wrote.
BOOKKEEPING_TYPES = ("genesis", "audit", "correction")


def can_view_stored(role: str, username: str, data, has_consent: HasConsent,
                    protected_access: Optional[dict] = None) -> bool:
    """can_view() for a block as it is stored, before any password is given.

    A password-protected block is still a string here. Its record type is unknown
    until it is decrypted, so a practitioner needs consent for all records to see
    it at all. Its audience is kept outside the ciphertext (`protected_access`:
    access_level and created_by), so a client's private journal is not even
    listed for the practitioner, nor a practitioner's locked note for the client.
    Blocks written before that was recorded have no `protected_access`; they
    fall back to the consent-for-all rule alone.

    Bookkeeping blocks (genesis, audit, correction wrappers) say who did what and
    when — the client and operators may see them, a practitioner may not."""
    if isinstance(data, str):
        if protected_access:
            # The type stays unknown, so "all" stands in for it.
            record = dict(protected_access, record_type="all")
            return can_view(role, username, record, has_consent)
        return role != "practitioner" or has_consent("all")
    if isinstance(data, dict) and data.get("type") in BOOKKEEPING_TYPES:
        return role != "practitioner"
    return can_view(role, username, data, has_consent)
