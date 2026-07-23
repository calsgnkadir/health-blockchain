"""
tests/test_deadman_switch.py — Dead-Man's Switch (Miras Kilidi) Tests
======================================================================
"""

import time
import os
import tempfile
import unittest
from fastapi.testclient import TestClient


class TestDeadManSwitch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._tmp = tempfile.mkdtemp()
        db_path = os.path.join(cls._tmp, "test_deadman_vault.db")

        os.environ["TESTING"] = "true"
        os.environ["ENVIRONMENT"] = "test"
        os.environ["VHV_DEMO_MODE"] = "true"

        import database.sql_db as _sql_mod
        _sql_mod.DEFAULT_SQLITE_PATH = db_path
        from database.sql_db import SQLDatabaseManager
        _bootstrap = SQLDatabaseManager()
        _bootstrap.seed_default_users()
        _sql_mod.default_sql_db = _bootstrap
        import infrastructure.repositories.sql_repositories as _sql_repo_mod
        _sql_repo_mod.default_sql_db = _bootstrap

        from backend.main import app
        cls.client = TestClient(app, raise_server_exceptions=False)

        # Login VIP patient
        resp = cls.client.post(
            "/api/v1/auth/login",
            json={"username": "vip001", "password": "VIPPatient@2026!"}
        )
        data1 = resp.json()
        cls.vip_token = data1.get("access_token", "")
        cls.patient_id = "VIP-001"

        # Login doctor / beneficiary (dr.smith)
        resp2 = cls.client.post(
            "/api/v1/auth/login",
            json={"username": "dr.smith", "password": "Doctor@2026Secure!"}
        )
        data2 = resp2.json()
        cls.doctor_token = data2.get("access_token", "")

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    # ── Test 1: Configure Dead-Man's Switch ───────────────────────────────────

    def test_01_configure_deadman_switch(self):
        """VIP hasta miras kilidini 90 gün inaktivite ve varis parametreleri ile aktif edebilmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp = self.client.post(
            "/api/v1/deadman/config",
            json={
                "inactivity_days": 90,
                "beneficiaries": [
                    {
                        "username": "dr.smith",
                        "relation": "Doktor / Varis",
                        "email": "dr.smith@hospital.org",
                        "access_scope": "all_records"
                    }
                ]
            },
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200, f"Config failed: {resp.text}")
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["inactivity_days"], 90)
        self.assertEqual(data["status"], "active")

    # ── Test 2: Get Dead-Man's Config ─────────────────────────────────────────

    def test_02_get_deadman_config(self):
        """VIP hasta yapılandırılmış miras kilidi durumunu görüntüleyebilmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp = self.client.get(
            f"/api/v1/deadman/config/{self.patient_id}",
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200, f"Get config failed: {resp.text}")
        data = resp.json()
        self.assertTrue(data["configured"])
        self.assertEqual(data["inactivity_days"], 90)
        self.assertEqual(data["status"], "active")
        self.assertGreaterEqual(data["remaining_days"], 89)
        self.assertEqual(len(data["beneficiaries"]), 1)
        self.assertEqual(data["beneficiaries"][0]["username"], "dr.smith")

    # ── Test 3: Heartbeat Ping ────────────────────────────────────────────────

    def test_03_heartbeat_ping(self):
        """VIP hasta 'Ben Hayattayım' pingi gönderip inaktivite süresini sıfırlayabilmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        time.sleep(0.1)
        resp = self.client.post(
            "/api/v1/deadman/ping",
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp.status_code, 200, f"Ping failed: {resp.text}")
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "active")

    # ── Test 4: Toggle Pause / Resume ─────────────────────────────────────────

    def test_04_toggle_pause_and_resume(self):
        """Hasta miras kilidini dondurabilmeli ve tekrar aktif edebilmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        # Pause
        resp_pause = self.client.post(
            "/api/v1/deadman/toggle",
            json={"status": "paused"},
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp_pause.status_code, 200)
        self.assertEqual(resp_pause.json()["status"], "paused")

        # Resume
        resp_resume = self.client.post(
            "/api/v1/deadman/toggle",
            json={"status": "active"},
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp_resume.status_code, 200)
        self.assertEqual(resp_resume.json()["status"], "active")

    # ── Test 5: Beneficiary Access Blocked when Active ────────────────────────

    def test_05_beneficiary_access_blocked_when_active(self):
        """Miras kilidi aktif ama inaktivite süresi dolmamışken varis veriye erişememeli."""
        if not self.doctor_token:
            self.skipTest("Doctor token not available")

        resp = self.client.get(
            f"/api/v1/deadman/beneficiary-access/{self.patient_id}",
            headers=self._auth(self.doctor_token)
        )
        self.assertEqual(resp.status_code, 403, "Beneficiary access should be blocked when active")

    # ── Test 6: Trigger Dead-Man's Switch on Inactivity ──────────────────────

    def test_06_trigger_deadman_switch_on_inactivity(self):
        """İnaktivite süresi (100 gün > 90 gün) aşıldığında durum 'triggered' olmalı ve varis erişebilmeli."""
        if not self.doctor_token or not self.vip_token:
            self.skipTest("Tokens not available")

        # DB'deki last_heartbeat'i 100 gün geriye çek
        from database.sql_db import get_sql_db
        db = get_sql_db()
        past_heartbeat = time.time() - (100 * 86400)
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE deadman_configs SET last_heartbeat = ?, status = 'active' WHERE patient_id = ?",
                (past_heartbeat, self.patient_id)
            )
            conn.commit()

        # Config sorgulama otomatik trigger etmeli
        resp_cfg = self.client.get(
            f"/api/v1/deadman/config/{self.patient_id}",
            headers=self._auth(self.doctor_token)
        )
        self.assertEqual(resp_cfg.status_code, 200)
        data_cfg = resp_cfg.json()
        self.assertEqual(data_cfg["status"], "triggered")
        self.assertTrue(data_cfg["is_triggered"])

        # Şimdi varis tıbbi verileri çekebilmeli
        resp_access = self.client.get(
            f"/api/v1/deadman/beneficiary-access/{self.patient_id}",
            headers=self._auth(self.doctor_token)
        )
        self.assertEqual(resp_access.status_code, 200, f"Beneficiary access failed: {resp_access.text}")
        data_access = resp_access.json()
        self.assertEqual(data_access["switch_status"], "triggered")
        self.assertIn("unlocked_records", data_access)

    # ── Test 7: Patient Reset Triggered Switch via Ping ──────────────────────

    def test_07_patient_ping_resets_triggered_switch(self):
        """Tetiklenmiş kilidi olan hasta tekrar sisteme girip ping atarsa durum 'active'e dönmeli."""
        if not self.vip_token:
            self.skipTest("VIP token not available")

        resp_ping = self.client.post(
            "/api/v1/deadman/ping",
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp_ping.status_code, 200)
        data = resp_ping.json()
        self.assertEqual(data["status"], "active")

        # Kontrol et
        resp_cfg = self.client.get(
            f"/api/v1/deadman/config/{self.patient_id}",
            headers=self._auth(self.vip_token)
        )
        self.assertEqual(resp_cfg.json()["status"], "active")


if __name__ == "__main__":
    unittest.main(verbosity=2)
