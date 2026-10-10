"""Freeze 1-minute OHLCV (with VOLUME) for the tape's NSE symbols, 2026-09-29 .. 2026-10-08 (Yahoo chart endpoint).

    python -m scripts.fetch_ohlcv

Rules (same as the parent project's tools/fetch_market_data.py): no bar is generated, interpolated or back-filled; a
missing minute stays missing (NaN); timestamps are exchange minutes in UTC epoch seconds; provenance in the .meta.json.
Volume is NSE-only (symbol.NS). BSE executions are NOT included - any quantity reasoning must say so.
Yahoo serves 1-minute bars only for ~30 days and at most 7 days per request; this file is therefore a frozen snapshot.
Output: data/market/ohlcv_1m_20260929_20261008.npz (+ .meta.json)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
WINDOWS = [("2026-09-29", "2026-10-03"), ("2026-10-05", "2026-10-09")]


def fetch(sym: str, a: str, b: str):
    p1 = int(dt.datetime.fromisoformat(a).replace(tzinfo=IST).timestamp())
    p2 = int(dt.datetime.fromisoformat(b).replace(tzinfo=IST).timestamp())
    ysym = sym if sym.startswith("^") else sym + ".NS"
    url = ENDPOINT + urllib.parse.quote(ysym) + "?" + urllib.parse.urlencode(
        dict(period1=p1, period2=p2, interval="1m", includePrePost="false"))
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as f:
                r = json.load(f)["chart"]["result"][0]
            ts = r.get("timestamp") or []
            q = r["indicators"]["quote"][0]
            return [(int(t), q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]) for i, t in enumerate(ts)]
        except Exception as e:  # noqa: BLE001
            err = repr(e)[:120]
            time.sleep(1.5 * (attempt + 1))
    return {"error": err}


def main():
    z = np.load(PARENT / "research/smalldata/results/tape_1m.npz")
    syms = [str(s) for s in z["syms"]]
    days = []
    d = dt.date(2026, 9, 29)
    while d <= dt.date(2026, 10, 8):
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    minutes = []
    for d in days:
        base = dt.datetime(d.year, d.month, d.day, 9, 15, tzinfo=IST).timestamp()
        minutes += [int(base + 60 * m) for m in range(375)]
    idx = {t: k for k, t in enumerate(minutes)}
    N, K = len(syms), len(minutes)
    O, H, L, C, V = (np.full((N, K), np.nan) for _ in range(5))
    errors = {}

    def job(i):
        rows = []
        for a, b in WINDOWS:
            r = fetch(syms[i], a, b)
            if isinstance(r, dict):
                return i, r
            rows += r
            time.sleep(0.2)
        return i, rows
    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        for i, rows in ex.map(job, range(N)):
            if isinstance(rows, dict):
                errors[syms[i]] = rows["error"]
                continue
            for t, o, h, l, c, v in rows:
                k = idx.get(t - t % 60)
                if k is None or o is None:
                    continue
                O[i, k], H[i, k], L[i, k], C[i, k], V[i, k] = o, h, l, c, v
    out = ROOT / "data/market/ohlcv_1m_20260929_20261008.npz"
    np.savez_compressed(out, syms=np.array(syms), minutes=np.array(minutes), open=O, high=H, low=L, close=C, volume=V.astype(np.float32),
                        days=np.array([d.isoformat() for d in days]))
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    meta = {"provider": "Yahoo Finance chart endpoint (public, unauthenticated)", "endpoint": ENDPOINT, "interval": "1m",
            "symbols": "NSE (.NS) + indices; BSE volume NOT included", "days": [d.isoformat() for d in days],
            "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "seconds": round(time.time() - t0, 1),
            "n_symbols": N, "n_errors": len(errors), "errors": errors, "sha256": sha,
            "missing_minute_fraction": float(np.isnan(C).mean()),
            "licence_note": "Yahoo data are for personal/research use; redistribution in a public deployment may require a licensed "
                            "exchange data feed. The hosted demo ships only the minutes needed for its samples (see docs/DATA_AUDIT.md)."}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("n_symbols", "n_errors", "seconds", "missing_minute_fraction")}), out.stat().st_size / 1e6, "MB")


if __name__ == "__main__":
    main()
