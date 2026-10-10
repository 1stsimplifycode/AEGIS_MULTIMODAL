"""Regression tests: every failure found on real data or in adversarial tests is pinned here (see docs/REGRESSIONS.md).

    python -m pytest -q tests
"""
from __future__ import annotations

import datetime as dt

import pytest

from encoders.claims import extract
from encoders.market import IST, get_market
from verification.engine import (CONSISTENT, CONTRADICTED, INSUFFICIENT, NOT_CHECKABLE, Assumptions, check_c, verify_price_claim)

M = get_market()


def at(y, mo, d, h, mi, s=0):
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=IST).timestamp()


def one(text):
    cl, _ = extract([{"start": 0.0, "end": 5.0, "text": text, "words": []}])
    return cl


def verdict(text, t_air, value=None):
    cl = one(text)
    if value is not None:
        cl = [c for c in cl if c["value"] == value]
    assert cl, f"no claim extracted from: {text}"
    c = cl[0]
    c["t_media"] = 0.0
    return verify_price_claim(c, t_air, 10.0, M)["verdict"], c


def test_R1_vendor_day_high_discrepancy_is_not_a_contradiction():
    # real: CNBC-TV18 2026-10-06 13:03:53 "55,220 was the high yesterday" - vendor bars say 55,191.25 (0.05 %)
    v, _ = verdict("Bank Nifty 55,220 was the high yesterday.", at(2026, 10, 6, 13, 3, 53), 55220.0)
    assert v == INSUFFICIENT


def test_R2_viewer_past_purchase_is_not_a_current_quote():
    v, c = verdict("He is holding 1000 shares of Infosys borrowed a prize of 1100 rupees. Should he continue to hold?",
                   at(2026, 10, 6, 14, 15, 18), 1100.0)
    assert c["type"] == "HISTORICAL" and v == INSUFFICIENT


def test_R3_support_zone_is_not_checkable():
    v, c = verdict("You have turned positive on HDFC Bank because the long-term supports are at 680.", at(2026, 10, 5, 15, 9, 56), 680.0)
    assert v == NOT_CHECKABLE


def test_R4_option_strike_is_not_a_price():
    assert not [c for c in one("The tricky part is what happens on the Nifty 22,700 call this week.") if c["value"] == 22700.0]


def test_R5_entity_from_previous_sentence_never_contradicts():
    cl, _ = extract([{"start": 0, "end": 3, "text": "Kotak Bank has seen a long build up.", "words": []},
                     {"start": 4, "end": 8, "text": "The stock fell from 800 bucks all the way down today.", "words": []}])
    c = [x for x in cl if x["value"] == 800.0]
    if c:
        c[0]["t_media"] = 0.0
        assert verify_price_claim(c[0], at(2026, 10, 6, 14, 49, 56), 10.0, M)["verdict"] != CONTRADICTED


def test_R6_self_correction_is_retracted():
    vals = [c["value"] for c in one("Nifty is seeing a fall 23,000 uh 22,000 pardon 22,672 is where the Nifty is.")]
    assert 23000.0 not in vals and 22000.0 not in vals and 22672.0 in vals


def test_R7_above_is_an_inequality():
    v, c = verdict("Now the Nifty above that 22,700 mark near the 800 mark at this point.", at(2026, 9, 30, 13, 1, 54), 22700.0)
    assert c["inequality"] == ">=" and v != CONTRADICTED


def test_R8_day_low_so_far_is_checked_against_the_session_low():
    v, c = verdict("Today's low becomes an important mark to track. 22570 is what the low on the nifty is.", at(2026, 9, 29, 11, 30, 19), 22570.0)
    assert c["role"] == "day_stat" and v == CONSISTENT


def test_R9_genuine_misstatement_is_contradicted():
    # real: NDTV Profit 2026-09-30 15:17:43 "I pull up the benchmark Nifty50 24,616.6" while the Nifty was near 22,600
    v, _ = verdict("I pull up the benchmark Nifty50 24,616.6 and so pretty much at the low point of the day.", at(2026, 9, 30, 15, 17, 43), 24616.6)
    assert v == CONTRADICTED


def test_R10_trading_call_entry_is_not_contradicted():
    v, c = verdict("Buy HDFC Bank at 855 with a stop loss at 820.", at(2026, 9, 30, 14, 16, 31), 855.0)
    assert v == NOT_CHECKABLE


def _personal(inst_cands, price, qty, date, hhmm):
    d = dt.date.fromisoformat(date)
    st = None
    if hhmm:
        h, m = (int(x) for x in hhmm.split(":"))
        st = at(d.year, d.month, d.day, h, m) + 30
    c = {"id": "t", "type": "PERSONAL_TRADE", "value": price, "tolerance": 0.05, "candidates": inst_cands, "quantity": qty,
         "instrument_span": inst_cands[0] if inst_cands else "?"}
    return verify_price_claim(c, None, 0.0, M, Assumptions(), stated_time=st, stated_date=d)


def test_R11_holiday_trade_contradicted_and_identity_never_verified():
    r = _personal(["RELIANCE"], 1180.0, 100, "2026-10-02", "11:00")
    assert r["verdict"] == CONTRADICTED
    r2 = _personal(["ITC"], 265.50, 1800, "2026-10-06", "10:31")
    assert r2["verdict"] == CONSISTENT and r2["identity"]["verdict"].startswith("Claimed execution not independently verified")


