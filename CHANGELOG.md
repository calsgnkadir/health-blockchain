# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [4.0.0] - 2026-07-22 — Passkey / WebAuthn + Multi-Notary + SIWE

### Added
- **Passkey / WebAuthn Hardware Authentication (FIDO2):** New `/api/v1/auth/webauthn/challenge`, `/register`, `/login` endpoints; frontend `SIGN-IN WITH PASSKEY / TOUCHID` button using `navigator.credentials` standard W3C API.
- **SIWE (Sign-In with Ethereum) Wallet Login:** Connected MetaMask EIP-4361 flow end-to-end to frontend (`loginWithWeb3Wallet`) via `eth_account.recover_message`.
- **Social Recovery — SQL Persistence:** `guardians` and `recovery_requests` tables added; recovery state is now durable across server restarts.
- **AnchorStore Multi-Notary Consensus:** Smart contract upgraded from single `onlyOwner` to 2-of-N multi-sig `proposeOrApproveRoot()` mechanism.
- **WebAuthn Credential DB Table:** `webauthn_credentials` table with seed passkey credential for out-of-box demo.
- **Test Suite:** `test_webauthn_passkeys.py` added; total 35/35 tests passing.

### Fixed
- `create_token()` signature mismatch in passkey login endpoint — now calls `user_entity.to_dict()`.
- Recovery requests table missing closing SQL quotes (syntax error in `sql_db.py`).

---

## [3.1.0] - 2026-07-10 — XSS Hardening + Phase 3

### Added
- Multi-vector XSS protection middleware (`backend/middleware/xss_protection.py`): CSP headers, X-XSS-Protection, HTML entity escaping.
- CSRF double-submit cookie middleware (`backend/middleware/csrf.py`).
- W3C DID Document generation endpoint (`/api/v1/auth/did/{username}`).
- W3C Verifiable Credential endpoint (`/api/v1/auth/vc/{username}`).
- IPFS off-chain pinning with simulation fallback.
- Break-Glass emergency access with 15-minute time-limited tokens and full audit log.
- `test_xss_hardening.py`, `test_phase3_advanced.py`, `test_siwe_auth.py` test files.

---

## [3.0.0] - 2026-06-25 — Blockchain Notarizer + FHIR + Smart Contracts

### Added
- `AnchorStore.sol` Solidity smart contract for Merkle Root on-chain anchoring.
- `core/services/notarizer.py` with Simulation Mode fallback (no RPC required for demo).
- FHIR R4 schema conversion for all record types (Diagnosis, Prescription, VitalSigns, LabResult).
- Merkle tree computation per patient record chain.
- `test_notarizer.py`, `test_fhir.py`, `test_ipfs.py` test files.

---

## [2.0.0] - 2026-06-15 — Clean Architecture + CQRS Refactor

### Added
- Full 4-layer Clean Architecture (Domain → Ports → Infrastructure → Presentation).
- CQRS separation of read/write operations in service layer.
- LMDB-backed repository with port/interface abstraction.
- RS256 JWT with hardware device fingerprint binding.
- Argon2id password hashing.
- TOTP 2-Factor Authentication with QR code generation.
- Rate limiting middleware.

---

## [1.0.0] - 2026-06-01 — Initial Release

### Added
- Initial blockchain-linked health record system.
- AES-256-GCM dual-layer encryption.
- Patient record CRUD with per-block SHA-256 hashing.
- Basic login/logout with SQLite user store.
