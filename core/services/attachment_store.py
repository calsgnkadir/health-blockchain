"""
core/services/attachment_store.py — encrypted attachment blob store
===================================================================
Record attachments (imaging/DICOM files) are kept inside the same tamper-evident
LMDB store as the chain, not on a separate off-chain service. The blob handed to
this store is *already* AES-encrypted by the caller, so what lands on disk is
ciphertext addressed by the SHA-256 of that ciphertext (content-addressing:
identical uploads collapse to one entry and the reference can be integrity-checked
on the way out).

This replaces the earlier IPFS client. The vault runs inside one private subnet
for a few individuals — a distributed content network was never the fit; the fold
removes an external dependency, its simulation-mode fallback, and a network egress
path, keeping every attachment on the same disk as the records they belong to.
"""

import hashlib
from typing import Optional

from database.connection import LMDBConnectionManager

# A dedicated LMDB namespace, kept apart from any patient chain.
_ATTACHMENT_PROJECT = "attachments"
_KEY_PREFIX = "attachment_"


class AttachmentStore:
    """Content-addressed store for already-encrypted attachment blobs."""

    def __init__(self, db_manager: Optional[LMDBConnectionManager] = None):
        self._manager = db_manager

    def _mgr(self) -> LMDBConnectionManager:
        if self._manager is not None:
            return self._manager
        from database.storage import default_db_manager
        return default_db_manager

    def put(self, encrypted_data_b64: str) -> str:
        """Store an encrypted blob; return its content reference (SHA-256 hex)."""
        ref = hashlib.sha256(encrypted_data_b64.encode("utf-8")).hexdigest()
        key = f"{_KEY_PREFIX}{ref}".encode("utf-8")
        value = encrypted_data_b64.encode("utf-8")

        def txn_block(txn):
            txn.put(key, value)

        self._mgr().run_write_transaction(_ATTACHMENT_PROJECT, txn_block)
        return ref

    def get(self, ref: str) -> str:
        """Return the encrypted blob for a reference, or raise FileNotFoundError."""
        env = self._mgr().open_db(_ATTACHMENT_PROJECT)
        key = f"{_KEY_PREFIX}{ref}".encode("utf-8")
        with env.begin(write=False) as txn:
            value = txn.get(key)
        if value is None:
            raise FileNotFoundError(f"Attachment {ref} not found in the encrypted store")
        return value.decode("utf-8")
