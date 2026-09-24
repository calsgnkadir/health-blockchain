"""
tests/test_secret_guards.py — production refuses built-in default secrets
=========================================================================
The pseudonymisation secret keys anon_id = HMAC(secret, patient_id). If a
production deployment fell back to the shipped default, anyone with the code could
recompute a patient's pseudonym and the whole decoupling/erasure story would
collapse. Production must refuse the default and fail closed.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pseudonymization.engine import PseudonymizationEngine

_KEYS = ("ENVIRONMENT", "TESTING", "VHV_DEMO_MODE", "PSEUDONYM_SECRET")


class TestPseudonymSecretGuard(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _KEYS}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _production_no_secret(self):
        os.environ["ENVIRONMENT"] = "production"
        for k in ("TESTING", "VHV_DEMO_MODE", "PSEUDONYM_SECRET"):
            os.environ.pop(k, None)

    def test_production_without_secret_is_refused(self):
        self._production_no_secret()
        with self.assertRaises(RuntimeError):
            PseudonymizationEngine()

    def test_explicit_secret_is_accepted_in_production(self):
        self._production_no_secret()
        self.assertTrue(PseudonymizationEngine(secret="a-long-random-secret"))

    def test_env_secret_is_accepted_in_production(self):
        self._production_no_secret()
        os.environ["PSEUDONYM_SECRET"] = "a-long-random-secret"
        self.assertTrue(PseudonymizationEngine())

    def test_development_allows_the_default(self):
        os.environ["ENVIRONMENT"] = "development"
        os.environ.pop("PSEUDONYM_SECRET", None)
        self.assertTrue(PseudonymizationEngine())

    def test_a_stable_pseudonym_under_a_fixed_secret(self):
        a = PseudonymizationEngine(secret="fixed").generate_anon_id("CL-001")
        b = PseudonymizationEngine(secret="fixed").generate_anon_id("CL-001")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)


if __name__ == "__main__":
    unittest.main()
