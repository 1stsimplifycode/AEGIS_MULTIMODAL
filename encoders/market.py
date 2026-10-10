"""Historical market evidence encoder: frozen NSE 1-minute bars (NOT trade-level data).

Two frozen files (both sha256-recorded in every audit report):
  tape_lohi_1m_20260910_20261008.npz   low/high per minute, 427 symbols (forward-filled within a day when a minute had no trade,
                                       as built by the parent project's mpf.Tape; flagged as such)
  ohlcv_1m_20260929_20261008.npz       open/high/low/close/VOLUME per minute (NSE only), no filling: a minute without
                                       trades is NaN

`bars()` prefers the OHLCV file (it has volume and no filling) and falls back to the low/high tape outside its days.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "data/market"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TAPE = MD / "tape_lohi_1m_20260910_20261008.npz"
OHLCV = MD / "ohlcv_1m_20260929_20261008.npz"
OPEN_MIN, CLOSE_MIN = 9 * 60 + 15, 15 * 60 + 30


def ist(t: float) -> str:
    return dt.datetime.fromtimestamp(t, IST).strftime("%Y-%m-%d %H:%M:%S IST")


@dataclass
class Bar:
    t: int                 # minute start, unix seconds
    lo: float
    hi: float
    open: float | None
    close: float | None
    volume: float | None
    source: str            # "ohlcv" | "tape"
    filled: bool           # True if the minute had no trade and the value is carried from the previous minute (tape only)

    def as_dict(self):
        return {"t": self.t, "time_ist": ist(self.t)[11:16], "low": round(self.lo, 2), "high": round(self.hi, 2),
                "open": None if self.open is None else round(self.open, 2), "close": None if self.close is None else round(self.close, 2),
                "volume": None if self.volume is None else int(self.volume), "source": self.source, "filled": self.filled}


class MarketRecord:
    def __init__(self):
        z = np.load(TAPE)
        self.t_tape = z["t"].astype(np.int64)
        self.syms = [str(s) for s in z["syms"]]
        self.sidx = {s: i for i, s in enumerate(self.syms)}
        self.lo_t, self.hi_t = z["lo"], z["hi"]
        self.tape_days = [dt.date.fromisoformat(str(d)) for d in z["days"]]
        self.k_tape = {int(t): k for k, t in enumerate(self.t_tape)}
        self.has_ohlcv = OHLCV.exists()
        if self.has_ohlcv:
            o = np.load(OHLCV)
            self.o_syms = {str(s): i for i, s in enumerate(o["syms"])}
            self.t_o = o["minutes"].astype(np.int64)
            self.k_o = {int(t): k for k, t in enumerate(self.t_o)}
            self.O, self.H, self.L, self.C, self.V = o["open"], o["high"], o["low"], o["close"], o["volume"]
            self.o_days = [dt.date.fromisoformat(str(d)) for d in o["days"]]
        inst = json.loads((MD / "instruments.json").read_text(encoding="utf-8"))["instruments"]
        self.instruments = inst
        self.coverage = {"lohi_days": [str(self.tape_days[0]), str(self.tape_days[-1])],
                         "ohlcv_days": [str(self.o_days[0]), str(self.o_days[-1])] if self.has_ohlcv else None}

    # ------------------------------------------------------------------ calendar
    def session_bounds(self, d: dt.date):
        base = dt.datetime(d.year, d.month, d.day, tzinfo=IST).timestamp()
        return int(base + 60 * OPEN_MIN), int(base + 60 * CLOSE_MIN)

    def day_status(self, d: dt.date) -> str:
        """'trading' | 'no_trading_recorded' (weekday inside coverage with no bars: holiday) | 'weekend' | 'outside_coverage'"""
        if d.weekday() >= 5:
            return "weekend"
        if self.has_ohlcv and self.o_days[0] <= d <= self.o_days[-1]:
            a, b = self.session_bounds(d)
            ks = [self.k_o.get(t) for t in range(a, b, 60)]
            ks = [k for k in ks if k is not None]
            if ks and not np.isnan(self.C[:, ks]).all():
                return "trading"
            return "no_trading_recorded"
        if d in self.tape_days:
            return "trading"
        if self.tape_days[0] <= d <= self.tape_days[-1]:
            return "no_trading_recorded"
        return "outside_coverage"

    # ------------------------------------------------------------------ bars
    def bars(self, sym: str, t0: float, t1: float) -> list[Bar]:
        """All minutes whose start lies in [t0, t1] (inclusive of the minute containing t0)."""
        out = []
        a = int(t0) - int(t0) % 60
        for t in range(a, int(t1) + 1, 60):
            ko = self.k_o.get(t) if self.has_ohlcv else None
            if ko is not None and sym in self.o_syms:
                i = self.o_syms[sym]
                c = self.C[i, ko]
                if np.isnan(c):
                    out.append(Bar(t, np.nan, np.nan, None, None, 0.0, "ohlcv", False))   # session minute with no trade
                else:
                    out.append(Bar(t, float(self.L[i, ko]), float(self.H[i, ko]), float(self.O[i, ko]), float(c),
                                   float(self.V[i, ko]), "ohlcv", False))
                continue
            kt = self.k_tape.get(t)
            if kt is not None and sym in self.sidx:
                i = self.sidx[sym]
                lo, hi = self.lo_t[i, kt], self.hi_t[i, kt]
                filled = kt > 0 and lo == self.lo_t[i, kt - 1] and hi == self.hi_t[i, kt - 1]
                out.append(Bar(t, float(lo), float(hi), None, None, None, "tape", bool(filled)))
        return out

    def day_range(self, sym: str, d: dt.date):
        a, b = self.session_bounds(d)
        bs = [x for x in self.bars(sym, a, b - 60) if not np.isnan(x.lo)]
        if not bs:
            return None
        return min(x.lo for x in bs), max(x.hi for x in bs)

    def file_hashes(self) -> dict:
        return {p.name: _sha(p) for p in (TAPE, OHLCV) if p.exists()}


@lru_cache(maxsize=4)
def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def get_market() -> MarketRecord:
    return MarketRecord()
