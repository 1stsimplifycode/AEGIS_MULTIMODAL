"""HELD-OUT evaluation: run the frozen pipeline (extractor + verifier as of the 16-capture tuning) on 8 archived full-day
YouTube live streams (NDTV Profit, CNBC-TV18; 2026-09-29 .. 10-05) that were NOT used for any rule tuning.

    python -m experiments.heldout_replays

Speech: YouTube's own English auto-captions (a different speech recogniser from ours). Air time: the stream's
release_timestamp + caption offset (validated to within seconds in the parent project's dating work; we assume +-30 s).
Only captions during market hours (09:15-15:30 IST) are used. Output: experiments/results/heldout_claims.json + summary.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from collections import Counter
from pathlib import Path

from encoders.claims import extract
from encoders.clock import CaptureClock
from encoders.market import IST, get_market, ist
from verification.engine import NOT_CHECKABLE, verify_price_claim

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT.parent / "research/icsc2027/replays"
OUT = ROOT / "experiments/results"


def caption_segments(p: Path):
    d = json.loads(p.read_text(encoding="utf-8"))
    segs = []
    for e in d.get("events", []):
        t = "".join(s.get("utf8", "") for s in (e.get("segs") or [])).replace("\n", " ").strip()
        if t:
            segs.append({"start": e["tStartMs"] / 1000, "end": (e["tStartMs"] + e.get("dDurationMs", 0)) / 1000, "text": t, "words": []})
    return segs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    M = get_market()
    rows, cnt = [], Counter()
    t0 = time.perf_counter()
    for info in sorted(REP.glob("*.info.json")):
        vid = info.name[:-10]
        cap = next((p for p in (REP / f"{vid}.en-orig.json3", REP / f"{vid}.en.json3") if p.exists()), None)
        meta = json.loads(info.read_text(encoding="utf-8"))
        if not cap or not meta.get("release_timestamp"):
            continue
        rel = float(meta["release_timestamp"])
        clk = CaptureClock(rel, 1.0, 0.0, 25.0, 5.0, f"YouTube release_timestamp of {vid} + caption offset")
        segs = caption_segments(cap)
        day = dt.datetime.fromtimestamp(rel, IST).date()
        a, b = M.session_bounds(day)
        segs = [s for s in segs if a <= rel + s["start"] <= b]
        claims, _ = extract(segs)
        for c in claims:
            r = verify_price_claim(c, clk.wall(c["t_media"]), clk.uncertainty_s, M)
            cnt[(c["type"], r["verdict"])] += 1
            rows.append({"video": vid, "channel": meta.get("channel"), "day": str(day), "t_media": c["t_media"],
                         "aired": ist(clk.wall(c["t_media"])), "type": c["type"], "role": c["role"], "span": c["instrument_span"],
                         "candidates": c["candidates"], "ctx": c["entity_from_context"], "value": c["value"], "verdict": r["verdict"],
                         "tolerance": c["tolerance"], "inequality": c.get("inequality"), "binding": c.get("binding"),
                         "timing": r.get("timing", {}).get("class"), "finding": r.get("finding"), "sentence": c["sentence"][:400]})
    secs = time.perf_counter() - t0
    chk = [r for r in rows if r["verdict"] != NOT_CHECKABLE]
    summ = {"videos": sorted({r["video"] for r in rows}), "claims_extracted": len(rows), "checkable": len(chk),
            "verdicts_checkable": dict(Counter(r["verdict"] for r in chk)),
            "by_type_verdict": {f"{k[0]} | {k[1]}": v for k, v in sorted(cnt.items())}, "runtime_s": round(secs, 1)}
    (OUT / "heldout_claims.json").write_text(json.dumps(rows, indent=0, ensure_ascii=False), encoding="utf-8")
    (OUT / "heldout_summary.json").write_text(json.dumps(summ, indent=1), encoding="utf-8")
    print(json.dumps(summ, indent=1))
    for r in chk:
        if r["verdict"] != "Not enough evidence":
            print(r["verdict"][:12], r["video"], r["aired"][5:19], r["type"], r["candidates"][:2], r["value"], r["timing"], "|", r["sentence"][:140])


if __name__ == "__main__":
    main()
