# VIP Onboarding & Out-of-Band Identity Verification Protocol (v5.0.0)

> [!IMPORTANT]
> **Specification Status**: Planned / Not Yet Implemented (Specification Draft)  
> **Planned State Machine**: `STAGING_PENDING` $\rightarrow$ `ACTIVE_ENROLLED` (Target Release: v5.1.0)

---

## Overview

Passkeys bind a physical device (FIDO2 chip), but **not** a real-world identity. For cabinet ministers, defense personnel, and high-net-worth individuals, an out-of-band identity verification step is required before account activation.

---

## Onboarding Procedure & Planned State Machine

### 1. In-Person / Secure Channel Verification (Out-of-Band)
- The VIP patient or authorized medical protocol officer undergoes in-person verification with the Security Officer (`security_officer` role).
- Government ID / Diplomatic Credentials are verified out-of-band.

### 2. Dual-Control Account Activation
1. Administrator creates the account in `STAGING_PENDING` state:
   - Role: `vip_patient`
   - Pseudonym ID (`anon_id`): Generated via `PseudonymEngine`
   - Account Status: `STAGING_PENDING`
2. Security Officer co-signs the activation token (`co_sign_request`).
3. State transitions to `ACTIVE_ENROLLED`.

### 3. Hardware Passkey Registration
The VIP registers their physical FIDO2 YubiKey / Biometric Passkey directly into the hardware chip via `navigator.credentials.create()`.
