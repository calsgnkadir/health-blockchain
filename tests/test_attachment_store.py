"""
tests/test_attachment_store.py — encrypted attachment blob store
================================================================
Attachments live in the same LMDB store as the chain, content-addressed by the
SHA-256 of the (already-encrypted) blob. A round-trip returns the bytes verbatim,
the reference is deterministic (identical uploads collapse), and a missing
reference raises rather than returning silent garbage.

(Replaces the former IPFS client test — the vault is single-subnet, so a
distributed content network was folded back into the local encrypted store.)
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import LMDBConnectionManager
from core.services.attachment_store import AttachmentStore


class TestAttachmentStore(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="vhv_attach_")
        self.manager = LMDBConnectionManager(self.base)
        self.store = AttachmentStore(db_manager=self.manager)

    def tearDown(self):
        self.manager.close_all()
        shutil.rmtree(self.base, ignore_errors=True)

    def test_put_returns_the_content_hash(self):
        payload = "EncryptedSecretTextPayload123!"
        ref = self.store.put(payload)
        self.assertEqual(ref, hashlib.sha256(payload.encode("utf-8")).hexdigest())
        self.assertEqual(len(ref), 64)

    def test_roundtrip_returns_the_blob_verbatim(self):
        payload = "EncryptedSecretTextPayload123!"
        ref = self.store.put(payload)
        self.assertEqual(self.store.get(ref), payload)

    def test_identical_uploads_collapse_to_one_reference(self):
        ref1 = self.store.put("same-blob")
        ref2 = self.store.put("same-blob")
        self.assertEqual(ref1, ref2)

    def test_missing_reference_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.get("0" * 64)


if __name__ == "__main__":
    unittest.main()
