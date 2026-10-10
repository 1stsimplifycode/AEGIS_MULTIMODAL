"""E5: does the VISUAL FRAME ENCODER identify the video->market time map from chart ratchets alone, and is it right?

    python -m experiments.tau_validation

Inputs: full-recording frame OCR (experiments/results/frames/<session>_tv18.json, 1 frame / 10 s) and the demo samples' frames.
The encoder never sees a clock. Ground truth for checking only: the true broadcast date (our capture date, 2026-10-06) and our
SNTP capture clock. Reported per recording: identified? correct day? tau half-width, implied broadcast delay (air - market time),
ratchet (day-high extension) events. Writes reports/tau_validation.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from encoders.clock import from_validation
from encoders.frame_encoder import encode
from encoders.market import get_market

ROOT = Path(__file__).resolve().parents[1]
SESS = ROOT.parent / "research_hipc_2026/icoac_research/live_capture/sessions"


def main():
    M = get_market()
    rows = []
    for f in sorted((ROOT / "experiments/results/frames").glob("*_tv18.json")):
        sess = f.name.split("_")[0]
        doc = json.loads(f.read_text(encoding="utf-8"))
        clk = from_validation(SESS / sess / "validation.json", "tv18")
        r = encode(doc, M, clk)
        t = r["tau"]
        ag = r.get("agreement_with_capture_clock") or {}
        rows.append({"recording": f"{sess}/tv18", "frames": r["n_frames"], "panel_frames": r["n_panel_frames"], "status": t["status"],
                     "day": t.get("day"), "day_correct": t.get("day") == "2026-10-06" if t.get("day") else None,
                     "tau_radius_s": round(t["tau_radius"], 1) if t.get("tau_radius") is not None else None,
                     "delay_s": ag.get("air_minus_market_s"), "ratchet_events": len(r["ratchet_events"]), "reason": t.get("reason")})
        print(rows[-1])
    ident = [r for r in rows if r["status"] == "IDENTIFIED"]
    out = {"n_recordings": len(rows), "n_identified": len(ident), "n_day_correct": sum(1 for r in ident if r["day_correct"]),
           "delay_min": min((r["delay_s"] for r in ident), default=None), "delay_max": max((r["delay_s"] for r in ident), default=None),
           "tau_radius_median_s": sorted(r["tau_radius_s"] for r in ident)[len(ident) // 2] if ident else None,
           "ratchet_events_total": sum(r["ratchet_events"] for r in rows), "rows": rows,
           "note": "frames at 1 per 10 s over each full 20-minute recording; tau never uses a clock; the clock is only used to check it"}
    (ROOT / "reports/tau_validation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print({k: v for k, v in out.items() if k != "rows"})


if __name__ == "__main__":
    main()
