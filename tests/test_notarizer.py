import os
import shutil
import unittest
import sys
from unittest.mock import MagicMock, patch

# Setup project root import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import LMDBConnectionManager
from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
from core.services.record_service import RecordService
from core.services.notarizer import BlockchainNotarizer
from core.utils.crypto_utils import calculate_merkle_root

class TestBlockchainNotarizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_projects_notary")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_manager = LMDBConnectionManager(self.test_dir)
        self.block_repo = LMDBBlockRepository(self.db_manager)
        self.crypto_strategy = AESGCMStrategy()
        self.record_service = RecordService(self.block_repo, self.crypto_strategy)
        
        # Override VHV env vars to guarantee Simulation Mode for base tests
        self.env_patcher = patch.dict(os.environ, {
            "VHV_RPC_URL": "",
            "VHV_CONTRACT_ADDRESS": "",
            "VHV_PRIVATE_KEY": ""
        })
        self.env_patcher.start()
        self.notarizer = BlockchainNotarizer(self.block_repo)

    def tearDown(self):
        self.env_patcher.stop()
        self.db_manager.close_all()
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_merkle_root_computation(self):
        # Calculate Merkle Root of an array of hashes manually
        hashes = [
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", # hash of empty string
            "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae"  # hash of "foo"
        ]
        computed_root = calculate_merkle_root(hashes)
        self.assertIsNotNone(computed_root)
        self.assertEqual(len(computed_root), 64)

    def test_simulated_notarization_flow(self):
        patient_id = "VIP-TEST-100"
        project_name = f"patient_{patient_id.replace('-', '_')}"
        
        # Add a block to the patient's chain
        data = {"record_type": "vital_signs", "title": "Checkup", "data": {"hr": 75}}
        block = self.record_service.add_record(patient_id, data, username="dr.notary")
        self.assertIsNotNone(block)
        
        # Verify that notarization transaction was auto-saved during add_record
        tx_hash = self.block_repo.load_notarization_tx(project_name)
        self.assertIsNotNone(tx_hash)
        self.assertTrue(tx_hash.startswith("0x"))
        
        # Check simulated Merkle Root in storage
        stored_root = self.block_repo.load_simulated_merkle_root(project_name)
        self.assertIsNotNone(stored_root)
        
        # Run on-chain verification
        verification = self.notarizer.verify_on_chain(patient_id)
        self.assertTrue(verification["verified"])
        self.assertEqual(verification["tx_hash"], tx_hash)
        self.assertEqual(verification["reason"], "Match")

    def test_verify_on_chain_unanchored(self):
        patient_id = "VIP-UNANCHORED-999"
        
        # Querying verification for non-existent chain
        verification = self.notarizer.verify_on_chain(patient_id)
        self.assertFalse(verification["verified"])
        self.assertEqual(verification["reason"], "No local blocks found")

if __name__ == '__main__':
    unittest.main()
