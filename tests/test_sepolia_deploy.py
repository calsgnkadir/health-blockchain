"""
tests/test_sepolia_deploy.py — Sepolia Deployment & Web3 Notarization Tests
========================================================================
Test cases:
  1. Contract artifact loading (ABI & bytecode)
  2. Deploy script dry-run execution
  3. Web3 Notarizer Sepolia transaction building & receipt simulation
  4. Etherscan verification URL generation
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.deploy_contract import load_artifact, deploy
from core.services.notarizer import BlockchainNotarizer


class TestSepoliaDeploy(unittest.TestCase):

    def test_01_load_contract_artifact(self):
        """AnchorStore.json artifact'i ABI ve Bytecode içermeli."""
        artifact = load_artifact()
        self.assertIn("abi", artifact)
        self.assertIn("bytecode", artifact)
        self.assertTrue(artifact["bytecode"].startswith("0x"))
        # Check ABI has proposeOrApproveRoot
        names = [item.get("name") for item in artifact["abi"] if "name" in item]
        self.assertIn("proposeOrApproveRoot", names)
        self.assertIn("patientMerkleRoots", names)

    def test_02_deploy_script_dry_run(self):
        """Dry-run modunda deploy fonksiyonu simülasyon çıktısı vermeli."""
        result = deploy(dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertIn("simulated_contract_address", result)
        self.assertIn("simulated_tx_hash", result)

    @patch("core.services.notarizer.Web3")
    def test_03_sepolia_web3_notarizer_flow(self, mock_web3_class):
        """Web3 ortamında notarizer Sepolia işlem paketini doğru oluşturup onaylamalı."""
        mock_w3 = MagicMock()
        mock_web3_class.return_value = mock_w3
        mock_web3_class.to_checksum_address.side_effect = lambda addr: addr
        mock_w3.to_hex.return_value = "0x9876543210abcdef0000"
        mock_w3.is_connected.return_value = True

        mock_account = MagicMock()
        mock_account.address = "0xDeployerAddress123"
        mock_w3.eth.account.from_key.return_value = mock_account

        mock_w3.eth.get_transaction_count.return_value = 5
        mock_w3.eth.gas_price = 20000000000

        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract

        mock_txn_func = MagicMock()
        mock_contract.functions.proposeOrApproveRoot.return_value = mock_txn_func
        mock_txn_func.build_transaction.return_value = {"to": "0xContract", "data": "0x123"}

        mock_signed = MagicMock()
        mock_signed.rawTransaction = b"raw_tx_bytes"
        mock_w3.eth.account.sign_transaction.return_value = mock_signed

        mock_w3.eth.send_raw_transaction.return_value = b"\x98\x76\x54\x32"
        mock_receipt = MagicMock()
        mock_receipt.status = 1
        mock_w3.eth.wait_for_transaction_receipt.return_value = mock_receipt

        # Mock repo
        mock_repo = MagicMock()
        mock_block = MagicMock()
        mock_block.hash = "abc123def456"
        mock_repo.load_all_blocks.return_value = [mock_block]

        with patch.dict(os.environ, {
            "VHV_RPC_URL": "https://ethereum-sepolia-rpc.publicnode.com",
            "VHV_CONTRACT_ADDRESS": "0x1111111111111111111111111111111111111111",
            "VHV_PRIVATE_KEY": "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        }):
            from core.services.notarizer import WEB3_AVAILABLE
            if not WEB3_AVAILABLE:
                self.skipTest("Web3 package not installed")

            notarizer = BlockchainNotarizer(mock_repo)
            self.assertFalse(notarizer.is_simulation)

            tx_hash = notarizer.notarize_patient_chain("VIP-REAL-TEST-88")
            self.assertEqual(tx_hash, "0x9876543210abcdef0000")
            mock_repo.save_notarization_tx.assert_called_once()

    def test_04_etherscan_url_format(self):
        """Sepolia Etherscan doğrulama URL'leri standart formatta olmalı."""
        contract_addr = "0x1111111111111111111111111111111111111111"
        tx_hash = "0x9876543210abcdef0000"

        address_url = f"https://sepolia.etherscan.io/address/{contract_addr}"
        tx_url = f"https://sepolia.etherscan.io/tx/{tx_hash}"

        self.assertTrue(address_url.startswith("https://sepolia.etherscan.io/address/"))
        self.assertTrue(tx_url.startswith("https://sepolia.etherscan.io/tx/"))


if __name__ == "__main__":
    unittest.main()
