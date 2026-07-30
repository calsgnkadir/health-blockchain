# Changelog — VIP Health Vault

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
