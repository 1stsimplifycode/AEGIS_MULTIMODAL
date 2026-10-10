"""Analysis pipeline - implements the mandated architecture exactly, stage by stage (each stage reports input, status, output, evidence):

  1 visual_frame   VISUAL FRAME ENCODER   chart panels -> day-high ratchets -> video->market time map tau(t) with uncertainty
  2 visual_text    VISUAL TEXT ENCODER    trading panels, fill quantities, prices, names, on-screen clocks, P&L
  3 audio          AUDIO ENCODER          speech -> spoken executions, quoted prices, quantities, speech times
  4 claim_set      CLAIM SET WITH MARKET TIME   who said/showed what, when (market time via tau), with evidence pointers
  5 tape           ANONYMOUS EXCHANGE TAPE     NSE 1-minute price/volume with resolution and completeness metadata
  6 fill           FILL CONSERVATION      (parallel branch)
  7 knowability    KNOWABILITY            (parallel branch)
  8 data_age       DATA AGE               (parallel branch)
  9 certificate    FINAL IMPOSSIBILITY CERTIFICATE (PASS / FAIL / ABSTAIN per check)

OCR and speech recognition of the demo samples ran offline on this machine (recorded CPU time is shown, status 'done_offline');
everything from parsing onwards runs live on every request. Nothing is shown that the backend did not execute.
"""
from __future__ import annotations

import datetime as dt
import json
import platform
import time
import tracemalloc
from pathlib import Path

from encoders.claims import extract
from encoders.clock import CaptureClock
from encoders.market import IST, get_market, ist
from verification import branches as BR
from verification.engine import (CONSISTENT, CONTRADICTED, INSUFFICIENT, NOT_CHECKABLE, VERSION, Assumptions, check_c,
                                 outcome_after, verify_price_claim)

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "demo/samples"
STAGES = [("visual_frame", "Visual frame encoder"), ("visual_text", "Visual text encoder"), ("audio", "Audio encoder"),
          ("claim_set", "Claim set with market time"), ("tape", "Anonymous exchange tape"), ("fill", "Fill conservation"),
          ("knowability", "Knowability"), ("data_age", "Data age"), ("certificate", "Impossibility certificate")]


def list_samples():
    out = []
    for p in sorted(SAMPLES.glob("*/package.json")):
        m = json.loads(p.read_text(encoding="utf-8"))["meta"]
        d = {k: m.get(k) for k in ("id", "title", "channel_name", "recorded_ist", "duration_s", "description", "synthetic", "thumbnail", "kind")}
        if d["thumbnail"] and not (p.parent / "media" / d["thumbnail"]).exists():
            d["thumbnail"] = None
        out.append(d)
    return sorted(out, key=lambda x: (bool(x.get("synthetic")), x.get("recorded_ist") or ""))


def load_package(sample_id: str) -> dict:
    p = SAMPLES / sample_id / "package.json"
    if not p.exists() or "/" in sample_id or "\\" in sample_id or ".." in sample_id:
        raise FileNotFoundError(sample_id)
    pkg = json.loads(p.read_text(encoding="utf-8"))
    fr = SAMPLES / sample_id / "frames.json"
    if fr.exists():
        pkg["frames_doc"] = json.loads(fr.read_text(encoding="utf-8"))
    return pkg


def _plain(verdict):
    return {CONSISTENT: "consistent", CONTRADICTED: "contradicted", INSUFFICIENT: "insufficient", NOT_CHECKABLE: "not_checkable"}.get(verdict, "other")


def _nearest_thumb(frames_doc, t):
    if not frames_doc or t is None:
        return None
    f = min(frames_doc["frames"], key=lambda f: abs(f["t_media"] - t))
    return {"thumb": f.get("thumb"), "t_media": f["t_media"]} if abs(f["t_media"] - t) <= 3 else None


