"""
core/services/notarizer.py — Local Merkle Hash-Chain Notarizer
================================================================
Calculates and anchors Merkle roots for patient block chains to an isolated,
cryptographically signed local hash-chain (ADR-0001).

Zero public blockchain / Web3 RPC dependencies — ensures 100% stealth and
local tamper-evidence for VIP medical data.
"""

import hmac
from typing import Optional, Dict
from core.ports.repositories import IBlockRepository
from core.utils.crypto_utils import calculate_merkle_root
from core.pseudonymization.service import project_name_for
from core.security import signaturedata


class BlockchainNotarizer:
    """
    Local Merkle tree notarizer for VIP health record chains.
    Computes cryptographic Merkle roots over patient data blocks
    and anchors them into the isolated local ledger.
    """

    def __init__(self, block_repo: IBlockRepository):
        self.block_repo = block_repo

    def _get_project_name(self, patient_id: str) -> str:
        return project_name_for(patient_id)

    def notarize_patient_chain(self, patient_id: str) -> Optional[str]:
        """
        Computes the Merkle root of the patient's block hashes and anchors it
        locally with a real signature.

        The anchor is an HMAC-SHA256 signature of the Merkle root under the
        server's KMS signing key (``core.security.signaturedata``) — a verifiable
        commitment that this chain state was notarized here. Only the key-holder
        can produce it, so an attacker who alters the chain cannot forge a
        matching anchor. It is deliberately *not* a public-chain transaction hash;
        see ADR-0001. Returns the anchor signature.
        """
        project_name = self._get_project_name(patient_id)
        chain = self.block_repo.load_all_blocks(project_name)
        if not chain:
            return None

        # Extract block hashes in index order
        hashes = [b.hash for b in chain if b.hash]
        if not hashes:
            return None

        merkle_root_hex = calculate_merkle_root(hashes)
        anchor_signature = signaturedata(merkle_root_hex)

        self.block_repo.save_simulated_merkle_root(project_name, merkle_root_hex)
        self.block_repo.save_notarization_tx(project_name, anchor_signature)

        return anchor_signature

    def get_on_chain_merkle_root(self, patient_id: str) -> Optional[str]:
        """
        Queries the anchored local Merkle Root for a patient.
        """
        project_name = self._get_project_name(patient_id)
        return self.block_repo.load_simulated_merkle_root(project_name)

    def verify_on_chain(self, patient_id: str) -> Dict[str, str]:
        """
        Verifies local blocks chain Merkle root against the anchored root.
        """
        project_name = self._get_project_name(patient_id)
        chain = self.block_repo.load_all_blocks(project_name)
        if not chain:
            return {"verified": False, "reason": "No local blocks found", "tx_hash": None}

        hashes = [b.hash for b in chain if b.hash]
        local_root = calculate_merkle_root(hashes)

        stored_signature = self.block_repo.load_notarization_tx(project_name)
        anchored_root = self.get_on_chain_merkle_root(patient_id)

        if not anchored_root:
            return {
                "verified": False,
                "local_root": f"0x{local_root}",
                "on_chain_root": "N/A",
                "tx_hash": stored_signature,
                "reason": "Not anchored in local ledger"
            }

        clean_local = local_root.lower().strip()
        clean_anchored = anchored_root.lower().strip()
        if clean_anchored.startswith("0x"):
            clean_anchored = clean_anchored[2:]

        roots_match = (clean_local == clean_anchored)
        # The anchor is only trustworthy if it is a valid signature of the
        # anchored root under our key: recompute it and compare in constant time.
        expected_signature = signaturedata(anchored_root)
        signature_valid = bool(stored_signature) and hmac.compare_digest(
            str(stored_signature), expected_signature
        )
        verified = roots_match and signature_valid

        if verified:
            reason = "Match"
        elif not roots_match:
            reason = "Merkle root mismatch"
        else:
            reason = "Anchor signature invalid"

        return {
            "verified": verified,
            "local_root": f"0x{local_root}",
            "on_chain_root": f"0x{clean_anchored}",
            "tx_hash": stored_signature,
            "reason": reason
        }
