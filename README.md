Health Blockchain System

This is a secure staring, correcting and validating Health medical data on block chain platform.

Each entry is a signed block using an HMAC-SHA256 signature (with device based authentication), and blocks are chained with SHA-256 to make it tamper resistant.

To ensure the highest level of protection, the system provides security features like AES-256 end-to-end encryption, device-based authentication and secure key management.

You can also reward data entries with a token, and also save/load the blockchain from/to a JSON file (with optional encryption).

---

 Features

Health blocks will be added to the blockchain.

- Encrypted blockchain, if applicable, with AES-256
- Device authentication means that the blocks created by each blockchain were created using the specific device.
- Key storage is accomplished through the use of environment variables.
- HMAC-SHA256 digital signature is located on each block and identifies the device that created it
- SHA-256 hash chain linked to maintain and validate block integrity
- Data should have "correction" blocks to provide updates to previous or erroneous data.
- Devices will validate their own blockchains by using a complete chain verification system.
- Users can earn tokens for entering data into the blockchain.
- Blockchains can be saved and loaded from a JSON file and will remain encrypted or unencrypted as needed.
- A reconstruction of the corrected information can be achieved by this process.
- Clear, simple command line interface for the software
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

All blocks are signed using a private key with HMAC-SHA256. Any attempts to tamper with a block will be detected at the time of validation.

---

 🔹 Correction Blocks

Rather than modifying previously entered data, we create a new, almost normal block called a correction block, which has a link back to the erroneous block (correction_of) and describes the corrected information. In the final reconstruction of the data, we apply the latest correction for all blocks.

---

 🔹 Token System

For every new entry of medical information, the user receives tokens stored in tokens.json.


 ## Project Management
- There are multiple projects, meaning that each blockchain has its own associated project folder.
- The Blockchain automatically saves after every operation that you perform on it.
- When you launch the application, you can either choose to load existing projects or create a new project.
- On application startup, the application will automatically open the last-used project folder.
- The structure of your project folder will be structured like this: projects/project_name/blockchain.json

## Saving & Loading
- The blockchain automatically saves to your project folder whenever you perform an operation on it
- Each project will have its own blockchain.json and tokens.json files.
- It is possible to encrypt your blockchain (AES-256 encryption) or leave it unencrypted.
- You can also load an existing chain from your project menu (if it has been encrypted, you will need a password to load it).

## Security Features
- Device ID: Every device has a unique device ID stored in the file called '.device_id'
- Encryption: You can optionally encrypt your blockchain data using AES-256
- Key Management: The private keys for your blockchains are managed using the environment variable called 'HEALTH_BLOCKCHAIN_KEY'
- Access Control: Your blockchains are tied to specific devices only

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


