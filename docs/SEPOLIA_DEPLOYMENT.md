# Ethereum Sepolia Testnet — Gerçek Akıllı Sözleşme Dağıtım (Deploy) Rehberi
# VIP Health Vault v3.1

> **Belge Türü:** Teknik Dağıtım Rehberi ve Canlı Ağ Entegrasyonu  
> **Ağ:** Ethereum Sepolia Testnet (Chain ID: `11155111`) / Polygon Amoy (Chain ID: `80002`)  
> **Sözleşme:** `contracts/AnchorStore.sol` (Multi-Notary Consensus Enabled)  
> **Sürüm:** 2026-07-24

---

## 1. Mimari Genel Bakış

VIP Health Vault, **Hibrit Mimari (Off-Chain Storage + On-Chain Anchoring)** modelini kullanır:

```
+-----------------------------------------------------------------------+
|                             VIP HASTA                                 |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|  Off-Chain Şifreli Depolama (AES-256-GCM + LMDB / IPFS)                |
|  Ham Sağlık Verileri (PHI) Güvenli Yerel/Bulut Depoda Tutulur         |
+-----------------------------------------------------------------------+
                                   |
                  [SHA-256 Merkle Root Hesaplaması]
                                   v
+-----------------------------------------------------------------------+
|                   Ethereum Sepolia Testnet                            |
|  AnchorStore.sol Smart Contract (proposeOrApproveRoot)               |
|  📍 Değiştirilemez Zaman Damgası ve Bütünlük Kanıtı                   |
+-----------------------------------------------------------------------+
```

---

## 2. Ön Gereksinimler

1. **Python Bağımlılıkları:**
   ```bash
   pip install web3 py-solc-x
   ```
2. **Sepolia Test ETH (Gas Ücretleri İçin):**
   - [Alchemy Sepolia Faucet](https://alchemy.com/faucets/ethereum-sepolia)
   - [QuickNode Sepolia Faucet](https://faucet.quicknode.com/drip)
   - [Sepolia PoW Faucet](https://sepolia-faucet.pk910.de/)
3. **RPC Sunucusu (Provider):**
   - Ücretsiz Sepolia RPC'leri:
     - `https://ethereum-sepolia-rpc.publicnode.com` (Genel / Doğrudan kullanım)
     - `https://rpc.sepolia.org`
     - `https://eth-sepolia.g.alchemy.com/v2/YOUR-API-KEY` (Alchemy)
     - `https://sepolia.infura.io/v3/YOUR-PROJECT-ID` (Infura)

---

## 3. Adım Adım Dağıtım (Deploy) Adımları

### Adım 1: Çevre Değişkenlerini (`.env`) Yapılandırın

`.env` dosyanıza Ethereum cüzdanınızın private key'ini ve RPC URL'sini ekleyin:

```env
ENVIRONMENT=production
VHV_DEMO_MODE=false

# Sepolia RPC URL
VHV_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com

# Yayınlayıcı Cüzdan Private Key (0x ile başlayan hex string)
VHV_PRIVATE_KEY=0xYOUR_SEPOLIA_PRIVATE_KEY_HEX

# Dağıtım sonrasında otomatik doldurulacaktır:
# VHV_CONTRACT_ADDRESS=0x...
```

### Adım 2: Deployment Script'ini Çalıştırın

Otomatik deployer betiğini çalıştırın:

```bash
python scripts/deploy_contract.py
```

**Script Çıktı Örneği:**

```
=================================================================
🚀 VIP Health Vault — Sepolia / EVM Smart Contract Deployer
=================================================================
📡 RPC Sunucusuna Bağlanılıyor: https://ethereum-sepolia-rpc.publicnode.com ...
✅ Bağlantı Başarılı! Ağ: Sepolia Testnet (Chain ID: 11155111)
👤 Yayınlayıcı Cüzdan: 0x90F79bf6EB2c4f870365E785982E1f101E93b906
💰 Bakiye:           0.542100 ETH

📦 Sözleşme Dağıtımı (Deployment) Başlatılıyor...
🔑 İşlem imzalanıyor...
🌐 Raw transaction zincire gönderiliyor...
⏳ İşlem Gönderildi! Tx Hash: 0x8cde1c017aeda2cfc7ba1c3e4a3ce26d1ae773426f14e7fa9faec11c194d9ed2
⏳ Onay bekleniyor (Blok onaylama süreci)...

=================================================================
🎉 SÖZLEŞME BAŞARIYLA CANLIYA ALINDI (DEPLOYED)!
=================================================================
📍 Contract Address:  0xd9145CCE52D386f254917e481eB44e9943F39138
🔗 Tx Hash:           0x8cde1c017aeda2cfc7ba1c3e4a3ce26d1ae773426f14e7fa9faec11c194d9ed2
⛽ Kullanılan Gas:    642105
🔍 Etherscan Explorer: https://sepolia.etherscan.io/address/0xd9145CCE52D386f254917e481eB44e9943F39138
=================================================================
💾 `.env` dosyası VHV_CONTRACT_ADDRESS ile güncellendi!
```

---

## 4. Canlı Ağ Doğrulaması (Etherscan & Notarization)

### Etherscan İncelemesi
- Dağıtılan sözleşmeyi Sepolia Etherscan üzerinden görüntüleyin:  
  `https://sepolia.etherscan.io/address/<VHV_CONTRACT_ADDRESS>`
- Akıllı sözleşme fonksiyonları:
  - `proposeOrApproveRoot(string patientId, bytes32 root)`: Merkle Root teklif et veya onayla (2-of-N Notary Consensus)
  - `patientMerkleRoots(string patientId)`: Onaylanmış Merkle Root sorgula
  - `addNotary(address newNotary)`: Yeni noter adresi ekle

### Test Notarizasyonu Çalıştırma
Uygulama çalıştırıldığında veya kayıt eklendiğinde `BlockchainNotarizer` otomatik olarak Sepolia ağındaki sözleşmeyi günceller:

```python
from core.services.notarizer import BlockchainNotarizer
from infrastructure.repositories.sql_repositories import SQLBlockRepository

notarizer = BlockchainNotarizer(SQLBlockRepository())
tx_hash = notarizer.notarize_patient_chain("VIP-001")
print("Sepolia Tx Hash:", tx_hash)
```

---

## 5. Çoklu Noter (Multi-Notary) Konsensüs Yapılandırması

AnchorStore sözleşmesi **2-of-N konsensüs** mekanizmasına sahiptir. Birden fazla onaylayıcı düğüm (notary node) eklemek için:

```python
# Sözleşme kurucusu ikinci bir noter adresi ekler:
txn = contract.functions.addNotary("0xSecondNotaryAddress").build_transaction(...)
```

İki farklı noter `proposeOrApproveRoot("VIP-001", root)` çağırdığında, eşik dolduğu an Merkle Root otomatik olarak zincire sabitlenir (`RootAnchored` olayı tetiklenir).

---

## 6. Hata Durumları ve Fallback Mekanizması

Eğer RPC sunucusu yanıt vermezse veya `.env` içerisinde `VHV_RPC_URL` tanımsızsa, `BlockchainNotarizer` **otomatik olarak Simülasyon Moduna** geçer:

```
[Notarizer] RPC provider not connected. Falling back to Simulation Mode.
[Notarizer] Running in Simulation Mode (Sepolia/Polygon Testnet mocked)
```

Bu sayede testler ve yerel geliştirme hiçbir kesintiye uğramadan devam eder.