def test_R12_quantity_beyond_nse_volume():
    r = _personal(["GRASIM"], 2955.50, 5_000_000, "2026-10-06", "14:20")
    assert r["verdict"] == INSUFFICIENT and r["price_verdict"] == CONSISTENT and r["quantity"]["verdict"].startswith(CONTRADICTED)


def test_R13_after_hours_time_is_insufficient():
    assert _personal(["SBIN"], 800.0, 200, "2026-10-06", "16:10")["verdict"] == INSUFFICIENT


def test_R14_ambiguous_name_checks_all_candidates():
    r = _personal(["HDFCAMC", "HDFCBANK", "HDFCLIFE"], 712.70, 100, "2026-10-06", "13:00")
    assert r["verdict"] == CONSISTENT and r["instrument"] == "HDFCBANK" and "ambiguous" in r["finding"]


def test_R15_check_c_never_says_violation():
    a = check_c(dt.date(2026, 10, 6), "capture", dt.date(2026, 10, 6), True, "news_broadcast")
    assert "violation" not in a["verdict"].lower() and a["data_age_days"] == 0
    assert check_c(dt.date(2026, 6, 1), "x", dt.date(2026, 6, 1), True)["verdict"] == "Rule not yet in force on the date of use"
    assert check_c(dt.date(2026, 10, 6), "x", dt.date(2026, 9, 1), True)["verdict"] == "Data age meets the 30-day lag"


def test_R16_single_frame_screen_reading_is_not_evidence():
    from encoders.visual import MIN_FRAMES
    assert MIN_FRAMES >= 2


def test_R21_tau_from_chart_ratchets_agrees_with_independent_clock():
    """Visual frame encoder: the date and the video->market offset are identified from the chart panel alone (all trading days
    searched) and agree with our SNTP capture clock up to a plausible broadcast delay (0-120 s)."""
    import json
    from pathlib import Path
    from encoders.clock import CaptureClock
    from encoders.frame_encoder import encode
    d = Path(__file__).resolve().parents[1] / "demo/samples/tv18_nifty_bank_1301"
    pkg = json.loads((d / "package.json").read_text(encoding="utf-8"))
    r = encode(json.loads((d / "frames.json").read_text(encoding="utf-8")), M, CaptureClock.from_dict(pkg["clock"]))
    assert r["tau"]["status"] == "IDENTIFIED" and r["tau"]["day"] == "2026-10-06" and r["tau"]["tau_radius"] <= 30
    assert 0 <= r["agreement_with_capture_clock"]["air_minus_market_s"] <= 120


def test_R22_chart_high_label_rule_includes_ceiling():
    """22,728.10 is displayed as 22729: the label rule may be ceiling, so the ratchet cell must include it."""
    from encoders.frame_encoder import parse_panel
    p = parse_panel([["NIFTY50", 0.99, 66, 91, 158, 110], ["22701.30", 1.0, 67, 119, 192, 149], ["145.55", 1.0, 225, 127, 299, 149],
                     ["22729", 1.0, 67, 173, 112, 191], ["22643", 1.0, 66, 223, 112, 239], ["22555", 1.0, 68, 271, 113, 286]])
    assert p["layout_ok"] and p["axis_top"] == 22729 and p["prev_close_consistent"]


def test_R23_channel_name_profit_is_not_pnl():
    from encoders.visual_text import encode
    doc = {"frames": [{"t_media": 0, "lines": [["NDTV Profit", 0.99, 0, 0, 100, 20], ["24,616", 0.99, 110, 0, 160, 20]]},
                      {"t_media": 1, "lines": [["P&L +12,000", 0.99, 0, 0, 100, 20]]}]}
    r = encode(doc)
    assert [f["t_media"] for f in r["pnl_frames"]] == [1]


def test_R24_loose_time_map_is_weak_not_identified():
    import json
    from pathlib import Path
    from encoders.frame_encoder import encode
    d = Path(__file__).resolve().parents[1] / "demo/samples/tv18_nifty_levels_1250"
    r = encode(json.loads((d / "frames.json").read_text(encoding="utf-8")), M)
    assert r["tau"]["status"] == "WEAK" and "too loose" in r["tau"]["reason"]


def test_R26_ratchet_event_detector():
    """Day-high extension events are detected only when the top label rises (synthetic frame sequence; no real event occurred in
    the analysed windows - the 6 Oct high was set before them)."""
    from encoders.frame_encoder import ratchet_events
    mk = lambda t, top: {"t_media": t, "panel": {"symbol": "^NSEBANK", "layout_ok": True, "axis_top": top}}
    ev = ratchet_events([mk(0, 55197), mk(1, 55197), mk(2, 55201), mk(3, 55201), mk(4, 55190)])
    assert [(e["t_media"], e["from"], e["to"]) for e in ev] == [(2, 55197, 55201)]


def test_R27_index_level_is_recorded_not_traded():
    """an index is calculated, not traded: verdict text must not say the market 'did trade' an index."""
    from backend import pipeline as P
    r = P.analyze(P.load_package("tv18_nifty_bank_1301"), lambda *a, **k: None)
    items = [it for it in r["branches"]["knowability"]["items"] if it.get("instrument", "").startswith("^") and it["verdict"] == "PASS"]
    assert items
    for it in items:
        assert "did trade" not in it["reason"] and "recorded range" in it["reason"]
