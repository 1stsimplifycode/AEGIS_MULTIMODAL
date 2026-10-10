"""Spoken claim extraction: ASR segments -> sentences -> (instrument, number, claim type, role) records.

Rule-based and fully inspectable (every rule that fired is recorded in `why`). It is deliberately conservative: a number is
attached to an instrument only when the instrument is mentioned in the same sentence, or (flagged `entity_from_context`) in
the previous sentence within 20 s. Accuracy is measured in experiments/claim_extraction_eval.py against blind labels,
not assumed.
"""
from __future__ import annotations

import re

from encoders.entities import find_mentions

NUM = re.compile(r"(?<![\w.$₹/:])(?P<cur>(?:rs\.?|inr|₹)\s*)?(?P<int>\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(?P<dec>\d{1,2}))?(?![\d:])", re.I)
AFTER_NOT_PRICE = re.compile(r"^\s*(%|percent|per cent|crore|cr\b|lakh|million|billion|bn|mn|bps|basis|times|x\b|years?|months?|"
                             r"days?|weeks?|minutes?|hours?|shares? (?!at)|points?|stocks|companies|lots?|kg|tonnes?|mw|gw|km|th\b|st\b|nd\b|rd\b|"
                             r"calls?\b|puts?\b|ce\b|pe\b|strike|contracts?|open interest|oi\b|-?\s?weeks?\b)", re.I)   # strikes, '52-week' are not prices
ABOVE = re.compile(r"\b(above|over|past|crossed|beyond|higher than|more than)\s+(?:the\s+|that\s+)?(?:rs\.?\s*|₹\s*)?$", re.I)
BELOW = re.compile(r"\b(below|under|beneath|lower than|less than|breaking)\s+(?:the\s+|that\s+)?(?:rs\.?\s*|₹\s*)?$", re.I)
LEVEL = re.compile(r"\b(supports?|resistances?|zones?|ranges?|levels? to watch|breakout|breakdown|hurdle|pivot|band|between|"
                   r"watch(?:ing)? (?:out )?for|mark of|psychological)\b", re.I)
PAST_BUY = re.compile(r"\b(bought|purchased|acquired|buy(?:ing)? price|average price|avg price|cost price|entry price|"
                      r"borrowed a pri[cz]e|at a pri[cz]e of|holding (?:[\w,]+ )?shares|holding on to|holds? (?:\w+ ){1,3}at)\b[^.]{0,40}$", re.I)   # ASR: 'borrowed a prize of' = 'bought at a price of'
RETRACT = re.compile(r"^[\s,.]*(?:(?:uh|um|er)[\s,.]+)?(?:\d[\d,.]*[\s,.]+(?:(?:uh|um)[\s,.]+)?)?(?:pardon|sorry|i mean|i'm sorry|correction|rather)\b", re.I)
RANGE_PCT = re.compile(r"^\s*(?:to|-)\s*\d+(?:\.\d+)?\s*(%|percent|per cent)", re.I)
MAX_ATTACH_CHARS = 90          # a number is attached to a stock name only if it follows it within ~15 words (run-on ASR sentences)
# v2 (after the held-out round): a spoken number is a CURRENT price only "strongly" if the words between the name and the number are
# locator words ("Nifty is currently at 22,411", "22,411 is currently where the Nifty is at", "22,555 on the Nifty").
BIND_GAP = re.compile(r"^(?:[\s,.>-]|\b(?:is|are|now|currently|at|trading|quoting|trades|stands|sitting|hovering|around|near|about|closer|"
                      r"50|to|the|on|index|presently|right|as|of|we|speak|where|it|its|levels?|just|still|back|seen|seeing|has|have|"
                      r"fallen|slipped|dropped|risen|moved|crossed|below|above|nearing|well|so|over|under|uh)\b)*$", re.I)
DAYSTAT = re.compile(r"\b(?:today'?s|day'?s|intraday|of the day|session'?s?)\s+(low|high)s?\b|\bthe\s+(low|high)\b", re.I)
BEFORE_NOT_PRICE = re.compile(r"(\$|usd|dollars?|fy|f-|q[1-4]|in|since|by|till|until|year|of the)\s*$", re.I)
APPROX = re.compile(r"\b(around|about|near|nearly|roughly|close to|approximately|odd|somewhere)\b", re.I)
HYPO = re.compile(r"\b(suppose|let's say|lets say|assuming|assume|imagine)\b|\bif\b[^.]{0,40}\b(goes|go|breaks?|falls?|rises?|comes?|"
                  r"moves?|sustains?|crosses?|slips?|holds?|were|was|gets?|closes?|ends?|settles?)\b", re.I)
