"""
core/webauthn.py — FIDO2 / WebAuthn Assertion Verification (ES256 / secp256r1)
==============================================================================
Server-side verification of WebAuthn registration and authentication ceremonies.

The vault accepts a passkey assertion only when every one of the following
holds true:

1. ``clientDataJSON.type`` matches the expected ceremony ("webauthn.create" or
   "webauthn.get") — prevents cross-ceremony replay.
2. ``clientDataJSON.challenge`` matches a challenge this server issued, and that
   challenge has not been used before (single-use, TTL bound).
3. ``clientDataJSON.origin`` is an allowlisted origin.
4. ``authenticatorData`` carries an rpIdHash matching an expected Relying Party
   ID, and the User Present (UP) flag is set.
5. The ECDSA P-256 signature over ``authenticatorData || SHA256(clientDataJSON)``
   verifies against the credential's stored public key.
6. The authenticator signature counter has not gone backwards (clone detection).
"""

import base64
import hashlib
import json
import os
import re
import secrets
import time
from typing import Optional, Set

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key

CHALLENGE_TTL_SECONDS = 120

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04

# Loopback origins are always acceptable: the vault is deployed inside a private
# subnet (see IPAllowlistMiddleware) and is reached over 127.0.0.1 / localhost on
# an operator-chosen port.
_LOOPBACK_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d{1,5})?$")


class WebAuthnError(Exception):
    """Raised when a registration or assertion fails verification."""


def b64url_decode(value: str) -> bytes:
    """Decodes base64url (or standard base64) input, tolerating missing padding."""
    if not isinstance(value, str) or not value.strip():
        raise WebAuthnError("Malformed credential payload: expected base64url data")
    normalized = value.strip().replace("+", "-").replace("/", "_")
    normalized += "=" * (-len(normalized) % 4)
    try:
        return base64.urlsafe_b64decode(normalized)
    except Exception:
        raise WebAuthnError("Malformed credential payload: invalid base64url data")


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def expected_rp_ids() -> Set[str]:
    """Relying Party IDs whose rpIdHash the vault will accept."""
    configured = os.getenv("VHV_WEBAUTHN_RP_ID", "").strip()
    if configured:
        return {configured}
    return {"localhost", "127.0.0.1"}


def allowed_origins() -> Set[str]:
    """Explicitly allowlisted origins (loopback origins are matched separately)."""
    configured = os.getenv("VHV_WEBAUTHN_ORIGINS", "").strip()
    if not configured:
        return set()
    return {item.strip() for item in configured.split(",") if item.strip()}


def _is_origin_allowed(origin: str) -> bool:
    if not origin:
        return False
    if origin in allowed_origins():
        return True
    return bool(_LOOPBACK_ORIGIN_RE.match(origin))


class ChallengeStore:
    """In-memory single-use challenge store with a time-to-live."""

    def __init__(self, ttl_seconds: int = CHALLENGE_TTL_SECONDS):
        self._issued = {}
        self._ttl = ttl_seconds

    def issue(self) -> str:
        self._prune()
        challenge = b64url_encode(secrets.token_bytes(32))
        self._issued[challenge] = time.time()
        return challenge

    def consume(self, challenge: str) -> bool:
        """Burns the challenge. Returns False if unknown, expired, or already used."""
        self._prune()
        return self._issued.pop(challenge, None) is not None

    def _prune(self) -> None:
        cutoff = time.time() - self._ttl
        for challenge in [c for c, issued_at in self._issued.items() if issued_at < cutoff]:
            del self._issued[challenge]


challenge_store = ChallengeStore()


def _verify_client_data(
    client_data_json_b64: str,
    expected_type: str,
    store: ChallengeStore,
) -> bytes:
    """Validates clientDataJSON and burns the challenge. Returns the raw bytes."""
    raw = b64url_decode(client_data_json_b64)
    try:
        client_data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise WebAuthnError("Malformed clientDataJSON")
    if not isinstance(client_data, dict):
        raise WebAuthnError("Malformed clientDataJSON")

    if client_data.get("type") != expected_type:
        raise WebAuthnError(
            f"Unexpected ceremony type: expected {expected_type}"
        )

    if not _is_origin_allowed(client_data.get("origin", "")):
        raise WebAuthnError("Assertion origin is not authorized for this vault")

    challenge = client_data.get("challenge")
    if not isinstance(challenge, str) or not store.consume(challenge):
        raise WebAuthnError("Unknown, expired, or already used challenge")

    return raw


def _load_es256_public_key(public_key_spki_b64: str) -> ec.EllipticCurvePublicKey:
    try:
        key = load_der_public_key(b64url_decode(public_key_spki_b64))
    except WebAuthnError:
        raise
    except Exception:
        raise WebAuthnError("Stored credential public key is unreadable")
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(
        key.curve, ec.SECP256R1
    ):
        raise WebAuthnError("Unsupported credential algorithm: ES256 (secp256r1) required")
    return key


def verify_registration(
    public_key_spki_b64: str,
    client_data_json_b64: str,
    store: Optional[ChallengeStore] = None,
) -> None:
    """Verifies a registration ceremony and that the public key is usable ES256."""
    _verify_client_data(
        client_data_json_b64, "webauthn.create", store or challenge_store
    )
    _load_es256_public_key(public_key_spki_b64)


def verify_assertion(
    public_key_spki_b64: str,
    client_data_json_b64: str,
    authenticator_data_b64: str,
    signature_b64: str,
    stored_sign_count: int = 0,
    require_user_verification: bool = False,
    store: Optional[ChallengeStore] = None,
) -> int:
    """
    Verifies an authentication assertion.

    Returns the authenticator's new signature counter. Raises WebAuthnError with
    a caller-safe message on any failure.
    """
    public_key = _load_es256_public_key(public_key_spki_b64)
    client_data_raw = _verify_client_data(
        client_data_json_b64, "webauthn.get", store or challenge_store
    )

    auth_data = b64url_decode(authenticator_data_b64)
    if len(auth_data) < 37:
        raise WebAuthnError("Malformed authenticatorData")

    rp_id_hash = auth_data[:32]
    if rp_id_hash not in {
        hashlib.sha256(rp_id.encode("utf-8")).digest() for rp_id in expected_rp_ids()
    }:
        raise WebAuthnError("Assertion was issued for a different Relying Party")

    flags = auth_data[32]
    if not flags & FLAG_USER_PRESENT:
        raise WebAuthnError("Authenticator did not assert user presence")
    if require_user_verification and not flags & FLAG_USER_VERIFIED:
        raise WebAuthnError("Authenticator did not perform user verification")

    sign_count = int.from_bytes(auth_data[33:37], "big")

    signed_payload = auth_data + hashlib.sha256(client_data_raw).digest()
    try:
        public_key.verify(
            b64url_decode(signature_b64),
            signed_payload,
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        raise WebAuthnError("Passkey signature verification failed")
    except WebAuthnError:
        raise
    except Exception:
        raise WebAuthnError("Passkey signature could not be verified")

    stored = int(stored_sign_count or 0)
    if not (sign_count == 0 and stored == 0) and sign_count <= stored:
        raise WebAuthnError(
            "Authenticator signature counter did not advance — possible cloned passkey"
        )

    return sign_count
