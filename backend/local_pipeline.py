"""LOCAL mode only: build an evidence package from an uploaded video by actually running ffmpeg + speech recognition + OCR.

Air time: an uploaded file has no trustworthy clock. If the user enters the recording date/time it is used, but labelled
'user-supplied, not independently established' with a 5-minute uncertainty; otherwise timing checks are not performed.
"""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import time
from pathlib import Path

from encoders.audio import transcribe
from encoders.market import IST
from encoders.visual import ocr_video

ROOT = Path(__file__).resolve().parents[1]


def build_package_from_upload(path: Path, recorded_date: str | None, recorded_time: str | None, progress) -> dict:
    sid = "upload_" + time.strftime("%Y%m%dT%H%M%S")
    media_dir = ROOT / "demo/samples" / sid / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    progress("read_video", "running")
    t0 = time.perf_counter()
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                               capture_output=True, text=True, check=True).stdout.strip() or 0)
    vis = ocr_video(str(path), every_s=2.0, max_frames=int(min(600, dur / 2 + 1)))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf", "scale=640:-2", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "31", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(media_dir / "clip.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(path), "-frames:v", "1", "-vf", "scale=640:-2",
                    str(media_dir / "poster.jpg")], check=True)
    t_read = time.perf_counter() - t0
    progress("read_video", "done", round(t_read, 1), f"{vis['n_frames']} frames read, {len(vis['observations'])} on-screen price readings")
    progress("listen", "running")
    t0 = time.perf_counter()
    tr = transcribe(str(path), "base")
    progress("listen", "done", round(time.perf_counter() - t0, 1), f"{len(tr['segments'])} speech segments ({tr['model']})")
    clock = None
    use_date = None
    if recorded_date and recorded_time:
        d = dt.date.fromisoformat(recorded_date)
        hh, mm = [int(x) for x in recorded_time.split(":")]
        w0 = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST).timestamp()
        clock = {"wall_at_media0": w0, "slope": 1.0, "sntp_offset_s": 0.0, "resid_p95_s": 300.0, "live_edge_s": 0.0,
                 "source": "USER-SUPPLIED recording time (not independently established)"}
        use_date = recorded_date
    for o in vis["observations"]:
        o["usable"] = False
        o["unusable_reason"] = "uploaded video: ticker layout not validated"
    shutil.rmtree(path.parent, ignore_errors=True)
    return {"meta": {"id": sid, "kind": "upload", "synthetic": False, "title": "Your uploaded video", "description": "",
                     "channel_name": "unknown", "recorded_ist": f"{recorded_date} {recorded_time} (user-supplied)" if clock else "unknown",
                     "duration_s": dur, "source": "uploaded file (deleted after processing)", "clip": [0, dur],
                     "media": {"video": "clip.mp4", "poster": "poster.jpg", "offset_s": 0}, "thumbnail": "poster.jpg",
                     "use_date": use_date, "use_date_source": "user-supplied (not independently established)" if use_date else "unknown",
                     "presenter_status": "unknown", "live_capture": False},
            "clock": clock, "transcript": {"model": tr["model"], "segments": tr["segments"]},
            "screen": {"engine": vis["engine"], "layout_validated": False, "observations": vis["observations"]},
            "offline_stages": {"read_video": {"seconds": round(t_read, 1), "detail": "run live", "live": True},
                               "listen": {"seconds": None, "detail": "run live", "live": True}}}