def analyze(pkg: dict, progress) -> dict:
    """progress(stage_key, status, seconds=None, detail=None)"""
    market = get_market()
    meta = dict(pkg["meta"])
    if meta.get("media"):
        meta["media_available"] = (SAMPLES / meta["id"] / "media" / meta["media"]["video"]).exists()
    clock = CaptureClock.from_dict(pkg["clock"]) if pkg.get("clock") else None
    frames_doc = pkg.get("frames_doc")
    off = pkg.get("offline_stages", {})
    detail = {}
    tracemalloc.start()
    run_t = {}

    # ---------------------------------------------------------------- 1 VISUAL FRAME ENCODER
    progress("visual_frame", "running")
    t0 = time.perf_counter()
    if frames_doc:
        from encoders.frame_encoder import encode as fenc
        vf = fenc(frames_doc, market, clock)
        tau = vf["tau"]
        out_txt = (f"{vf['n_panel_frames']} of {vf['n_frames']} frames show a readable index chart panel; "
                   f"{len(vf['ratchet_events'])} day-high extension (ratchet) event(s). ")
        if tau["status"] == "IDENTIFIED":
            out_txt += (f"Video->market time identified from the chart alone: {tau['day']}, uncertainty ±{tau['tau_radius']:.0f} s "
                        f"(searched {len(tau['days_searched'])} trading days).")
        else:
            out_txt += f"Time map NOT identified: {tau['reason']}."
        detail["visual_frame"] = {"input": f"{vf['n_frames']} full frames decoded at {frames_doc.get('fps')} frame/s from {frames_doc.get('source')}",
                                  "processing": "OCR (offline, recorded) -> chart-panel parser -> ratchet detector -> exact set-valued "
                                                "dating (display_clock T2b) over every trading day",
                                  "output": out_txt, "result": vf, "ocr_cpu_s_offline": frames_doc.get("ocr_cpu_s")}
        status = "done"
    else:
        tau = {"status": "ABSTAIN", "reason": "no video frames for this input (typed or synthetic claims)"}
        detail["visual_frame"] = {"input": "none", "processing": "-", "output": "Not available: no video frames.", "result": {"tau": tau}}
        status = "not_available"
    run_t["visual_frame"] = time.perf_counter() - t0
    progress("visual_frame", status, round(run_t["visual_frame"], 2), detail["visual_frame"]["output"])

    # ---------------------------------------------------------------- 2 VISUAL TEXT ENCODER
    progress("visual_text", "running")
    t0 = time.perf_counter()
    if frames_doc:
        from encoders.visual_text import encode as tenc
        vt = tenc(frames_doc)
        clocks = sorted({c["clock"] for c in vt["screen_clock_frames"]})
        detail["visual_text"] = {"input": f"OCR text of the same {vt['n_frames']} frames", "processing": "trading-panel / quantity / P&L / clock / "
                                 "name-price pattern finder", "output": vt["summary"] + (f". On-screen clock read: {', '.join(clocks[:4])}" if clocks else "")
                                 + f". {vt['n_name_price_pairs']} name-price pairs on screen.", "result": vt}
        status = "done"
    else:
        vt = None
        detail["visual_text"] = {"input": "none", "processing": "-", "output": "Not available: no video frames.", "result": None}
        status = "not_available"
    run_t["visual_text"] = time.perf_counter() - t0
    progress("visual_text", status, round(run_t["visual_text"], 2), detail["visual_text"]["output"])

    # ---------------------------------------------------------------- 3 AUDIO ENCODER
    progress("audio", "running")
    t0 = time.perf_counter()
    if pkg.get("transcript"):
        claims, sents = extract(pkg["transcript"]["segments"])
        claims = [c for c in claims if meta["clip"][0] <= c["t_media"] <= meta["clip"][1]]
        for c in claims:
            c["source"], c["who"] = "speech", "a speaker on the broadcast (speaker not identified)"
        sents = [s for s in sents if meta["clip"][0] <= s["start"] <= meta["clip"][1]]
        detail["audio"] = {"input": f"audio track, {len(sents)} spoken sentences ({pkg['transcript']['model']}; recognition ran offline)",
                           "processing": "sentence building -> stock/index names -> numbers -> claim type (observation, recall, prediction, "
                                         "recommendation, execution, conditional) -> binding / inequality / retraction",
                           "output": f"{len(claims)} number(s) attached to a stock or index; "
                                     f"{sum(1 for c in claims if c['type'] == 'PERSONAL_TRADE')} spoken execution(s); "
                                     f"{sum(1 for c in claims if c.get('quantity'))} with a quantity", "result": {"n_claims": len(claims)}}
        status = "done"
    else:
        claims, sents = [], []
        detail["audio"] = {"input": "none", "processing": "-", "output": "Not available: no audio for this input.", "result": None}
        status = "not_available"
    run_t["audio"] = time.perf_counter() - t0
    progress("audio", status, round(run_t["audio"], 2), detail["audio"]["output"])

    # ---------------------------------------------------------------- 4 CLAIM SET WITH MARKET TIME
    progress("claim_set", "running")
    t0 = time.perf_counter()
    if tau.get("status") == "IDENTIFIED":
        time_source = "chart ratchets (video->market time map, from the video itself)"
        to_market = lambda t: t + tau["tau_centre"]                                  # noqa: E731
        u = tau["tau_radius"]
        A = Assumptions(broadcaster_delay_max_s=0.0)                                 # tau already contains broadcast + display delay
        tnote = f"tau identified from the chart; ±{u:.0f} s"
    elif clock:
        time_source = "our capture clock (SNTP-corrected, independently measured) - chart ratchets unavailable"
        to_market = clock.wall
        u = clock.uncertainty_s
        A = Assumptions()
        tnote = ("Chart ratchets could not be used (" + tau.get("reason", "?") + "). Using our own capture clock instead, plus a 0-120 s "
                 "broadcast-delay assumption.")
    else:
        time_source, to_market, u, A = "none", None, 0.0, Assumptions()
        tnote = "No time source: claims without a stated time cannot be placed in market time."
    typed = pkg.get("typed_claims", [])
    for c in typed:
        c.setdefault("source", "typed")
        c.setdefault("who", "synthetic test claim (made up)" if meta.get("synthetic") else "typed by the user")
    all_claims = claims + typed
    claim_set = []
    for c in all_claims:
        tm = to_market(c["t_media"]) if (to_market and c.get("t_media") is not None) else None
        claim_set.append({"id": c["id"], "source": c.get("source"), "who": c.get("who"), "what": c.get("sentence"),
                          "type": c["type"], "kind": BR.OBS_KIND.get(c["type"], c["type"]), "instrument_span": c.get("instrument_span"),
                          "candidates": c.get("candidates"), "number": c.get("value"), "quantity": c.get("quantity"),
                          "t_media": c.get("t_media"), "market_time": ist(tm) if tm else c.get("stated_time_text"),
                          "time_source": time_source if tm else ("stated in the claim" if c.get("stated_date") else "none"),
                          "uncertainty_s": u if tm else None, "evidence": {"sentence_id": c.get("sentence_id"),
                                                                           "frame": _nearest_thumb(frames_doc, c.get("t_media"))}})
    detail["claim_set"] = {"input": "audio claims + visual text + typed claims; time map from stage 1 (or the capture clock)",
                           "processing": "join each observation with its source, speaker, market time and evidence pointers",
                           "output": f"{len(claim_set)} claim(s). Time source: {time_source}. {tnote}", "result": claim_set}
    run_t["claim_set"] = time.perf_counter() - t0
    progress("claim_set", "done", round(run_t["claim_set"], 2), detail["claim_set"]["output"])

    # ---------------------------------------------------------------- 5 ANONYMOUS EXCHANGE TAPE (+ per-claim market matching)
    progress("tape", "running")
    t0 = time.perf_counter()
    results = []
    for c in all_claims:
        tm = to_market(c["t_media"]) if (to_market and c.get("t_media") is not None) else None
        stated_time = c.get("stated_time_epoch")
        stated_date = dt.date.fromisoformat(c["stated_date"]) if c.get("stated_date") else None
        r = verify_price_claim(c, tm, u, market, A, stated_time=stated_time, stated_date=stated_date)
        if c["type"] in ("TARGET", "CALL") and c.get("candidates") and tm:
            s0 = next((s for s in c["candidates"] if s in market.sidx), None)
            if s0:
                rng = market.day_range(s0, dt.datetime.fromtimestamp(tm, IST).date())
                if rng and A.plausible_low * rng[0] <= c["value"] <= A.plausible_high * rng[1]:
                    r["outcome_after"] = outcome_after(market, s0, c["value"], tm)
        r.update(claim=c, t_air_ist=ist(tm) if tm else None, t_air_epoch=tm, plain=_plain(r["verdict"]), time_source=time_source if tm else None,
                 instrument_names={s: market.instruments.get(s, {}).get("name", s) for s in c.get("candidates", [])})
        sym = r.get("instrument") or next((s for s in c.get("candidates", []) if s in market.sidx), None)
        tref = tm or stated_time
        if sym and tref:
            r["context_bars"] = [b.as_dict() for b in market.bars(sym, tref - 15 * 60, tref + 10 * 60) if b.lo == b.lo]
            r["context_symbol"] = sym
        r["frame"] = _nearest_thumb(frames_doc, c.get("t_media"))
        results.append(r)
    # numbers shown NOT to be prices of the named stock (points moves, %, fragments) are not claims: drop them from the claim set
    dropped = {r["claim"]["id"] for r in results if r["claim"]["type"] in ("QUOTE", "HISTORICAL", "UNCLASSIFIED") and r["verdict"] == NOT_CHECKABLE}
    claim_set = [c for c in claim_set if c["id"] not in dropped]
    results = [r for r in results if r["claim"]["id"] not in dropped]
    detail["claim_set"]["result"] = claim_set
    detail["claim_set"]["output"] += f" {len(dropped)} number(s) dropped as not being a price of the named stock (e.g. a points move)."
    used_syms = sorted({r.get("context_symbol") for r in results if r.get("context_symbol")})
    detail["tape"] = {"input": f"{len(used_syms)} instrument(s): {', '.join(used_syms) or '-'}",
                      "processing": "NSE 1-minute price ranges and volumes in each claim's window; completeness measured per window",
                      "output": "Resolution: 1 minute (NOT trade-by-trade). Volume: NSE only. Coverage: low/high "
                                f"{market.coverage['lohi_days'][0]}..{market.coverage['lohi_days'][1]}, volume {market.coverage['ohlcv_days'][0]}.."
                                f"{market.coverage['ohlcv_days'][1]}. Holidays have no bars.",
                      "result": {"files": market.file_hashes(), "coverage": market.coverage, "symbols": used_syms}}
    run_t["tape"] = time.perf_counter() - t0
    progress("tape", "done", round(run_t["tape"], 2), detail["tape"]["output"])

    # ---------------------------------------------------------------- screen observations for KNOWABILITY (ticker; panels define tau)
    screen, screen_items = [], []
    obs_all = [dict(o) for o in (pkg.get("screen") or {}).get("observations", [])]
    layout = None
    if obs_all and clock and (pkg.get("screen") or {}).get("layout_validated", True):
        from encoders.visual import recording_layout_check
        layout = recording_layout_check(obs_all, market, dt.datetime.fromtimestamp(clock.wall(obs_all[0]["t_media"]), IST).date())
    for o in obs_all:
        if not (meta["clip"][0] <= o["t_media"] <= meta["clip"][1]):
            continue
        e = dict(o)
        tm = to_market(o["t_media"]) if to_market else None
        if o.get("usable") and tm:
            c = {"id": f"screen{len(screen)}", "type": "QUOTE", "value": o["price"], "tolerance": 0.05, "candidates": [o["symbol"]],
                 "instrument_span": o["name"], "why_type": ["on-screen ticker"], "binding": "strong"}
            v = verify_price_claim(c, tm, u, market, A)
            e.update(verdict=v["verdict"], plain=_plain(v["verdict"]), timing=(v.get("timing") or {}).get("class"), certificate=v.get("certificate", []))
            pv = {CONSISTENT: BR.PASS, CONTRADICTED: BR.FAIL}.get(v["verdict"], BR.ABSTAIN)
            screen_items.append({"claim_id": c["id"], "source": "screen ticker", "kind": "observation (displayed price)", "value": o["price"],
                                 "instrument": o["symbol"], "market_time": ist(tm), "verdict": pv, "reason": v.get("finding"),
                                 "certificate_bars": v.get("certificate", [])[:1], "frame_t_media": o["t_media"]})
        else:
            e.update(verdict="Not used as evidence", plain="unused")
        e["t_air_ist"] = ist(tm) if tm else None
        screen.append(e)

    # ---------------------------------------------------------------- 6-8 THREE PARALLEL BRANCHES
    t0 = time.perf_counter()
    progress("fill", "running"); progress("knowability", "running"); progress("data_age", "running")
    b_fill = BR.fill_branch(results)
    b_know = BR.knowability_branch(results, screen_items)
    use_date = dt.date.fromisoformat(meta["use_date"]) if meta.get("use_date") else None
    data_dates = sorted({r.get("day") for r in results if r["plain"] == "consistent" and r.get("day")})
    data_date = (dt.date.fromisoformat(tau["day"]) if tau.get("status") == "IDENTIFIED" else
                 dt.date.fromisoformat(data_dates[0]) if data_dates else (use_date if meta.get("live_capture") else None))
    cc = check_c(use_date, meta.get("use_date_source", "unknown"), data_date, any(r["claim"]["type"] in ("CALL", "TARGET") for r in results),
                 meta.get("presenter_status", "unknown"))
    b_age = BR.data_age_branch(cc)
    b_age["data_date_basis"] = ("the day identified from the chart ratchets" if tau.get("status") == "IDENTIFIED" else
                                "the day the spoken prices match" if data_dates else "live capture date" if meta.get("live_capture") else "unknown")
    for key, b in (("fill", b_fill), ("knowability", b_know), ("data_age", b_age)):
        n = len(b["items"])
        cnt = {v: sum(1 for i in b["items"] if i["verdict"] == v) for v in (BR.PASS, BR.FAIL, BR.ABSTAIN)}
        detail[key] = {"input": f"{n} item(s) from the claim set" if key != "data_age" else "market-data date, use date, presenter status",
                       "processing": b["question"], "output": f"{b['verdict']} — PASS {cnt['PASS']}, FAIL {cnt['FAIL']}, ABSTAIN {cnt['ABSTAIN']}"
                       + (f". {b['note']}" if b.get("note") else ""), "result": b}
        progress(key, "done", round(time.perf_counter() - t0, 3), detail[key]["output"])
    run_t["branches"] = time.perf_counter() - t0

    # ---------------------------------------------------------------- 9 CERTIFICATE
    progress("certificate", "running")
    t0 = time.perf_counter()
    peak = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()
    audit = {"algorithm_version": VERSION, "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "source": meta.get("source"), "clip_media_s": meta["clip"], "clock": pkg.get("clock"),
             "market_data": {"files": market.file_hashes(), "granularity": "1-minute bars (NOT trade-by-trade)", "coverage": market.coverage,
                             "provider": "Yahoo Finance chart endpoint snapshot (NSE); see docs/DATA_AUDIT.md"},
             "speech_model": (pkg.get("transcript") or {}).get("model"), "ocr": (frames_doc or {}).get("engine"),
             "time_source": time_source, "assumptions": A.as_dict(), "regulation_source": "data/regulatory/sebi_circular_2026-05-08.txt",
             "runtime_s": {k: round(v, 3) for k, v in run_t.items()}, "peak_traced_memory_MB_live_stages": round(peak, 1),
             "python": platform.python_version(), "offline_stages": off, "synthetic": meta.get("synthetic", False), "screen_layout_check": layout}
    steps = [f"python -m scripts.extract_frames --sample {meta['id']}  (OCR, offline)" if frames_doc else None,
             "python -m encoders.audio <capture> <out.json>  (speech recognition, offline)" if pkg.get("transcript") else None,
             f"POST /api/analyses {{\"sample_id\": \"{meta['id']}\"}}  (all later stages, deterministic)",
             "python -m pytest -q  (regression tests)"]
    cert = BR.certificate(meta, {k: v for k, v in tau.items() if k != "candidates"}, [b_fill, b_know, b_age], audit, [s for s in steps if s])
    detail["certificate"] = {"input": "the three branch results", "processing": "assemble verdicts, meanings, assumptions, evidence, sources, steps",
                             "output": f"Certificate {cert['certificate_id']}: FILL {b_fill['verdict']} · KNOWABILITY {b_know['verdict']} · "
                                       f"DATA AGE {b_age['verdict']}", "result": {"certificate_id": cert["certificate_id"]}}
    progress("certificate", "done", round(time.perf_counter() - t0, 3), detail["certificate"]["output"])
    timeline = build_timeline(results, screen, detail.get("visual_frame", {}).get("result"))
    return {"meta": meta, "stages": detail, "claims": results, "claim_set": claim_set, "screen": screen, "timeline": timeline,
            "branches": {"fill": b_fill, "knowability": b_know, "data_age": b_age}, "certificate": cert, "audit": audit, "tau": tau,
            "sentences": [{"id": s["id"], "start": s["start"], "end": s["end"], "text": s["text"]} for s in sents]}


def build_timeline(results, screen, vf):
    ev = []
    for r in results:
        c = r["claim"]
        if c.get("t_media") is None:
            continue
        ev.append({"kind": "speech", "t_media": c["t_media"], "label": c["sentence"][:140], "claim_id": c["id"], "plain": r["plain"],
                   "type": c["type"], "t_air_ist": r.get("t_air_ist")})
    for s in screen:
        if s.get("usable"):
            ev.append({"kind": "screen", "t_media": s["t_media"], "label": f"Ticker: {s['name']} {s['price']:,}", "plain": s["plain"],
                       "symbol": s["symbol"], "t_air_ist": s.get("t_air_ist")})
    for e in (vf or {}).get("ratchet_events", []) if isinstance(vf, dict) else []:
        ev.append({"kind": "ratchet", "t_media": e["t_media"], "label": f"Chart day-high extends {e['from']:,.0f} → {e['to']:,.0f} ({e['symbol']})",
                   "plain": "ratchet", "thumb": e.get("thumb")})
    return sorted(ev, key=lambda e: e["t_media"])
