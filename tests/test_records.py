import os
import shutil
import unittest
import sys

# Setup project root import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import LMDBConnectionManager
from infrastructure.repositories.lmdb_repositories import LMDBBlockRepository
from infrastructure.cryptography.crypto_strategies import AESGCMStrategy
from core.services.record_service import RecordService

class TestRecordService(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_projects_rec")
        os.makedirs(self.test_dir, exist_ok=True)
        self.db_manager = LMDBConnectionManager(self.test_dir)
        self.block_repo = LMDBBlockRepository(self.db_manager)
        self.crypto_strategy = AESGCMStrategy()
        self.record_service = RecordService(self.block_repo, self.crypto_strategy)

    def tearDown(self):
        self.db_manager.close_all()
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_add_record_and_chain_validation(self):
        patient_id = "VIP-007"
        
        # Initial chain validation (empty/Genesis auto-creation)
        self.assertTrue(self.record_service.is_chain_valid(patient_id))
        
        # Add a block
        data1 = {"record_type": "vital_signs", "title": "Checkup", "data": {"hr": 80}}
        block1 = self.record_service.add_record(patient_id, data1, is_protected=False, protection_password=None, username="dr.test")
        self.assertIsNotNone(block1)
        self.assertEqual(block1.index, 1)
        
        # Chain should still be valid
        self.assertTrue(self.record_service.is_chain_valid(patient_id))
        
        # Add protected block
        data2 = {"record_type": "prescription", "title": "Meds", "data": {"med": "Aspirin"}}
        block2 = self.record_service.add_record(patient_id, data2, is_protected=True, protection_password="SuperSecurePassword123!", username="dr.test")
        self.assertIsNotNone(block2)
        self.assertEqual(block2.index, 3)  # Expect 3 because index 2 is the system audit block for block 1
        self.assertTrue(block2.is_protected)
        
        # Verify valid chain
        self.assertTrue(self.record_service.is_chain_valid(patient_id))
