"""Survey every transcribed capture: verify all extracted claims and rank 240-s windows by checkable claims (demo selection)."""
import glob, json, os
from collections import Counter
from encoders.claims import extract
from encoders.clock import from_validation
from encoders.market import get_market, ist
from verification.engine import verify_price_claim, NOT_CHECKABLE

R = "../research_hipc_2026/icoac_research/live_capture/sessions"
M = get_market()
rows, tot = [], Counter()
for f in sorted(glob.glob("data/transcripts/*.json")):
    sess, ch = os.path.basename(f)[:-5].split("_")
    clk = from_validation(f"{R}/{sess}/validation.json", ch)
    cl, _ = extract(json.load(open(f, encoding="utf-8"))["segments"])
    for c in cl:
        r = verify_price_claim(c, clk.wall(c["t_media"]), clk.uncertainty_s, M)
        tot[(c["type"], r["verdict"])] += 1
        rows.append({"sess": sess, "ch": ch, "t": c["t_media"], "type": c["type"], "verdict": r["verdict"], "value": c["value"],
                     "cands": c["candidates"], "sentence": c["sentence"][:120], "timing": r.get("timing", {}).get("class"),
                     "air": ist(clk.wall(c["t_media"]))})
chk = [r for r in rows if r["verdict"] != NOT_CHECKABLE]
print("claims", len(rows), "checkable", len(chk))
for k, v in sorted(tot.items()): print("  ", k, v)
best = []
for sess, ch in sorted({(r["sess"], r["ch"]) for r in rows}):
    rs = [r for r in chk if r["sess"] == sess and r["ch"] == ch]
    for st in range(0, 1200 - 240 + 1, 30):
        w = [r for r in rs if st <= r["t"] < st + 240]
        if w:
            best.append((len(w), len({r["verdict"] for r in w}), sess, ch, st))
best.sort(reverse=True)
seen = set()
for n, nv, sess, ch, st in best:
    if (sess, ch) in seen: continue
    seen.add((sess, ch))
    print(n, "checkable,", nv, "verdict kinds:", sess, ch, "start", st)
    for r in [r for r in chk if r["sess"] == sess and r["ch"] == ch and st <= r["t"] < st + 240]:
        print("     ", round(r["t"]), r["air"][11:19], r["type"], r["cands"][:2], r["value"], "->", r["verdict"][:14], r["timing"], "|", r["sentence"][:70])
json.dump(rows, open("experiments/survey_all_claims.json", "w", encoding="utf-8"), indent=0, default=str)
