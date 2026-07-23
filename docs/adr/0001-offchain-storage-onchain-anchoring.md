# ADR 0001: Off-Chain Storage with On-Chain Merkle Root Anchoring

**Status:** Accepted
**Date:** 2026-06-20
**Deciders:** Core Engineering Team

---

## Context and Problem Statement

The platform is designed to manage high-confidentiality Protected Health Information (PHI) and Electronic Health Records (EHR) for VIP patients.
We needed a technical design that guarantees **data immutability, auditability, and tamper-proofing** while strictly respecting **GDPR/HIPAA privacy regulations** (specifically the "Right to be Forgotten" and strict access controls).

Storing raw PHI or raw encrypted blobs directly on a public blockchain (like Ethereum or Polygon) presents critical trade-offs:
1. **Public Immutability Conflict:** Data on a public blockchain cannot be deleted. If encrypted PHI is posted on-chain, future cryptographic breakthroughs (e.g. quantum computing) could compromise privacy indefinitely.
2. **GDPR Compliance Violation:** GDPR Article 17 grants patients the right to request erasure of personal data. Raw on-chain data makes compliance legally impossible.
3. **Transaction Cost & Bandwidth Constraints:** Storing high-resolution DICOM medical images or PDF health reports on-chain incurs prohibitively high Gas fees.

---

## Decision Drivers

* Strict compliance with GDPR & HIPAA regulations.
* Absolute protection against unauthorized disclosure or future cryptographic decay.
* Immutable auditability so no party can secretly tamper with medical histories.
* Low latency and high throughput for clinical workflows.

---

## Considered Options

1. **On-Chain Encrypted Storage:** Encrypt raw health data and publish directly to smart contract storage.
2. **Pure Off-Chain Database:** Store health data in traditional relational or document databases without blockchain.
3. **Hybrid Architecture (Off-Chain Storage + On-Chain Merkle Root Anchoring):** Store encrypted health records off-chain (LMDB / IPFS) and anchor only the cryptographic Merkle Root hashes to an Ethereum smart contract.

---

## Decision Outcome

**Chosen Option:** **Option 3 — Hybrid Architecture (Off-Chain Encrypted Storage + On-Chain Merkle Root Anchoring)**.

### How It Works:
1. **Off-Chain Storage:** Patient record payloads are encrypted using **AES-256-GCM** with unique salts/IVs and stored in high-performance LMDB or decentralized IPFS nodes.
2. **Merkle Tree Computation:** Patient block headers are grouped into a cryptographic Merkle tree, yielding a single 32-byte **Merkle Root**.
3. **Smart Contract Notarization:** Only the 32-byte Merkle Root is notarized to the `AnchorStore.sol` smart contract via a 2-of-N Multi-Notary consensus mechanism.
4. **Tamper Verification:** Any modification to off-chain data invalidates the Merkle Root proof (`GET /api/v1/records/proof/{patient_id}/{block_index}`).
5. **GDPR Erasure:** Deleting the off-chain encryption key or LMDB entry permanently destroys the readable data while leaving the immutable Merkle Root as an un-linkable mathematical proof.

---

## Consequences

* **Positive:** 100% GDPR/HIPAA compliant, zero raw PHI on public ledgers, negligible Ethereum gas costs, instant query speeds.
* **Negative:** Requires managing off-chain storage key lifecycles and IPFS pinning services.
