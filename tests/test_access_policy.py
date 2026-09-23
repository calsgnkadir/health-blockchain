"""
tests/test_access_policy.py — the access policy on its own
==========================================================
core/services/access_policy.py is a set of pure functions, so every rule can
be checked here without a database, a server or a login.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.access_policy import can_view, can_create, can_view_stored

ME = "psk.elif"
OTHER = "psk.other"


def consent_for(*types):
    """A has_consent() that says yes only for the given record types."""
    return lambda record_type: record_type in types or "all" in types


def record(level, record_type="session_note", created_by=ME):
    return {"access_level": level, "record_type": record_type, "created_by": created_by}


class TestCanView(unittest.TestCase):
    def test_client_sees_shared_and_client_only_records(self):
        self.assertTrue(can_view("client", "client001", record("doctor_shared"), consent_for()))
        self.assertTrue(can_view("client", "client001", record("private"), consent_for()))

    def test_client_never_sees_a_practitioner_only_note(self):
        self.assertFalse(can_view("client", "client001", record("practitioner_only"), consent_for()))

    def test_practitioner_needs_consent_for_the_record_type(self):
        rec = record("doctor_shared", "assessment")
        self.assertFalse(can_view("practitioner", ME, rec, consent_for()))
        self.assertFalse(can_view("practitioner", ME, rec, consent_for("session_note")))
        self.assertTrue(can_view("practitioner", ME, rec, consent_for("assessment")))
        self.assertTrue(can_view("practitioner", ME, rec, consent_for("all")))

    def test_practitioner_never_sees_a_client_only_record(self):
        self.assertFalse(can_view("practitioner", ME, record("private"), consent_for("all")))

    def test_practitioner_only_note_is_for_its_author(self):
        self.assertTrue(can_view("practitioner", ME, record("practitioner_only"), consent_for("all")))
        self.assertFalse(can_view("practitioner", OTHER, record("practitioner_only"), consent_for("all")))

    def test_own_note_still_needs_consent(self):
        # Revoking consent closes the file, the practitioner's own notes included.
        self.assertFalse(can_view("practitioner", ME, record("practitioner_only"), consent_for()))

    def test_unknown_access_level_is_closed(self):
        for role in ("client", "practitioner"):
            self.assertFalse(can_view(role, ME, record("admin_only"), consent_for("all")))

    def test_record_without_a_level_is_treated_as_shared(self):
        rec = {"record_type": "assessment"}
        self.assertTrue(can_view("client", "client001", rec, consent_for()))
        self.assertTrue(can_view("practitioner", ME, rec, consent_for("assessment")))

    def test_non_record_is_never_visible(self):
        self.assertFalse(can_view("client", "client001", None, consent_for()))
        self.assertFalse(can_view("client", "client001", "ciphertext", consent_for()))


class TestCanViewStored(unittest.TestCase):
    def test_password_protected_block_needs_consent_for_all_records(self):
        self.assertFalse(can_view_stored("practitioner", ME, "ciphertext", consent_for("session_note")))
        self.assertTrue(can_view_stored("practitioner", ME, "ciphertext", consent_for("all")))
        self.assertTrue(can_view_stored("client", "client001", "ciphertext", consent_for()))

    def test_bookkeeping_blocks_are_hidden_from_practitioners(self):
        for block_type in ("genesis", "audit", "correction"):
            data = {"type": block_type}
            self.assertFalse(can_view_stored("practitioner", ME, data, consent_for("all")))
            self.assertTrue(can_view_stored("client", "client001", data, consent_for()))

    def test_ordinary_record_uses_can_view(self):
        self.assertFalse(can_view_stored("practitioner", ME, record("private"), consent_for("all")))
        self.assertTrue(can_view_stored("practitioner", ME, record("doctor_shared"), consent_for("all")))


class TestCanCreate(unittest.TestCase):
    def test_client_levels(self):
        self.assertTrue(can_create("client", "doctor_shared", "other", consent_for()))
        self.assertTrue(can_create("client", "private", "other", consent_for()))
        self.assertFalse(can_create("client", "practitioner_only", "other", consent_for()))

    def test_practitioner_levels(self):
        self.assertTrue(can_create("practitioner", "doctor_shared", "session_note", consent_for("all")))
        self.assertTrue(can_create("practitioner", "practitioner_only", "session_note", consent_for("all")))
        self.assertFalse(can_create("practitioner", "private", "session_note", consent_for("all")))

    def test_practitioner_needs_consent_to_write(self):
        self.assertFalse(can_create("practitioner", "doctor_shared", "session_note", consent_for()))
        self.assertFalse(can_create("practitioner", "doctor_shared", "session_note", consent_for("homework")))
        self.assertTrue(can_create("practitioner", "doctor_shared", "session_note", consent_for("session_note")))


if __name__ == "__main__":
    unittest.main()
