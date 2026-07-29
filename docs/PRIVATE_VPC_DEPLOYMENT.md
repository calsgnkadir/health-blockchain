# VIP Health Vault — Private VPC / Sovereign Cloud Deployment Specification

> [!IMPORTANT]
> **Regulatory & Architecture Mandate (KVKK Art. 9 & Air-Gapped Network Isolation)**  
> High-confidentiality VIP health records (cabinet ministers, defense officials, state protocol) **MUST NOT** be hosted on public US-based PaaS platforms. Deployment must be conducted inside an isolated Private VPC, private cloud, or institutional on-premise datacenter.

---

## 1. Network Topology & IP Isolation Architecture

```
[ VIP Authorized Terminals ]
            │
   (Encrypted VPN / TLS)
            ▼
[ Institutional Firewall / WAF ] ──▶ [ Private Subnet (10.0.0.0/8) ]
                                                │
                                                ▼
                                    [ VIP Health Vault Container ]
                                     ├── IPAllowlistMiddleware
                                     ├── Persistent Storage Mounts
                                     └── Hardware Passkey Auth
```

- **Allowed Subnets**: `127.0.0.1/32`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- **Public Ingress Restrictions**: Public internet CIDRs (`0.0.0.0/0`) are blocked by `IPAllowlistMiddleware`.

---

## 2. Persistent Storage Requirements

Public cloud free-tier PaaS environments feature ephemeral containers where local databases are destroyed upon redeployment. The private deployment architecture mandates persistent volume mounts:

| Storage Asset | Container Path | Host Volume Mount Path | Purpose |
| :--- | :--- | :--- | :--- |
| **LMDB Encrypted Off-Chain Store** | `/app/lmdb_data` | `/var/lib/vhv/lmdb_data` | AES-256-GCM Encrypted Record Payloads |
| **SQLite Vault Database** | `/app/database/vault.db` | `/var/lib/vhv/database/vault.db` | User Accounts, Audit Logs & Access Records |

---

## 3. Environment Variables & Configuration

```env
ENVIRONMENT=production
VHV_DEMO_MODE=false
VIP_IP_ALLOWLIST_ENABLED=true
TRUST_PROXIES=true
TRUSTED_PROXIES=10.0.0.1,10.0.0.2
JWT_PRIVATE_KEY_PATH=/etc/vhv/keys/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/etc/vhv/keys/jwt_public.pem
```

---

## 4. KVKK Article 9 & Cross-Border Compliance

Under **KVKK Article 9 (Transfer of Personal Data Abroad)**, special category health data of Turkish citizens/officials cannot be transferred to foreign cloud jurisdictions without explicit consent or statutory authorization. Operating the vault inside a sovereign local VPC guarantees **100% compliance** with Turkish data sovereignty laws.
