"""VISUAL TEXT ENCODER: on-screen text that could carry a trade claim, from full-frame OCR.

Looks for, per frame:
  trading_panel  order/position panel fields: Qty/Quantity/Filled, Avg/Average price, LTP, Buy/Sell, Order/Executed, P&L/PnL/MTM
  pnl            profit/loss figures (P&L / profit / loss next to a number)
  screen_clock   an on-screen HH:MM clock (not a chart axis row)
  pairs          (name, price) adjacency pairs anywhere on screen (ticker, gainers lists, panels)
Reports counts and evidence frames. On business-news broadcasts there are normally NO trading panels; the stage then says
so explicitly instead of inventing fills.
"""
from __future__ import annotations

import re

from encoders.visual import _pairs_from_lines

PANEL_WORDS = re.compile(r"\b(qty|quantity|filled|avg\.?|average price|ltp|buy|sell|order|executed|position|p\s?&\s?l|pnl|mtm)\b", re.I)
# P&L needs an explicit P&L / PnL / MTM label, or 'profit'/'loss' followed by a currency sign ('NDTV Profit' is a channel name, R23)
PNL = re.compile(r"(?:\b(?:p\s?&\s?l|pnl|mtm)\b\W*[+\-]?\s*(?:₹|rs\.?)?\s*[\d,]+(?:\.\d+)?)|(?:\b(?:profit|loss)\b\W*[+\-]?\s*(?:₹|rs\.?)\s*[\d,]+(?:\.\d+)?)", re.I)
QTY = re.compile(r"\b(?:qty|quantity|filled)\W*(\d[\d,]*)\b", re.I)
CLOCK = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def encode(frames_doc, panel_frames=None):
    out_frames, panel_hits, pnl_hits, qty_hits, clocks, pair_count = [], [], [], [], [], 0
    for fr in frames_doc["frames"]:
        texts = [l[0] for l in fr["lines"] if l[1] >= 0.8]
        joined = " ".join(texts)
        words = PANEL_WORDS.findall(joined)
        pn = PNL.findall(joined)
        qt = QTY.findall(joined)
        rows = {}
        for l in fr["lines"]:
            if CLOCK.match(l[0].strip()):
                rows.setdefault(round(l[3] / 8), []).append(l[0].strip())
        ck = [v[0] for v in rows.values() if len(v) == 1]
        pairs = _pairs_from_lines(fr["lines"], row_tol=12.0)
        pair_count += len(pairs)
        # a trading panel needs >= 3 distinct panel words in one frame (single words like 'buy' occur in headlines)
        is_panel = len({w.lower() for w in words}) >= 3
        if is_panel:
            panel_hits.append({"t_media": fr["t_media"], "thumb": fr.get("thumb"), "words": sorted({w.lower() for w in words})})
        if pn:
            pnl_hits.append({"t_media": fr["t_media"], "thumb": fr.get("thumb"), "text": pn[:3]})
        if qt:
            qty_hits.append({"t_media": fr["t_media"], "thumb": fr.get("thumb"), "qty": qt[:3]})
        if ck:
            clocks.append({"t_media": fr["t_media"], "clock": ck[0], "thumb": fr.get("thumb")})
        out_frames.append({"t_media": fr["t_media"], "n_text_lines": len(texts), "pairs": [[a, b] for a, b, _ in pairs][:8]})
    return {"n_frames": len(out_frames), "trading_panel_frames": panel_hits, "pnl_frames": pnl_hits, "quantity_frames": qty_hits,
            "screen_clock_frames": clocks, "n_name_price_pairs": pair_count,
            "summary": ("No trading panel, fill quantity or P&L figure was found on screen" if not (panel_hits or pnl_hits or qty_hits)
                        else f"{len(panel_hits)} frame(s) look like a trading panel; {len(qty_hits)} show a quantity; {len(pnl_hits)} show P&L"),
            "frames": out_frames}
