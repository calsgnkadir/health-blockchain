"""
tests/test_ip_allowlist_setting.py — the IP allowlist switch
============================================================
The setting was renamed from VIP_IP_ALLOWLIST_ENABLED to
VHV_IP_ALLOWLIST_ENABLED, like the other VHV_ settings. A deployment that
still sets the old name must keep its setting, and the allowlist stays on
unless it is explicitly turned off.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.middleware.ip_allowlist import ip_allowlist_enabled

NAMES = ("VHV_IP_ALLOWLIST_ENABLED", "VIP_IP_ALLOWLIST_ENABLED")


def _env(**values):
    clean = {k: v for k, v in os.environ.items() if k not in NAMES}
    clean.update(values)
    return mock.patch.dict(os.environ, clean, clear=True)


class TestIPAllowlistSetting(unittest.TestCase):
    def test_on_by_default(self):
        with _env():
            self.assertTrue(ip_allowlist_enabled())

    def test_new_name(self):
        with _env(VHV_IP_ALLOWLIST_ENABLED="false"):
            self.assertFalse(ip_allowlist_enabled())

    def test_old_name_still_works(self):
        with _env(VIP_IP_ALLOWLIST_ENABLED="false"):
            self.assertFalse(ip_allowlist_enabled())

    def test_new_name_wins(self):
        with _env(VHV_IP_ALLOWLIST_ENABLED="true", VIP_IP_ALLOWLIST_ENABLED="false"):
            self.assertTrue(ip_allowlist_enabled())


if __name__ == "__main__":
    unittest.main()
