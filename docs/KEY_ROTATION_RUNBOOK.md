# KMS Key Rotation & Device Revocation Runbook (v5.0.0)

## Overview

In high-threat environments (presidents, ministers, defense personnel), device theft or master key compromise requires an immediate, deterministic **Key Revocation and Rotation Protocol**.

---

## 1. Trigger Conditions

- **Lost / Stolen Authenticator Device**: Loss of a hardware YubiKey / FIDO2 Passkey credential.
- **Insider Threat / Suspicious Access**: Compromise of a doctor or administrator account.
- **Scheduled Cryptographic Hygiene**: Periodic KMS master key rotation (e.g., every 90 days).

---

## 2. Key Rotation & Device Revocation Flow

### Step 1: Emergency Device Revocation via API / CLI
An Administrator or Security Officer revokes the compromised credential ID:

```bash
# Revoke FIDO2 Credential / Device ID
POST /api/v1/auth/webauthn/revoke
Headers:
  Authorization: Bearer <ADMIN_JWT>
  X-Dual-Control-Token: <CO_SIGNED_TOKEN>
Body:
  {
    "username": "dr.smith",
    "credential_id": "cred_abc123_stolen_device"
  }
```

### Step 2: KMS Envelope Key Re-Encryption
1. Generate a new Master Envelope Key (`MEK_v2`) in AWS KMS / HashiCorp Vault.
2. Re-encrypt all patient data encryption keys (`DEK`) stored in LMDB metadata:
   $$\text{DEK}_{\text{new}} = \text{KMS}_{\text{v2}}.\text{Encrypt}(\text{DEK}_{\text{raw}})$$
3. Log the key rotation event to the immutable local audit log:
   - Event: `KMS_KEY_ROTATED`
   - Actor: `security_officer`
   - Timestamp: ISO 8601 UTC

### Step 3: Out-of-Band Passkey Re-Enrollment
The VIP or Doctor undergoes physical in-person or out-of-band identity verification to enroll a new hardware Passkey device.
