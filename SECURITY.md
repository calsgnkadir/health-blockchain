# 🔐 Enterprise Security & Cryptographic Architecture (v5.0.0)

**VIP Health Vault** employs a zero-trust, defense-in-depth security model engineered specifically for high-confidentiality healthcare datasets (PHI / EHR) and high-profile patient records.

---

## 🛡️ Core Security Architecture & Layers

### 1. Dual-Layer Cryptographic Data Encryption (AES-GCM-256)
- **Off-Chain Encrypted Storage:** Sensitive patient data is stored off-chain using Galois/Counter Mode (**AES-256-GCM**) with random 96-bit IVs and 128-bit authentication tags.
- **Envelope Encryption:** Key derivation uses **PBKDF2** with 600,000 iterations and 128-bit cryptographic salts.
- **Client-Side E2EE Option:** Patient records can optionally be sealed with AES-256 client-side passwords before being sent to the server.

### 2. Multi-Factor Authentication & Identity Hardening
- **Passkey / WebAuthn Hardware Auth:** Hardware-backed biometric authentication (FIDO2 / TouchID / FaceID / YubiKey) using `navigator.credentials` and secp256r1 signature verification.
- **TOTP (RFC 6238 2FA):** Time-based One-Time Password support with 6-digit verification.
- **Password Hashing:** **Argon2id** password hashing with high memory-cost parameters.

### 3. Dual-Control M-of-N Approval Engine
- **Anti-Insider Threat Protection:** System Administrators **cannot** unilaterally view or decrypt raw VIP medical records.
- **Security Officer Co-Signature:** Privileged decryption requires an active token co-signed by an authorized Security Officer (`security_officer` role).

### 4. Local Cryptographic Hash-Chain (Merkle Root Anchoring)
- **Zero Raw PHI On-Chain:** Raw medical data is **NEVER** stored directly on any public blockchain to comply with GDPR "Right to be Forgotten" and HIPAA privacy guidelines.
- **Merkle Tree Proofs:** Patient record blocks are hashed into a SHA-256 Merkle tree. Only the resulting **32-byte Merkle Root** is anchored into the isolated, local signed Merkle Hash-Chain (ADR-0001).

### 5. Application & Network Level Security
- **Network Level Isolation:** `IPAllowlistMiddleware` blocks public internet access attempts, accepting requests exclusively from authorized CIDR subnets and private VPNs.
- **XSS Protection Middleware:** Enforces strict `Content-Security-Policy (CSP)`, `X-XSS-Protection`, `X-Content-Type-Options: nosniff`, and `X-Frame-Options: SAMEORIGIN`.
- **Output Encoding:** Clinical text is stored verbatim and HTML-escaped at the point of rendering (`escapeHtml` in the web client). Escaping on input was removed deliberately: it corrupted medical text permanently in an append-only chain, and left any unescaped sink exploitable anyway.
- **CSRF Token Verification:** Double-Submit Cookie pattern for state-changing endpoints.
- **Rate Limiting:** Sliding-window IP rate limiting middleware to prevent brute-force attacks.

---

## 📋 Security Policy & Vulnerability Reporting

If you discover a potential security vulnerability within VIP Health Vault, please report findings directly to security@healthchain.org or file a private security report on GitHub.
