"""VISUAL FRAME ENCODER: chart-panel reading, ratchet (day-high extension) events, and the video->market time map tau(t).

Observed on CNBC-TV18 (verified on real frames, 2026-10-06): the index chart panel shows
    <INDEX NAME>  <price xxxxx.xx>  <change>  [pct]      and a y-axis of three labels:
    top    = the day's HIGH so far (e.g. 55201 when the market high was 55,200.85)  -> an UP-RATCHET
    middle = (top + bottom) / 2                                                       -> layout self-check
    bottom = the previous close (e.g. 54714 = 55,141.45 - 427.35)                    -> a constant
Nothing here reads a clock or metadata. tau is identified from the market record alone, using the parent project's exact
set-valued dating (encoders/display_clock.py, Theorem T2b: joint price + ratchet feasibility per 1-minute bar):

    F_frame = { market minutes j : the displayed price and day-high are achievable together in bar j }
    tau-set = intersection over frames of ( F_frame shifted by -t_media )   (tau assumed constant within a recording)

Searched over EVERY trading day with OHLCV bars (2026-09-29..10-08), so the date is identified too. If no day / an empty set
survives, the model is rejected and the stage reports ABSTAIN - it never falls back silently to metadata.
"""
from __future__ import annotations

import datetime as dt
import math
import re

from encoders import display_clock as DC
from encoders.market import IST, ist

