"""Build the SYNTHETIC demonstration package: made-up personal-trade claims (no video), checked against the REAL market record.

    python -m scripts.build_synthetic

Every claim here was written by us to exercise the checks. None is attributed to any real person or broadcast.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from encoders.entities import resolve_typed
from encoders.market import IST

ROOT = Path(__file__).resolve().parents[1]

CASES = [  # (id, text, instrument, price, qty, date, time, what it tests)
    ("s1", "I bought 1,800 shares of ITC at ₹265.50 at 10:31 AM.", "ITC", 265.50, 1800, "2026-10-06", "10:31", "realistic claim"),
    ("s2", "I sold 2,000 shares of TCS at ₹2,150 at 11:15.", "TCS", 2150.0, 2000, "2026-10-06", "11:15", "price outside the traded range"),
    ("s3", "I bought 50 lakh shares of Grasim at ₹2,955.50 at 2:20 PM.", "Grasim", 2955.50, 5_000_000, "2026-10-06", "14:20", "quantity larger than NSE volume"),
    ("s4", "I bought 100 Reliance shares at ₹1,180 on 2 October at 11 AM.", "Reliance", 1180.0, 100, "2026-10-02", "11:00", "market holiday"),
    ("s5", "I bought 100 HDFC at ₹712.70 at 1 PM.", "HDFC", 712.70, 100, "2026-10-06", "13:00", "ambiguous name (three HDFC companies)"),
    ("s6", "I bought 500 Infosys shares at ₹1,030 on 5 October.", "Infosys", 1030.0, 500, "2026-10-05", None, "no time stated"),
    ("s7", "I bought 200 SBI shares at ₹800 at 4:10 PM.", "SBI", 800.0, 200, "2026-10-06", "16:10", "time outside market hours"),
]


def main():
    claims = []
    for cid, text, inst, price, qty, d, t, what in CASES:
        day = dt.date.fromisoformat(d)
        st = None
        if t:
            hh, mm = (int(x) for x in t.split(":"))
            st = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST).timestamp() + 30
        claims.append({"id": cid, "type": "PERSONAL_TRADE", "role": "execution_price", "sentence": text, "instrument_span": inst,
                       "candidates": resolve_typed(inst), "ambiguous": len(resolve_typed(inst)) > 1, "value": price,
                       "tolerance": 0.05, "tolerance_why": "stated to the paisa; tolerance ±0.05 (tick)", "quantity": qty,
                       "stated_date": d, "stated_time_epoch": st, "stated_time_text": f"{d} {t} IST (stated)" if t else f"{d} (no time stated)",
                       "t_media": None, "why_type": ["synthetic first-person trade claim"], "synthetic_purpose": what})
    out = ROOT / "demo/samples/synthetic_trade_claims"
    out.mkdir(parents=True, exist_ok=True)
    pkg = {"meta": {"id": "synthetic_trade_claims", "kind": "synthetic", "synthetic": True,
                    "title": "Made-up 'I bought…' claims (synthetic test cases)",
                    "description": "Seven invented personal-trade claims checked against real NSE records: a realistic one, a wrong price, an "
                                   "impossible quantity, a market holiday, an ambiguous name, no time, and after-hours.",
                    "channel_name": "No video (typed claims)", "recorded_ist": None, "duration_s": None, "source": "synthetic, written by the project team",
                    "clip": [0, 0], "media": None, "thumbnail": None, "use_date": None, "use_date_source": "not applicable (no video)",
                    "presenter_status": "unknown", "live_capture": False},
           "clock": None, "transcript": None, "screen": {"observations": []}, "typed_claims": claims,
           "offline_stages": {}}
    (out / "package.json").write_text(json.dumps(pkg, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out / "package.json", len(claims), "claims")


if __name__ == "__main__":
    main()
