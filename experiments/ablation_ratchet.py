"""E6 ablation: does the day-high RATCHET matter for the visual frame encoder's time map?

    python -m experiments.ablation_ratchet

Same frames, same market record, same algorithm (infer_tau), two variants:
  full        - joint price + day-high ratchet constraint (as deployed)
  price_only  - ratchet removed (each frame constrains tau only by its displayed price)
Inputs: the E5 full-recording frame OCR (experiments/results/frames/*_tv18.json) and the demo samples' frames.json.
Writes reports/ablation_ratchet.json. No clock is used by either variant.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from encoders.frame_encoder import infer_tau, parse_panel
from encoders.market import get_market

ROOT = Path(__file__).resolve().parents[1]


def _frames(doc):
    out = []
    for f in doc.get("frames", []):
        p = f.get("panel") or parse_panel(f.get("lines", []))
        out.append({"t_media": f["t_media"], "panel": p})
    return out


def _summ(r):
    s = {"status": r["status"], "day": r.get("day"), "candidate_days": len(r.get("candidates", {})) or (1 if r.get("day") else 0)}
    if r["status"] == "IDENTIFIED":
        s["tau_radius_s"] = round(r["tau_radius"], 1)
    elif r.get("tau_intervals"):
        ivs = r["tau_intervals"]
        s["stretches"] = len(ivs)
        s["span_radius_s"] = round((ivs[-1][1] - ivs[0][0]) / 2, 1)
    return s


def main():
    M = get_market()
    sources = [(f.name.split("_")[0] + "/tv18", f) for f in sorted((ROOT / "experiments/results/frames").glob("*_tv18.json"))]
    sources += [("sample:" + p.parent.name, p) for p in sorted((ROOT / "demo/samples").glob("tv18_*/frames.json"))]
    rows = []
    for name, path in sources:
        frames = _frames(json.loads(path.read_text(encoding="utf-8")))
        full = infer_tau(frames, M)
        ab = copy.deepcopy(frames)
        for f in ab:
            if f["panel"]:
                f["panel"]["layout_ok"] = False          # disables the ratchet constraint inside infer_tau
        po = infer_tau(ab, M)
        rows.append({"recording": name, "full": _summ(full), "price_only": _summ(po)})
        print(rows[-1])
    out = {"rows": rows, "note": "price_only = identical pipeline with the day-high ratchet constraint removed"}
    (ROOT / "reports/ablation_ratchet.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