INDEX_KEYS = {"NIFTY50": "^NSEI", "NIFTY": "^NSEI", "NIFTYBANK": "^NSEBANK", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN"}
PRICE_RE = re.compile(r"^(\d{4,6}\.\d{2})$")
CHANGE_RE = re.compile(r"^[+\-]?(\d{1,5}\.\d{2})$")
INT_RE = re.compile(r"^(\d{4,6})$")
CLOCK_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
MAX_TAU_RADIUS = 90       # a time map wider than this (or split in pieces) is reported as WEAK and not used to time claims
PRICE_TOL = 0.10          # display vs reference vendor: +-0.10 index points on the shown price (measured, see experiments E5)


def _key(t):
    return re.sub(r"[^A-Z0-9]", "", t.upper())


def parse_panel(lines):
    """-> dict or None. lines: [text, conf, x0, y0, x1, y1]."""
    L = [l for l in lines if l[1] >= 0.8]
    names = [l for l in L if _key(l[0]) in INDEX_KEYS and l[3] < 200]
    clocks = [l for l in L if CLOCK_RE.match(l[0].strip())]
    rows = {}
    for c in clocks:
        rows.setdefault(round(c[3] / 8), []).append(c)
    axis_times = [c for r in rows.values() if len(r) >= 2 for c in r]
    screen_clock = [c[0] for c in clocks if c not in axis_times]
    out = {"screen_clock": screen_clock[0] if screen_clock else None}
    for n in sorted(names, key=lambda l: l[3]):
        price = next((l for l in L if PRICE_RE.match(l[0].replace(",", "")) and abs(l[2] - n[2]) <= 30 and n[5] - 5 <= l[3] <= n[5] + 50), None)
        if not price:
            continue
        chg = next((l for l in L if CHANGE_RE.match(l[0].replace(",", "")) and l[2] > price[4] - 5 and abs(l[3] - price[3]) <= 15
                    and l is not price), None)
        axis = sorted([l for l in L if INT_RE.match(l[0]) and abs(l[2] - n[2]) <= 40 and price[5] + 10 <= l[3] <= price[5] + 200],
                      key=lambda l: l[3])
        rec = {"name_text": n[0], "symbol": INDEX_KEYS[_key(n[0])], "price": float(price[0].replace(",", "")),
               "change": float(chg[0].replace(",", "").lstrip("+")) if chg else None, "boxes": {"name": n[2:6], "price": price[2:6]},
               **out}
        if len(axis) >= 3:
            top, mid, bot = (float(axis[0][0]), float(axis[1][0]), float(axis[-1][0]))
            rec.update(axis_top=top, axis_mid=mid, axis_bottom=bot, layout_ok=abs(mid - (top + bot) / 2) <= 1.5)
            rec["boxes"]["axis"] = [axis[0][2:6], axis[-1][2:6]]
        else:
            rec.update(axis_top=None, axis_mid=None, axis_bottom=None, layout_ok=False)
        if rec["change"] is not None and rec.get("axis_bottom"):
            rec["prev_close_consistent"] = abs((rec["price"] - rec["change"]) - rec["axis_bottom"]) <= 1.5 or \
                abs((rec["price"] + rec["change"]) - rec["axis_bottom"]) <= 1.5
        return rec
    return out if out["screen_clock"] else None


def _bars_for_day(market, sym, d):
    a, b = market.session_bounds(d)
    bars = market.bars(sym, a, b - 60)
    if len(bars) < 300 or any(x.source != "ohlcv" for x in bars):
        return None, None
    O, H, Lo, C = [], [], [], []
    last = None
    for x in bars:                                 # a minute without a bar: carry the last close (flat bar) - documented
        if math.isnan(x.lo):
            if last is None:
                return None, None
            O.append(last); H.append(last); Lo.append(last); C.append(last)
        else:
            lo, hi = x.lo, x.hi
            o = min(max(x.open, lo), hi)
            c = min(max(x.close, lo), hi)
            O.append(o); H.append(hi); Lo.append(lo); C.append(c)
            last = c
    return DC.Bars(tuple(O), tuple(H), tuple(Lo), tuple(C), tuple([0.0] * len(O))), a


def infer_tau(frames, market, tol=PRICE_TOL):
    """frames: [{t_media, panel}] -> identification result (all days searched)."""
    use = [f for f in frames if f.get("panel") and f["panel"].get("price") and f["panel"].get("symbol")]
    if not use:
        return {"status": "ABSTAIN", "reason": "no chart panel with a readable index price in these frames", "frames_used": 0}
    sym_counts = {}
    for f in use:
        sym_counts[f["panel"]["symbol"]] = sym_counts.get(f["panel"]["symbol"], 0) + 1
    days = [d for d in market.o_days if market.day_status(d) == "trading"] if market.has_ohlcv else []
    results = {}
    for d in days:
        tau_set = None
        n = 0
        for f in use:
            p = f["panel"]
            bars, base = _bars_for_day(market, p["symbol"], d)
            if bars is None:
                tau_set = None
                break
            cp = (p["price"] - tol, p["price"] + tol)
            cM = None
            if p.get("layout_ok") and p.get("axis_top") and abs(p["axis_top"] - (p.get("axis_bottom") or -1e9)) > 1.5:
                cM = (p["axis_top"] - 1.0 - tol, p["axis_top"] + 1.0 + tol)   # label rule unknown: round, truncate or CEILING (observed 22,728.10 -> 22729)
            J = DC.joint_price_ratchets(bars, cp, cM, None)
            s = DC.IntervalSet.from_bars(J).shift(base - f["t_media"])
            tau_set = s if tau_set is None else (tau_set & s)
            n += 1
            if not tau_set.ivs:
                break
        if tau_set is not None and tau_set.ivs:
            results[str(d)] = {"intervals": tau_set.ivs, "frames": n}
    if not results:
        return {"status": "ABSTAIN", "reason": "no trading day in the market record is consistent with every displayed price and day-high "
                "(model rejected: wrong layout reading, a different data feed, or the day is outside our records)",
                "frames_used": len(use), "symbols": sym_counts, "days_searched": [str(d) for d in days]}
    if len(results) > 1:
        return {"status": "ABSTAIN", "reason": f"more than one trading day fits the display ({', '.join(results)}): date not identified",
                "frames_used": len(use), "candidates": results, "symbols": sym_counts}
    day, r = next(iter(results.items()))
    lo_, hi_ = r["intervals"][0][0], r["intervals"][-1][1]
    if len(r["intervals"]) > 1 or (hi_ - lo_) / 2 > MAX_TAU_RADIUS:
        return {"status": "WEAK", "reason": f"the chart narrows the time only to {len(r['intervals'])} stretch(es) spanning ±{(hi_ - lo_) / 2:.0f} s on {day} "
                f"({r['frames']} usable frames) - too loose to time claims (need one stretch within ±{MAX_TAU_RADIUS} s)",
                "day": day, "tau_intervals": r["intervals"], "frames_used": r["frames"], "symbols": sym_counts,
                "days_searched": [str(d) for d in days]}
    lo, hi = r["intervals"][0][0], r["intervals"][-1][1]
    return {"status": "IDENTIFIED", "day": day, "tau_intervals": r["intervals"], "tau_lo": lo, "tau_hi": hi,
            "tau_centre": (lo + hi) / 2, "tau_radius": (hi - lo) / 2, "frames_used": r["frames"], "symbols": sym_counts,
            "days_searched": [str(d) for d in days], "method": "exact joint price + day-high ratchet sets (display_clock T2b), all days"}


def ratchet_events(frames):
    """Day-high (top axis label) extensions between consecutive frames of the same instrument."""
    ev, last = [], {}
    for f in frames:
        p = f.get("panel") or {}
        if not p.get("layout_ok") or p.get("axis_top") is None:
            continue
        s = p["symbol"]
        if s in last and p["axis_top"] > last[s]["axis_top"]:
            ev.append({"t_media": f["t_media"], "symbol": s, "from": last[s]["axis_top"], "to": p["axis_top"], "thumb": f.get("thumb")})
        last[s] = p
    return ev


def encode(frames_doc, market, clock=None):
    """Full visual-frame stage. clock (capture clock) is used ONLY to report agreement afterwards, never as an input to tau."""
    frames = []
    for fr in frames_doc["frames"]:
        frames.append({"t_media": fr["t_media"], "thumb": fr.get("thumb"), "panel": parse_panel(fr["lines"])})
    panels = [f for f in frames if f["panel"] and f["panel"].get("price")]
    tau = infer_tau(frames, market)
    ev = ratchet_events(frames)
    out = {"n_frames": len(frames), "n_panel_frames": len(panels), "ratchet_events": ev, "tau": tau,
           "frames": [{"t_media": f["t_media"], "thumb": f["thumb"], **({k: v for k, v in (f["panel"] or {}).items() if k != "boxes"})}
                      for f in frames], "engine": frames_doc.get("engine"), "ocr_cpu_s": frames_doc.get("ocr_cpu_s")}
    if tau["status"] == "IDENTIFIED" and clock is not None:
        t_mid = sum(f["t_media"] for f in panels) / len(panels)
        cap = clock.wall(t_mid)
        mk = t_mid + tau["tau_centre"]
        out["agreement_with_capture_clock"] = {"capture_air_time": ist(cap), "market_time_from_ratchets": ist(mk),
                                               "air_minus_market_s": round(cap - mk, 1), "tau_radius_s": round(tau["tau_radius"], 1),
                                               "note": "positive = the broadcast shows market data this many seconds after it happened"}
    return out
