"""The three parallel verification branches and the Final Impossibility Certificate.

Verdict meanings (fixed; shown verbatim in the UI and the certificate):
  PASS     the tested constraint was satisfied by the available records. It does NOT prove who traded, that the recording is
           authentic, or that anyone complied with any regulation.
  FAIL     a contradiction was demonstrated under the stated assumptions (listed with the item).
  ABSTAIN  an essential observation is missing, or no reliable conclusion is possible.

FILL CONSERVATION  claimed executed quantity (and its price/time) vs the maximum executed volume available in that instrument,
                   venue and interval (NSE 1-minute volume; BSE not in our data -> the venue is an explicit assumption).
KNOWABILITY        an asserted observation ("it is now at X", a displayed price) vs what the market record made observable at that
                   market moment. Predictions, targets, recommendations and conditionals are NOT observations -> ABSTAIN.
DATA AGE           market-data date vs use date under SEBI's 30-day educational rule, with scope (who it applies to) explicit.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from verification.engine import CONSISTENT, CONTRADICTED, INSUFFICIENT, NOT_CHECKABLE

PASS, FAIL, ABSTAIN = "PASS", "FAIL", "ABSTAIN"
MEANING = {
    PASS: "The tested constraint was satisfied by the available records. This does not prove who traded, that the recording is "
          "authentic, or regulatory compliance.",
    FAIL: "A contradiction was demonstrated under the assumptions listed with this item.",
    ABSTAIN: "An essential observation is missing or no reliable conclusion is possible, so no verdict is given.",
}
OBS_KIND = {"QUOTE": "observation (current price)", "HISTORICAL": "recall (past price)", "TARGET": "prediction / level",
            "CALL": "recommendation", "HYPOTHETICAL": "conditional", "UNCLASSIFIED": "unclear", "PERSONAL_TRADE": "claimed execution"}


def _branch_verdict(items):
    v = [i["verdict"] for i in items]
    if not v:
        return ABSTAIN
    if FAIL in v:
        return FAIL
    if PASS in v:
        return PASS
    return ABSTAIN


def fill_branch(results):
    items = []
    for r in results:
        c = r["claim"]
        if not c.get("quantity"):
            continue
        q = r.get("quantity") or {}
        price_v = r.get("price_verdict", r["verdict"])
        base = {"claim_id": c["id"], "quantity": c["quantity"], "price": c["value"], "instrument": r.get("instrument") or (c.get("candidates") or [None])[0],
                "window": r.get("window"), "certificate_bars": (q.get("certificate") or r.get("certificate") or [])[:6],
                "assumptions": ["venue = NSE cash market (BSE executions are not in our data)",
                                "the claimed time is correct to the minute (or the whole session if no time was stated)",
                                "1-minute volume is an upper bound on what could execute at the claimed price in that minute"]}
        if r.get("day_status") == "no_trading_recorded" or (price_v == CONTRADICTED and r["verdict"] == CONTRADICTED):
            items.append({**base, "verdict": FAIL, "reason": r.get("finding")})
        elif q.get("verdict", "").startswith(CONTRADICTED):
            items.append({**base, "verdict": FAIL, "reason": q["finding"], "nse_volume_bound": q.get("nse_volume_at_compatible_minutes")})
        elif q.get("verdict") == CONSISTENT and price_v == CONSISTENT:
            items.append({**base, "verdict": PASS, "reason": q["finding"], "nse_volume_bound": q.get("nse_volume_at_compatible_minutes")})
        else:
            items.append({**base, "verdict": ABSTAIN, "reason": r.get("finding")})
    return {"name": "FILL CONSERVATION", "question": "Could the claimed executed quantity have traded at that price and time?",
            "verdict": _branch_verdict(items), "items": items,
            "note": None if items else "No executed-quantity (fill) claim was found in speech, on screen, or typed - nothing to test."}


def knowability_branch(results, screen_items):
    items = []
    for r in results:
        c = r["claim"]
        kind = OBS_KIND.get(c["type"], c["type"])
        if c.get("quantity"):
            continue                                   # executions are tested by FILL CONSERVATION
        base = {"claim_id": c["id"], "source": c.get("source", "speech"), "kind": kind, "value": c["value"],
                "instrument": r.get("instrument") or (c.get("candidates") or [None])[0], "market_time": r.get("t_air_ist"),
                "window": r.get("window"), "certificate_bars": r.get("certificate", [])[:2], "timing": (r.get("timing") or {}).get("class")}
        if c["type"] in ("QUOTE", "HISTORICAL") and r["verdict"] == NOT_CHECKABLE:
            continue                                   # the number is not a price of that stock (points move, %, ...) - not a claim
        if c["type"] in ("TARGET", "CALL", "HYPOTHETICAL", "UNCLASSIFIED"):
            items.append({**base, "verdict": ABSTAIN, "reason": f"This is a {kind}, not an observation, so knowability does not apply."})
        elif r["verdict"] == CONSISTENT:
            items.append({**base, "verdict": PASS, "reason": r.get("finding")})
        elif r["verdict"] == CONTRADICTED:
            t = (r.get("timing") or {}).get("finding")
            items.append({**base, "verdict": FAIL, "reason": (t or r.get("finding")), "assumptions": _assump_text(r)})
        else:
            items.append({**base, "verdict": ABSTAIN, "reason": r.get("finding")})
    for s in screen_items:
        items.append(s)
    return {"name": "KNOWABILITY", "question": "Was each asserted observation consistent with what the market had made observable at that "
            "moment?", "verdict": _branch_verdict(items), "items": items}


def _assump_text(r):
    A = r.get("assumptions") or {}
    return [f"look-back for a 'current' quote: {A.get('quote_lookback_s', 180):g} s", f"broadcast delay: 0-{A.get('broadcaster_delay_max_s', 120):g} s",
            f"rounding tolerance ±{r.get('tolerance', 0):g}", "the instrument named in the same sentence, the number tightly bound to it"]


def data_age_branch(check_c_result):
    v = check_c_result["verdict"]
    if v == "Data age meets the 30-day lag":
        verdict = PASS
    elif v == "Rule not yet in force on the date of use":
        verdict = PASS
    else:
        verdict = ABSTAIN
    return {"name": "DATA AGE", "question": "Was the market data at least 30 days old where SEBI's educational-use rule applies?",
            "verdict": verdict, "items": [{"claim_id": "segment", "verdict": verdict, "reason": check_c_result["finding"],
                                           "facts": {k: check_c_result.get(k) for k in ("market_data_date", "use_date", "use_date_source",
                                                                                         "data_age_days", "names_security_with_call_or_target",
                                                                                         "presenter_status")},
                                           "assumptions": ["scope: the 30-day usage rule applies only to a person engaged solely in education; "
                                                           "sharing lag binds exchanges/intermediaries", "FAIL is never issued from video alone: "
                                                           "the presenter's status cannot be established from the video"]}],
            "rule": check_c_result.get("rule"), "source_url": check_c_result.get("source_url")}


def certificate(meta, tau, branches, audit, steps):
    body = {"title": "Final Impossibility Certificate", "video": {k: meta.get(k) for k in ("id", "title", "source", "recorded_ist", "clip", "synthetic")},
            "verdict_meanings": MEANING, "time_mapping": tau,
            "checks": [{k: b[k] for k in ("name", "question", "verdict", "items") if k in b} | ({"note": b["note"]} if b.get("note") else {})
                       for b in branches],
            "sources": audit.get("market_data"), "algorithm_version": audit.get("algorithm_version"),
            "reproduce": steps, "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "disclaimer": "PASS establishes only that the tested constraint was satisfied. It does not establish trade ownership, recording "
                          "authenticity, or regulatory compliance. FAIL rests on the listed assumptions. ABSTAIN means no reliable conclusion."}
    body["certificate_id"] = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return body
