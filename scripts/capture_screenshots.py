"""
scripts/capture_screenshots.py — regenerate the README screenshot gallery.

Drives a running demo instance with a headless browser and saves the four
gallery images to docs/screenshots/. Run it against a PRISTINE demo (only the
seeded 4-week cardiology chart) so the dashboard shows populated vitals, the
allergy banner and the trend chart.

Setup (one time):
    pip install playwright
    python -m playwright install chromium

Start a clean demo server (fresh data), e.g. from a copy with no backend/projects:
    ENVIRONMENT=development VHV_DEMO_MODE=true VHV_BIND_HOST=127.0.0.1 PORT=8093 \
        python backend/main.py

Then:
    python scripts/capture_screenshots.py            # uses http://127.0.0.1:8093
    python scripts/capture_screenshots.py http://127.0.0.1:8090
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8093"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "screenshots")
DEMO_USER, DEMO_PASS = "vip001", "VIPPatient@2026!"


def _shot(page, name, settle=1400):
    page.wait_for_timeout(settle)
    page.screenshot(path=os.path.join(OUT, name))
    print("saved", name)


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 860})

        page.goto(BASE, wait_until="networkidle")
        _shot(page, "01_login.png", settle=1200)

        page.fill('input[placeholder="username"]', DEMO_USER)
        page.fill('input[type="password"]', DEMO_PASS)
        page.click('button[type="submit"]')
        _shot(page, "02_dashboard.png", settle=4000)   # Argon2 login + dashboard load

        page.click("text=Medical Records")
        _shot(page, "03_records.png", settle=2500)

        page.click("text=Who Accessed My Records")
        _shot(page, "04_access_ledger.png", settle=2500)

        browser.close()
    print("Done ->", OUT)


if __name__ == "__main__":
    main()
