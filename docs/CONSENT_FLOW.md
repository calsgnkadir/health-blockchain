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
   - One rule enforces this on every record endpoint: the list, decryption, corrections and attachment
     downloads (`_practitioner_may_access` in `backend/routers/records.py`, mirroring `core/cqrs/queries.py`).