ASR_DASH = re.compile(r"\b(\d{1,2})-(\d{3})\b(?!-)")          # whisper writes "22,700" as "22-700"
ASR_SPACE = re.compile(r"\b(\d{1,2}), (\d{3})\b")              # ... or as "55, 150"
PERSONAL = re.compile(r"\bI\s+(?:have\s+|had\s+|just\s+|also\s+)?(bought|sold|purchased|shorted|entered|exited|booked|added)\b", re.I)
HIST = re.compile(r"\b(closed|yesterday|last (?:week|month|year|session|friday|quarter)|previous close|52[- ]week|all[- ]time|ago|"
                  r"earlier this (?:year|month|week)|listed at|issue price|ipo price|did speak|spoke of|had said|we said|mentioned earlier)\b", re.I)
TARGET = re.compile(r"\b(target(?:s| price)?|upside|could (?:go|move|test|head|rally)|towards|potential|fair value|price objective|"
                    r"expect(?:ing)?|will (?:go|reach|test))\b", re.I)
STOP = re.compile(r"(stop[- ]?loss|stop at|stop of|\bsl\b)\W*(?:of|at|is|would be|placed at|around|near)?\W*$", re.I)
CALL = re.compile(r"\b(buy|sell|accumulate|short|go long|add|book profits?|exit)\b", re.I)
ENTRY = re.compile(r"\b(buy|sell|accumulate|short|add)\b[^.]{0,40}?\b(at|around|near|between|above|below|on dips (?:to|towards)?)\s*$", re.I)
QUOTE = re.compile(r"\b(trading|quoting|currently|right now|at the moment|presently|now at|is at|are at|hit|touched|crossed|breached|"
                   r"reached|hovering|trades|is up|is down|up \d|down \d|higher at|lower at|gaining|falling|slipped|jumped|surged|holding|"
                   r"nearing|is where|finds itself|levels? of|sitting at|stands at|at this point|as we speak|as of now)\b", re.I)
QTY = re.compile(r"(\d[\d,]*)\s+(shares|quantity|qty|units)\b", re.I)


def sentences(segments: list[dict], max_gap: float = 1.2) -> list[dict]:
    """Merge ASR segments into sentences (split on . ? ! or a pause > max_gap). Keeps media times and word confidences."""
    out, cur = [], None
    for s in segments:
        if cur and (s["start"] - cur["end"] > max_gap):
            out.append(cur)
            cur = None
        if cur is None:
            cur = {"start": s["start"], "end": s["end"], "text": s["text"], "words": list(s.get("words", []))}
        else:
            cur["end"] = s["end"]
            cur["text"] += " " + s["text"]
            cur["words"] += s.get("words", [])
        if re.search(r"[.?!]\s*$", s["text"]):
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    for i, s in enumerate(out):
        s["id"] = i
    return out


def rounding(raw_int: str, dec: str | None, approx: bool, value: float) -> tuple[float, str]:
    if dec:
        tol, why = 0.05, "stated to the paisa; tolerance ±0.05 (tick)"
    else:
        digits = raw_int.replace(",", "")
        tz = len(digits) - len(digits.rstrip("0")) if digits.strip("0") else 0
        unit = 10 ** tz
        tol, why = max(0.05, unit / 2), f"whole number rounded to {unit}; tolerance ±{unit / 2:g}"
    if approx:
        t2 = round(0.005 * value, 2)
        if t2 > tol:
            tol, why = t2, why + "; said 'around/about' so ±0.5 %"
    return tol, why


def word_conf(words, t0, t1):
    ps = [w[3] for w in words if w[1] >= t0 - 0.05 and w[2] <= t1 + 0.05]
    return round(min(ps), 3) if ps else None


def _char_time(sent, char_pos):
    """approximate media time of a character position by proportional word index"""
    ws = sent["words"]
    if not ws:
        return sent["start"]
    frac = char_pos / max(1, len(sent["text"]))
    return ws[min(len(ws) - 1, int(frac * len(ws)))][1]


