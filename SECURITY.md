# 🔐 Security Features

This blockchain system now includes advanced security features.

## 🛡️ Security Layers

### 1. **Device-Based Authentication**
- A unique Device ID is created for each device
- Blockchains provide full access only on the device where they were created
- Access attempts from other devices trigger warnings

### 2. **AES-256 Encryption**
- Blockchain data can be optionally encrypted
- Uses Fernet (AES-128-CBC) encryption
- Encrypted blockchains can only be opened with the correct password

### 3. **Secure Private Key Management**
- Private key is no longer hardcoded in the code
- Managed via environment variable (`HEALTH_BLOCKCHAIN_KEY`)
- Automatically generated on first use and notified to the user

### 4. **HMAC-SHA256 Signing (Enhanced)**
- Each block is signed with device ID
- Other devices cannot create the same signature
- Integrity verification is performed

## 📋 Usage

### Setting Environment Variable

**Windows PowerShell:**
```powershell
$env:HEALTH_BLOCKCHAIN_KEY="your-secret-key-here"
```

**Windows CMD:**
```cmd
set HEALTH_BLOCKCHAIN_KEY=your-secret-key-here
```

**Linux/Mac:**
```bash
export HEALTH_BLOCKCHAIN_KEY="your-secret-key-here"
```

### Creating Encrypted Blockchain

When starting the program, when creating a new blockchain, encryption option is offered:
- Use `y` option to create encrypted blockchain
- Set password and blockchain is saved encrypted

### Loading Encrypted Blockchain

When loading an encrypted blockchain, password is requested. Loading cannot be done with wrong password.

## ⚠️ Security Warnings

1. **Keep Private Key Secure**: Store the environment variable in a secure location
2. **Don't Forget Password**: If you lose the password of an encrypted blockchain, you cannot access the data
3. **Device ID**: Each device has its own unique ID. If you delete the `.device_id` file, a new ID will be created
4. **Backup**: Take backups of important blockchains

## 🔒 Security Levels

### Level 1: Basic (No Encryption)
- Device ID check
- HMAC signing
- Hash chaining

### Level 2: Advanced (With Encryption)
- All Level 1 features
- AES-256 encryption
- Password-protected access

## 🚫 Access Control

- **Same Device**: Full access (read, write, verify)
- **Different Device**: 
  - Read: Possible with warning
  - Write: Signature verification fails
  - Verify: Device ID mismatch detected

## 📝 Notes

- Old format blockchains (unencrypted) can still be loaded (backward compatibility)
- New blockchains automatically include device ID
- Encryption is optional, not mandatory
