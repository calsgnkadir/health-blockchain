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
  - **Pseudonymization Engine (`core.pseudonymization.engine.PseudonymizationEngine`):** Real identity remains masked behind dynamic HMAC-SHA256 pseudonyms.
  - **Immutable Decryption Audit Logging (`storage.append_access_log`):** Every record decryption generates a permanent `RECORD_DECRYPTED` log entry.

### Threat Actor 3: Stolen / Lost Hardware Credential
- **Vector:** An attacker physically steals a VIP's hardware YubiKey / FIDO2 Passkey or mobile device.
- **Countermeasures:**
  - **Passkey Revocation API (`POST /api/v1/auth/webauthn/revoke`):** Hardware credentials can be revoked out-of-band by Security Officers.
  - **Time-Bound Consent & 2FA/TOTP Verification.**

### Threat Actor 4: Curious Practitioner (reading beyond consent)
- **Vector:** A practitioner with consent for *some* of a client's records tries to reach more: other record
  types, client-only notes, attachments, or a correction that widens who may see a record.
- **Countermeasures:**
  - **One access policy for every record endpoint** (`core/services/access_policy.py`, ADR-0003): consent for
    the record's own type (or all records) on the list, single record, decryption, corrections, attachment
    downloads and Merkle proofs. The single-record endpoint used to check nothing for a practitioner — any
    practitioner could read any client's unprotected records by walking block numbers (an IDOR). An encrypted
    record needs consent for all records before it is decrypted, so no endpoint can be used to test passwords.
  - **No consent, no file:** without an active consent a practitioner gets the same `403` for a client's records,
    chain status and proofs as for a client who does not exist, so client IDs cannot be probed. Writing into a
    file needs consent too, and notifications are readable by the client only.
  - **Practitioner-only notes** (process notes) are visible to their author only, never to the client.
  - **Client-only records stay hidden** from practitioners, even one holding the record's password.
  - **Corrections cannot change the access level** — who may see a record is not content.
  - **No emergency override.** Break-glass was removed: a private practice has no emergency-access need that
    would justify a path around consent.

---

## 3. Summary Mapping Matrix

| Adversary Profile | Threat Vector | System Countermeasure | Enforcing Code / Class |
| :--- | :--- | :--- | :--- |
| External Attacker | `X-Forwarded-For` IP Spoofing | IP Peer Host Verification | `backend.middleware.ip_allowlist.resolve_secure_client_ip` |
| Rogue Administrator | Unauthorized PHI Query | Dual-Control Co-Signature | `core.services.dual_control.DualControlEngine` |
| Stolen Hardware Passkey | Stolen YubiKey Credential | Hardware Passkey Revocation API | `POST /api/v1/auth/webauthn/revoke` |
| Curious Practitioner | Reading beyond consent | One access policy (file + record level) on every record endpoint | `core.services.access_policy` |

---

## 4. Trust Assumptions & Residual Risk

### What we assume about the attacker

We do **not** rely on hiding the system. The source code is public, so we assume the
attacker knows exactly how it works and can reach the service. A private network
(private VPC) is only one extra layer, not the main defense. Security must come from
keys and access rules, not from secrecy.

### What still protects data under these assumptions

| Attacker | Control that still works |
| :--- | :--- |
| One stolen admin account | Dual-control: reading a record needs a second, different approver. Self-approval is rejected. |
| Stolen disk or backup | Records are AES-256-GCM ciphertext, stored under HMAC pseudonyms — no real patient ID on disk. |
| Password guessing or theft | Argon2id hashing, login rate-limiting, and optional mandatory FIDO2 passkeys. |
| Changing the history | Signed, append-only hash-chain: any edit is detected when the chain is verified. |
| "Delete my data" / subpoena | Crypto-shred: destroying a per-patient key makes that patient's data unreadable for good. |

### Residual risk (chosen limits for this tier — not defects)

This is a single-institution, single-node build. The items below are **known limits**,
not bugs. Each one names what a real production system would add.

| Residual risk | Why it is accepted here | What production would add |
| :--- | :--- | :--- |
| Encryption/signing keys and `PSEUDONYM_SECRET` can live on the app host, so taking over the host can mean taking the keys. | Keeps the demo self-contained; the KMS layer is abstracted but defaults to software. | Move keys to an HSM / Vault Transit so the host never holds raw key material. |
| Tampering is **detected, not blocked**. | Tamper-evidence is the design goal; blocking needs more infrastructure. | Real-time monitoring, alerting, and incident response. |
| No high availability (single node = single point of failure). | This tier optimizes confidentiality and integrity, not uptime. | Replication behind a load balancer; DoS protection at the edge. |
| No independent penetration test or audit. | Solo portfolio project. | Third-party pentest and code audit before handling real PHI. |
| If passkeys are not enforced, a stolen patient password exposes that patient's own data. | Passkey enforcement is opt-in (`MANDATORY_FIDO2`). | Enforce hardware passkeys for all roles. |

### Scope

This system is built for a small number of protected people inside one institution's
private network (see [ADR-0001](adr/0001-offchain-storage-onchain-anchoring.md),
[ADR-0002](adr/0002-single-node-deployment.md)). It is **not** a multi-tenant hospital
EHR and does not claim to be. The legal and operational work needed for real use is
tracked in [GDPR_KVKK_COMPLIANCE.md](GDPR_KVKK_COMPLIANCE.md) and [DPIA.md](DPIA.md).
