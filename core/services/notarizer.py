import os
import hashlib
import json
import secrets
from typing import Optional, List
from core.ports.repositories import IBlockRepository
from core.utils.crypto_utils import calculate_merkle_root

# Try to import Web3
try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    Web3 = None
    WEB3_AVAILABLE = False

ANCHOR_ABI = [
  {
    "inputs": [
      {
        "internalType": "string",
        "name": "patientId",
        "type": "string"
      },
      {
        "internalType": "bytes32",
        "name": "root",
        "type": "bytes32"
      }
    ],
    "name": "updateRoot",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "inputs": [
      {
        "internalType": "string",
        "name": "",
        "type": "string"
      }
    ],
    "name": "patientMerkleRoots",
    "outputs": [
      {
        "internalType": "bytes32",
        "name": "",
        "type": "bytes32"
      }
    ],
    "stateMutability": "view",
    "type": "function"
  }
]

class BlockchainNotarizer:
    def __init__(self, block_repo: IBlockRepository):
        self.block_repo = block_repo
        
        self.rpc_url = os.getenv("VHV_RPC_URL")
        self.contract_address = os.getenv("VHV_CONTRACT_ADDRESS")
        self.private_key = os.getenv("VHV_PRIVATE_KEY")
        
        self.is_simulation = not (WEB3_AVAILABLE and self.rpc_url and self.contract_address and self.private_key)
        
        if not self.is_simulation:
            try:
                self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
                self.contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(self.contract_address),
                    abi=ANCHOR_ABI
                )
                # Verify connection
                if not self.w3.is_connected():
                    print("[Notarizer] RPC provider not connected. Falling back to Simulation Mode.")
                    self.is_simulation = True
            except Exception as e:
                print(f"[Notarizer] Web3 initialization failed ({e}). Falling back to Simulation Mode.")
                self.is_simulation = True

        if self.is_simulation:
            print("[Notarizer] Running in Simulation Mode (Sepolia/Polygon Testnet mocked)")

    def _get_project_name(self, patient_id: str) -> str:
        return f"patient_{patient_id.replace('-', '_').replace(' ', '_')}"

    def notarize_patient_chain(self, patient_id: str) -> Optional[str]:
        """
        Computes Merkle Root of patient's block hashes and notarizes it to smart contract.
        Returns the transaction hash.
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
        
        if self.is_simulation:
            # Simulation Mode
            sim_tx = f"0x{secrets.token_hex(32)}"
            self.block_repo.save_simulated_merkle_root(project_name, merkle_root_hex)
            self.block_repo.save_notarization_tx(project_name, sim_tx)
            print(f"[Notarizer Simulation] Patient {patient_id} Merkle Root: {merkle_root_hex} anchored. Tx: {sim_tx}")
            return sim_tx
            
        # Real Web3 Mode
        try:
            account = self.w3.eth.account.from_key(self.private_key)
            sender_address = account.address
            
            # Convert hex string (e.g. 64 chars) to 32 bytes
            merkle_bytes = bytes.fromhex(merkle_root_hex)
            
            nonce = self.w3.eth.get_transaction_count(sender_address)
            gas_price = self.w3.eth.gas_price
            
            # Build transaction (Multi-Notary proposeOrApproveRoot or legacy updateRoot)
            if hasattr(self.contract.functions, "proposeOrApproveRoot"):
                txn_func = self.contract.functions.proposeOrApproveRoot(patient_id, merkle_bytes)
            else:
                txn_func = self.contract.functions.updateRoot(patient_id, merkle_bytes)

            txn = txn_func.build_transaction({
                'from': sender_address,
                'nonce': nonce,
                'gas': 200000,
                'gasPrice': gas_price
            })
            
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=self.private_key)
            
            # Send raw transaction
            tx_hash_bytes = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash_str = self.w3.to_hex(tx_hash_bytes)
            
            # Wait for transaction receipt confirmation
            print(f"[Notarizer On-Chain] Sent Tx: {tx_hash_str}. Waiting for receipt confirmation...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)
            if receipt.status != 1:
                raise RuntimeError(f"On-chain transaction failed/reverted: {tx_hash_str}")
            
            # Save tx hash locally
            self.block_repo.save_notarization_tx(project_name, tx_hash_str)
            print(f"[Notarizer On-Chain] Patient {patient_id} root notarized successfully. Tx: {tx_hash_str}")
            return tx_hash_str
        except Exception as e:
            print(f"[Notarizer Error] Failed to publish root on-chain: {e}")
            raise RuntimeError(f"On-chain notarization failed: {e}")

    def get_on_chain_merkle_root(self, patient_id: str) -> Optional[str]:
        """
        Queries on-chain Merkle Root from smart contract or simulated local store.
        """
        project_name = self._get_project_name(patient_id)
        if self.is_simulation:
            return self.block_repo.load_simulated_merkle_root(project_name)
            
        try:
            # Query contract (read-only call)
            merkle_bytes = self.contract.functions.patientMerkleRoots(patient_id).call()
            if merkle_bytes == b'\x00' * 32:
                # If not set on contract, try simulated store
                return self.block_repo.load_simulated_merkle_root(project_name)
            return merkle_bytes.hex()
        except Exception as e:
            print(f"[Notarizer Warning] Failed to query contract ({e}), falling back to simulated store.")
            return self.block_repo.load_simulated_merkle_root(project_name)

    def verify_on_chain(self, patient_id: str) -> dict:
        """
        Verifies local blocks chain Merkle root against on-chain Merkle root.
        """
        project_name = self._get_project_name(patient_id)
        chain = self.block_repo.load_all_blocks(project_name)
        if not chain:
            return {"verified": False, "reason": "No local blocks found", "tx_hash": None}

        hashes = [b.hash for b in chain if b.hash]
        local_root = calculate_merkle_root(hashes)
        
        tx_hash = self.block_repo.load_notarization_tx(project_name)
        on_chain_root = self.get_on_chain_merkle_root(patient_id)
        
        if not on_chain_root:
            return {
                "verified": False, 
                "local_root": f"0x{local_root}",
                "on_chain_root": "N/A",
                "tx_hash": tx_hash,
                "reason": "Not notarized on-chain"
            }
            
        clean_local = local_root.lower().strip()
        clean_on_chain = on_chain_root.lower().strip()
        if clean_on_chain.startswith("0x"):
            clean_on_chain = clean_on_chain[2:]
            
        verified = (clean_local == clean_on_chain)
        return {
            "verified": verified,
            "local_root": f"0x{local_root}",
            "on_chain_root": f"0x{clean_on_chain}",
            "tx_hash": tx_hash,
            "reason": "Match" if verified else "Merkle root mismatch"
        }
