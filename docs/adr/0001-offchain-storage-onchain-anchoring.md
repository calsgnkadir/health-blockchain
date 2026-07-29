# ADR 0001: Off-Chain Storage with Cryptographic Merkle Root Hash-Chain Notarization

**Status:** Accepted (Updated for v5.0.0 Architecture)  
**Date:** 2026-06-20 (Revised: 2026-07-29)  
**Deciders:** Security Engineering & Protocol Architecture Team  

---

## Context and Problem Statement

The platform manages high-confidentiality Protected Health Information (PHI) and Electronic Health Records (EHR) for VIP patients (cabinet ministers, defense personnel, high-net-worth individuals).
We required an architecture guaranteeing **data immutability, tamper-evidence, and auditability** while strictly obeying **GDPR / KVKK privacy laws** (specifically Article 17 "Right to be Forgotten" and KVKK M.7 pseudonymization rules).

Publishing raw PHI or encrypted payloads to a public blockchain (like Ethereum or Polygon) creates severe security and regulatory risks:
1. **Public Metadata & Cryptographic Decay:** Data on a public ledger cannot be deleted. Encrypted payloads posted publicly risk future decryption via quantum computing or key compromise.
2. **GDPR / KVKK Non-Compliance:** GDPR Art. 17 and KVKK M.7 grant data subjects erasure rights. Public immutability makes legal compliance impossible.
3. **Public Network Footprint:** Interacting with public RPC nodes creates network metadata trails connecting VIP identities to public ledger addresses (`0x...`).

---

## Decision Drivers

* **Zero Public RPC / Web3 Dependencies:** Eliminate external metadata trails and public ledger privacy leaks.
* **Strict GDPR / KVKK Compliance:** Enable full cryptographic right-to-erasure via key destruction.
* **Immutable Tamper-Evidence:** Ensure no single rogue administrator or compromised component can silently mutate historical clinical records.
* **Air-Gapped Private Network Compatibility:** Operate within isolated institutional VPC / VPN subnets.

---

## Considered Options

1. **Public Blockchain Encrypted Storage:** Encrypt PHI and publish directly to public smart contract storage.
2. **Traditional Relational Database Only:** Store health data in a standard SQL database without cryptographic anchoring.
3. **Isolated Hybrid Architecture (Off-Chain Encrypted Storage + Local Signed Merkle Root Hash-Chain Notarization):** Store AES-256-GCM encrypted health records off-chain (LMDB) and anchor cryptographic Merkle Root hashes to an isolated local signed hash-chain (`notarizer.py`).

---

## Decision Outcome

**Chosen Option:** **Option 3 — Isolated Hybrid Architecture (Off-Chain Storage + Local Signed Merkle Hash-Chain Notarization)**.

### Architectural Mechanics:
1. **Off-Chain Encrypted Storage:** Patient record payloads are encrypted using **AES-256-GCM** with per-record salt/IV vectors and stored in high-performance LMDB.
2. **Merkle Tree Computation:** Patient block headers are aggregated into a cryptographic Merkle tree, generating a single 32-byte **Merkle Root**.
3. **Signed Hash-Chain Notarization:** Merkle roots are signed with HMAC-SHA256 and appended to an isolated sequential hash-chain (`notarizer.py`). No public Web3 or Ethereum RPC calls are performed.
4. **Tamper Verification:** Any modification to off-chain data invalidates the Merkle Root proof (`GET /api/v1/records/proof/{patient_id}/{block_index}`).
5. **GDPR / KVKK Erasure:** Destroying the off-chain encryption key or LMDB entry permanently renders the PHI unreadable, leaving only an un-linkable mathematical hash behind.

---

## Consequences

* **Positive:** 100% GDPR/KVKK compliant, zero public Web3 privacy leaks, zero gas fees, instant local query speeds, air-gapped VPC deployment compatible.
* **Negative:** Hash-chain immutability guarantees operate within the institutional trust boundary against external breaches and post-hoc log tampering.
