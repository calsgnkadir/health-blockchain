# 🔐 Enterprise Security & Cryptographic Architecture

**VIP Health Vault** employs a zero-trust, defense-in-depth security model engineered specifically for high-confidentiality healthcare datasets (PHI / EHR) and high-profile patient records.

---

## 🛡️ Core Security Architecture & Layers

### 1. Dual-Layer Cryptographic Data Encryption (AES-GCM-256)
- **Off-Chain Encrypted Storage:** Sensitive patient data (FHIR records, clinical attachments, DICOM medical images) is stored off-chain using Galois/Counter Mode (**AES-256-GCM**) with random 96-bit IVs and 128-bit authentication tags.
- **Envelope Encryption:** Key derivation uses **PBKDF2** with 600,000 iterations and 128-bit cryptographic salts.
- **Client-Side E2EE Option:** Patient records can optionally be sealed with AES-256 client-side passwords before being sent to the server.

### 2. Multi-Factor Authentication & Multi-Scheme Identity
- **Sign-In with Ethereum (SIWE - EIP-4361):** Cryptographic Web3 wallet login via EIP-191 ECDSA `personal_sign` message verification.
- **Passkey / WebAuthn Hardware Auth:** Hardware-backed biometric authentication (FIDO2 / TouchID / FaceID / YubiKey) using `navigator.credentials` and secp256r1 signature verification.
- **TOTP (RFC 6238 2FA):** Time-based One-Time Password support with QR code initialization and 6-digit verification.
- **Password Hashing:** **Argon2id** password hashing with high memory-cost parameters.

### 3. JWT Session & Hardware Device Binding
- **RS256 Signature Scheme:** Asymmetric RSA-256 JWT tokens signed with private keys tied to hardware device signatures (`WMI` hardware UUID / Linux system UUID).
- **Token Revocation & Blacklisting:** Token IDs (`jti`) are checked against an active DB blacklist on every request and automatically purged upon expiration.

### 4. Blockchain Integrity & Consensus (Merkle Root Anchoring)
- **Zero Raw PHI On-Chain:** Raw medical data is **NEVER** stored directly on the public Ethereum blockchain to comply with GDPR "Right to be Forgotten" and HIPAA privacy guidelines.
- **Merkle Tree Proofs:** Each patient record block is hashed into a SHA-256 Merkle tree. Only the resulting **Merkle Root** is anchored to the smart contract (`AnchorStore.sol`).
- **Multi-Notary Consensus:** Smart contract notarization requires a 2-of-N multi-sig consensus threshold across authorized notary nodes.

### 5. Application & Web Security Headers
- **XSS Protection Middleware:** Enforces strict `Content-Security-Policy (CSP)`, `X-XSS-Protection`, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: SAMEORIGIN`.
- **Input Sanitization:** Recursive HTML entity escaping and tag stripping against Reflected, Stored, and Header Injection XSS.
- **CSRF Token Verification:** Double-Submit Cookie pattern for state-changing endpoints with path exemptions for OAuth/SIWE nonces.
- **Rate Limiting:** Sliding-window IP rate limiting middleware to prevent brute-force attacks.

---

## 📋 Security Policy & Vulnerability Reporting

If you discover a potential security vulnerability within VIP Health Vault, please do NOT open a public issue. Report findings directly to security@healthchain.org or file a private security report on GitHub.
