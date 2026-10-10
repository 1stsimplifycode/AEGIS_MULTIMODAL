"""Visual evidence encoder: on-screen (name, price) observations from the scrolling ticker.

Two sources:
  ticker_from_dense(dense.jsonl)  reuse the parent project's ticker-band OCR (RapidOCR on a cropped band, 4 frames/s)
  ocr_video(video, every_s)       run RapidOCR on full frames of a new video (local mode; needs rapidocr-onnxruntime + ffmpeg)
Names are mapped to NSE symbols by the parent project's frozen, conservative OCR resolver when it is importable
(research/icsc2027/src/symbol_resolve.py - abstains instead of guessing); the mapping is stored in the evidence package,
so the hosted server never needs the resolver.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

PRICE = re.compile(r"^[+]?(\d{1,6}(?:,\d{3})*\.\d{1,2})")
NAME = re.compile(r"[A-Za-z]{2,}")


def _pairs_from_lines(lines, row_tol=9.0, min_conf=0.5):
    """lines: [text, conf, x0, y0, x1, y1]. Group into rows, read left->right, emit (name, price_text) adjacency pairs."""
    items = sorted([(l[3] + l[5]) / 2 for l in lines if l[1] >= min_conf])
    rows = []
    for l in sorted([l for l in lines if l[1] >= min_conf], key=lambda l: (l[3] + l[5]) / 2):
        yc = (l[3] + l[5]) / 2
        if rows and abs(rows[-1][0] - yc) <= row_tol:
            rows[-1][1].append(l)
        else:
            rows.append([yc, [l]])
    out = []
    for _, row in rows:
        toks = []
        for l in sorted(row, key=lambda l: l[2]):
            toks += [(t, l[1]) for t in re.split(r"[\s�]+", l[0]) if t]
        for i, (tok, conf) in enumerate(toks[:-1]):
            if not NAME.search(tok) or re.match(r"^\d", tok):
                continue
            m = PRICE.match(toks[i + 1][0])
            if m:
                out.append((tok, float(m.group(1).replace(",", "")), min(conf, toks[i + 1][1])))
    return out


def _resolver():
    try:
        import sys
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from research.icsc2027.src.symbol_resolve import resolve
        return resolve
    except Exception:  # noqa: BLE001
        return None


# Ticker layouts whose (name -> price) adjacency was validated against market data on held-in captures (2026-10-06 08:44Z):
# NDTV Profit 98 % of plausible stable reads agree with the market; CNBC-TV18's band puts lot-size superscripts and prices on a
# second line, so adjacency pairs the WRONG price (e.g. 'Concor 798.1' vs a 440-446 day range) -> not used for verdicts.
LAYOUT_VALIDATED = {"ndtv": True, "tv18": False}
MIN_FRAMES = 2          # a reading must repeat in >= 2 frames to count as evidence (single-frame reads are OCR-error prone)


LAYOUT_MIN_PLAUSIBLE = 0.9


def recording_layout_check(obs: list[dict], market, day) -> dict:
    """Per-RECORDING ticker check (2026-10-10: the per-channel flag did not generalise - E1). Uses only price MAGNITUDE: a
    stable, resolved reading is 'plausible' if its price lies within [0.5x, 2x] of the named stock's range that day. It does NOT
    use whether the price matches at the time shown, so passing it does not pre-judge the verdicts. If < 90 % are plausible, the
    name->price pairing is broken for this recording and no reading is used."""
    cand = [o for o in obs if o.get("symbol") and o.get("n_frames", 1) >= MIN_FRAMES]
    ok = 0
    for o in cand:
        rng = market.day_range(o["symbol"], day)
        ok += bool(rng and 0.5 * rng[0] <= o["price"] <= 2.0 * rng[1])
    frac = ok / len(cand) if cand else 0.0
    passed = bool(cand) and frac >= LAYOUT_MIN_PLAUSIBLE
    for o in obs:
        if not passed:
            o["usable"] = False
            o["unusable_reason"] = (f"this recording's ticker failed our layout check: only {frac:.0%} of readings are plausible prices "
                                    "for the named stock, so names and prices are probably mis-paired")
        else:
            o["usable"] = bool(o.get("symbol") and o.get("n_frames", 1) >= MIN_FRAMES)
            if not o["usable"]:
                o["unusable_reason"] = "name not resolved to an instrument" if not o.get("symbol") else f"read in only {o.get('n_frames', 1)} frame"
    return {"passed": passed, "plausible_fraction": round(frac, 3), "n_checked": len(cand), "threshold": LAYOUT_MIN_PLAUSIBLE}


def ticker_from_dense(dense_path: Path, frames_index: Path | None = None, channel: str | None = None) -> dict:
    """-> {"observations": [{name, symbol, resolver, price, t_media, conf}], "ocr_cpu_s": ..., "n_frames": ...}.
    One observation per distinct (name, price): the first time it was seen."""
    resolve = _resolver()
    seen, obs, cpu = {}, [], 0.0
    n = 0
    for line in open(dense_path, encoding="utf-8"):
        fr = json.loads(line)
        n += 1
        cpu += float(fr.get("cpu_s", 0.0))
        for name, price, conf in _pairs_from_lines(fr["lines"]):
            key = (name, price)
            if key in seen:
                obs[seen[key]]["n_frames"] += 1
                continue
            seen[key] = len(obs)
            r = resolve(name) if resolve else {"symbol": None, "status": "RESOLVER_UNAVAILABLE"}
            ok = r.get("status") in ("EXACT", "ALIAS", "ABBREV", "SYMSUBSEQ")
            obs.append({"name": name, "symbol": r.get("symbol") if ok else None, "resolver": r.get("status"), "price": price,
                        "t_media": float(fr["t"]), "conf": round(conf, 3), "n_frames": 1})
    lv = LAYOUT_VALIDATED.get(channel or "", False)
    for o in obs:
        o["usable"] = bool(o["symbol"] and o["n_frames"] >= MIN_FRAMES and lv)
        o["unusable_reason"] = (None if o["usable"] else "ticker layout not validated for this channel" if not lv else
                                "name not resolved to an instrument" if not o["symbol"] else f"read in only {o['n_frames']} frame")
    return {"observations": obs, "ocr_cpu_s": round(cpu, 1), "n_frames": n, "source": str(dense_path), "layout_validated": lv,
            "engine": "RapidOCR (onnxruntime, CPU) on the ticker band, 4 frames/s"}


def ocr_video(video: str, every_s: float = 2.0, max_frames: int = 600) -> dict:
    """Full-frame OCR of a new video (local mode). Returns raw lines per sampled frame + (name, price) pairs."""
    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR()
    tmp = Path(tempfile.mkdtemp())
    subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps=1/{every_s},scale=960:-2", "-frames:v", str(max_frames),
                    str(tmp / "f%05d.jpg")], check=True)
    t0 = time.perf_counter()
    frames, obs, seen = [], [], set()
    resolve = _resolver()
    for i, f in enumerate(sorted(tmp.glob("f*.jpg"))):
        res, _ = eng(str(f))
        lines = [[r[1], float(r[2]), r[0][0][0], r[0][0][1], r[0][2][0], r[0][2][1]] for r in (res or [])]
        t = i * every_s
        frames.append({"t": t, "lines": lines})
        for name, price, conf in _pairs_from_lines(lines, row_tol=12.0):
            if (name, price) in seen:
                continue
            seen.add((name, price))
            r = resolve(name) if resolve else {"symbol": None, "status": "RESOLVER_UNAVAILABLE"}
            ok = r.get("status") in ("EXACT", "ALIAS", "ABBREV", "SYMSUBSEQ")
            obs.append({"name": name, "symbol": r.get("symbol") if ok else None, "resolver": r.get("status"), "price": price,
                        "t_media": t, "conf": round(conf, 3)})
        f.unlink()
    tmp.rmdir()
    return {"observations": obs, "frames": frames, "ocr_cpu_s": round(time.perf_counter() - t0, 1), "n_frames": len(frames),
            "engine": f"RapidOCR (onnxruntime, CPU) full frames every {every_s:g} s"}
