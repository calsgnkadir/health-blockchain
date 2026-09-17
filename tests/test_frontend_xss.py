"""
tests/test_frontend_xss.py — output-encoding regression guard for the web UI
============================================================================
The backend stores clinical text as ciphertext and returns it verbatim; escaping
user-controlled data is a *render-time* concern (see
test_storage_and_metadata_safety.py). The whole burden of stopping DOM/stored XSS
therefore sits in the frontend, where every value that reaches an `innerHTML` sink
must pass through `escapeHtml()` (contextual output encoding).

A self-audit of the UI (source -> sink, the same methodology used against third
-party targets) found one *reflected* DOM XSS and a family of defense-in-depth
gaps:

  * `renderCommandPaletteResults()` reflected the raw search box value into
    `innerHTML` on the "No results found for ..." branch. Payload:
    `<img src=x onerror=...>` typed into search -> no command matches -> the
    string is parsed as HTML and the handler fires. httpOnly cookies keep the
    session token out of `document.cookie`, but the script still runs with the
    victim's session (it can drive the same authenticated API the user can).
  * several `catch` handlers wrote `${e.message}` / `${err.message}` straight into
    `innerHTML`; an error string that echoes attacker input would be reflected.

All of these now route through `escapeHtml()`. This test is a *static* guard (no
browser, no server) that fails CI if any of them regress: the raw tainted
interpolations must never reappear in an `innerHTML` string, and `escapeHtml`
must keep neutralising the five HTML-significant characters.
"""

import os
import re
import unittest
from pathlib import Path

JS_ROOT = Path(__file__).resolve().parent.parent / "backend" / "static" / "js"

# Identifiers that carry user/attacker-controlled text. If any of these is dropped
# straight into a template literal ( `${e.message}` ) it lands unescaped in the
# innerHTML sink. The fixed code wraps each as `${escapeHtml(e.message)}`, so the
# bare form below must not appear anywhere in the shipped JS.
BANNED_RAW_INTERPOLATIONS = [
    re.compile(r"\$\{\s*query\s*\}"),
    re.compile(r"\$\{\s*e\.message\s*\}"),
    re.compile(r"\$\{\s*err\.message\s*\}"),
]


def _all_js_files():
    return sorted(p for p in JS_ROOT.rglob("*.js"))


class TestFrontendOutputEncoding(unittest.TestCase):
    def test_js_tree_exists(self):
        self.assertTrue(JS_ROOT.is_dir(), f"frontend JS root not found: {JS_ROOT}")
        self.assertTrue(_all_js_files(), "no .js files found to scan")

    def test_no_raw_tainted_interpolation_survives(self):
        """No known user-controlled value may be interpolated without escapeHtml()."""
        offenders = []
        for path in _all_js_files():
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                for pat in BANNED_RAW_INTERPOLATIONS:
                    if pat.search(line):
                        offenders.append(f"{path.name}:{lineno}: {line.strip()}")
        self.assertFalse(
            offenders,
            "unescaped user-controlled interpolation reached an innerHTML sink:\n"
            + "\n".join(offenders),
        )

    def test_search_reflection_is_escaped(self):
        """The specific finding: the command-palette 'No results' branch is encoded."""
        app_js = (JS_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("No results found for", app_js)
        self.assertIn("${escapeHtml(query)}", app_js,
                      "search reflection must be wrapped in escapeHtml()")

    def test_escapehtml_neutralises_html_metacharacters(self):
        """escapeHtml() must encode all five HTML-significant characters."""
        utils = (JS_ROOT / "modules" / "utils.js").read_text(encoding="utf-8")
        self.assertIn("export function escapeHtml", utils)
        for needle in ("&amp;", "&lt;", "&gt;", "&quot;", "&#039;"):
            self.assertIn(needle, utils,
                          f"escapeHtml() does not emit {needle}")


if __name__ == "__main__":
    unittest.main()
