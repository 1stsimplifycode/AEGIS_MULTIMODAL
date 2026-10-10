"""All Review-2 experiments in one reproducible run (offline, CPU). Writes reports/experiments.json.

    python -m experiments.run_experiments

E1  Screen evidence: NDTV ticker readings vs market at air time, on the 7 NDTV recordings NOT used to validate the layout.
E2  Spoken claims, held-out broadcast days: decisive verdicts vs blind LLM labels (v1 frozen = true held-out; v2.1 = after repair, in-sample).
E3  Controlled manipulations (SYNTHETIC stress test, separate from real-world evaluation): genuine current-price quotes (blind label
    CURRENT_PRICE and verified consistent) are altered - price +-0.1 % (should stay consistent), +-2 % / +-5 %, previous trading
    day, wrong instrument - and re-verified. Reports false support (altered claim still 'consistent') and false contradiction
    (unaltered or within-rounding claim 'contradicted').
E4  Resources: tape/OHLCV load, live analysis time and peak traced memory per sample, process RSS.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import time
import tracemalloc
from collections import Counter
from pathlib import Path

from encoders.clock import from_validation
from encoders.market import IST, get_market
from encoders.visual import ticker_from_dense
from verification.engine import CONSISTENT, CONTRADICTED, INSUFFICIENT, NOT_CHECKABLE, verify_price_claim

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
RES = ROOT / "experiments/results"


def e1_screen(M):
    out = {}
    S = PARENT / "research_hipc_2026/data/streams"
    for d in sorted(S.glob("live_20261006T*_ndtv")):
        sess = d.name.split("_")[1]
        if not (d / "dense.jsonl").exists():
            continue
        clk = from_validation(PARENT / f"research_hipc_2026/icoac_research/live_capture/sessions/{sess}/validation.json", "ndtv")
        v = ticker_from_dense(d / "dense.jsonl", channel="ndtv")
        c = Counter()
        raw = Counter()                        # before the per-recording layout check (what the per-channel rule would have used)
        for o in v["observations"]:
            if o["usable"]:
                cl = {"id": "s", "type": "QUOTE", "value": o["price"], "tolerance": 0.05, "candidates": [o["symbol"]], "instrument_span": o["name"]}
                raw[verify_price_claim(cl, clk.wall(o["t_media"]), clk.uncertainty_s, M)["verdict"]] += 1
        from encoders.visual import recording_layout_check
        lay = recording_layout_check(v["observations"], M, dt.datetime.fromtimestamp(clk.wall(0), IST).date())
        for o in v["observations"]:
            if not o["usable"]:
                c["unused:" + (o["unusable_reason"] or "")[:30]] += 1
                continue
            cl = {"id": "s", "type": "QUOTE", "value": o["price"], "tolerance": 0.05, "candidates": [o["symbol"]], "instrument_span": o["name"]}
            r = verify_price_claim(cl, clk.wall(o["t_media"]), clk.uncertainty_s, M)
            c[r["verdict"]] += 1
        used = sum(v for k, v in c.items() if not k.startswith("unused"))  # after the layout check
        out[sess] = {"role": "layout validated here (in-sample)" if sess == "20261006T084431Z" else "held-out",
                     "per_channel_rule_verdicts": dict(raw), "layout_check": lay, "used_after_layout_check": used,
                     **dict(c), "consistent_rate_of_used": round(c[CONSISTENT] / used, 3) if used else None,
                     "contradicted_rate_of_used": round(c[CONTRADICTED] / used, 3) if used else None}
    ho = [v for v in out.values() if v["role"] == "held-out"]
    tot_used = sum(v["used_after_layout_check"] for v in ho)
    out["_heldout_total"] = {"used": tot_used, "consistent": sum(v.get(CONSISTENT, 0) for v in ho),
                             "contradicted": sum(v.get(CONTRADICTED, 0) for v in ho), "insufficient": sum(v.get(INSUFFICIENT, 0) for v in ho)}
    return out


def e2_spoken():
    v1 = json.loads((RES / "annotation_heldout_confusion.json").read_text())["v1"] if (RES / "annotation_heldout_confusion.json").exists() else None
    v21 = json.loads((RES / "annotation_heldout_confusion_v21.json").read_text())

    def summarize(t):
        g = lambda v, l: t.get(f"{v}|{l}", 0)
        con = {k.split("|")[1]: n for k, n in t.items() if k.startswith("Contradicted")}
        cns = {k.split("|")[1]: n for k, n in t.items() if k.startswith("Consistent")}
        nc = sum(con.values())
        return {"contradicted": con, "consistent": cns,
                "contradiction_precision_vs_CURRENT_PRICE": round(con.get("CURRENT_PRICE", 0) / nc, 3) if nc else None,
                "consistent_on_CURRENT_PRICE": cns.get("CURRENT_PRICE", 0), "consistent_total": sum(cns.values())}
    s1 = json.loads((RES / "heldout_summary_v1_frozen.json").read_text())
    s2 = json.loads((RES / "heldout_summary_v21_insample.json").read_text())
    return {"data": "8 full-day YouTube live streams (NDTV Profit x4, CNBC-TV18 x4), 2026-09-29..10-05, market hours, YouTube auto-captions",
            "labels": "independent LLM subagent, blind to verdicts, 105 sentence windows centred on the number (first labelling round had "
                      "truncated sentences - our error - and was redone)",
            "v1_frozen_heldout": {"summary": s1["verdicts_checkable"], "vs_labels": summarize(v1) if v1 else None},
            "v21_after_repair_IN_SAMPLE": {"summary": s2["verdicts_checkable"], "vs_labels": summarize(v21)}}


def e3_manipulations(M):
    rows = json.loads((RES / "heldout_claims_v21_insample.json").read_text(encoding="utf-8"))
    items = json.loads((RES / "annotation_heldout_v1b_items.json").read_text(encoding="utf-8"))["items"]
    labels = json.loads((RES / "annotation_heldout_v1b_labels.json").read_text(encoding="utf-8"))["labels"]
    genuine = {(round(it["number"], 2), tuple(it["instrument_candidates"])) for it in items if labels[str(it["item"])]["label"] == "CURRENT_PRICE"}
    base = [r for r in rows if r["verdict"] == CONSISTENT and r["type"] == "QUOTE" and (round(r["value"], 2), tuple(r["candidates"])) in genuine]
    other = {"^NSEI": "^NSEBANK", "^NSEBANK": "^NSEI", "^BSESN": "^NSEI"}
    tally = {}

    def run(name, r, value=None, shift_days=0, cand=None):
        # the altered claim keeps the ORIGINAL spoken-number tolerance and wording (inequality), as a speaker saying a wrong round
        # number would; only the number / day / instrument changes
        c = {"id": "m", "type": "QUOTE", "value": value if value is not None else r["value"], "candidates": cand or r["candidates"],
             "instrument_span": r["span"], "binding": "strong", "tolerance": r.get("tolerance", _tol(r["value"])),
             "inequality": r.get("inequality")}
        t = dt.datetime.strptime(r["aired"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST).timestamp()
        if shift_days:
            d = dt.datetime.fromtimestamp(t, IST).date()
            k = 0
            while True:
                d -= dt.timedelta(days=1)
                if M.day_status(d) == "trading":
                    k += 1
                    if k == shift_days:
                        break
            t = dt.datetime.combine(d, dt.datetime.fromtimestamp(t, IST).time(), IST).timestamp()
        v = verify_price_claim(c, t, 30.0, M)["verdict"]
        tally.setdefault(name, Counter())[v] += 1
    for r in base:
        P = r["value"]
        run("A0 unaltered", r)
        run("A1 shifted by 40 % of its rounding tolerance (expect consistent)", r, value=round(P + 0.4 * r.get("tolerance", _tol(P)), 2))
        iq = r.get("inequality")
        tag = "exact" if not iq else "inequality"
        if not iq:
            run(f"B1 [{tag}] +2%", r, value=round(P * 1.02, 2))
            run(f"B2 [{tag}] -2%", r, value=round(P * 0.98, 2))
            run(f"B3 [{tag}] +5%", r, value=round(P * 1.05, 2))
        else:          # falsify in the direction that makes 'above X' / 'below X' untrue
            f = 1.0 if iq == ">=" else -1.0
            run(f"B1 [{tag}] 2% in the falsifying direction", r, value=round(P * (1 + f * 0.02), 2))
            run(f"B3 [{tag}] 5% in the falsifying direction", r, value=round(P * (1 + f * 0.05), 2))
        run(f"C1 [{tag}] previous trading day", r, shift_days=1)
        alt = other.get(r["candidates"][0])
        if alt:
            run("D1 wrong instrument", r, cand=[alt])
    out = {"n_base_quotes": len(base), "note": "SYNTHETIC alterations of real, blind-confirmed current-price quotes"}
    for k, c in tally.items():
        n = sum(c.values())
        out[k] = {"n": n, **dict(c), "still_consistent_rate": round(c[CONSISTENT] / n, 3), "contradicted_rate": round(c[CONTRADICTED] / n, 3)}
    return out


def _tol(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    if "." in s:
        return 0.05
    tz = len(s) - len(s.rstrip("0"))
    return max(0.05, 10 ** tz / 2)


def e4_resources():
    from backend import pipeline
    out = {}
    t0 = time.perf_counter()
    tracemalloc.start()
    from encoders.market import MarketRecord
    MarketRecord()
    out["market_load_s"] = round(time.perf_counter() - t0, 3)
    out["market_load_peak_MB"] = round(tracemalloc.get_traced_memory()[1] / 1e6, 1)
    tracemalloc.stop()
    for s in pipeline.list_samples():
        pkg = pipeline.load_package(s["id"])
        t0 = time.perf_counter()
        res = pipeline.analyze(pkg, lambda *a, **k: None)
        out[s["id"]] = {"live_analysis_s": round(time.perf_counter() - t0, 3), "peak_traced_MB": res["audit"]["peak_traced_memory_MB_live_stages"],
                        "offline_stages": {k: v.get("seconds") for k, v in pkg.get("offline_stages", {}).items()},
                        "clip_s": s.get("duration_s")}
    try:
        import psutil
        out["process_rss_MB"] = round(psutil.Process(os.getpid()).memory_info().rss / 1e6, 1)
    except ImportError:
        out["process_rss_MB"] = "psutil not installed"
    sizes = {p.name: round(p.stat().st_size / 1e6, 2) for p in (ROOT / "data/market").glob("*.npz")}
    out["storage_MB"] = {"market_files": sizes, "demo_samples": round(sum(p.stat().st_size for p in (ROOT / "demo").rglob("*") if p.is_file()) / 1e6, 1),
                         "code_kB": round(sum(p.stat().st_size for d in ("backend", "encoders", "verification", "frontend")
                                              for p in (ROOT / d).rglob("*") if p.is_file() and p.suffix in (".py", ".js", ".css", ".html")) / 1e3, 1)}
    asr = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "data/transcripts").glob("*.json")]
    out["asr_offline"] = {"files": len(asr), "audio_s": sum(a["audio_s"] for a in asr), "runtime_s": round(sum(a["runtime_s"] for a in asr), 1),
                          "real_time_factor": round(sum(a["runtime_s"] for a in asr) / sum(a["audio_s"] for a in asr), 3)}
    return out


def main():
    M = get_market()
    rep = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    for name, f in (("E1_screen_ticker", lambda: e1_screen(M)), ("E2_spoken_heldout", e2_spoken),
                    ("E3_controlled_manipulations", lambda: e3_manipulations(M)), ("E4_resources", e4_resources)):
        t0 = time.perf_counter()
        rep[name] = f()
        rep[name + "_runtime_s"] = round(time.perf_counter() - t0, 1)
        print(name, json.dumps(rep[name], default=str)[:1500])
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/experiments.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
