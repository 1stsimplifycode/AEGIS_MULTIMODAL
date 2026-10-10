"""Audio evidence encoder: speech -> timestamped transcript (faster-whisper, CPU, int8).

    python -m encoders.audio <media file> <out.json> [--model base] [--start S] [--dur D]

Output JSON: {"media": path, "model": ..., "language": ..., "segments": [{"start", "end", "text", "words": [[w, s, e, p], ...]}],
              "runtime_s": ..., "audio_s": ...}. Times are seconds of MEDIA time (convert to wall clock with the capture's
media_to_wall mapping; see encoders/clock.py).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def transcribe(media: str, model_name: str = "base", start: float | None = None, dur: float | None = None) -> dict:
    from faster_whisper import WhisperModel
    import subprocess
    import tempfile

    src = media
    tmp = None
    if start is not None or dur is not None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        cmd = ["ffmpeg", "-v", "error", "-y"]
        if start is not None:
            cmd += ["-ss", str(start)]
        cmd += ["-i", media]
        if dur is not None:
            cmd += ["-t", str(dur)]
        cmd += ["-vn", "-ac", "1", "-ar", "16000", tmp]
        subprocess.run(cmd, check=True)
        src = tmp
    t0 = time.perf_counter()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, info = model.transcribe(src, language="en", word_timestamps=True, vad_filter=True, beam_size=1)
    off = start or 0.0
    out = []
    for s in segs:
        out.append({"start": round(s.start + off, 2), "end": round(s.end + off, 2), "text": s.text.strip(),
                    "words": [[w.word.strip(), round(w.start + off, 2), round(w.end + off, 2), round(w.probability, 3)] for w in (s.words or [])]})
    res = {"media": str(media), "model": f"faster-whisper-{model_name} int8 CPU", "language": info.language,
           "segments": out, "runtime_s": round(time.perf_counter() - t0, 1), "audio_s": round(info.duration, 1)}
    if tmp:
        Path(tmp).unlink(missing_ok=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("out")
    ap.add_argument("--model", default="base")
    ap.add_argument("--start", type=float)
    ap.add_argument("--dur", type=float)
    a = ap.parse_args()
    res = transcribe(a.media, a.model, a.start, a.dur)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    print(a.out, len(res["segments"]), "segments", res["runtime_s"], "s for", res["audio_s"], "s audio")


if __name__ == "__main__":
    main()
