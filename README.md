 Health Blockchain System

This is a secure blockchain-based system to store, correct, and validate health medical data.  
Each entry is a block that is signed by an HMAC-SHA256 signature (with device-based authentication), and each block is chained together with a SHA-256 hash for tamper-resistance.  
The system includes advanced security features: AES-256 encryption, device-based authentication, and secure key management.  
There is also a token reward system for data entries, and you can save/load the blockchain to/from a JSON file (with optional encryption). 

---

 Features

- Add health data as blocks to the blockchain  
- 🔐 **AES-256 encryption** (optional) for blockchain data
- 🔒 **Device-based authentication** - each blockchain is tied to a device
- 🔑 **Secure key management** via environment variables
- HMAC-SHA256 digital signature on each block (device-specific)
- SHA-256 hash chaining for block integrity  
- Includes correction blocks to update wrong/old data  
- Complete chain validation system with device verification
- Token rewards for entries in the chain  
- Save/load blockchain to/from a JSON file (encrypted or plain)
- Reconstruction of final corrected data  
- Easy and clear command line interface  

---

   Project Structure

```text

.
├── app.py                # Main CLI menu and application logic
├── healthchain.py        # Blockchain and Block classes
├── token_system.py       # Token reward system
├── security.py           # Security functions (encryption, device ID, key management)
├── project_manager.py   # Project management system
├── projects/             # Project directories (auto generated)
│   ├── project1/
│   │   ├── blockchain.json
│   │   └── tokens.json
│   └── project2/
│       ├── blockchain.json
│       └── tokens.json
├── .device_id            # Device identifier (auto generated)
├── project_config.json   # Last used project (auto generated)
├── requirements.txt      # Python dependencies
├── SECURITY.md           # Security documentation
└── README.md             # Project documentation
```
---

   ### How It Works
 🔹Block Contents

Each block contains:

index

timestamp

data

previous_hash

hash (SHA-256)

signature (HMAC-SHA256)

---

 🔹 Digital Signatures

Each block has a private key signature utilizing HMAC-SHA256, which lets us know if anything has been tampered with the block when we use it during validation.

---

 🔹 Correction Blocks

Instead of altering old medical data we add an almost ordinary block, known as a correction block that references the wrong block (correction_of) and states the corrected content. For final data reconstruction, we apply the most recent correction for each block

---

 🔹 Token System

For every new entry of health data, the user receives tokens that are stored in tokens.json

---

 🔹 Project Management

- **Multiple Projects**: Each blockchain is stored in its own project folder
- **Auto-save**: Blockchain automatically saves after each operation
- **Project Selection**: Choose from existing projects or create new ones
- **Last Project**: Automatically loads the last used project on startup
- **Project Structure**: `projects/project_name/blockchain.json`

 🔹 Saving & Loading

- Blockchain automatically saves to project folder after each operation
- Each project has its own blockchain.json and tokens.json files
- Blockchain can be saved encrypted (AES-256) or unencrypted
- Existing chains can be loaded through the project menu (password required if encrypted)

 🔹 Security Features

- **Device ID**: Each device has a unique identifier stored in `.device_id`
- **Encryption**: Optional AES-256 encryption for blockchain data
- **Key Management**: Private keys managed via `HEALTH_BLOCKCHAIN_KEY` environment variable
- **Access Control**: Blockchains are tied to specific devices

See `SECURITY.md` for detailed security documentation.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variable (optional, will be auto-generated on first run):
```bash
# Windows PowerShell
$env:HEALTH_BLOCKCHAIN_KEY="your-secret-key"

# Linux/Mac
export HEALTH_BLOCKCHAIN_KEY="your-secret-key"
```

3. Run the application:
```bash
python app.py
```


