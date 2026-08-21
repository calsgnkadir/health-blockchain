# Changelog — VIP Health Vault

## [5.4.0] - 2026-08-21

### ✂️ Cut list — remove scope drift

Three residual features that did not fit a single-tenant, single-subnet vault for
a few individuals were removed outright.

- **`wallet_address` field deleted.** A dead column carried through the `User`
  entity, the SQL schema and the repository, never read by any logic — a leftover
  from an abandoned wallet-identity idea. Removed from the entity, `CREATE TABLE`,
  the migration, `_USER_COLS`, and every INSERT/UPDATE/SELECT mapping. Because it
  was the last column, existing rows read back cleanly (the trailing value is
  simply ignored).
- **LIS laboratory webhook gateway deleted.** `POST /api/v1/webhooks/lis`, its
  authentication, the `LisWebhookPayload` schema and `VHV_LIS_API_KEY` are gone;
  there is no real lab-integration contract, so the endpoint was only attack
  surface. The genuinely general tests that lived in its test file
  (path-traversal confinement, at-rest ciphertext, cross-patient metadata) moved
  to `tests/test_storage_and_metadata_safety.py`, rewritten to use the normal
  record path.
- **IPFS attachment storage folded into the encrypted LMDB store.** A distributed
  content network was never the fit for one private subnet. Attachments (already
  AES-encrypted) now live in the same LMDB store as the chain, content-addressed
  by the SHA-256 of the ciphertext (`core.services.attachment_store`). The IPFS
  client, its simulation-mode fallback, its network egress path and
  `VHV_IPFS_API_URL` are removed. Verified end-to-end: an imaging file uploads,
  downloads byte-for-byte, and the plaintext is not recoverable from the blob on
  disk.

## [5.3.0] - 2026-08-21

### 🎯 Scope realignment — closing the gap between claimed and actual behavior

