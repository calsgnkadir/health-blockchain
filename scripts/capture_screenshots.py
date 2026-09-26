"""
scripts/capture_screenshots.py — regenerate the README screenshot gallery.

Drives a running demo instance with a headless browser and saves the six
gallery images to docs/screenshots/. Run it against a PRISTINE demo (only the
seeded CL-001 file, its appointments and invoices).

Setup (one time):
    pip install playwright
    python -m playwright install chromium

Start a clean demo, e.g. with Docker (fresh volumes):
    docker compose -f docker-compose.yml -f docker-compose.demo.yml up --build

Then:
    python scripts/capture_screenshots.py            # uses http://127.0.0.1:8000
    python scripts/capture_screenshots.py http://127.0.0.1:8093

It signs in twice; the demo allows 5 sign-ins per IP per minute.
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "docs", "screenshots")
PRACTITIONER = ("psk.elif", "Practitioner@2026!")
CLIENT = ("client001", "Client@2026Secure!")
VIEWPORT = {"width": 1366, "height": 860}


def _shot(page, name, settle=1400):
    page.wait_for_timeout(settle)
    page.screenshot(path=os.path.join(OUT, name))
    print("saved", name)


def _sign_in(page, user, password):
    page.goto(BASE, wait_until="networkidle")
    page.fill("#inp-username", user)
    page.fill("#inp-password", password)
    page.click("#btn-login")


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # The practitioner first: their reads are what the client's ledger shows.
        page = browser.new_context(viewport=VIEWPORT).new_page()
        page.goto(BASE, wait_until="networkidle")
        _shot(page, "01_login.png", settle=1200)

        _sign_in(page, *PRACTITIONER)
        _shot(page, "02_dashboard.png", settle=5500)   # Argon2 login + client list + appointments

        page.click('[data-page="records"]')
        _shot(page, "03_records.png", settle=3500)

        page.click('[data-page="appointments"]')
        _shot(page, "04_appointments.png", settle=2500)

        page.click('[data-action="open-invoice"]')
        _shot(page, "05_invoice.png", settle=1800)

        # Then the client, who sees who read their file.
        page = browser.new_context(viewport=VIEWPORT).new_page()
        _sign_in(page, *CLIENT)
        page.wait_for_timeout(4000)
        if page.is_visible("#kvkk-notice-overlay"):      # first sign-in: the privacy notice
            # The styled box hides the real checkbox, so tick it directly.
            page.evaluate("document.getElementById('kvkk-consent-check').checked = true")
            page.click('[data-action="kvkk-accept"]')
            page.wait_for_timeout(1000)
        page.click('[data-page="my-access"]')
        _shot(page, "06_access_ledger.png", settle=2500)

        browser.close()
    print("Done ->", OUT)


if __name__ == "__main__":
    main()
