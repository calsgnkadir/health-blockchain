import os
import json
import hashlib
import urllib.request
import urllib.error
import secrets

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_IPFS_STORAGE = os.path.join(_PROJECT_ROOT, "backend", "ipfs_storage")

class IPFSClient:
    def __init__(self):
        self.api_url = os.getenv("VHV_IPFS_API_URL", "http://localhost:5001/api/v0").rstrip("/")
        self.is_simulation = True
        
        # Test connection to IPFS API
        try:
            req = urllib.request.Request(
                f"{self.api_url}/version",
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=1.5) as response:
                if response.status == 200:
                    self.is_simulation = False
                    print(f"[IPFS Client] Connected successfully to IPFS daemon at: {self.api_url}")
        except Exception:
            # Silent fallback to simulation mode
            pass
            
        if self.is_simulation:
            print("[IPFS Client] Daemon offline or unconfigured. Running in IPFS Simulation Mode.")
            os.makedirs(DEFAULT_IPFS_STORAGE, exist_ok=True)

    def upload_to_ipfs(self, encrypted_data_b64: str) -> str:
        """
        Uploads encrypted payload to IPFS (or local simulated directory) and returns its CID.
        """
        if self.is_simulation:
            # Generate simulated Qm... CID based on sha256 hash of the content
            h = hashlib.sha256(encrypted_data_b64.encode("utf-8")).hexdigest()
            cid = "Qm" + h[:44]
            
            # Save file locally in simulated IPFS store with strict owner-only permissions (0o600)
            file_path = os.path.join(DEFAULT_IPFS_STORAGE, cid)
            fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(encrypted_data_b64)
                
            print(f"[IPFS Simulation] File uploaded. CID: {cid}")
            return cid
            
        # Real IPFS upload using multipart form-data over raw urllib
        try:
            boundary = f"----IPFSBoundary{secrets.token_hex(8)}"
            boundary_bytes = boundary.encode("utf-8")
            
            # Construct body bytes
            parts = []
            parts.append(b"--" + boundary_bytes)
            parts.append(b'Content-Disposition: form-data; name="file"; filename="file"')
            parts.append(b"Content-Type: application/octet-stream")
            parts.append(b"")
            parts.append(encrypted_data_b64.encode("utf-8"))
            parts.append(b"--" + boundary_bytes + b"--")
            parts.append(b"")
            
            body = b"\r\n".join(parts)
            
            req = urllib.request.Request(
                f"{self.api_url}/add",
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(body))
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=5.0) as response:
                resp_data = response.read().decode("utf-8")
                result = json.loads(resp_data)
                cid = result.get("Hash")
                if not cid:
                    raise Exception("Response from IPFS add did not contain Hash")
                print(f"[IPFS On-Chain] File uploaded successfully. CID: {cid}")
                return cid
        except Exception as e:
            print(f"[IPFS Error] Failed to upload to real IPFS: {e}. Falling back to simulation storage.")
            # Fallback to simulation storage on failure with strict owner-only permissions (0o600)
            h = hashlib.sha256(encrypted_data_b64.encode("utf-8")).hexdigest()
            cid = "Qm" + h[:44]
            os.makedirs(DEFAULT_IPFS_STORAGE, exist_ok=True)
            file_path = os.path.join(DEFAULT_IPFS_STORAGE, cid)
            fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(encrypted_data_b64)
            return cid

    def download_from_ipfs(self, cid: str) -> str:
        """
        Downloads encrypted payload from IPFS (or local simulated directory).
        """
        # If simulation mode or CID starts with Qm and matches simulated locally, check local first
        local_path = os.path.join(DEFAULT_IPFS_STORAGE, cid)
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                return f.read()
                
        if self.is_simulation:
            raise FileNotFoundError(f"Simulated IPFS file with CID {cid} not found locally.")
            
        # Real IPFS download
        try:
            req = urllib.request.Request(
                f"{self.api_url}/cat?arg={cid}",
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5.0) as response:
                return response.read().decode("utf-8")
        except Exception as e:
            print(f"[IPFS Error] Failed to retrieve from real IPFS: {e}. Checking local cache.")
            if os.path.exists(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    return f.read()
            raise e
