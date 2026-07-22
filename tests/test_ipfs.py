import os
import shutil
import unittest
import tempfile
import core.services.ipfs as ipfs
from core.services.ipfs import IPFSClient

class TestIPFSClient(unittest.TestCase):
    def setUp(self):
        # Create a temp dir for simulated IPFS storage
        self.test_dir = tempfile.mkdtemp()
        self.original_storage = ipfs.DEFAULT_IPFS_STORAGE
        ipfs.DEFAULT_IPFS_STORAGE = self.test_dir
        
        # Override env var to force Simulation Mode for tests
        self.original_url = os.environ.get("VHV_IPFS_API_URL")
        os.environ["VHV_IPFS_API_URL"] = "http://offline-ipfs-node:5001/api/v0"
        
        self.client = IPFSClient()

    def tearDown(self):
        # Restore settings
        ipfs.DEFAULT_IPFS_STORAGE = self.original_storage
        if self.original_url is not None:
            os.environ["VHV_IPFS_API_URL"] = self.original_url
        else:
            os.environ.pop("VHV_IPFS_API_URL", None)
            
        # Clean up temp dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_simulation_fallback(self):
        # Verify that client falls back to simulation mode
        self.assertTrue(self.client.is_simulation)

    def test_upload_and_download_roundtrip(self):
        test_payload = "EncryptedSecretTextPayload123!"
        
        # 1. Upload
        cid = self.client.upload_to_ipfs(test_payload)
        self.assertTrue(cid.startswith("Qm"))
        self.assertEqual(len(cid), 46) # "Qm" + 44 chars = 46 chars
        
        # Verify file is physically saved in the temp directory
        expected_path = os.path.join(self.test_dir, cid)
        self.assertTrue(os.path.exists(expected_path))
        
        # 2. Download
        downloaded = self.client.download_from_ipfs(cid)
        self.assertEqual(downloaded, test_payload)

    def test_download_missing_file_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            self.client.download_from_ipfs("QmNonExistentHash123456789012345678901234567")

if __name__ == '__main__':
    unittest.main()
