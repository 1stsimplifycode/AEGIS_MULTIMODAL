"""Financial entity recognition for SPOKEN or typed text: surface form -> candidate NSE instruments.

Deterministic, self-contained (no network, no external alias tables), so it also runs on the hosted server.
  * aliases: hand-written spoken forms (below) + full company names + distinctive first words + symbols
  * an alias shared by several instruments is AMBIGUOUS: every candidate is kept (the verifier must hold for all of them)
  * fuzzy fallback (rapidfuzz token_set_ratio >= 90 on company names) only for typed input, never for ASR spans
Indices available in the market record: NIFTY 50 (^NSEI), SENSEX (^BSESN), NIFTY BANK (^NSEBANK).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SPOKEN = {
    "nifty": ["^NSEI"], "nifty 50": ["^NSEI"], "nifty fifty": ["^NSEI"], "sensex": ["^BSESN"], "bank nifty": ["^NSEBANK"],
    "nifty bank": ["^NSEBANK"], "reliance": ["RELIANCE"], "ril": ["RELIANCE"], "hdfc bank": ["HDFCBANK"], "icici bank": ["ICICIBANK"],
    "infosys": ["INFY"], "infy": ["INFY"], "tcs": ["TCS"], "sbi": ["SBIN"], "state bank": ["SBIN"], "l&t": ["LT"], "l and t": ["LT"],
    "larsen": ["LT"], "itc": ["ITC"], "axis bank": ["AXISBANK"], "kotak bank": ["KOTAKBANK"], "kotak mahindra bank": ["KOTAKBANK"],
    "kotak": ["KOTAKBANK"], "bharti airtel": ["BHARTIARTL"], "airtel": ["BHARTIARTL"], "hul": ["HINDUNILVR"],
    "hindustan unilever": ["HINDUNILVR"], "m&m": ["M&M"], "mahindra": ["M&M"], "maruti": ["MARUTI"], "bajaj finance": ["BAJFINANCE"],
    "bajaj finserv": ["BAJAJFINSV"], "wipro": ["WIPRO"], "hcl tech": ["HCLTECH"], "tech mahindra": ["TECHM"], "sun pharma": ["SUNPHARMA"],
    "titan": ["TITAN"], "asian paints": ["ASIANPAINT"], "ultratech": ["ULTRACEMCO"], "nestle": ["NESTLEIND"], "ntpc": ["NTPC"],
    "power grid": ["POWERGRID"], "ongc": ["ONGC"], "coal india": ["COALINDIA"], "tata steel": ["TATASTEEL"], "jsw steel": ["JSWSTEEL"],
    "hindalco": ["HINDALCO"], "grasim": ["GRASIM"], "adani ports": ["ADANIPORTS"], "adani enterprises": ["ADANIENT"],
    "eternal": ["ETERNAL"], "zomato": ["ETERNAL"], "trent": ["TRENT"], "cipla": ["CIPLA"], "dr reddy's": ["DRREDDY"], "dr reddy": ["DRREDDY"],
    "eicher": ["EICHERMOT"], "hero motocorp": ["HEROMOTOCO"], "bajaj auto": ["BAJAJ-AUTO"], "britannia": ["BRITANNIA"],
    "indusind bank": ["INDUSINDBK"], "shriram finance": ["SHRIRAMFIN"], "bel": ["BEL"], "bharat electronics": ["BEL"], "hal": ["HAL"],
    "jio financial": ["JIOFIN"], "apollo hospitals": ["APOLLOHOSP"], "tata consumer": ["TATACONSUM"], "lic": ["LICI"],
    "tata motors": ["TMPV", "TMCV"],          # post-demerger: passenger vs commercial vehicles -> ambiguous by design
    "tata": [],                                # too ambiguous to propose candidates
}
NAME_STOP = {"limited", "ltd", "the", "and", "of", "india", "industries", "company", "corporation", "co", "(india)", "services", "&"}
COMMON_FIRST = {"bank", "state", "national", "indian", "india", "power", "the", "united", "new", "global", "general", "bharat", "tata",
                "adani", "bajaj", "hindustan", "jsw", "mahindra", "union", "central", "punjab", "great", "first", "life", "home", "max"}


GENERIC = {"oil", "bank", "fact", "power", "steel", "finance", "capital", "energy", "gujarat", "india", "life", "home", "gas", "gold",
           "silver", "metal", "metals", "cement", "auto", "pharma", "infra", "trade", "trust", "share", "market", "global", "future",
           "growth", "value", "best", "star", "sun", "titan", "delta", "alpha", "prime", "ideal", "orient", "national", "united",
           "equity", "money", "bharat", "hindustan", "jindal", "sugar", "cable", "cables", "paper", "glass", "textiles", "chemicals",
           "foods", "hotels", "motors", "electric", "electricals", "engineering", "systems", "technologies", "solutions", "ports",
           "airlines", "aviation", "railway", "railways", "defence", "shipping", "logistics", "realty", "estate", "housing", "sector",
           "south", "north", "east", "west", "nifty", "sensex", "mahindra", "kotak", "zee", "tata", "adani", "birla", "godrej", "bajaj", "reliance", "wipro", "infosys"}


def norm(s: str) -> str:
    s = s.lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9&' ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def alias_index() -> dict[str, list[str]]:
    return {a: v for a, (v, _) in alias_table().items()}


@lru_cache(maxsize=1)
def alias_table() -> dict[str, tuple[list[str], str]]:
    """alias -> (candidates, kind); kind in spoken | name | firstword | symbol (firstword/symbol need case evidence in text)."""
    inst = json.loads((ROOT / "data/market/instruments.json").read_text(encoding="utf-8"))["instruments"]
    idx: dict[str, set] = {}
    kinds: dict[str, str] = {}

    def add(a, s, kind="name"):
        a = norm(a)
        if len(a) >= 3:
            idx.setdefault(a, set()).add(s)
            kinds.setdefault(a, kind)
    for s, v in inst.items():
        if v["kind"] != "equity":
            continue
        words = [w for w in norm(v["name"]).split() if w not in NAME_STOP]
        if words:
            add(" ".join(words), s)
            if len(words) >= 2:
                add(" ".join(words[:2]), s)
            if words[0] not in COMMON_FIRST and words[0] not in GENERIC and len(words[0]) >= 5:
                add(words[0], s, "firstword")
        if len(s) >= 3 and s.isalpha():
            add(s, s, "symbol")
    out = {a: (sorted(v), kinds[a]) for a, v in idx.items() if a not in GENERIC}
    for a, v in SPOKEN.items():
        out[norm(a)] = ([x for x in v if x in inst], "spoken")
    return out


def find_mentions(text: str) -> list[dict]:
    """Longest-match scan over 1-4 word n-grams. Returns [{span, start_char, end_char, candidates, ambiguous}]."""
    idx = alias_table()
    toks = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[A-Za-z][A-Za-z&'.]*", text)]
    out, i = [], 0
    while i < len(toks):
        hit = None
        for n in (4, 3, 2, 1):
            if i + n > len(toks):
                continue
            span = " ".join(t[0] for t in toks[i:i + n])
            k = norm(span)
            if k in idx:
                cands, kind = idx[k]
                if kind == "symbol" and not span.replace("&", "").isupper():
                    continue                       # symbol-only alias needs an acronym-like token ("ONGC", not "oil")
                if kind == "firstword" and not span[0].isupper():
                    continue                       # distinctive first word must look like a proper noun
                hit = (n, span, cands)
                break
        if hit:
            n, span, cands = hit
            if cands:
                out.append({"span": span, "start_char": toks[i][1], "end_char": toks[i + n - 1][2], "candidates": cands,
                            "ambiguous": len(cands) > 1})
            i += n
        else:
            i += 1
    return out


def resolve_typed(name: str) -> list[str]:
    """For a user-typed instrument: exact alias / symbol first, then fuzzy (>= 90) on company names."""
    idx = alias_index()
    k = norm(name)
    if k in idx and idx[k]:
        return idx[k]
    inst = json.loads((ROOT / "data/market/instruments.json").read_text(encoding="utf-8"))["instruments"]
    if name.upper() in inst:
        return [name.upper()]
    try:
        from rapidfuzz import fuzz, process
        names = {s: v["name"] for s, v in inst.items()}
        res = process.extract(name, names, scorer=fuzz.token_set_ratio, limit=3)
        return [r[2] for r in res if r[1] >= 90]
    except ImportError:
        return []
