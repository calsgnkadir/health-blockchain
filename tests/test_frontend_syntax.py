"""
tests/test_frontend_syntax.py — every frontend module must parse as an ES module
===============================================================================
The web UI is plain ES modules (`import` / `export`, no bundler), so a single
syntax error stops the whole module from loading and the page silently loses
its behaviour — which is exactly what an apostrophe inside a single-quoted
string once did ('... this client's chain ...').

Why the files are copied to `.mjs` first: `node --check file.js` does NOT
reliably catch this. Node 22 decides per file whether a `.js` file is CommonJS
or an ES module ("module syntax detection"), and on these files it exited 0
even with that syntax error present. A `.mjs` file is always parsed as an ES
module, so the check is real.

Skipped when Node.js is not installed (it is on the GitHub Actions runners).
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

JS_ROOT = Path(__file__).resolve().parent.parent / "backend" / "static" / "js"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node.js is not installed")
class TestFrontendModulesParse(unittest.TestCase):
    def test_every_module_parses(self):
        modules = sorted(p for p in JS_ROOT.rglob("*.js") if "vendor" not in p.parts)
        self.assertTrue(modules, "no frontend modules found")
        failures = []
        with tempfile.TemporaryDirectory() as tmp:
            for src in modules:
                copy = Path(tmp) / f"{src.stem}.mjs"
                shutil.copyfile(src, copy)
                result = subprocess.run([NODE, "--check", str(copy)],
                                        capture_output=True, text=True)
                if result.returncode != 0:
                    failures.append(f"{src.name}:\n{result.stderr.strip()}")
        self.assertFalse(failures, "frontend modules that do not parse:\n\n" + "\n\n".join(failures))

    def test_the_check_really_catches_a_broken_module(self):
        """Guards the guard: a known-bad module must fail the same check."""
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.mjs"
            bad.write_text("export const x = '<p>this client's chain</p>';\n", encoding="utf-8")
            result = subprocess.run([NODE, "--check", str(bad)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
