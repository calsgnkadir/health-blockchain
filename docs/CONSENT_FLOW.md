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

3. **Break-Glass Emergency Overrides**:
   - In life-threatening emergencies, doctors invoke Break-Glass with a mandatory clinical justification.
   - Access is opened for a strict 15-minute window while publishing real-time security alerts to the Security Officer dashboard.
