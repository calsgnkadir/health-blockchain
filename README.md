# VIP Health Vault (v5.0.0) — Stealth VIP Health Privacy Platform

> **Isolated, High-Security Medical Privacy Vault for High-Net-Worth Individuals, Executive Cabinets, and Defense Personnel.**

---

## 🛡️ Core Security Architecture

The **VIP Health Vault** is engineered strictly for isolated, high-security single-tenant deployments. Unlike generic commercial SaaS health applications, this vault prioritizes **attack surface reduction, metadata privacy, and insider-threat mitigation**.

1. **Local Cryptographic Hash-Chain (ADR-0001)**:
   - Eliminates public blockchain transaction timing leaks (Etherscan/Sepolia).
   - Anchors patient block trees into an isolated, locally-signed Merkle Hash-Chain.
2. **KMS-Driven AES-256-GCM Double-Layer Encryption**:
   - Off-chain LMDB storage with AES-256-GCM payload encryption.
   - Abstracted KMS envelope encryption support (Software, AWS KMS, HashiCorp Vault).
3. **Pseudonymization Engine (PII Decoupling)**:
   - Complete cryptographic isolation between real patient identities (`full_name`, `TCKN/SSN`) and medical record blocks (`anon_id`).
4. **Time-Bound Granular RBAC & Consent Engine**:
   - Doctors receive strictly time-bound hours/days consent windows.
   - Instant auto-expiration with immutable `CONSENT_EXPIRED` audit logging.
5. **Network-Level Isolation (`IPAllowlistMiddleware`)**:
   - Blocks public internet access attempts. Accepts connections exclusively from authorized CIDR subnets, private VPNs, and internal networks.
6. **Dual-Control M-of-N Approval Engine (`dual_control.py`)**:
   - Prevents insider-threat abuses. System Administrators **cannot** view or decrypt raw VIP medical records without an active Security Officer co-signed token.
7. **Hardware Passkey / WebAuthn First**:
   - Donanım tabanlı FIDO2 / YubiKey authentication for primary and multi-factor authentication.
8. **Real-Time Security Alert & Anomaly Engine (`alert_service.py`)**:
   - Real-time detection and alert logging for Break-Glass events, rapid failed login spikes, or unauthorized IP access attempts.

---

## ⚡ Quick Start

### Prerequisites
- Python 3.10+
- Virtualenv (`python -m venv venv`)

### Installation & Run

```bash
# 1. Clone repository
git clone https://github.com/calsgnkadir/health-blockchain.git
cd health-blockchain

# 2. Install lightweight dependencies
pip install -r requirements.txt

# 3. Launch application server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Access the Stealth Vault Web Console at: `http://127.0.0.1:8000`

---

## 🧪 Running Automated Test Suite

```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## ⚖️ Compliance & Governance

- **GDPR / KVKK**: Complete compliance via identity pseudonymization and strict time-bound consent.
- **ISO 27001 / INFOSEC**: Full cryptographic access audit logs and Dual-Control co-signatures for privileged operations.
