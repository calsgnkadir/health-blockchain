"""
tests/test_record_schemas.py — the psychology record schemas
============================================================
The API checks the `data` of each record type against a schema
(backend/schemas/requests.py -> DATA_SCHEMAS). These tests pin the main rules,
and check that the bundled demo file passes the same rules the API enforces —
otherwise the demo could show data a real user could never enter.
"""

import os
import sys
import unittest

from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.schemas.requests import (
    DATA_SCHEMAS, RECORD_TYPES, AssessmentSchema, SessionNoteSchema, HomeworkSchema,
)
from backend.demo_seed import _demo_chart, _confidential_record


class TestRecordSchemas(unittest.TestCase):
    def test_every_schema_belongs_to_a_known_type(self):
        for record_type in DATA_SCHEMAS:
            self.assertIn(record_type, RECORD_TYPES)

    def test_demo_file_passes_the_api_schemas(self):
        for record in _demo_chart() + [_confidential_record()]:
            schema = DATA_SCHEMAS.get(record["record_type"])
            if schema:
                schema(**record["data"])  # raises if the demo drifts from the rules

    def test_score_above_max_is_rejected(self):
        with self.assertRaises(ValidationError):
            AssessmentSchema(instrument="GAD-7", score=22, max_score=21, interpretation="x")

    def test_negative_score_is_rejected(self):
        with self.assertRaises(ValidationError):
            AssessmentSchema(instrument="GAD-7", score=-1, max_score=21, interpretation="x")

    def test_unknown_session_format_is_rejected(self):
        with self.assertRaises(ValidationError):
            SessionNoteSchema(session_number=1, duration_min=50,
                              session_format="Phone", summary="x")

    def test_homework_due_date_may_be_in_the_future(self):
        HomeworkSchema(task="Thought record", due_date="2999-01-01")  # must not raise


if __name__ == "__main__":
    unittest.main()
