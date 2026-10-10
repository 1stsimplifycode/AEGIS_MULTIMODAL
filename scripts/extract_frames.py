"""Visual stage input: decode full frames from the ORIGINAL capture at a fixed rate, OCR them, keep small thumbnails as evidence.

    python -m scripts.extract_frames --sample tv18_nifty_bank_1301 [--fps 1]
    python -m scripts.extract_frames --session 20261006T071609Z --channel tv18 --fps 0.2 --out experiments/results/frames_...json

For a sample: reads meta.source session/channel + clip range from its package, writes demo/samples/<id>/frames.json
(per frame: t_media, OCR lines [text, conf, x0, y0, x1, y1] in 854x480 pixel coordinates, thumbnail name) and
demo/samples/<id>/media/frames/f_<t>.jpg (480 px). OCR: RapidOCR (onnxruntime, CPU). The CPU time is recorded.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESS = ROOT.parent / "research_hipc_2026/icoac_research/live_capture/sessions"


def run(capture: Path, t0: float, t1: float, fps: float, thumbs_dir: Path | None):
    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR()
    tmp = Path(tempfile.mkdtemp(prefix="frames_"))
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-i", str(capture), "-t", str(t1 - t0), "-vf", f"fps={fps}",
                    "-q:v", "3", str(tmp / "f%05d.jpg")], check=True)
    frames = []
    cpu0 = time.process_time()
    wall0 = time.perf_counter()
    for i, f in enumerate(sorted(tmp.glob("f*.jpg"))):
        t = round(t0 + i / fps, 2)
        res, _ = eng(str(f))
        lines = [[r[1], round(float(r[2]), 3), round(r[0][0][0], 1), round(r[0][0][1], 1), round(r[0][2][0], 1), round(r[0][2][1], 1)]
                 for r in (res or [])]
        rec = {"t_media": t, "lines": lines}
        if thumbs_dir is not None:
            name = f"f_{int(round(t * 10)):06d}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-vf", "scale=480:-2", "-q:v", "6", str(thumbs_dir / name)], check=True)
            rec["thumb"] = name
        frames.append(rec)
        f.unlink()
    tmp.rmdir()
    return {"fps": fps, "engine": "RapidOCR (onnxruntime, CPU) on full 854x480 frames", "frames": frames,
            "ocr_cpu_s": round(time.process_time() - cpu0, 1), "ocr_wall_s": round(time.perf_counter() - wall0, 1),
            "source": str(capture.relative_to(ROOT.parent)).replace("\\", "/"), "range_media_s": [t0, t1]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample")
    ap.add_argument("--session")
    ap.add_argument("--channel")
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.sample:
        sd = ROOT / "demo/samples" / a.sample
        pkg = json.loads((sd / "package.json").read_text(encoding="utf-8"))
        src = pkg["meta"]["source"].split()[3]                    # "our live capture <session>/<channel>/capture.mkv (...)"
        sess, ch = src.split("/")[:2]
        th = sd / "media/frames"
        th.mkdir(parents=True, exist_ok=True)
        out = run(SESS / sess / ch / "capture.mkv", pkg["meta"]["clip"][0], pkg["meta"]["clip"][1], a.fps, th)
        (sd / "frames.json").write_text(json.dumps(out), encoding="utf-8")
        print(a.sample, len(out["frames"]), "frames", out["ocr_wall_s"], "s")
    else:
        cap = SESS / a.session / a.channel / "capture.mkv"
        out = run(cap, 0, 1200, a.fps, None)
        Path(a.out).write_text(json.dumps(out), encoding="utf-8")
        print(a.session, a.channel, len(out["frames"]), "frames", out["ocr_wall_s"], "s")


if __name__ == "__main__":
    main()
