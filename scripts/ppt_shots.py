"""Element-level screenshots of the REAL running app for the deck (desktop 1440x900). Writes assets/ppt/*.png.

    python -m scripts.ppt_shots [--base http://localhost:8765]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/ppt"


def cap(path, max_h):
    im = Image.open(path)
    if im.height > max_h:
        im.crop((0, 0, im.width, max_h)).save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8765")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
        pg.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
                           "s.textContent = 'header.top{position:static !important}'; document.head.appendChild(s); });")
        pg.goto(a.base + "/#/")
        pg.wait_for_selector(".sample")
        pg.wait_for_timeout(400)
        pg.screenshot(path=str(OUT / "landing_view.png"))
        pg.click('.sample[data-id="tv18_nifty_bank_1301"]')
        pg.click("#start")
        pg.wait_for_url("**/investigation", timeout=30000)
        pg.wait_for_selector("#stagedetail")
        pg.wait_for_timeout(400)
        jid = pg.url.split("/result/")[1].split("/")[0]
        pg.locator(".certbar").screenshot(path=str(OUT / "certbar.png"))
        pg.locator("#archwrap").screenshot(path=str(OUT / "arch.png"))
        for k, h in (("visual_frame", 1500), ("visual_text", 900), ("claim_set", 1050), ("data_age", 1100)):
            pg.click(f'.arch .node[data-stage="{k}"]')
            pg.wait_for_timeout(500)
            f = OUT / f"stage_{k}.png"
            pg.locator("#stagedetail").screenshot(path=str(f))
            cap(f, h)
        cid = None
        pg.click('.arch .node[data-stage="knowability"]')
        pg.wait_for_selector("#stagedetail a[href*='/trace/']")
        pg.click("#stagedetail a[href*='/trace/'] >> nth=0")
        pg.wait_for_selector(".tracechain img.tframe")
        pg.wait_for_timeout(600)
        pg.locator(".tracechain > li").nth(0).screenshot(path=str(OUT / "trace_1_certificate.png"))
        pg.locator(".tracechain > li").nth(2).screenshot(path=str(OUT / "trace_3_encoders.png"))
        pg.locator(".tracechain > li").nth(3).screenshot(path=str(OUT / "trace_4_tape.png"))
        pg.goto(f"{a.base}/#/result/{jid}/certificate")
        pg.wait_for_selector(".card.flat")
        pg.wait_for_timeout(400)
        f = OUT / "certificate.png"
        pg.locator(".card.flat").screenshot(path=str(f))
        cap(f, 1250)
        pg.goto(a.base + "/#/check")
        pg.wait_for_selector("#cf")
        pg.click("#ex button >> nth=1")
        pg.wait_for_selector("#cres .pfa")
        pg.wait_for_timeout(500)
        f = OUT / "check_huge_quantity.png"
        pg.locator("#cres").screenshot(path=str(f))
        cap(f, 1150)
        pg.goto(a.base + "/#/")
        pg.wait_for_selector(".sample")
        pg.click('.sample[data-id="synthetic_trade_claims"]')
        pg.click("#start")
        pg.wait_for_url("**/investigation", timeout=30000)
        pg.wait_for_selector("#stagedetail")
        pg.click('.arch .node[data-stage="fill"]')
        pg.wait_for_timeout(500)
        f = OUT / "synthetic_fill.png"
        pg.locator("#stagedetail").screenshot(path=str(f))
        cap(f, 1500)
        b.close()
    print(sorted(x.name for x in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
