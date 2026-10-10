"""Evidence verification engine (verifier 1.0). Implements docs/SPECIFICATION.md - read that first.

Public entry points
  verify_price_claim(claim, t_air, u, market, A)   Check A (+ Check B for QUOTE) for one claim
  check_c(...)                                     SEBI 30-day-lag applicability facts
  verify_package(pkg, market)                      all claims + screen observations of an evidence package
Every result carries: verdict (one of VERDICTS), plain-language finding, why, certificate, cannot_establish, assumptions.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import asdict, dataclass

import numpy as np

from encoders.market import IST, MarketRecord, ist

VERSION = "verifier 1.0 (2026-10-10)"
CONSISTENT, CONTRADICTED, INSUFFICIENT = "Consistent with available records", "Contradicted by available records", "Not enough evidence"
NOT_CHECKABLE = "Not a checkable claim"
IDENTITY = "Claimed execution not independently verified"
import re as _re0
DAYSTAT_RE = _re0.compile(r"\b(?:today'?s|day'?s|intraday|of the day|session'?s?)\s+(low|high)s?\b|\bthe\s+(low|high)\b")
VENDOR_EXTREME_ALLOWANCE = 0.0025   # 0.25 %: day high/low/open/close from vendor 1-min bars vs official statistics (see REGRESSIONS.md R1)
REG_UNCLEAR = "Regulatory applicability requires further information"


@dataclass
class Assumptions:
    broadcaster_delay_max_s: float = 120.0       # broadcaster/ingest delay range [0, this]
    quote_lookback_s: float = 180.0              # a "current" quote may refer to a price seen up to this long before speaking
    plausible_low: float = 0.5                   # a number is a price of the stock only within [0.5x day low, 2x day high]
    plausible_high: float = 2.0
    min_coverage: float = 0.9                    # share of session minutes in the window that must have bars to contradict
    stated_time_slack_s: float = 60.0            # a stated clock time "10:31" is resolved to the minute

    def as_dict(self):
        return asdict(self)


def _tol_words(tol):
    return f"±{tol:g}"


def money(x, sym):
    """₹ for shares, 'points' for indices."""
    return f"{x:,.2f} points" if str(sym).startswith("^") else f"₹{x:,.2f}"


def _window_bars(market: MarketRecord, sym: str, t0: float, t1: float):
    d0 = dt.datetime.fromtimestamp(t0, IST).date()
    a, b = market.session_bounds(d0)
    lo_t, hi_t = max(t0, a), min(t1, b - 1)
    if hi_t < lo_t:
        return [], 0
    bars = market.bars(sym, lo_t, hi_t)
    n_session = len(range(int(lo_t) - int(lo_t) % 60, int(hi_t) + 1, 60))
    return bars, n_session


def _assess(bars, n_session, P, tol, A, ineq=None):
    """-> state in {'compatible','incompatible','unknown'}, certificate bars, coverage. ineq '>=' / '<=' for 'above X' / 'below X'."""
    good = [b for b in bars if not math.isnan(b.lo)]
    cov = len(good) / n_session if n_session else 0.0
    if not good:
        return "unknown", [], cov
    if ineq in (">=", "<="):
        hits = [b for b in good if (b.hi + tol >= P if ineq == ">=" else b.lo - tol <= P)]
        if hits:
            return "compatible", hits, cov
        if cov < A.min_coverage:
            return "unknown", [], cov
        return "incompatible", [max(good, key=lambda b: b.hi) if ineq == ">=" else min(good, key=lambda b: b.lo)], cov
    hits = [b for b in good if b.lo - tol <= P <= b.hi + tol]
    if hits:
        return "compatible", hits, cov
    if cov < A.min_coverage:
        return "unknown", [], cov
    lo = min(good, key=lambda b: b.lo)
    hi = max(good, key=lambda b: b.hi)
    guard = 0.0
    if cov < 1.0:                                  # a minute without a bar could have traded up to one typical 1-min range further
        guard = float(np.median([b.hi - b.lo for b in good]))
    if P < lo.lo - tol - guard or P > hi.hi + tol + guard:
        return "incompatible", [lo, hi] if lo is not hi else [lo], cov
    return "unknown", [], cov



def _index_phrase(what: str) -> str:
    """an index level is recorded, not traded: say that the recorded range included / reached / came within rounding of the value."""
    if what.startswith("at about "):
        return "came within rounding of " + what[len("at about "):]
    if what.startswith("at "):
        return "included " + what[len("at "):]
    if what.startswith("above "):
        return "reached " + what[len("above "):] + " or more"
    if what.startswith("below "):
        return "went down to " + what[len("below "):] + " or less"
    return "was " + what

def verify_price_claim(claim: dict, t_air: float | None, u: float, market: MarketRecord, A: Assumptions = Assumptions(),
                       stated_time: float | None = None, stated_date: dt.date | None = None) -> dict:
    """Check A for QUOTE / PERSONAL_TRADE / CALL-entry / HISTORICAL; Check B (timing) for QUOTE."""
    P, tol = float(claim["value"]), float(claim.get("tolerance", 0.05))
    ctype = claim["type"]
    res = {"claim_id": claim.get("id"), "type": ctype, "value": P, "tolerance": tol, "assumptions": A.as_dict(), "check": "A"}
    cannot = []
    if ctype in ("HYPOTHETICAL", "UNCLASSIFIED", "TARGET", "CALL"):
        msg = {"HYPOTHETICAL": "This is a conditional ('if…') statement, not a statement about a price that already happened.",
               "TARGET": "This is a target, forecast or level to watch, not a statement about a price that already happened.",
               "CALL": "This is a trading recommendation (advice, not a statement of fact), so it cannot be true or false against "
                       "past market records.",
               "UNCLASSIFIED": "We could not tell what this number means (it may be a percentage, a points move or something else), "
                               "so we do not check it."}[ctype]
        res.update(verdict=NOT_CHECKABLE, finding=msg + (" What the market did afterwards is shown as information where possible - "
                   "never as cause and effect." if ctype in ("TARGET", "CALL") else ""),
                   why=f"Claim type: {ctype} ({', '.join(claim.get('why_type', []))}).", certificate=[], cannot_establish=[])
        return res
    if ctype == "HISTORICAL":
        return historical_check(claim, t_air, market, res)
    # ---- when?
    if stated_time is not None:
        t_ref = stated_time
        W = (stated_time - A.stated_time_slack_s, stated_time + A.stated_time_slack_s)
        when_txt = f"the stated time {ist(stated_time)[11:16]} IST (±1 min)"
    elif t_air is not None and ctype in ("QUOTE", "CALL", "PERSONAL_TRADE"):
        t_ref = t_air
        W = (t_air - A.broadcaster_delay_max_s - A.quote_lookback_s - u, t_air + u)
        delay_txt = (f"up to {int(A.broadcaster_delay_max_s)} s broadcast delay, " if A.broadcaster_delay_max_s > 0
                     else "market time read from the chart's ratchets, ")
        when_txt = (f"the {int((W[1] - W[0]) / 60)}-minute window before it was said "
                    f"({ist(W[0])[11:16]}–{ist(W[1])[11:16]} IST: {delay_txt}"
                    f"{int(A.quote_lookback_s)} s for the speaker's own screen, ±{u:.0f} s time uncertainty)")
    elif stated_date is not None:
        a, b = market.session_bounds(stated_date)
        t_ref, W = a, (a, b - 60)
        when_txt = f"the whole session of {stated_date} (no time stated)"
    else:
        res.update(verdict=INSUFFICIENT, finding="We do not know when this refers to, so it cannot be compared with market records.",
                   why="No air time, stated time or date is available for this claim.", certificate=[],
                   cannot_establish=["the time the claim refers to"])
        return res
    day = dt.datetime.fromtimestamp(t_ref, IST).date()
    status = market.day_status(day)
    res["day"], res["day_status"], res["window"] = str(day), status, [ist(W[0]), ist(W[1])]
    if status != "trading":
        if status == "no_trading_recorded" and ctype == "PERSONAL_TRADE" and stated_date is not None:
            res.update(verdict=CONTRADICTED, finding=f"No NSE trading at all is recorded on {day} (a market holiday), so a regular-session "
                       "NSE execution that day is not compatible with the records.",
                       why="Every one of the 427 instruments has no 1-minute bar on that weekday.", certificate=[],
                       cannot_establish=["special sessions (e.g. Muhurat trading) are not in this data", "trades on other venues"])
        else:
            msg = {"weekend": "it was a weekend", "no_trading_recorded": "no trading is recorded that day (market holiday)",
                   "outside_coverage": "our market records do not cover that day"}[status]
            res.update(verdict=INSUFFICIENT, finding=f"Cannot check: {msg}.", why=f"Day {day}: {status}.", certificate=[],
                       cannot_establish=["whether the price applied on another day (a rerun or old clip)"])
        return res
    # ---- which instrument(s)?
    cands = [c for c in claim.get("candidates", []) if c in market.sidx or (market.has_ohlcv and c in market.o_syms)]
    if not cands:
        res.update(verdict=INSUFFICIENT, finding=f"'{claim.get('instrument_span')}' is not an instrument in our market records.",
                   why="No candidate instrument with market data.", certificate=[], cannot_establish=["the instrument meant"])
        return res
    per = {}
    for s in cands:
        rng = market.day_range(s, day)
        if rng is None:
            per[s] = {"state": "unknown", "reason": "no bars that day"}
            continue
        if not (A.plausible_low * rng[0] <= P <= A.plausible_high * rng[1]):
            per[s] = {"state": "not_a_price", "reason": f"{P:g} is far outside its day range {rng[0]:.2f}–{rng[1]:.2f}"}
            continue
        bars, n = _window_bars(market, s, W[0], W[1])
        st, cert, cov = _assess(bars, n, P, tol, A, claim.get("inequality"))
        if st == "compatible":      # best evidence: a minute containing the exact price, closest to the moment it refers to
            cert = sorted(cert, key=lambda b: (not (b.lo <= P <= b.hi), abs(b.t + 30 - t_ref)))
        per[s] = {"state": st, "coverage": round(cov, 3), "certificate": [b.as_dict() for b in cert[:2]],
                  "day_range": [round(rng[0], 2), round(rng[1], 2)]}
    res["per_instrument"] = per
    states = {s: v["state"] for s, v in per.items()}
    name = market.instruments.get(cands[0], {}).get("name", cands[0])
    amb = " (the name was ambiguous; checked every matching instrument)" if len(cands) > 1 else ""
    if any(v == "compatible" for v in states.values()):
        s = next(k for k, v in states.items() if v == "compatible")
        b = per[s]["certificate"][0]
        ineq = claim.get("inequality")
        lo_ok, hi_ok = P - tol, P + tol
        if ineq == ">=":
            what = f"above {money(P, s)}"
            how = f"its high ({money(b['high'], s)}) reached {money(P, s)} or more"
        elif ineq == "<=":
            what = f"below {money(P, s)}"
            how = f"its low ({money(b['low'], s)}) was at or under {money(P, s)}"
        elif b["low"] <= P <= b["high"]:
            what = f"at {money(P, s)}"
            how = f"that range contains {money(P, s)}"
        else:
            what = f"at about {money(P, s)}"
            how = (f"that range overlaps {money(lo_ok, s)}–{money(hi_ok, s)}, which is what a spoken {P:,.0f} can mean "
                   f"({claim.get('tolerance_why', 'tick size')})")
        res.update(verdict=CONSISTENT, instrument=s,
                   finding=(f"The recorded range of {market.instruments.get(s, {}).get('name', s)} {_index_phrase(what)} within {when_txt}.{amb}" if s.startswith("^") else
                            f"The market did trade {market.instruments.get(s, {}).get('name', s)} {what} within {when_txt}.{amb}"),
                   why=f"The 1-minute bar at {b['time_ist']} IST ranged {money(b['low'], s)}–{money(b['high'], s)}; {how}.",
                   certificate=per[s]["certificate"][:1])
    elif all(v == "incompatible" for v in states.values()) and ctype == "QUOTE" and claim.get("binding", "strong") == "weak":
        res.update(verdict=INSUFFICIENT, finding="The number does not match the market at that time, but the sentence does not clearly say it "
                   "is the current price - it may be a level to watch, a target or another figure.",
                   why="Contradictions are only drawn when the words between the stock name and the number state a current price "
                       "(e.g. 'Nifty is currently at …'). Here they do not.", certificate=[])
        cannot.append("whether the number was meant as the current price")
    elif all(v == "incompatible" for v in states.values()) and claim.get("entity_from_context"):
        res.update(verdict=INSUFFICIENT, finding="The number does not match the stock named earlier in the conversation - but the stock was "
                   "only inferred from a previous sentence, so the number may be about a different company.",
                   why="Assumption set includes 'an instrument we did not identify'; a contradiction would need the stock to be named "
                       "in the same sentence.", certificate=[])
        cannot.append("which company the number was about")
    elif all(v == "incompatible" for v in states.values()):
        s = cands[0]
        c = per[s]["certificate"]
        lo, hi = min(x["low"] for x in c), max(x["high"] for x in c)
        res.update(verdict=CONTRADICTED, instrument=s,
                   finding=f"In {when_txt}, {name} {'was recorded' if s.startswith('^') else 'traded'} only between {money(lo, s)} and {money(hi, s)}; {money(P, s)} is outside that range.{amb}",
                   why=f"{int(per[s]['coverage'] * 100)} % of the minutes in the window have bars; the claimed price lies outside the full "
                       f"range even after the tolerance {_tol_words(tol)}" + (" and a one-minute guard for missing minutes" if per[s]['coverage'] < 1 else "") + ".",
                   certificate=c)
    elif all(v == "not_a_price" for v in states.values()):
        res.update(verdict=NOT_CHECKABLE, finding=f"{P:g} is not a price of {name} (far outside its trading range that day) - most likely "
                   "a points move, a percentage or another number in the same sentence.",
                   why="; ".join(f"{k}: {v['reason']}" for k, v in per.items()), certificate=[], cannot_establish=[])
        return res
    else:
        reasons = "; ".join(f"{k}: {v.get('reason', v['state'])}" for k, v in per.items() if v["state"] != "incompatible")
        res.update(verdict=INSUFFICIENT, finding="The records do not settle this claim either way.",
                   why=f"Not decisive for every possible instrument/assumption ({reasons}).", certificate=[])
        cannot.append("which instrument or which number was meant")
    cannot += ["whether the speaker personally traded", "trade-by-trade detail (only 1-minute ranges are available)"]
    if ctype == "QUOTE":
        cannot.append("why the price moved (timing is not causation)")
    res["cannot_establish"] = cannot
    # ---- Check B: timing, QUOTE only, when instrument is unique and the price is plausible
    if ctype == "QUOTE" and not claim.get("inequality") and len(cands) == 1 and per[cands[0]]["state"] in ("compatible", "incompatible"):
        res["timing"] = timing(market, cands[0], P, tol, W, t_ref, day)
    # ---- quantity + identity (PERSONAL_TRADE)
    if ctype == "PERSONAL_TRADE":
        res["identity"] = {"verdict": IDENTITY, "finding": "Public market records cannot show who placed a trade. Only a broker "
                           "contract note or exchange records obtained through an authorised channel could link this execution to the presenter."}
        q = claim.get("quantity")
        if q and res["verdict"] != INSUFFICIENT:
            res["quantity"] = quantity_check(market, res.get("instrument", cands[0]), P, tol, W, q)
            if res["verdict"] == CONSISTENT and res["quantity"]["verdict"].startswith(CONTRADICTED):
                # robust overall verdict: the price existed, but the quantity is impossible on NSE; BSE (not in our data) remains
                # possible, so the claim as a whole is neither supported nor contradicted.
                res["price_verdict"] = CONSISTENT
                res.update(verdict=INSUFFICIENT,
                           finding=f"The price existed, but the claimed {q:,} shares is more than everything traded on NSE at that price in "
                                   "that window. The trade could only have happened on BSE, which is not in our data - so the claim as a "
                                   "whole can be neither confirmed nor ruled out.",
                           why=res["why"] + " Quantity: " + res["quantity"]["finding"])
                res["cannot_establish"] = res.get("cannot_establish", []) + ["BSE executions (not in our data)"]
    return res


def historical_check(claim, t_air, market, res):
    """'55,220 was the high yesterday' -> compare with the previous trading day's 1-minute-bar high (or low / close / open).
    Data-source allowance: tolerance is at least 0.02 % because 1-minute bars from a data vendor can differ slightly from the
    exchange's official day statistics. Contradiction needs >= 98 % of that day's session minutes."""
    import re as _re
    _full = claim.get("sentence", "").lower()
    _pos = claim.get("char_pos")
    text = _full if _pos is None else _full[max(0, _pos - 80):_pos + 60]   # cues must be NEAR the number (run-on ASR sentences)
    P = float(claim["value"])
    if t_air is not None:                         # plausibility first: '7 8 points higher' is not a past price of an index
        d0 = dt.datetime.fromtimestamp(t_air, IST).date()
        s0 = next((c for c in claim.get("candidates", []) if c in market.sidx), None)
        r0 = market.day_range(s0, d0) if s0 else None
        if r0 and not (Assumptions.plausible_low * r0[0] <= P <= Assumptions.plausible_high * r0[1]):
            res.update(verdict=NOT_CHECKABLE, finding=f"{P:g} is not a price of {market.instruments.get(s0, {}).get('name', s0)} - most "
                       "likely a points move or another number.", why="", certificate=[], cannot_establish=[])
            return res
    if t_air is not None and claim.get("role") == "day_stat" and not _re.search(r"yesterday|previous (session|close|day)|last session", text):
        return day_stat_check(claim, t_air, market, res)
    if t_air is None or not _re.search(r"yesterday|previous (session|close|day)|last session", text):
        res.update(verdict=INSUFFICIENT, finding="This refers to a past price, but the day it refers to cannot be identified from the "
                   "sentence.", why="Only 'yesterday' / 'previous session' are resolved automatically.", certificate=[],
                   cannot_establish=["which past day was meant"])
        return res
    stat = "high" if " high" in text else "low" if " low" in text else "close" if ("close" in text or "closed" in text) else "open" if " open" in text else None
    d = dt.datetime.fromtimestamp(t_air, IST).date() - dt.timedelta(days=1)
    while market.day_status(d) != "trading" and d > dt.date(2026, 9, 1):
        d -= dt.timedelta(days=1)
    cands = [c for c in claim.get("candidates", []) if c in market.sidx]
    if not stat or not cands:
        res.update(verdict=INSUFFICIENT, finding="It is not clear which statistic (high, low, close, open) or instrument was meant.",
                   why="No high/low/close/open keyword or no instrument with data.", certificate=[], cannot_establish=["the statistic meant"])
        return res
    sym = cands[0]
    a, b = market.session_bounds(d)
    bars = [x for x in market.bars(sym, a, b - 60) if not math.isnan(x.lo)]
    cov = len(bars) / 375
    rng = (min(x.lo for x in bars), max(x.hi for x in bars)) if bars else None
    if rng and not (Assumptions.plausible_low * rng[0] <= P <= Assumptions.plausible_high * rng[1]):
        res.update(verdict=NOT_CHECKABLE, finding=f"{P:g} is not a price of {market.instruments.get(sym, {}).get('name', sym)} (far outside "
                   f"its range on {d}) - most likely a points move or another number.", why="", certificate=[], cannot_establish=[])
        return res
    if not bars:
        res.update(verdict=INSUFFICIENT, finding=f"No market records for {d}.", why="", certificate=[], cannot_establish=[])
        return res
    if stat == "high":
        bx = max(bars, key=lambda x: x.hi); val = bx.hi
    elif stat == "low":
        bx = min(bars, key=lambda x: x.lo); val = bx.lo
    elif stat == "close":
        bx = bars[-1]; val = bx.close if bx.close is not None else bx.hi
    else:
        bx = bars[0]; val = bx.open if bx.open is not None else bx.lo
    tol = max(float(claim.get("tolerance", 0.05)), round(0.0002 * P, 2))
    name = market.instruments.get(sym, {}).get("name", sym)
    res.update(day=str(d), instrument=sym, certificate=[bx.as_dict()], cannot_establish=["official exchange day statistics (we use 1-minute bars)"])
    if abs(P - val) <= tol:
        res.update(verdict=CONSISTENT, finding=f"{name}'s {stat} on {d} (the previous trading day) was {money(val, sym)}, matching the "
                   f"stated {money(P, sym)}.", why=f"Difference {abs(P - val):.2f} ≤ tolerance {tol:g}.")
    elif cov >= 0.98 and abs(P - val) > max(tol, VENDOR_EXTREME_ALLOWANCE * P):
        res.update(verdict=CONTRADICTED, finding=f"{name}'s {stat} on {d} was {money(val, sym)}, not {money(P, sym)}.",
                   why=f"Difference {abs(P - val):.2f} exceeds both the rounding tolerance {tol:g} and the "
                       f"{VENDOR_EXTREME_ALLOWANCE * 100:g} % allowance for vendor data; {int(cov * 100)} % of that day's minutes have bars.")
    elif cov >= 0.98:
        res.update(verdict=INSUFFICIENT, finding=f"Our records give {name}'s {stat} on {d} as {money(val, sym)}, slightly different from the "
                   f"stated {money(P, sym)} ({abs(P - val) / P * 100:.2f} %). That is too small a gap to call a contradiction.",
                   why=f"Day highs, lows, opens and closes come from a single extreme minute, where 1-minute data from a data vendor can "
                       f"differ from the exchange's official statistics; we only treat gaps above {VENDOR_EXTREME_ALLOWANCE * 100:g} % as "
                       "contradictions. Official exchange day statistics would settle it.",
                   discrepancy={"stated": P, "records": round(val, 2), "pct": round(abs(P - val) / P * 100, 3)})
    else:
        res.update(verdict=INSUFFICIENT, finding=f"The {stat} we can compute ({money(val, sym)}) differs, but that day's records are "
                   "incomplete.", why=f"Only {int(cov * 100)} % of minutes have bars.")
    return res


def day_stat_check(claim, t_air, market, res):
    """'22,570 is the low on the Nifty' (said during the session): compare with the session low/high so far.
    Contradiction only beyond the vendor allowance and only when the low/high so far is not within the broadcast-delay window."""
    import re as _re
    _full = claim.get("sentence", "").lower()
    _pos = claim.get("char_pos")
    text = _full if _pos is None else _full[max(0, _pos - 80):_pos + 60]   # cues must be NEAR the number (run-on ASR sentences)
    P = float(claim["value"])
    m = DAYSTAT_RE.search(text)
    stat = (m.group(1) or m.group(2)).lower() if m else None
    cands = [c for c in claim.get("candidates", []) if c in market.sidx]
    if not stat or not cands or claim.get("entity_from_context"):
        res.update(verdict=INSUFFICIENT, finding="This refers to the day's high or low, but which one or for which stock is unclear.",
                   why="", certificate=[], cannot_establish=["the statistic or instrument meant"])
        return res
    sym = cands[0]
    d = dt.datetime.fromtimestamp(t_air, IST).date()
    a, _ = market.session_bounds(d)
    bars = [x for x in market.bars(sym, a, t_air) if not math.isnan(x.lo)]
    if not bars:
        res.update(verdict=INSUFFICIENT, finding="No market records before this moment.", why="", certificate=[], cannot_establish=[])
        return res
    bx = min(bars, key=lambda x: x.lo) if stat == "low" else max(bars, key=lambda x: x.hi)
    val = bx.lo if stat == "low" else bx.hi
    tol = max(float(claim.get("tolerance", 0.05)), round(0.0002 * P, 2))
    name = market.instruments.get(sym, {}).get("name", sym)
    res.update(day=str(d), instrument=sym, certificate=[bx.as_dict()], cannot_establish=["official exchange statistics (we use 1-minute bars)"],
               window=[ist(a), ist(t_air)])
    if abs(P - val) <= tol:
        res.update(verdict=CONSISTENT, finding=f"{name}'s {stat} so far that day was {money(val, sym)} (at {ist(bx.t)[11:16]} IST), matching the "
                   f"stated {money(P, sym)}.", why=f"Difference {abs(P - val):.2f} ≤ tolerance {tol:g}.")
    elif abs(P - val) > max(tol, VENDOR_EXTREME_ALLOWANCE * P) and len(bars) >= 0.98 * ((t_air - a) / 60):
        res.update(verdict=CONTRADICTED, finding=f"{name}'s {stat} so far that day was {money(val, sym)}, not {money(P, sym)}.",
                   why=f"Difference {abs(P - val):.2f} exceeds the tolerance and the vendor-data allowance.")
    else:
        res.update(verdict=INSUFFICIENT, finding=f"Our records give the {stat} so far as {money(val, sym)}, close to but not exactly "
                   f"{money(P, sym)} - too small a gap to call a contradiction.", why="Within the vendor-data allowance or incomplete minutes.")
    return res


def timing(market, sym, P, tol, W, t_ref, day):
    a, b = market.session_bounds(day)
    bars = [x for x in market.bars(sym, a, b - 60) if not math.isnan(x.lo)]
    hit = [x for x in bars if x.lo - tol <= P <= x.hi + tol]
    inw = [x for x in hit if W[0] - 60 < x.t <= W[1]]
    before = [x for x in hit if x.t <= W[0] - 60]
    after = [x for x in hit if x.t > W[1]]
    if inw:
        return {"class": "consistent", "finding": "The timing fits: the price was in the market at the time it was mentioned."}
    if after and not before:
        f = after[0]
        return {"class": "seen_only_later", "first_seen": ist(f.t), "delta_min": round((f.t - t_ref) / 60, 1),
                "finding": f"The available market records first show {money(P, sym)} at {ist(f.t)[11:16]} IST, about "
                           f"{round((f.t - t_ref) / 60)} min after it was mentioned. This is a timing inconsistency under the displayed "
                           "assumptions. It does not show deliberate fabrication: 1-minute bars cannot prove the price was unknowable earlier.",
                "certificate": [f.as_dict()]}
    if before and not after:
        f = before[-1]
        return {"class": "earlier_only", "last_seen": ist(f.t), "finding": f"{money(P, sym)} matches an EARLIER price ({ist(f.t)[11:16]} IST) "
                "but not the time it was mentioned - possibly an older (stale) quote.", "certificate": [f.as_dict()]}
    if before and after:
        return {"class": "other_times", "finding": "The price occurred earlier and later that day, but not around the time it was mentioned."}
    return {"class": "not_seen_that_day", "finding": f"{money(P, sym)} never occurred in that day's records - possibly a misstatement or a "
            "speech-recognition error (see the word confidence)."}


def quantity_check(market, sym, P, tol, W, q):
    bars, _ = _window_bars(market, sym, W[0], W[1])
    vol = [b for b in bars if b.volume is not None and not math.isnan(b.lo) and b.lo - tol <= P <= b.hi + tol]
    if not any(b.source == "ohlcv" for b in bars):
        return {"verdict": INSUFFICIENT, "finding": "No volume data for this period, so the quantity cannot be checked."}
    V = int(sum(b.volume for b in vol))
    if q > V:
        return {"verdict": CONTRADICTED + " (if executed on NSE in this window)", "nse_volume_at_compatible_minutes": V,
                "finding": f"The claimed {q:,} shares is more than ALL shares traded on NSE ({V:,}) in the minutes when {money(P, sym)} was "
                           "available. This holds only if the trade was on NSE in this window; BSE volume is not in our data.",
                "certificate": [b.as_dict() for b in vol][:5]}
    return {"verdict": CONSISTENT, "nse_volume_at_compatible_minutes": V,
            "finding": f"NSE volume in the matching minutes ({V:,} shares) is large enough for {q:,} shares. This does not show that "
                       "this particular person traded them."}


def outcome_after(market, sym, P, t_air, direction=None):
    """Information only: first time the price P was reached after the statement, in the records (no causation implied)."""
    out = None
    d = dt.datetime.fromtimestamp(t_air, IST).date()
    for k in range(0, 10):
        dd = d + dt.timedelta(days=k)
        if market.day_status(dd) != "trading":
            continue
        a, b = market.session_bounds(dd)
        for x in market.bars(sym, max(a, t_air), b - 60):
            if not math.isnan(x.lo) and x.lo <= P <= x.hi:
                return {"reached": True, "time": ist(x.t), "finding": f"After this was said, the market reached {money(P, sym)} at "
                        f"{ist(x.t)} (no causal link is implied)."}
    return out or {"reached": False, "finding": f"{money(P, sym)} was not reached in the records after the statement (up to "
                   f"{market.coverage['ohlcv_days'][1] if market.coverage['ohlcv_days'] else ''})."}


def check_c(use_date: dt.date | None, use_date_source: str, data_date: dt.date | None, names_security_with_call: bool,
            presenter_status: str = "unknown") -> dict:
    """SEBI circular HO/47/17/12(11)2025-MRD-POD3/I/11107/2026 (2026-05-08), FAQ Q8 as modified; effective 2026-07-01."""
    eff = dt.date(2026, 7, 1)
    facts = {"rule": "SEBI circular HO/47/17/12(11)2025-MRD-POD3/I/11107/2026 dated 2026-05-08, para 6.2 (FAQ Q8): a person engaged "
                     "solely in education should not use market price data of the preceding thirty days to name a security while "
                     "indicating future price, advice or recommendation. Effective 2026-07-01 (para 7).",
             "source_url": "https://www.sebi.gov.in/legal/circulars/may-2026/norms-for-sharing-and-usage-of-price-data-for-educational-purposes_101293.html",
             "market_data_date": str(data_date) if data_date else None, "use_date": str(use_date) if use_date else None,
             "use_date_source": use_date_source, "names_security_with_call_or_target": names_security_with_call,
             "presenter_status": presenter_status}
    if data_date and use_date:
        facts["data_age_days"] = (use_date - data_date).days
    if use_date is None or data_date is None:
        return {**facts, "verdict": REG_UNCLEAR, "finding": "The age of the market data cannot be computed: the date of use or of the "
                "data is not independently established."}
    if use_date < eff:
        return {**facts, "verdict": "Rule not yet in force on the date of use", "finding": f"Used on {use_date}, before 2026-07-01."}
    if facts["data_age_days"] >= 30:
        return {**facts, "verdict": "Data age meets the 30-day lag", "finding": f"The market data is {facts['data_age_days']} days old (≥ 30)."}
    return {**facts, "verdict": REG_UNCLEAR,
            "finding": f"The market data shown is {facts['data_age_days']} day(s) old when used, which is less than 30 days. The 30-day rule "
                       "only applies to a person engaged solely in education (and to data sharing by exchanges/intermediaries). Whether "
                       "this presenter falls in that category cannot be determined from the video"
                       + (" (this is a business-news broadcast; news channels and registered analysts are regulated differently)" if presenter_status == "news_broadcast" else "")
                       + ". This is not a finding of any violation."}
