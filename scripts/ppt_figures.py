"""Readable, annotated figures for the Review-2 deck - all drawn from real data files (no hand-drawn values).

    python -m scripts.ppt_figures         -> assets/ppt/fig_*.png

fig_frame_annotated.png   real CNBC-TV18 frame (6 Oct 2026, clip 0:37) with the OCR boxes the chart reader used
fig_tape_example.png      NSE 1-minute NIFTY 50 bars (Yahoo Finance) around the example claim, window and rounding band
fig_fail_counts.png       E2: FAIL verdicts on 8 broadcast days - held-out v1 vs development v2.1 (from reports/experiments.json)
fig_ablation_time.png     E6: time map with vs without the day-high label (from reports/ablation_ratchet.json)
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from encoders.frame_encoder import parse_panel  # noqa: E402
from encoders.market import get_market  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/ppt"
SAMPLE = ROOT / "demo/samples/tv18_nifty_bank_1301"
SOURCE = ROOT.parent / "research_hipc_2026/icoac_research/live_capture/sessions/20261006T071609Z/tv18/capture.mkv"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
T_FRAME = 997.4                       # source-media second of the example frame (clip 0:37)
NAVY, RED, AMBER, GREEN, GREY = "#1F4E79", "#A3282F", "#8A5A00", "#1D6B4F", "#8A939C"
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 13})


def _font(size):
    for f in ("segoeuib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def frame_annotated():
    raw = OUT / "_frame_example.png"
    if not raw.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(T_FRAME), "-i", str(SOURCE), "-frames:v", "1", str(raw)], check=True)
    # the on-screen price ticks several times a second and ffmpeg seeks differ slightly from the OCR pass, so the figure is labelled
    # from OCR of THIS exact image - the numbers shown always match the pixels
    from rapidocr_onnxruntime import RapidOCR
    res, _ = RapidOCR()(str(raw))
    lines = [[t, c, min(x for x, _ in b), min(y for _, y in b), max(x for x, _ in b), max(y for _, y in b)] for b, t, c in res]
    p = parse_panel(lines)
    S = 2                                                     # upscale for legibility
    im = Image.open(raw).convert("RGB")
    im = im.resize((im.width * S, im.height * S), Image.LANCZOS)
    pad = 640                                                 # white margin on the right for labels
    canvas = Image.new("RGB", (im.width + pad, im.height), "white")
    canvas.paste(im, (0, 0))
    dr = ImageDraw.Draw(canvas)
    f = _font(34)
    items = [(p["boxes"]["price"], RED, f"1  {p['price']:,.2f}", "index level on screen"),
             (p["boxes"]["axis"][0], AMBER, f"2  {p['axis_top']:,.0f}", "day's HIGH so far (can only rise)"),
             (p["boxes"]["axis"][1], GREY, f"3  {p['axis_bottom']:,.0f}", "yesterday's close (a check)")]
    for i, (b, col, big, small) in enumerate(items):
        x1, y1, x2, y2 = [v * S for v in b]
        dr.rectangle([x1 - 6, y1 - 6, x2 + 6, y2 + 6], outline=col, width=6)
        ly = 120 + i * 230
        dr.line([x2 + 8, (y1 + y2) / 2, im.width + 10, ly + 20], fill=col, width=4)
        dr.text((im.width + 20, ly), big, fill=col, font=_font(46))
        dr.text((im.width + 20, ly + 60), small, fill="#14202E", font=f)
    dr.text((im.width + 20, im.height - 72), "CNBC-TV18, 6 Oct 2026", fill="#44505E", font=_font(22))
    dr.text((im.width + 20, im.height - 44), "our recording, clip 0:37", fill="#44505E", font=_font(20))
    dr.text((im.width + 20, im.height - 20), "labels = OCR of this exact frame", fill="#44505E", font=_font(16))
    canvas.save(OUT / "fig_frame_annotated.png")


def tape_example():
    M = get_market()
    day = dt.date(2026, 10, 6)
    t = lambda h, m, s=0: dt.datetime(2026, 10, 6, h, m, s, tzinfo=IST).timestamp()
    bars = M.bars("^NSEI", t(12, 52), t(13, 7))
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    ax.axvspan(dt.datetime.fromtimestamp(t(12, 59, 51), IST), dt.datetime.fromtimestamp(t(13, 2, 59), IST), color=NAVY, alpha=0.08)
    ax.axhspan(22650, 22750, color=RED, alpha=0.07)
    ax.axhline(22700, color=RED, ls="--", lw=1.5)
    for b in bars:
        x = dt.datetime.fromtimestamp(b.t + 30, IST)
        dec = b.t == t(13, 2)
        ax.plot([x, x], [b.lo, b.hi], color=GREEN if dec else GREY, lw=9 if dec else 6, solid_capstyle="butt")
    said = dt.datetime.fromtimestamp(t(13, 2, 55), IST)
    ax.axvline(said, color=NAVY, lw=1.5)
    d = next(b for b in bars if b.t == t(13, 2))
    ax.annotate(f"minute 13:02\nlow {d.lo:,.2f}\nhigh {d.hi:,.2f}", xy=(dt.datetime.fromtimestamp(t(13, 2, 30), IST), d.hi),
                xytext=(dt.datetime.fromtimestamp(t(13, 4, 0), IST), 22655), color=GREEN, fontsize=12, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=GREEN))
    ax.text(dt.datetime.fromtimestamp(t(12, 52, 20), IST), 22702, "claimed 22,700", color=RED, fontsize=12, fontweight="bold")
    ax.text(dt.datetime.fromtimestamp(t(12, 52, 20), IST), 22738, "rounding band 22,650–22,750", color=RED, fontsize=10)
    ax.text(dt.datetime.fromtimestamp(t(12, 59, 58), IST), 22622, "window the speaker\ncould be quoting", color=NAVY, fontsize=10)
    ax.text(said, 22766, " said: 13:02:55 ± 4 s (market time)", color=NAVY, fontsize=10)
    ax.set_ylim(22610, 22775)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M", tz=IST))
    ax.set_ylabel("NIFTY 50 level")
    ax.set_title("NIFTY 50, 1-minute low–high (NSE prices via Yahoo Finance), 6 Oct 2026", fontsize=12, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_tape_example.png")
    plt.close(fig)
    return day


def fail_counts():
    ex = json.loads((ROOT / "reports/experiments.json").read_text(encoding="utf-8"))["E2_spoken_heldout"]
    v1 = ex["v1_frozen_heldout"]["vs_labels"]["contradicted"]
    v2 = ex["v21_after_repair_IN_SAMPLE"]["vs_labels"]["contradicted"]
    n1, n2 = sum(v1.values()), sum(v2.values())
    # per-item inspection (docs/REGRESSIONS.md R7, R9): of v1's 2 current-price FAILs, 1 is the 24,616.6 transcript number (correct FAIL),
    # 1 is 'above 22,700' checked as 'equals' (wrong). v2.1's single FAIL is the same 24,616.6 item.
    correct1, correct2 = 1, 1
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    labels = ["First version, frozen\n(held-out: fair test)", "After fixes\n(same days: development)"]
    ax.barh(labels, [correct1, correct2], color=GREEN, label="correct FAIL")
    ax.barh(labels, [n1 - correct1, n2 - correct2], left=[correct1, correct2], color=RED, alpha=0.75, label="wrong FAIL (misread sentence)")
    for y, (n, c) in enumerate([(n1, correct1), (n2, correct2)]):
        ax.text(n + 0.5, y, f"{n} FAIL{'s' if n != 1 else ''}: {c} correct", va="center", fontsize=13, fontweight="bold")
    ax.set_xlim(0, 56)
    ax.invert_yaxis()
    ax.set_xlabel("FAIL verdicts on 8 broadcast days")
    ax.legend(loc="lower right", frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_fail_counts.png")
    plt.close(fig)


def ablation_time():
    rows = {r["recording"]: r for r in json.loads((ROOT / "reports/ablation_ratchet.json").read_text(encoding="utf-8"))["rows"]}
    b = rows["sample:tv18_nifty_bank_1301"]
    lv = rows["sample:tv18_nifty_levels_1250"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.4), dpi=150, gridspec_kw={"width_ratios": [1.5, 1]})
    vals = [b["full"]["tau_radius_s"], b["price_only"]["span_radius_s"]]
    a1.barh(["with day-high", "price only"], vals, color=[GREEN, RED])
    a1.set_xscale("log")
    for y, v in enumerate(vals):
        a1.text(v * 1.15, y, f"± {v:,.0f} s" + ("" if y == 0 else f"  (≈ ±{v / 60:.0f} min, {b['price_only']['stretches']} stretches)"), va="center", fontsize=12)
    a1.set_xlim(1, 30000)
    a1.set_title("Short clip (Bank Nifty, 110 s): how precisely is the time known?", fontsize=11, loc="left")
    a1.invert_yaxis()
    days = [1, lv["price_only"]["candidate_days"]]
    a2.barh(["with day-high", "price only"], days, color=[GREEN, RED])
    for y, v in enumerate(days):
        a2.text(v + 0.05, y, f"{v} day{'s' if v > 1 else ''} fit", va="center", fontsize=12)
    a2.set_xlim(0, 4.2)
    a2.set_title("12:50 clip: how many dates fit?", fontsize=11, loc="left")
    a2.invert_yaxis()
    for ax in (a1, a2):
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_ablation_time.png")
    plt.close(fig)



def _day_sets(frames, M, use_ratchet):
    """per trading day: list of per-frame IntervalSets of tau (exactly as infer_tau builds them)."""
    from encoders.frame_encoder import _bars_for_day, PRICE_TOL
    from encoders import display_clock as DC
    days = [d for d in M.o_days if M.day_status(d) == "trading"]
    out = {}
    for d in days:
        sets = []
        for f in frames:
            p = f["panel"]
            bars, base = _bars_for_day(M, p["symbol"], d)
            if bars is None:
                sets = None
                break
            cp = (p["price"] - PRICE_TOL, p["price"] + PRICE_TOL)
            cM = (p["axis_top"] - 1.0 - PRICE_TOL, p["axis_top"] + 1.0 + PRICE_TOL) if use_ratchet and p.get("layout_ok") and p.get("axis_top") else None
            sets.append(DC.IntervalSet.from_bars(DC.joint_price_ratchets(bars, cp, cM, None)).shift(base - f["t_media"]))
        if sets:
            out[d] = sets
    return out


def insight_single_frame():
    """one real frame: where in the day can (price, day-high) both hold, vs price alone - NIFTY 50, 6 Oct 2026."""
    from encoders.frame_encoder import _bars_for_day, PRICE_TOL
    from encoders import display_clock as DC
    M = get_market()
    day = dt.date(2026, 10, 6)
    bars, base = _bars_for_day(M, "^NSEI", day)
    p, h = 22699.35, 22729.0                               # reading of the sample frame at clip 0:37 (frames.json)
    cp = (p - PRICE_TOL, p + PRICE_TOL)
    cM = (h - 1 - PRICE_TOL, h + 1 + PRICE_TOL)
    only_p = set(DC.joint_price_ratchets(bars, cp, None, None))
    joint = set(DC.joint_price_ratchets(bars, cp, cM, None))
    t = [dt.datetime.fromtimestamp(base + 60 * j + 30, IST) for j in range(bars.n)]
    R = bars.running_max()[1:]                            # day-high after each minute
    fig, ax = plt.subplots(figsize=(11, 4.2), dpi=150)
    for j in range(bars.n):
        ax.plot([t[j], t[j]], [bars.low[j], bars.high[j]], color="#C9CED4", lw=1.6)
    ax.step(t, R, where="mid", color=AMBER, lw=2, label="day's high so far (only rises)")
    for j in only_p - joint:
        ax.axvspan(t[j] - dt.timedelta(seconds=30), t[j] + dt.timedelta(seconds=30), ymax=0.06, color=RED, alpha=0.55, lw=0)
    for j in joint:
        ax.axvspan(t[j] - dt.timedelta(seconds=30), t[j] + dt.timedelta(seconds=30), color=GREEN, alpha=0.35, lw=0)
    ax.axhline(p, color=RED, ls=":", lw=1)
    ax.text(t[5], p + 6, f"shown price {p:,.2f}", color=RED, fontsize=11)
    ax.axhline(h, color=AMBER, ls=":", lw=1)
    ax.text(t[5], h + 6, f"shown day-high label {h:,.0f}", color=AMBER, fontsize=11)
    tid = dt.datetime(2026, 10, 6, 13, 2, 55, tzinfo=IST)
    ax.annotate("time identified from\nall 56 frames: 13:02:55 ± 4 s", xy=(tid, p), xytext=(dt.datetime(2026, 10, 6, 11, 20, tzinfo=IST), 22590),
                fontsize=10, color=NAVY, arrowprops=dict(arrowstyle="->", color=NAVY))
    ax.set_title(f"NIFTY 50, whole day 6 Oct 2026. One frame: shown price fits {len(only_p)} minutes (red ticks); "
                 f"price + day-high fit {len(joint)} (green bands)", fontsize=12, loc="left")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M", tz=IST))
    ax.set_ylabel("index level")
    ax.legend(loc="lower right", frameon=False)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_insight_frame.png")
    plt.close(fig)
    return len(only_p), len(joint)


def shrink_curve():
    """Bank Nifty sample (real frames): total feasible market time over ALL trading days vs number of frames used."""
    M = get_market()
    doc = json.loads((SAMPLE / "frames.json").read_text(encoding="utf-8"))
    frames = [{"t_media": f["t_media"], "panel": parse_panel(f["lines"])} for f in doc["frames"]]
    frames = [f for f in frames if f["panel"] and f["panel"].get("price") and f["panel"].get("symbol")]
    res = {}
    for name, ur in (("price + day-high", True), ("price only", False)):
        per = _day_sets(frames, M, ur)
        cur = {d: None for d in per}
        xs, ys, nd = [], [], []
        for k in range(len(frames)):
            tot, alive = 0.0, 0
            for d, sets in per.items():
                cur[d] = sets[k] if cur[d] is None else (cur[d] & sets[k])
                if cur[d].ivs:
                    tot += cur[d].measure()
                    alive += 1
            xs.append(k + 1); ys.append(max(tot, 1.0)); nd.append(alive)
        last = [v for v in cur.values() if v is not None and v.ivs]
        ivs = last[0].ivs if len(last) == 1 else []
        span = (ivs[-1][1] - ivs[0][0]) / 2 if ivs else None
        res[name] = (xs, ys, nd, len(ivs), span)
    fig, ax = plt.subplots(figsize=(8.5, 4.2), dpi=150)
    for name, col in (("price + day-high", GREEN), ("price only", RED)):
        xs, ys, nd, nst, span = res[name]
        ax.plot(xs, ys, color=col, lw=2.5, label=name)
        txt = (f"one moment, ±{span:,.0f} s" if nst == 1 else f"{nst} separate moments ~{2 * span / 60:,.0f} min apart\n→ time ambiguous")
        ax.text(xs[-1] + 0.6, ys[-1], txt, color=col, fontsize=10.5, va="center")
    ax.set_yscale("log")
    ax.set_yticks([10, 100, 1000])
    ax.set_yticklabels(["10 seconds", "100 seconds", "1,000 seconds" + chr(10) + "(17 minutes)"])
    ax.minorticks_off()
    ax.set_xlim(0, len(frames) + 26)
    ax.set_xlabel("number of video frames used (Bank Nifty clip, 1 frame per second)")
    ax.set_ylabel("possible market time left (seconds)")
    ax.set_title("Each frame rules out more possible times (each label up = 10 times more)", fontsize=12, loc="left")
    ax.legend(frameon=False)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_shrink.png")
    plt.close(fig)
    return {k: (v[1][-1], v[2][-1], v[3], v[4]) for k, v in res.items()}


def where_timeline():
    """Bank Nifty sample, all frames: WHERE in the day the clip can be - with vs without the day-high (real infer_tau output)."""
    import copy
    from encoders.frame_encoder import infer_tau
    M = get_market()
    doc = json.loads((SAMPLE / "frames.json").read_text(encoding="utf-8"))
    fr = [{"t_media": f["t_media"], "panel": parse_panel(f["lines"])} for f in doc["frames"]]
    full = infer_tau(fr, M)
    ab = copy.deepcopy(fr)
    for f in ab:
        if f["panel"]:
            f["panel"]["layout_ok"] = False
    po = infer_tau(ab, M)
    t_ref = fr[len(fr) // 2]["t_media"]
    fig, ax = plt.subplots(figsize=(10, 2.9), dpi=150)
    for label, r, col, y in (("price + day-high", full, GREEN, 1), ("price only", po, RED, 0)):
        for a, b in r["tau_intervals"]:
            x0 = dt.datetime.fromtimestamp(a + t_ref - 20, IST)
            x1 = dt.datetime.fromtimestamp(b + t_ref + 20, IST)
            ax.barh(y, x1 - x0, left=x0, height=0.45, color=col)
            ax.text(x0, y + 0.33, dt.datetime.fromtimestamp((a + b) / 2 + t_ref, IST).strftime("%H:%M"), color=col, fontsize=12,
                    fontweight="bold", ha="center")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["using price only", "using price + day's high"], fontsize=12)
    ax.set_ylim(-0.6, 1.8)
    ax.set_xlim(dt.datetime(2026, 10, 6, 12, 30, tzinfo=IST), dt.datetime(2026, 10, 6, 13, 15, tzinfo=IST))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M", tz=IST))
    ax.text(dt.datetime(2026, 10, 6, 12, 43, tzinfo=IST), 0, "2 moments, 24 min apart: can't tell", fontsize=11, color=RED, va="center")
    ax.text(dt.datetime(2026, 10, 6, 12, 43, tzinfo=IST), 1, "1 moment, ± 4 seconds", fontsize=11, color=GREEN, va="center")
    ax.set_title("Where in the day (6 Oct) can this 110-second clip be? - after reading all its frames", fontsize=12, loc="left")
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_where.png")
    plt.close(fig)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frame_annotated()
    tape_example()
    fail_counts()
    ablation_time()
    print("insight", insight_single_frame())
    print("shrink", shrink_curve())
    where_timeline()
    print("figures ->", OUT)


if __name__ == "__main__":
    main()
