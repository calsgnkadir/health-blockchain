"""
core/services/notarizer.py — Local Merkle Hash-Chain Notarizer
================================================================
Calculates and anchors Merkle roots for patient block chains to an isolated,
cryptographically signed local hash-chain (ADR-0001).

Zero public blockchain / Web3 RPC dependencies — ensures 100% stealth and
local tamper-evidence for VIP medical data.
"""

import os
import hashlib
import json
import secrets
from typing import Optional, List, Dict
from core.ports.repositories import IBlockRepository
from core.utils.crypto_utils import calculate_merkle_root


class BlockchainNotarizer:
    """
    Local Merkle tree notarizer for VIP health record chains.
    Computes cryptographic Merkle roots over patient data blocks
    and anchors them into the isolated local ledger.
    """

    def __init__(self, block_repo: IBlockRepository):
        self.block_repo = block_repo

    def _get_project_name(self, patient_id: str) -> str:
        return f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"

    def notarize_patient_chain(self, patient_id: str) -> Optional[str]:
        """
        Computes Merkle Root of patient's block hashes and anchors it locally.
        Returns a local anchor transaction hash.
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
        anchor_tx = f"0x{secrets.token_hex(32)}"

        self.block_repo.save_simulated_merkle_root(project_name, merkle_root_hex)
        self.block_repo.save_notarization_tx(project_name, anchor_tx)

        return anchor_tx

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

        tx_hash = self.block_repo.load_notarization_tx(project_name)
        anchored_root = self.get_on_chain_merkle_root(patient_id)

        if not anchored_root:
            return {
                "verified": False,
                "local_root": f"0x{local_root}",
                "on_chain_root": "N/A",
                "tx_hash": tx_hash,
                "reason": "Not anchored in local ledger"
            }

        clean_local = local_root.lower().strip()
        clean_anchored = anchored_root.lower().strip()
        if clean_anchored.startswith("0x"):
            clean_anchored = clean_anchored[2:]

        verified = (clean_local == clean_anchored)
        return {
            "verified": verified,
            "local_root": f"0x{local_root}",
            "on_chain_root": f"0x{clean_anchored}",
            "tx_hash": tx_hash,
            "reason": "Match" if verified else "Merkle root mismatch"
        }
