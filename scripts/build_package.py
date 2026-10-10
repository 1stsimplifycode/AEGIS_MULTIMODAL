"""Build a REAL evidence package from one archived live capture (run locally, where the capture files exist).

    python -m scripts.build_package --session 20261006T071609Z --channel tv18 --start 300 --dur 240 --id tv18_halftime \
        --title "..." --description "..."

Writes demo/samples/<id>/package.json and demo/samples/<id>/media/{clip.mp4, poster.jpg}. The clip is a low-resolution excerpt
(640x360, ~1-2 MB/min) of OUR OWN capture of a public live broadcast, kept short for a capstone demonstration.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

from encoders.clock import from_validation
from encoders.market import IST, ist
from encoders.visual import ticker_from_dense

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
SESS = PARENT / "research_hipc_2026/icoac_research/live_capture/sessions"
STREAMS = PARENT / "research_hipc_2026/data/streams"
CHANNEL_NAMES = {"ndtv": "NDTV Profit", "tv18": "CNBC-TV18"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--channel", required=True)
    ap.add_argument("--start", type=float, required=True)
    ap.add_argument("--dur", type=float, required=True)
    ap.add_argument("--id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--description", default="")
    a = ap.parse_args()
    out = ROOT / "demo/samples" / a.id
    (out / "media").mkdir(parents=True, exist_ok=True)
    cap = SESS / a.session / a.channel / "capture.mkv"
    clock = from_validation(SESS / a.session / "validation.json", a.channel)
    tr = json.loads((ROOT / f"data/transcripts/{a.session}_{a.channel}.json").read_text(encoding="utf-8"))
    lo, hi = a.start, a.start + a.dur
    segs = [s for s in tr["segments"] if s["end"] >= lo - 30 and s["start"] <= hi + 5]
    dense = STREAMS / f"live_{a.session}_{a.channel}" / "dense.jsonl"
    screen = ticker_from_dense(dense, channel=a.channel) if dense.exists() else {"observations": [], "ocr_cpu_s": 0, "engine": None}
    screen_obs = [o for o in screen["observations"] if lo <= o["t_media"] <= hi]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a.start), "-i", str(cap), "-t", str(a.dur), "-vf", "scale=640:-2",
                    "-r", "15", "-c:v", "libx264", "-preset", "veryfast", "-crf", "33", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
                    str(out / "media/clip.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a.start + 3), "-i", str(cap), "-frames:v", "1", "-vf", "scale=640:-2",
                    "-q:v", "5", str(out / "media/poster.jpg")], check=True)
    share = a.dur / max(1.0, tr.get("audio_s", 1200.0))
    t_start = clock.wall(a.start)
    day = dt.datetime.fromtimestamp(t_start, IST).date()
    meta = {"id": a.id, "kind": "real", "synthetic": False, "title": a.title, "description": a.description,
            "channel_name": CHANNEL_NAMES.get(a.channel, a.channel), "recorded_ist": ist(t_start), "duration_s": a.dur,
            "source": f"our live capture {a.session}/{a.channel}/capture.mkv (public YouTube live stream of {CHANNEL_NAMES.get(a.channel)})",
            "clip": [lo, hi], "media": {"video": "clip.mp4", "poster": "poster.jpg", "offset_s": a.start}, "thumbnail": "poster.jpg",
            "use_date": str(day), "use_date_source": "our own live capture of the broadcast, SNTP-corrected clock (independently established)",
            "presenter_status": "news_broadcast", "live_capture": True, "language": "English"}
    pkg = {"meta": meta, "clock": clock.as_dict(),
           "transcript": {"model": tr["model"], "segments": segs},
           "screen": {"engine": screen.get("engine"), "layout_validated": screen.get("layout_validated"), "observations": screen_obs},
           "offline_stages": {
               "read_video": {"seconds": round(screen.get("ocr_cpu_s", 0) * share, 1),
                              "detail": f"{len(screen_obs)} ticker readings (RapidOCR, 4 frames/s; CPU time prorated to this clip; run offline "
                                        f"before this demo)" + ("" if screen.get("layout_validated") else
                                                                 " - this channel's ticker layout is NOT validated, readings are shown but not used")},
               "listen": {"seconds": round(tr.get("runtime_s", 0) * share, 1),
                          "detail": f"{len(segs)} speech segments ({tr['model']}; runtime prorated to this clip; run offline before this demo)"}}}
    (out / "package.json").write_text(json.dumps(pkg, ensure_ascii=False), encoding="utf-8")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(a.id, f"{size:.1f} MB", len(segs), "segments", len(screen_obs), "screen readings")


if __name__ == "__main__":
    main()
