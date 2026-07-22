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

    @patch('core.services.notarizer.WEB3_AVAILABLE', True)
    def test_real_web3_notarization_mocked(self):
        # Test the real Web3 pathway by mocking the Web3 providers and accounts
        mock_web3 = MagicMock()
        mock_contract = MagicMock()
        
        # Mock connection status
        mock_web3.is_connected.return_value = True
        mock_web3.eth.chain_id = 11155111  # Sepolia
        mock_web3.eth.gas_price = 20000000000
        mock_web3.eth.get_transaction_count.return_value = 5
        mock_web3.to_hex.return_value = "0x9876543210abcdef0000"
        
        # Mock signed transaction and Account from key
        mock_account = MagicMock()
        mock_account.address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
        mock_web3.eth.account.from_key.return_value = mock_account
        
        mock_signed = MagicMock()
        mock_signed.rawTransaction = b"signed_tx_raw_bytes"
        mock_web3.eth.account.sign_transaction.return_value = mock_signed
        mock_web3.eth.send_raw_transaction.return_value = b"tx_hash_bytes"
        
        mock_receipt = MagicMock()
        mock_receipt.status = 1
        mock_web3.eth.wait_for_transaction_receipt.return_value = mock_receipt
        
        # Mock contract function transaction builder
        mock_func = MagicMock()
        mock_func.build_transaction.return_value = {"to": "0xContract", "data": "0xData"}
        mock_contract.functions.updateRoot.return_value = mock_func
        mock_web3.eth.contract.return_value = mock_contract

        # Instantiate BlockchainNotarizer with mocked Web3.py environment
        with patch('core.services.notarizer.Web3', return_value=mock_web3, create=True), \
             patch.dict(os.environ, {
                 "VHV_RPC_URL": "https://sepolia.infura.io/v3/projectid",
                 "VHV_CONTRACT_ADDRESS": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
                 "VHV_PRIVATE_KEY": "0x0000000000000000000000000000000000000000000000000000000000000001"
             }):
            real_notarizer = BlockchainNotarizer(self.block_repo)
            self.assertFalse(real_notarizer.is_simulation)
            
            patient_id = "VIP-REAL-TEST-88"
            project_name = f"patient_{patient_id.replace('-', '_')}"
            
            # Seed a block (which triggers automatic notarization)
            self.record_service.add_record(patient_id, {"data": "test"}, username="dr.test")
            
            # Reset mock call counts so we can test the explicit call once
            mock_web3.eth.account.from_key.reset_mock()
            mock_contract.functions.updateRoot.reset_mock()
            mock_web3.eth.send_raw_transaction.reset_mock()
            
            # Trigger real notarization method manually to test execution flow
            tx_hash = real_notarizer.notarize_patient_chain(patient_id)
            
            # Assertions on mock calls
            self.assertEqual(tx_hash, "0x9876543210abcdef0000")
            mock_web3.eth.account.from_key.assert_called_once()
            mock_contract.functions.updateRoot.assert_called_once()
            mock_web3.eth.send_raw_transaction.assert_called_once_with(b"signed_tx_raw_bytes")
            
            # Verify saved tx_hash
            saved_tx = self.block_repo.load_notarization_tx(project_name)
            self.assertEqual(saved_tx, tx_hash)

if __name__ == '__main__':
    unittest.main()