A line-by-line audit of the mission ("single-tenant, private, tamper-evident
vault for a few protected individuals") flagged three things the README claimed
but the code did not do. Two are now fixed.

- **Identity pseudonymization is wired into the write path** (was: an isolated
  admin API that no record ever touched). The clinical chain store is now keyed by
  a deterministic `anon_id` (HMAC-SHA256 of the patient id under `PSEUDONYM_SECRET`),
  never the raw identifier — so the block store on disk holds only opaque
  pseudonyms. All read/write paths derive the store name from one canonical
  `project_name_for()`, so they cannot drift apart; the write path persists the
  reverse mapping for authorized resolution. Verified end-to-end: a record for
  `VIP-042` lands under `patient_18ce198d…`, the raw id names nothing on disk, and
  the server still decrypts and resolves it. **Breaking:** existing chains keyed by
  the raw id are not found under the new naming and must be re-seeded/migrated.
- **The notarizer anchor is a real signature, not a random number.** It previously
  generated `anchor_tx = f"0x{secrets.token_hex(32)}"` — a random token dressed up
  as a blockchain transaction hash — and stored it via `save_simulated_merkle_root`.
  The anchor is now an **HMAC-SHA256 signature of the Merkle root** under the KMS
  key; verification recomputes and checks it in constant time, so a tampered block
  fails as "Anchor signature invalid." The status API and UI drop the misleading
  `on_chain_tx_hash` / "Simulated Anchor" / "On-Chain Verified" wording for honest
  `anchor_signature` / "Local Signed Anchor" labels.

Still open from the same audit (tracked, not yet done): key-destruction erasure,
an externally-held / HSM signing key, and real out-of-band VIP onboarding. (The
`wallet_address`, LIS-gateway and IPFS cut-list items are done in 5.4.0.)

## [5.2.0] - 2026-08-21

### 🔑 Key-management hardening & honest documentation

The signing key both signs blocks and derives the at-rest encryption key, so its
handling is now treated as a first-class operational concern rather than an
implementation detail.

- **`keyring` is now a declared dependency** — the code advertised OS-keyring
  storage (DPAPI / Keychain / Secret Service) but never listed the package, so a
  clean install silently fell back to a plaintext `.private_key` file next to the
  encrypted chain store. `keyring==25.2.1` is now in `requirements.txt`.
- **Production refuses to auto-generate a signing key** — a key minted on boot
  would either land in plaintext on disk or orphan every record already encrypted
  under a previous key. Startup now fails with clear guidance unless a key is
  configured, with a `VHV_ALLOW_GENERATED_KEY=true` opt-in for a first-run install
  that has no data. Plaintext-on-disk storage logs a warning on every startup.
- **Honest threat model** — the README no longer implies the ciphertext is safe
  unconditionally; it is safe only while the key is kept out of the data backup.
  New [docs/KEY_MANAGEMENT.md](docs/KEY_MANAGEMENT.md) documents key sources,
  backup, and the rotation procedure.

### 🐞 Fixed — silent loss of access-log entries (audit trail)

- **The access ledger keyed entries on a wall-clock timestamp** (`time.time_ns()`),
  whose resolution on Windows is ~15.6 ms. Two access events in the same tick
  produced the **same LMDB key**, so the second silently overwrote the first — the
  audit trail could lose reads under any real load. Entries are now keyed on the
  monotonic, collision-free sequence number, so every access is stored and the
  hash-chain verifies deterministically. Confirmed: four back-to-back appends
  within one clock tick now store four rows (previously one). This also removes a
  timing-dependent flake in `tests/test_access_ledger.py`.

### 🧹 Removed misleading configuration

- **`.env.example` no longer advertises a public-chain integration that does not
  exist** — the `VHV_RPC_URL` (Polygon/Alchemy), `VHV_PRIVATE_KEY` and
  `VHV_CONTRACT_ADDRESS` lines contradicted the README's "Zero Web3/RPC
  dependencies" and were removed. The file now documents the real signing-key and
  file-attachment settings instead.
- **File attachments documented honestly** — the IPFS client is a real, working
  code path that AES-encrypts attachments and, with no daemon configured, stores
  them locally without any network call. It now appears in the feature matrix
  rather than being an undocumented surface.

## [5.1.0] - 2026-08-18

### 🔐 Security Audit — Findings and Remediation

Each item below was reproduced against a running instance before it was fixed, and
is covered by a regression test.

#### Authentication
- **Passkey login accepted any known credential id** — `/api/v1/auth/webauthn/login` issued a session token without checking the challenge, signature, origin, relying party or counter, and `init_db` seeded `passkey_default_demo → vip001` in every environment. Clicking "Sign in with Passkey" was enough to become the VIP patient. Assertions are now verified in `core/webauthn.py` (single-use TTL challenge, origin and rpId binding, User Present flag, ES256 signature, clone detection); the seeded credential is deleted on startup.
- **Credential material returned to the client** — the same endpoint answered with the full user record including the argon2 password hash, and fell back to the first account in the database when the credential owner could not be resolved.
- **Passkeys could not be enrolled** — no UI called the registration endpoint, so only the seeded credential ever worked. Enrolment lives in Security settings.
- **Session expiry was invisible** — a rejected token produced 401s while the UI still looked signed in. `apiFetch` now ends the session, and the stored token is validated on startup.

#### Authorization
- **Practitioners could grant themselves consent** — grant and revoke only rejected the `vip_patient` role, so a doctor could revoke a patient's decision and authorise themselves in its place, bypassing Break-Glass auditing. Consent is now a patient-only operation.
- **Dual-Control covered administrators only** — auditor and security officer roles could read raw records unchecked. Every non-clinical operator role now needs an M-of-N co-signature, and the flow is drivable from the new Dual-Control Access screen with a seeded Security Officer as the second principal.

#### Integrity
- **The laboratory gateway required no credentials** — `/api/v1/webhooks/lis` appended blocks to a patient's chain for anyone who could reach the API, and skipped the write path's sanitiser. It now requires `VHV_LIS_API_KEY` and fails closed.
- **Path traversal through the gateway** — its patient identifier became a directory name, so `../../../escaped_chain` created an LMDB store outside the projects directory. The identifier is validated and the store is confined at the connection manager.
- **The Merkle anchor was always one write behind** — anchoring ran inside the unit of work and read a pre-commit snapshot, so every chain reported "Merkle root mismatch". It now runs after commit.
- **The first record on a new patient chain failed with 500** — seeding the genesis block dropped the LMDB environment underneath the caller's open transaction.

#### Disclosure
- **Cross-patient metadata** — any signed-in patient could read another patient's chain length, Merkle root and anchoring transaction.
- **Device fingerprint** — the unauthenticated liveness probe returned it in full.

#### XSS
- **Inline event handlers forced a permissive CSP** — 76 `onclick`/`onchange`/`oninput`/`onsubmit` attributes meant `script-src` had to allow `'unsafe-inline'`, which is the directive that would have stopped an injected handler from running. All of them are replaced by `data-action` declarations resolved through a delegated dispatcher, and the policy is now `script-src 'self'`. Attachment bytes and record passwords, previously interpolated into `onclick` attributes, are held in a client-side stash and referenced by key.
- **Escaping happened in the wrong layer** — input was HTML-escaped on the way in (twice), which corrupted clinical text permanently in an append-only chain ("Dr. Smith & Co" → "Dr. Smith &amp;amp; Co", a dose of "<5 mg" → "&lt;5 mg") while leaving 31 unescaped render sinks exploitable by any write path that skipped the sanitiser. Text is now stored verbatim and escaped where it is rendered; `unsafe-eval` is gone from the CSP.

### 🩺 Application
- **Fixed**: the record view read fields from a shape the API does not return, so plain records rendered without type, doctor, institution or clinical data, filters and search matched nothing, and the Vaccine Passport and Medications pages threw TypeErrors.
- **Fixed**: Break-Glass could not be triggered — the panel was hidden by inline CSS nothing ever cleared.
- **Fixed**: the ledger activity chart padded quiet days with `Math.random()` values.
- **Fixed**: Chart.js was blocked by the application's own CSP; it is now vendored locally.
- **Added**: Merkle inclusion proof verification from the record view, sidebar entries for Vaccine Passport and Medications, and a demo chart so a fresh clone opens on a working vault.
- **Removed**: the unreachable Sign-In-With-Ethereum path, which called two endpoints that do not exist, and the AI-generated mockups that stood in for screenshots.

### 🧪 Tests
- 101 → 149, covering WebAuthn ceremonies, consent authorisation, Dual-Control, anchoring, the laboratory gateway and clinical text fidelity.

## [5.0.1] - 2026-07-30

### 🛡️ Security Audit Remediation & Architecture Alignment

#### Fixed & Security Hardened
- **Secured OpenAPI Schema & Docs**: Restricted `/api/v1/openapi.json` and OpenAPI docs endpoints behind `IPAllowlistMiddleware` to eliminate public API schema leakage.
- **X-Forwarded-For IP Spoofing Protection**: Hardened `resolve_secure_client_ip` in `backend/middleware/ip_allowlist.py` to only trust proxy headers if `TRUST_PROXIES=true` AND direct socket peer host is loopback or a trusted proxy.
- **Security Officer Role Authorization**: Fixed `Role` validation in `backend/schemas/requests.py` and `backend/routers/alerts.py` to include `security_officer`.
- **Immutable Record Decryption Audit Logging**: Added `RECORD_DECRYPTED` access log emission in `backend/routers/records.py` (`storage.append_access_log`).
- **Passkey Hardware Revocation API**: Implemented `POST /api/v1/auth/webauthn/revoke` endpoint backed by Dual-Control authorization for revoking lost/stolen hardware credentials.
- **Purged Dead Frontend Surface**: Completely purged dead FHIR export buttons, SIWE Web3 wallet login functions, Dead-Man's Switch, and ZKP modals from `index.html`, `app.js`, `auth.js`, and `records.js`.

#### Added
- **`THREAT_MODEL.md`**: Created formal threat model document mapping adversary vectors (external breach, rogue admin, passkey theft, coerced insider) to specific enforcing code.
- **`PRIVATE_VPC_DEPLOYMENT.md`**: Created institutional private VPC/VPN deployment specification documenting air-gapped network topology, persistent storage mounts (`/var/lib/vhv/data`), KVKK Art. 9 compliance, and the Institutional Deployment Gate.
- **`docker-compose.yml`**: Added containerized private VPC deployment configuration with persistent volume mounts (`vhv_db_data`, `vhv_lmdb_data`).

#### Documentation Alignment
- **ADR-0001 Alignment**: Updated `docs/adr/0001-offchain-storage-onchain-anchoring.md` replacing Ethereum `AnchorStore.sol` references with the actual local signed Merkle hash-chain notarization engine (`notarizer.py`).
- **Exact Python Symbol Paths**: Verified 100% exact module and class references (`core.services.notarizer.BlockchainNotarizer`, `core.pseudonymization.engine.PseudonymizationEngine`, `core.kms.provider.KMSProvider`).

---

## [5.0.0] - 2026-07-28

### 🚀 Major Release: Stealth VIP Health Privacy Vault & Hardened Security Architecture

#### Added
- **Dual-Control M-of-N Enforcement**: Hard lock on record decryption and viewing endpoints. System Administrators cannot decrypt raw VIP records without an active Security Officer co-signed token.
- **Network Level Isolation (`IPAllowlistMiddleware`)**: Enforces IP allowlisting restricting API access to internal subnets / private VPNs.
- **Real-Time Security Alert Engine (`alert_service.py`, `backend/routers/alerts.py`)**: Real-time event logging for Break-Glass access, rapid failed login spikes, and dual-control violations.
- **Mandatory FIDO2 Hardware Key Policy**: Policy enforcement option (`MANDATORY_FIDO2=true`) requiring WebAuthn/Passkey hardware keys for privileged personas.
- **Time-Bound Consent Engine (Hours/Days)**: Support for exact hourly consent windows with automatic expiration and `CONSENT_EXPIRED` audit logs.
- **Pseudonymization Engine**: Cryptographic identity decoupling isolating patient PII from medical records via `anon_id`.

#### Removed
- Removed SIWE / Web3 MetaMask wallet login endpoints (`/nonce`, `/wallet-login`).
- Removed Public Sepolia / Web3 contract deployer scripts (`contracts/`, `scripts/deploy_contract.py`).
- Removed ZKP / Pedersen commitment module (`core/zkp/`, `backend/routers/zkp.py`).
- Removed FHIR R4 export bundling (`backend/schemas/fhir.py`).
- Removed Social Recovery / Guardian endpoints (`/auth/recovery/*`).
- Removed Dead-Man's Switch (`backend/routers/deadman.py`) and Emergency QR (`backend/routers/emergency.py`) routers.
- Removed dead dependencies (`web3`, `keyring`) from `requirements.txt`.

#### Fixed & Hardened
- Aligned documentation (`README.md`, `GDPR_KVKK_COMPLIANCE.md`, `DPIA.md`, `CONSENT_FLOW.md`) with codebase reality.
- Enforced 100% test suite pass rate across 77+ unit and integration tests.
