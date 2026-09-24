"""
scripts/capture_walkthrough.py — regenerate the README security walkthrough GIF.

Drives a running demo instance with a headless browser, captures the nine
walkthrough scenes (patient journey + admin dual-control governance), overlays a
self-captioning top bar on each, and stitches them into a looping GIF at
docs/screenshots/walkthrough.gif.

Silent by design: every frame explains itself, so the GIF is legible in a README
without audio.

Setup (one time):
    pip install playwright pillow
    python -m playwright install chromium

Start a clean demo server (fresh data, only the seeded chart), e.g. from a copy
with no backend/projects:
    ENVIRONMENT=development VHV_DEMO_MODE=true VHV_BIND_HOST=127.0.0.1 PORT=8093 \
        python backend/main.py

Then:
    python scripts/capture_walkthrough.py                       # uses :8093
    python scripts/capture_walkthrough.py http://127.0.0.1:8090
"""

import os
import sys
import tempfile

from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8093"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_GIF = os.path.join(ROOT, "docs", "screenshots", "walkthrough.gif")

VIP = ("vip001", "VIPPatient@2026!")
ADMIN = ("admin", "Admin@2026Secure!")
VW = {"width": 1366, "height": 860}

# (id, caption, duration_ms)
SCENES = [
    ("01", "Sign in — Argon2id hashing, httpOnly-cookie sessions, optional FIDO2 passkey", 2300),
    ("02", "The patient signs in to their own vault  (vip001 \u00b7 Ahmet Karata\u015f)", 1500),
    ("03", "Dashboard — chain VALID, live vitals, critical-allergy banner", 3000),
    ("04", "Medical Records — every row is a signed block on the patient's hash-chain", 2400),
    ("05", "Records are AES-256-GCM encrypted at rest — decryption is per-record", 2600),
    ("06", "Who Accessed My Records — tamper-evident, append-only access ledger", 2500),
    ("07", "Blockchain — end-to-end hash + HMAC-signature verification", 2400),
    ("08", "Even an admin sees \u201cSELECT PATIENT\u201d — no data on their own authority", 2700),
    ("09", "Dual-Control — reading a record needs an M-of-N co-signature (self-approval is rejected)", 3400),
]

TITLE = "VIP HEALTH VAULT — SECURITY WALKTHROUGH"
W, BAR = 1100, 92
BG, ACC, MUT, FG = (11, 13, 18), (230, 168, 60), (150, 160, 175), (238, 242, 248)


def _font(sz, bold=False):
    for pth in ([r"C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
                if bold else [r"C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(pth, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def _login(page, user, pw, settle=3800):
    page.goto(BASE, wait_until="networkidle")
    page.fill('input[placeholder="username"]', user)
    page.fill('input[type="password"]', pw)
    return settle  # caller decides when to click / shoot


def capture(raw_dir):
    """Drive the browser and drop nine raw PNG scenes into raw_dir."""
    with sync_playwright() as p:
        b = p.chromium.launch()

        # Act 1 — the patient (vip001)
        pg = b.new_context(viewport=VW).new_page()
        pg.goto(BASE, wait_until="networkidle")
        pg.wait_for_timeout(700)
        pg.screenshot(path=os.path.join(raw_dir, "01.png"))
        pg.fill('input[placeholder="username"]', VIP[0])
        pg.fill('input[type="password"]', VIP[1])
        pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(raw_dir, "02.png"))
        pg.click('button[type="submit"]')
        pg.wait_for_timeout(3800)
        pg.screenshot(path=os.path.join(raw_dir, "03.png"))
        pg.click('[data-page="records"]')
        pg.wait_for_timeout(2200)
        pg.screenshot(path=os.path.join(raw_dir, "04.png"))
        # open the encrypted record via a real bubbling click on the delegated handler
        pg.evaluate("""() => {
            const c = document.querySelector('.record-card.is-encrypted')
                   || document.querySelector('[data-action="open-record"]');
            if (c) c.click();
        }""")
        pg.wait_for_timeout(1600)
        pg.screenshot(path=os.path.join(raw_dir, "05.png"))
        # close the modal deterministically — Escape isn't bound, and the open
        # overlay would otherwise intercept the next nav click.
        pg.evaluate("() => { const o = document.getElementById('modal-overlay');"
                    " if (o) o.classList.remove('open'); }")
        pg.wait_for_timeout(400)
        pg.click('[data-page="my-access"]')
        pg.wait_for_timeout(2000)
        pg.screenshot(path=os.path.join(raw_dir, "06.png"))
        pg.click('[data-page="chain-status"]')
        pg.wait_for_timeout(2000)
        pg.screenshot(path=os.path.join(raw_dir, "07.png"))

        # Act 2 — governance (admin cannot self-authorize)
        pg2 = b.new_context(viewport=VW).new_page()
        pg2.goto(BASE, wait_until="networkidle")
        pg2.fill('input[placeholder="username"]', ADMIN[0])
        pg2.fill('input[type="password"]', ADMIN[1])
        pg2.click('button[type="submit"]')
        pg2.wait_for_timeout(3800)
        pg2.screenshot(path=os.path.join(raw_dir, "08.png"))
        pg2.click('[data-page="dual-control"]')
        pg2.wait_for_timeout(1800)
        pg2.screenshot(path=os.path.join(raw_dir, "09.png"))

        b.close()


def compose(raw_dir):
    """Caption each raw scene and stitch the looping GIF."""
    f_title, f_step = _font(15, True), _font(19, True)
    frames, durs = [], []
    for sid, cap, dur in SCENES:
        src = Image.open(os.path.join(raw_dir, f"{sid}.png")).convert("RGB")
        h = int(src.height * W / src.width)
        src = src.resize((W, h), Image.LANCZOS)
        canvas = Image.new("RGB", (W, h + BAR), BG)
        canvas.paste(src, (0, BAR))
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, BAR - 2, W, BAR], fill=(30, 36, 46))
        d.rectangle([18, 20, 22, BAR - 20], fill=ACC)
        d.text((34, 18), TITLE, font=f_title, fill=MUT)
        step = f"{SCENES.index((sid, cap, dur)) + 1} / {len(SCENES)}"
        tw = d.textbbox((0, 0), step, font=f_step)[2]
        px = W - tw - 46
        avail = (px - 14) - 34 - 18
        sz, cf = 25, _font(25, True)
        while sz > 16 and d.textlength(cap, font=cf) > avail:
            sz -= 1
            cf = _font(sz, True)
        d.text((34, 44), cap, font=cf, fill=FG)
        d.rounded_rectangle([px - 14, 26, W - 20, 60], 10, fill=(24, 29, 38), outline=(52, 60, 72))
        d.text((px, 32), step, font=f_step, fill=ACC)
        frames.append(canvas)
        durs.append(dur)

    pal = frames[2].convert("P", palette=Image.ADAPTIVE, colors=256)
    q = [fr.quantize(palette=pal, dither=Image.NONE) for fr in frames]
    os.makedirs(os.path.dirname(OUT_GIF), exist_ok=True)
    q[0].save(OUT_GIF, save_all=True, append_images=q[1:], duration=durs,
              loop=0, optimize=True, disposal=2)
    print("wrote", OUT_GIF, "-", round(os.path.getsize(OUT_GIF) / 1024 / 1024, 2), "MB")


def main():
    with tempfile.TemporaryDirectory() as raw:
        capture(raw)
        compose(raw)


if __name__ == "__main__":
    main()
