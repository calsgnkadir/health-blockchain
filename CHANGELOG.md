# Changelog — VIP Health Vault

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
