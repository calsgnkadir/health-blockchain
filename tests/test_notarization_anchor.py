"""
tests/test_notarization_anchor.py — the anchored root must track the live chain
==============================================================================
The Merkle root is anchored from inside the same code path that appends blocks.
If it is computed before the unit of work commits, the anchor lags one write
behind for ever and the vault reports "Merkle root mismatch" on every chain it
has ever written — the exact opposite of the tamper-evidence claim.
"""

import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.storage as storage
from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
from core.services.record_service import RecordService
from core.services.notarizer import BlockchainNotarizer
from core.cqrs.commands import AddRecordCommand, CommandHandler

PATIENT_ID = "VIP-ANCHOR-1"


class TestNotarizationAnchor(unittest.TestCase):
    def setUp(self):
        # LMDBUnitOfWork transacts against the default connection manager, so the
        # command handler must be exercised against that same store.
        self.block_repo = LMDBBlockRepository()
        self.record_service = RecordService(self.block_repo, AESGCMStrategy())
        self.notarizer = BlockchainNotarizer(self.block_repo)
        self.handler = CommandHandler(self.record_service, None, self.block_repo)
        self.project = self.record_service._get_project_name(PATIENT_ID)
        storage.reset_db(self.project)

    def tearDown(self):
        storage.reset_db(self.project)

    def _add(self, title, protected=False, password=None):
        return self.handler.handle_add_record(AddRecordCommand(
            patient_id=PATIENT_ID,
            data={"record_type": "vital_signs", "title": title, "data": {"heart_rate": "72"}},
            is_protected=protected,
            protection_password=password,
            username="dr.anchor",
        ))

    def test_anchor_verifies_immediately_after_a_write(self):
        self._add("First observation")
        result = self.notarizer.verify_on_chain(PATIENT_ID)
        self.assertTrue(result["verified"], result["reason"])

    def test_anchor_keeps_up_across_successive_writes(self):
        for i in range(4):
            self._add(f"Observation {i}")
            result = self.notarizer.verify_on_chain(PATIENT_ID)
            self.assertTrue(result["verified"], f"stale anchor after write {i}: {result['reason']}")

    def test_anchor_tracks_protected_records_too(self):
        self._add("Plain note")
        self._add("Sealed note", protected=True, password="SuperSecret123!@#")
        result = self.notarizer.verify_on_chain(PATIENT_ID)
        self.assertTrue(result["verified"], result["reason"])

    def test_anchored_root_matches_the_full_committed_chain(self):
        self._add("Observation A")
        self._add("Observation B")
        chain = self.block_repo.load_all_blocks(self.project)

        from core.utils.crypto_utils import calculate_merkle_root
        live_root = calculate_merkle_root([b.hash for b in chain if b.hash])
        self.assertEqual(self.block_repo.load_simulated_merkle_root(self.project), live_root)

    def test_tampering_with_the_chain_breaks_verification(self):
        """The anchor is only worth anything if a changed block invalidates it."""
        block = self._add("Observation to tamper with")
        block.data = {"record_type": "vital_signs", "title": "Silently rewritten", "data": {}}
        block.hash = block.calculate_hash() if hasattr(block, "calculate_hash") else "0" * 64
        self.block_repo.save_block(self.project, block)

        result = self.notarizer.verify_on_chain(PATIENT_ID)
        self.assertFalse(result["verified"])


if __name__ == "__main__":
    unittest.main()


class TestNewChainBootstrap(unittest.TestCase):
    """The first record written to a patient chain must not fail."""

    NEW_PATIENT = "VIP-BOOTSTRAP-1"

    def setUp(self):
        self.block_repo = LMDBBlockRepository()
        self.record_service = RecordService(self.block_repo, AESGCMStrategy())
        self.notarizer = BlockchainNotarizer(self.block_repo)
        self.handler = CommandHandler(self.record_service, None, self.block_repo)
        self.project = self.record_service._get_project_name(self.NEW_PATIENT)
        storage.reset_db(self.project)

    def tearDown(self):
        storage.reset_db(self.project)

    def test_first_record_on_an_empty_chain_succeeds(self):
        block = self.handler.handle_add_record(AddRecordCommand(
            patient_id=self.NEW_PATIENT,
            data={"record_type": "vital_signs", "title": "First contact", "data": {"heart_rate": "72"}},
            is_protected=False,
            protection_password=None,
            username="dr.er",
        ))
        self.assertIsNotNone(block)

        chain = self.block_repo.load_all_blocks(self.project)
        self.assertEqual(chain[0].index, 0, "genesis block must be present")
        self.assertTrue(self.notarizer.verify_on_chain(self.NEW_PATIENT)["verified"])
