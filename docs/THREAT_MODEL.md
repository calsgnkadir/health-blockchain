# VIP Health Vault — Threat Model & Adversary Specification (v5.0.0)

> [!NOTE]
> **Document Purpose**: Defines adversary profiles, threat attack vectors, security boundaries, and technical countermeasures for high-value VIP health data protection.

---

## 1. System Boundary & Primary Assets

### Primary Assets
1. **VIP Protected Health Information (PHI):** Medical history, diagnoses, DICOM scans, prescription records.
2. **Identity & Pseudonym Mappings:** Re-identification mappings connecting real-world identities (ministers, defense personnel) to cryptographic pseudonym IDs (`anon_id`).
3. **Master Cryptographic Keys:** KMS key material, AES-256-GCM record encryption keys.
4. **Audit Trail Integrity:** Immutable access and decryption audit logs (`access_logs`, `RECORD_DECRYPTED` events).

---

## 2. Adversary Profiles & Threat Vectors

### Threat Actor 1: External Cyber Attacker (Remote Internet Breach)
- **Vector:** Attempts network scanning, credential brute-forcing, IP header spoofing (`X-Forwarded-For`), and API exploitation over public networks.
- **Countermeasures:**
  - `IPAllowlistMiddleware` & `resolve_secure_client_ip`: Blocks untrusted socket IPs attempting header spoofing.
  - Rate Limiting (`RateLimiterMiddleware`): Prevents brute-force credential stuffing.
  - XSS Protection & Strict Security Headers (`XSSProtectionMiddleware`).

### Threat Actor 2: Compromised Administrator (Rogue Insider)
- **Vector:** An administrator with DB access attempts to query raw PHI or bypass patient consent controls without authorization.
- **Countermeasures:**
  - **Dual-Control Engine (`core.services.dual_control.DualControlEngine`):** Raw record access by administrators is blocked (`403 Forbidden`) unless co-signed by an independent Security Officer (`security_officer` role).
  - **Pseudonymization Engine (`core.pseudonymization.engine.PseudonymEngine`):** Real identity remains masked behind dynamic HMAC-SHA256 pseudonyms.
  - **Immutable Decryption Audit Logging (`storage.append_access_log`):** Every record decryption generates a permanent `RECORD_DECRYPTED` log entry.

### Threat Actor 3: Stolen / Lost Hardware Credential
- **Vector:** An attacker physically steals a VIP's hardware YubiKey / FIDO2 Passkey or mobile device.
- **Countermeasures:**
  - **Passkey Revocation API (`POST /api/v1/auth/webauthn/revoke`):** Hardware credentials can be revoked out-of-band by Security Officers.
  - **Time-Bound Consent & 2FA/TOTP Verification.**

### Threat Actor 4: Coerced Insider / Break-Glass Emergency Abuse
- **Vector:** Unauthorized staff attempt to invoke emergency access (`break-glass`) under false pretexts.
- **Countermeasures:**
  - **Dual-Control Co-Signature & Audit Alerts:** Emergency overrides trigger high-priority security alerts (`alert_service.raise_alert`) and require Dual-Control authorization.

---

## 3. Summary Mapping Matrix

| Adversary Profile | Threat Vector | System Countermeasure | Enforcing Code / Class |
| :--- | :--- | :--- | :--- |
| External Attacker | `X-Forwarded-For` IP Spoofing | IP Peer Host Verification | `backend.middleware.ip_allowlist.resolve_secure_client_ip` |
| Rogue Administrator | Unauthorized PHI Query | Dual-Control Co-Signature | `core.services.dual_control.DualControlEngine` |
| Stolen Hardware Passkey | Stolen YubiKey Credential | Hardware Passkey Revocation API | `POST /api/v1/auth/webauthn/revoke` |
| Coerced Insider | Unauthorized Record Access | Immutable Access Log | `storage.append_access_log(action="RECORD_DECRYPTED")` |
