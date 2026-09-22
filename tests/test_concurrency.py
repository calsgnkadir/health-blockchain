"""
tests/test_concurrency.py — concurrent writes to one patient chain must not fork
================================================================================
add_record reads the current tail block, then appends. FastAPI runs sync endpoints
in a threadpool, so two writes to the same patient can overlap even in one process.
If the read-modify-write is not serialized, both readers see the same tail and
append at the same index — a fork or a lost block. This test fires many concurrent
writes and asserts every block landed with a unique, contiguous index and the
chain still verifies.
"""

import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database.storage as storage
from core.cqrs.commands import AddRecordCommand, CommandHandler
from core.services.record_service import RecordService
from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy


class TestConcurrentWrites(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING"] = "true"
        self.patient = "CL-CONCUR-777"
        self.repo = LMDBBlockRepository()
        self.service = RecordService(self.repo, AESGCMStrategy())
        self.handler = CommandHandler(self.service, None, self.repo)
        storage.reset_db(self.service._get_project_name(self.patient))

    def tearDown(self):
        storage.reset_db(self.service._get_project_name(self.patient))

    def _add(self, i, barrier):
        barrier.wait()  # release all threads together to maximise overlap
        self.handler.handle_add_record(AddRecordCommand(
            patient_id=self.patient,
            data={"record_type": "diagnosis", "title": f"dx-{i}",
                  "data": {"icd_code": "I10", "n": i}},
            is_protected=False, protection_password=None, username="dr.concurrent",
        ))

    def test_concurrent_writes_do_not_fork_the_chain(self):
        n = 12
        barrier = threading.Barrier(n)
        with ThreadPoolExecutor(max_workers=n) as ex:
            list(ex.map(lambda i: self._add(i, barrier), range(n)))

        chain = self.service.get_chain(self.patient)
        indices = sorted(b.index for b in chain)

        # No two blocks share an index — a fork would produce a duplicate.
        self.assertEqual(len(indices), len(set(indices)),
                         f"duplicate block indices (fork): {indices}")
        # Contiguous from genesis — a lost/overwritten write would leave a gap.
        self.assertEqual(indices, list(range(len(indices))),
                         f"gap in the chain (lost write): {indices}")
        # And the hash/signature chain still verifies end to end.
        self.assertTrue(self.service.is_chain_valid(self.patient),
                        "chain does not verify after concurrent writes")

        # Every concurrent write's record actually landed (none lost).
        revealed = " ".join(str(v) for v in self.service.get_final_data(self.patient).values())
        for i in range(n):
            self.assertIn(f"dx-{i}", revealed, f"write dx-{i} was lost")


if __name__ == "__main__":
    unittest.main()
