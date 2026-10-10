"""Phase F: drive the REAL running app in headless Chromium (desktop 1440x900), save screenshots, and assert behaviour.

    python -m scripts.browser_check [--base http://localhost:8765]

Writes assets/screenshots/*.png and reports/browser_check.json (console errors, failed requests, control checks).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "assets/screenshots"
STAGES = ["visual_frame", "visual_text", "audio", "claim_set", "tape", "fill", "knowability", "data_age", "certificate"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8765")
    a = ap.parse_args()
    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*.png"):
        old.unlink()
    rep = {"viewport": "desktop 1440x900", "console_errors": [], "failed_requests": [], "checks": {}}
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        pg = ctx.new_page()
        pg.on("console", lambda m: rep["console_errors"].append(m.text) if m.type == "error" else None)
        pg.on("requestfailed", lambda r: rep["failed_requests"].append(f"{r.url} {r.failure}") if not r.url.endswith(".mp4") else None)

        def shot(name, full=True):
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(SHOTS / f"{name}.png"), full_page=full)

        pg.goto(a.base + "/#/")
        pg.wait_for_selector(".sample")
        shot("01_landing")
        rep["checks"]["start_disabled_before_pick"] = pg.is_disabled("#start")
        pg.click('.sample[data-id="tv18_nifty_bank_1301"]')
        pg.click("#start")
        pg.wait_for_selector("#stages li")
        shot("02_progress", full=False)
        pg.wait_for_url("**/investigation", timeout=30000)
        pg.wait_for_selector("#stagedetail")
        shot("03_investigation_certificate")
        jid = pg.url.split("/result/")[1].split("/")[0]
        seen = {}
        for k in STAGES:
            pg.click(f'.arch .node[data-stage="{k}"]')
            pg.wait_for_timeout(250)
            seen[k] = pg.inner_text("#stagedetail")[:160]
            if k in ("visual_frame", "visual_text", "claim_set", "fill", "knowability", "data_age"):
                shot(f"04_stage_{k}")
        rep["checks"]["every_stage_node_opens_detail"] = {k: bool(v.strip()) for k, v in seen.items()}
        rep["checks"]["frame_encoder_text"] = seen["visual_frame"]
        imgs_ok = pg.evaluate("Array.from(document.querySelectorAll('#stagedetail img')).every(i => i.complete && i.naturalWidth > 0)")
        rep["checks"]["stage_images_loaded"] = imgs_ok
        pg.click('.arch .node[data-stage="knowability"]')
        pg.wait_for_selector("#stagedetail a[href*='/trace/']")
        pg.click("#stagedetail a[href*='/trace/'] >> nth=0")
        pg.wait_for_selector(".tracechain")
        shot("05_trace")
        rep["checks"]["trace_has_frame_image"] = pg.evaluate("(() => { const i = document.querySelector('.tracechain img.tframe'); return !!(i && i.complete && i.naturalWidth > 0); })()")
        rep["checks"]["trace_has_market_minutes"] = pg.locator(".tracechain table.cmp").count() >= 1
        pg.goto(f"{a.base}/#/result/{jid}/claims")
        pg.wait_for_selector(".claimrow")
        shot("06_claims")
        pg.goto(f"{a.base}/#/result/{jid}/timeline")
        pg.wait_for_selector("#track .ev")
        pg.wait_for_function("document.getElementById('vid').readyState >= 1", timeout=15000)
        evs = pg.query_selector_all("#track .ev.speech")
        before = pg.evaluate("document.getElementById('vid').currentTime")
        (evs[-1] if evs else pg.query_selector("#track .ev")).click()
        pg.wait_for_timeout(700)
        after = pg.evaluate("document.getElementById('vid').currentTime")
        rep["checks"]["marker_seeks_video"] = {"before": before, "after": after, "moved": abs(after - before) > 0.5}
        shot("07_timeline", full=False)
        pg.goto(f"{a.base}/#/result/{jid}/certificate")
        pg.wait_for_selector(".pfa")
        shot("08_certificate")
        for kind in ("HTML", "JSON"):
            with pg.expect_download() as dl:
                pg.click(f"text=Download certificate ({kind})")
            d = dl.value
            rep["checks"][f"download_{kind}"] = {"name": d.suggested_filename, "bytes": Path(d.path()).stat().st_size}
        # synthetic: FILL branch with PASS / FAIL / ABSTAIN
        pg.goto(a.base + "/#/")
        pg.wait_for_selector(".sample")
        pg.click('.sample[data-id="synthetic_trade_claims"]')
        pg.click("#start")
        pg.wait_for_url("**/investigation", timeout=30000)
        pg.wait_for_selector("#stagedetail")
        pg.click('.arch .node[data-stage="fill"]')
        pg.wait_for_timeout(300)
        shot("09_synthetic_fill_branch")
        rep["checks"]["synthetic_fill_text"] = pg.inner_text("#stagedetail")[:200]
        pg.goto(a.base + "/#/check")
        pg.wait_for_selector("#cf")
        pg.click("#ex button >> nth=1")
        pg.wait_for_selector("#cres .pfa", timeout=10000)
        shot("10_check_claim_huge_quantity")
        rep["checks"]["typed_huge_quantity_fill"] = pg.inner_text("#cres h2")
        pg.goto(a.base + "/#/how")
        pg.wait_for_selector("details")
        shot("11_how_it_works")
        ctx.close()
        b.close()
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/browser_check.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep, indent=1)[:3500])


if __name__ == "__main__":
    main()
