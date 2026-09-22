"""
tests/test_role_migration.py — old role ids are renamed on start
================================================================
Mahrem renamed two roles: doctor -> practitioner, vip_patient -> client. A
database created before the rename still holds the old ids, and every role
check would then reject those users. init_db() rewrites them in place.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.sql_db import default_sql_db

LEGACY_USERS = {"legacy.doc": "doctor", "legacy.client": "vip_patient"}


class TestRoleMigration(unittest.TestCase):
    def _run(self, sql, params=()):
        db = default_sql_db
        if db.is_postgres:
            sql = sql.replace("?", "%s")
        conn = db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            rows = cur.fetchall() if sql.lstrip().upper().startswith("SELECT") else None
            conn.commit()
            return rows
        finally:
            cur.close()
            conn.close()

    def setUp(self):
        default_sql_db.init_db()
        for username, old_role in LEGACY_USERS.items():
            self._run("DELETE FROM users WHERE username = ?", (username,))
            self._run(
                "INSERT INTO users (id, username, password_hash, role, full_name) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"USR-{username}", username, "x", old_role, "Legacy User"),
            )

    def tearDown(self):
        for username in LEGACY_USERS:
            self._run("DELETE FROM users WHERE username = ?", (username,))

    def test_old_role_ids_are_renamed_on_start(self):
        default_sql_db.init_db()
        roles = dict(self._run(
            "SELECT username, role FROM users WHERE username IN (?, ?)",
            tuple(LEGACY_USERS),
        ))
        self.assertEqual(roles["legacy.doc"], "practitioner")
        self.assertEqual(roles["legacy.client"], "client")

    def test_migration_is_safe_to_run_twice(self):
        default_sql_db.init_db()
        default_sql_db.init_db()  # must not fail or change anything further
        roles = dict(self._run(
            "SELECT username, role FROM users WHERE username IN (?, ?)",
            tuple(LEGACY_USERS),
        ))
        self.assertEqual(set(roles.values()), {"practitioner", "client"})


if __name__ == "__main__":
    unittest.main()
