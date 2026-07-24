"""
scripts/deploy_contract.py — Sepolia / EVM Smart Contract Deployer
===================================================================
Deploys AnchorStore.sol to Ethereum Sepolia Testnet (or any EVM network).

Usage:
  python scripts/deploy_contract.py [--rpc <RPC_URL>] [--key <PRIVATE_KEY>] [--dry-run]
"""

import os
import sys
import json
import time
import argparse

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

def load_artifact():
    artifact_path = os.path.join(_PROJECT_ROOT, "contracts", "AnchorStore.json")
    if os.path.exists(artifact_path):
        with open(artifact_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    # Try solcx if artifact not found
    try:
        import solcx
        sol_path = os.path.join(_PROJECT_ROOT, "contracts", "AnchorStore.sol")
        solcx.install_solc("0.8.20")
        solcx.set_solc_version("0.8.20")
        compiled = solcx.compile_files([sol_path], output_values=["abi", "bin"])
        key = list(compiled.keys())[0]
        return {
            "contractName": "AnchorStore",
            "abi": compiled[key]["abi"],
            "bytecode": "0x" + compiled[key]["bin"]
        }
    except Exception as e:
        print(f"[Error] Contract compilation failed: {e}")
        sys.exit(1)

def deploy(rpc_url: str = None, private_key: str = None, dry_run: bool = False):
    print("=" * 65)
    print("🚀 VIP Health Vault — Sepolia / EVM Smart Contract Deployer")
    print("=" * 65)

    rpc_url = rpc_url or os.getenv("VHV_RPC_URL") or "https://ethereum-sepolia-rpc.publicnode.com"
    private_key = private_key or os.getenv("VHV_PRIVATE_KEY")

    if dry_run or not private_key:
        print("\n[Simulasyon Modu / Dry-Run]")
        print(f"  Target RPC URL:   {rpc_url}")
        print("  Private Key:      [Eksik veya Dry-Run Modu]")
        print("  Contract Name:    AnchorStore.sol")
        print("\nℹ️ Gercek deploy yapmak icin `.env` dosyasina `VHV_RPC_URL` ve `VHV_PRIVATE_KEY` ekleyin:")
        print("   python scripts/deploy_contract.py --rpc <URL> --key <PRIVATE_KEY>")
        return {
            "status": "dry_run",
            "simulated_contract_address": "0x1234567890abcdef1234567890abcdef12345678",
            "simulated_tx_hash": "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        }

    try:
        from web3 import Web3
    except ImportError:
        print("[Hata] web3 paketi kurulu degil. 'pip install web3' calistirin.")
        sys.exit(1)

    print(f"📡 RPC Sunucusuna Baglaniliyor: {rpc_url} ...")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("[Hata] RPC sunucusuna baglanilamadi. Lutfen RPC URL'yi kontrol edin.")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    network_name = "Sepolia Testnet" if chain_id == 11155111 else f"EVM Chain ID {chain_id}"
    print(f"✅ Baglanti Basarili! Ag: {network_name} (Chain ID: {chain_id})")

    account = w3.eth.account.from_key(private_key)
    deployer_address = account.address
    balance_wei = w3.eth.get_balance(deployer_address)
    balance_eth = w3.from_wei(balance_wei, "ether")

    print(f"👤 Yayinlayici Cuzdan: {deployer_address}")
    print(f"💰 Bakiye:           {balance_eth:.6f} ETH")

    if balance_wei == 0:
        print("\n⚠️ [UYARI] Cuzdan bakiyesi 0 ETH! Gas ucreti odenemedigi icin islem basarisiz olabilir.")
        print("ℹ️ Sepolia Test ETH almak icin: https://sepoliafaucet.com / https://alchemy.com/faucets/ethereum-sepolia")

    artifact = load_artifact()
    abi = artifact["abi"]
    bytecode = artifact["bytecode"]

    print("\n📦 Sozlesme Dagitimi (Deployment) Baslatiliyor...")
    contract_factory = w3.eth.contract(abi=abi, bytecode=bytecode)

    nonce = w3.eth.get_transaction_count(deployer_address)
    gas_price = w3.eth.gas_price

    tx = contract_factory.constructor().build_transaction({
        "from": deployer_address,
        "nonce": nonce,
        "gasPrice": int(gas_price * 1.15),  # 15% buffer
    })

    try:
        tx["gas"] = w3.eth.estimate_gas(tx)
    except Exception:
        tx["gas"] = 3000000

    print("🔑 Islem imzalaniyor...")
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)

    print("🌐 Raw transaction zincire gonderiliyor...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    tx_hash_hex = w3.to_hex(tx_hash)
    print(f"⏳ Islem Gonderildi! Tx Hash: {tx_hash_hex}")
    print("⏳ Onay bekleniyor (Blok onaylama sureci)...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    if receipt.status == 1:
        contract_address = receipt.contractAddress
        print("\n" + "=" * 65)
        print("🎉 SOZLESME BASARIYLA CANLIYA ALINDI (DEPLOYED)!")
        print("=" * 65)
        print(f"📍 Contract Address:  {contract_address}")
        print(f"🔗 Tx Hash:           {tx_hash_hex}")
        print(f"⛽ Kullanilan Gas:    {receipt.gasUsed}")
        print(f"🔍 Etherscan Explorer: https://sepolia.etherscan.io/address/{contract_address}")
        print("=" * 65)

        # Update .env if exists or print instruction
        env_file = os.path.join(_PROJECT_ROOT, ".env")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "VHV_CONTRACT_ADDRESS=" in content:
                import re
                content = re.sub(r"VHV_CONTRACT_ADDRESS=.*", f"VHV_CONTRACT_ADDRESS={contract_address}", content)
            else:
                content += f"\nVHV_CONTRACT_ADDRESS={contract_address}\n"
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(content)
            print("💾 `.env` dosyasi VHV_CONTRACT_ADDRESS ile guncellendi!")
        else:
            print(f"\nℹ️ `.env` dosyaniza su satiri ekleyin:\nVHV_CONTRACT_ADDRESS={contract_address}")

        return {
            "status": "success",
            "contract_address": contract_address,
            "tx_hash": tx_hash_hex,
            "chain_id": chain_id,
            "etherscan_url": f"https://sepolia.etherscan.io/address/{contract_address}"
        }
    else:
        print("\n❌ Deployment islemi zincirde REVERT oldu (Basarisiz).")
        return {"status": "failed", "tx_hash": tx_hash_hex}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy AnchorStore contract to Sepolia")
    parser.add_argument("--rpc", help="EVM RPC URL")
    parser.add_argument("--key", help="Deployer Private Key (hex)")
    parser.add_argument("--dry-run", action="store_true", help="Run simulation only")
    args = parser.parse_args()

    deploy(rpc_url=args.rpc, private_key=args.key, dry_run=args.dry_run)
