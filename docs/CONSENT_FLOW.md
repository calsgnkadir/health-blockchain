# VIP Health Vault — Consent Engine & Time-Bound RBAC Specification (v5.0.0)

## Overview

The VIP Health Vault Consent Engine enforces time-bound, fine-grained access delegation on encrypted medical records.

## Core Flow

1. **Patient Consent Grant**:
   - Patient grants a doctor access specifying `doctor_username`, `record_type`, and explicit `duration_hours` or `duration_days`.
   - Engine calculates `expiry_timestamp = current_time + duration`.

2. **Auto-Expiration Enforcement**:
   - On every record read or decryption request, `ConsentValidator` evaluates `expiry_timestamp`.
   - If `current_time > expiry_timestamp`, access is denied instantly and a `CONSENT_EXPIRED` audit log is published.

3. **No emergency override**:
   - There is no break-glass path. A practitioner reads a client's records only with the client's
     consent for that record type, and client-only (`private`) records are never shown to a practitioner.
   - A hospital needs emergency access; a private psychology practice does not — and an override that
     bypasses consent is exactly the path an insider would abuse. It was removed rather than kept "just in case".
   - One policy enforces this on every record endpoint: the list, single record, decryption, corrections,
     attachment downloads and proofs (`core/services/access_policy.py`, see ADR-0003).
   - Without any active consent the whole file is closed to the practitioner, and writing a record needs
     the same consent as reading one.

4. **Invitations do not grant consent**:
   - A practitioner brings in a new client with an invitation (`POST /api/v1/onboarding/invite-client`):
     the system picks the next free client ID (never one that still has a chain), creates a pending
     account and returns a single-use code, valid for 72 hours and stored only as a hash.
   - The client redeems the code to choose their password. The redeem response names the practitioner
     who invited them, so the client knows whom to give consent to — but nothing is granted
     automatically. Until the client grants consent, the practitioner gets the same `403` for the new
     client's file as for any other client.
   - A practitioner sees only the clients they invited, can issue a new code only for their own pending
     clients, and may hold at most 20 open invitations at a time.
