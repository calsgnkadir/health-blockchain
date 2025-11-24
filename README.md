 Health Blockchain System

This is a basic blockchain-based system to securely store, correct, and validate health medical data.  
Each entry is a block that is signed by an HMAC-SHA256 signature, and each block is chained together with a SHA-256 hash for tamper-resistance.  
There is also a token reward system for data entries, and you can save/load the blockchain to/from a JSON file. 

---

 Features

- Add health data as blocks to the blockchain  
- HMAC-SHA256 digital signature on each block  
- SHA-256 hash chaining for block integrity  
- Includes correction blocks to update wrong/old data  
- Complete chain validation system  
- Token rewards for entries in the chain  
- Save/load blockchain to/from a JSON file  
- Reconstruction of final corrected data  
- Easy and clear command line interface  

---

   Project Structure

```text

.
├── app.py             # Main CLI menu and application logic
├── healthchain.py     # Blockchain and Block classes
├── token_system.py    # Token reward system
├── current_chain.json # Saved blockchain (auto generated)
├── tokens.json        # Token storage (auto generated)
└── README.md          # Project documentatation
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

 🔹 Saving & Loading

You can save the entire chain to current_chain.json or a chosen filename.

Existing chains can be loaded through the menu