def extract(segments: list[dict]) -> tuple[list[dict], list[dict]]:
    sents = sentences(segments)
    claims = []
    prev_mentions, prev_end = [], -1e9
    for s in sents:
        text = ASR_SPACE.sub(lambda m: m.group(1) + "," + m.group(2) + " ", ASR_DASH.sub(lambda m: m.group(1) + "," + m.group(2), s["text"]))  # lengths preserved
        s["text"] = text
        ments = find_mentions(text)
        for m in NUM.finditer(text):
            raw_int, dec = m.group("int"), m.group("dec")
            after, before = text[m.end():m.end() + 25], text[max(0, m.start() - 12):m.start()]
            if AFTER_NOT_PRICE.match(after) or RANGE_PCT.match(after) or BEFORE_NOT_PRICE.search(before):
                continue
            value = float(raw_int.replace(",", "") + ("." + dec if dec else ""))
            if value < 1 or (not dec and 1990 <= value <= 2035 and "," not in raw_int):
                continue
            if RETRACT.match(text[m.end():m.end() + 40]):
                continue                    # speaker corrected themselves: "23,000 uh 22,000 pardon 22,672" -> 23,000 and 22,000 retracted
            prior = [x for x in ments if x["end_char"] <= m.start()]
            ctx = False
            if prior and m.start() - prior[-1]["end_char"] <= MAX_ATTACH_CHARS:
                ent = prior[-1]
            elif ments and not prior and ments[0]["start_char"] - m.end() <= 40:
                ent = ments[0]
            elif not ments and prev_mentions and s["start"] - prev_end <= 20 and m.start() <= MAX_ATTACH_CHARS:
                ent, ctx = prev_mentions[-1], True
            else:
                continue
            head = text[:m.start()]
            near = text[max(0, m.start() - 60):m.start()]
            why = []
            approx = bool(APPROX.search(text[max(0, m.start() - 25):m.start()]))
            if PERSONAL.search(head):
                ctype, role = "PERSONAL_TRADE", "execution_price"
                why.append("first-person execution verb")
            elif HYPO.search(near):
                ctype, role = "HYPOTHETICAL", None
                why.append("conditional wording")
            elif PAST_BUY.search(text[max(0, m.start() - 60):m.start()]):
                ctype, role = "HISTORICAL", "past_purchase"
                why.append("someone's past purchase (date not stated)")
            elif STOP.search(text[max(0, m.start() - 30):m.start()]):
                ctype, role = "CALL", "stop"
                why.append("stop-loss wording")
            elif DAYSTAT.search(text[max(0, m.start() - 45):m.end() + 35]):
                ctype, role = "HISTORICAL", "day_stat"
                why.append("today's / the day's high or low")
            elif LEVEL.search(text[max(0, m.start() - 60):m.end() + 30]):
                ctype, role = "TARGET", "level"
                why.append("technical level / zone wording (a level to watch, not a traded price)")
            elif HIST.search(near) or HIST.search(text[m.end():m.end() + 40]):
                ctype, role = "HISTORICAL", None
                why.append("past-reference wording")
            elif TARGET.search(near):
                ctype, role = ("CALL", "target") if CALL.search(text) else ("TARGET", "target")
                why.append("target/forecast wording")
            elif ENTRY.search(text[max(0, m.start() - 60):m.start()]):
                ctype, role = "CALL", "entry"
                why.append("buy/sell ... at <price>")
            elif QUOTE.search(text):
                ctype, role = "QUOTE", "current_price"
                why.append("present-tense market wording")
            else:
                ctype, role = "UNCLASSIFIED", None
                why.append("no type cue")
            if ent["end_char"] <= m.start():
                gap = text[ent["end_char"]:m.start()]
            else:
                gap = text[m.end():ent["start_char"]]
            binding = "strong" if (not ctx and len(gap) <= 45 and BIND_GAP.match(gap)) else "weak"
            pre = text[max(0, m.start() - 25):m.start()]
            ineq = ">=" if ABOVE.search(pre) else "<=" if BELOW.search(pre) else None
            post = text[m.end():m.end() + 120]
            if ineq is None and re.search(r"\b(above|over|past|crossed)\s+(that|this|the|it)\b\s*(level|mark)?", post, re.I):
                ineq = ">="                      # "22,600 is something we highlighted ... we've come up above that level"
            elif ineq is None and re.search(r"\b(below|under|breached|broke)\s+(that|this|the|it)\b\s*(level|mark)?", post, re.I):
                ineq = "<="
            tol, tol_why = rounding(raw_int, dec, approx, value)
            t_num = _char_time(s, m.start())
            qty = None
            if ctype == "PERSONAL_TRADE":
                q = QTY.search(text)
                if q:
                    qty = int(q.group(1).replace(",", ""))
            claims.append({
                "id": f"c{len(claims) + 1}", "type": ctype, "role": role, "sentence_id": s["id"], "sentence": text.strip(),
                "t_media": round(t_num, 2), "t_sentence": [s["start"], s["end"]],
                "instrument_span": ent["span"], "candidates": ent["candidates"], "ambiguous": ent["ambiguous"],
                "entity_from_context": ctx, "number_raw": m.group(0).strip(), "value": value, "approx": approx,
                "tolerance": tol, "tolerance_why": tol_why, "quantity": qty,
                "binding": binding, "inequality": ineq, "char_pos": m.start(), "asr_word_conf": word_conf(s["words"], t_num - 0.6, t_num + 1.2), "why_type": why})
        if ments:
            prev_mentions, prev_end = ments, s["end"]
    return claims, sents
