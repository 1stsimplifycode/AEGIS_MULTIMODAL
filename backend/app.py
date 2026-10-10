"""FastAPI backend: 'Did That Trade Really Happen?'

    uvicorn backend.app:app --port 8000            (from the project directory)

Modes (env CAPSTONE_MODE): 'hosted' (default; Render) serves the stored evidence packages and runs the verifier live;
'local' additionally enables video upload, which runs speech recognition and OCR on this machine (needs ffmpeg,
faster-whisper, rapidocr-onnxruntime). The UI only shows the upload control when /api/health says it is enabled.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import pipeline
from encoders.entities import resolve_typed
from encoders.market import IST, get_market, ist
from verification.engine import VERSION, Assumptions, verify_price_claim

ROOT = Path(__file__).resolve().parents[1]
MODE = os.environ.get("CAPSTONE_MODE", "hosted")
app = FastAPI(title="Did That Trade Really Happen?", version=VERSION)
JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def upload_enabled() -> bool:
    if MODE != "local" or not shutil.which("ffmpeg"):
        return False
    try:
        import faster_whisper  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


@app.get("/api/health")
def health():
    m = get_market()
    return {"ok": True, "version": VERSION, "mode": MODE, "upload_enabled": upload_enabled(),
            "market_coverage": m.coverage, "n_instruments": len(m.instruments)}


@app.get("/api/samples")
def samples():
    return pipeline.list_samples()


def _new_job(kind, label):
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"id": jid, "kind": kind, "label": label, "created": time.time(), "status": "running",
                 "stages": [{"key": k, "label": l, "status": "pending", "seconds": None, "detail": None} for k, l in pipeline.STAGES],
                 "result": None, "error": None}
    return jid


def _progress(jid):
    def cb(key, status, seconds=None, detail=None):
        with LOCK:
            for s in JOBS[jid]["stages"]:
                if s["key"] == key:
                    s.update(status=status, seconds=seconds, detail=detail)
    return cb


def _run(jid, pkg):
    try:
        res = pipeline.analyze(pkg, _progress(jid))
        with LOCK:
            JOBS[jid]["result"] = res
            JOBS[jid]["status"] = "done"
    except Exception as e:  # noqa: BLE001
        with LOCK:
            JOBS[jid]["status"] = "error"
            JOBS[jid]["error"] = f"{type(e).__name__}: {e}"


class StartReq(BaseModel):
    sample_id: str


@app.post("/api/analyses")
def start(req: StartReq):
    try:
        pkg = pipeline.load_package(req.sample_id)
    except FileNotFoundError:
        raise HTTPException(404, "unknown sample")
    jid = _new_job("sample", pkg["meta"]["title"])
    threading.Thread(target=_run, args=(jid, pkg), daemon=True).start()
    return {"job_id": jid}


@app.get("/api/analyses/{jid}")
def status(jid: str):
    j = JOBS.get(jid)
    if not j:
        raise HTTPException(404, "unknown analysis (the server may have restarted - start it again)")
    with LOCK:
        return {k: j[k] for k in ("id", "kind", "label", "status", "stages", "error")} | {"has_result": j["result"] is not None}


@app.get("/api/analyses/{jid}/result")
def result(jid: str):
    j = JOBS.get(jid)
    if not j or j["result"] is None:
        raise HTTPException(404, "no result yet")
    return JSONResponse(json.loads(json.dumps(j["result"], default=str)))


@app.get("/api/analyses/{jid}/report.json")
def report_json(jid: str):
    j = JOBS.get(jid)
    if not j or j["result"] is None:
        raise HTTPException(404, "no result yet")
    body = json.dumps(_report(j["result"]), indent=1, default=str, ensure_ascii=False)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="certificate_{j["result"]["meta"]["id"]}_{jid}.json"'})


@app.get("/api/analyses/{jid}/report.html")
def report_html(jid: str):
    j = JOBS.get(jid)
    if not j or j["result"] is None:
        raise HTTPException(404, "no result yet")
    return HTMLResponse(_report_html(_report(j["result"])),
                        headers={"Content-Disposition": f'attachment; filename="certificate_{j["result"]["meta"]["id"]}_{jid}.html"'})


def _report(res):
    """The exported report IS the Final Impossibility Certificate, plus the claim set and reproducibility record."""
    return {**res["certificate"], "claim_set": res["claim_set"], "stages": {k: {kk: v[kk] for kk in ("input", "processing", "output")}
                                                                            for k, v in res["stages"].items()},
            "reproducibility": res["audit"]}


def _report_html(rep):
    e = html.escape
    sec = []
    for chk in rep["checks"]:
        rows = "".join(f"<tr><td>{e(str(i.get('claim_id')))}</td><td><b>{e(i['verdict'])}</b></td><td>{e(str(i.get('reason') or ''))}</td>"
                       f"<td>{e('; '.join(i.get('assumptions') or []))}</td></tr>" for i in chk["items"])
        sec.append(f"<h2>{e(chk['name'])}: {e(chk['verdict'])}</h2><p>{e(chk['question'])}</p>"
                   + (f"<p><i>{e(chk['note'])}</i></p>" if chk.get('note') else "")
                   + (f"<table><tr><th>Item</th><th>Verdict</th><th>Reason</th><th>Assumptions</th></tr>{rows}</table>" if rows else ""))
    tm = rep.get("time_mapping") or {}
    tm_txt = (f"identified from the chart: {tm.get('day')} ±{tm.get('tau_radius', 0):.0f} s ({tm.get('method')})" if tm.get("status") == "IDENTIFIED"
              else f"not identified from the video: {tm.get('reason')}")
    means = "".join(f"<li><b>{e(k)}</b>: {e(v)}</li>" for k, v in rep["verdict_meanings"].items())
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Impossibility certificate {e(rep['certificate_id'])}</title>
<style>body{{font-family:system-ui,Segoe UI,Arial;max-width:1000px;margin:24px auto;padding:0 16px;color:#13202f}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #c9d1db;padding:6px;vertical-align:top;font-size:13px}}
h1{{font-size:22px}}pre{{background:#f3f5f8;padding:8px;overflow:auto;font-size:12px}}</style></head><body>
<h1>Final Impossibility Certificate {e(rep['certificate_id'])}</h1>
<p>Video: {e(str(rep['video'].get('title')))} · {e(str(rep['video'].get('source')))} · recorded {e(str(rep['video'].get('recorded_ist')))}
 · algorithm {e(str(rep['algorithm_version']))} · generated {e(rep['generated_utc'])}</p>
<p><b>Video-to-market time:</b> {e(tm_txt)}</p><h2>What the verdicts mean</h2><ul>{means}</ul>{''.join(sec)}
<h2>Reproduce</h2><ol>{''.join(f'<li><code>{e(x)}</code></li>' for x in rep['reproduce'])}</ol>
<h2>Sources</h2><pre>{e(json.dumps(rep['sources'], indent=1, default=str))}</pre>
<p><b>{e(rep['disclaimer'])}</b></p></body></html>"""


class TypedClaim(BaseModel):
    instrument: str = Field(..., max_length=60)
    price: float = Field(..., gt=0)
    date: str
    time: str | None = None            # "HH:MM" IST
    quantity: int | None = Field(None, gt=0)
    action: str = "bought"


@app.post("/api/check-claim")
def check_claim(c: TypedClaim):
    """Verify a claim typed by the user (e.g. 'I bought 1,800 shares of X at 245.50 at 10:31'). Labelled as user-supplied."""
    m = get_market()
    try:
        d = dt.date.fromisoformat(c.date)
    except ValueError:
        raise HTTPException(422, "date must be YYYY-MM-DD")
    cands = resolve_typed(c.instrument)
    stated = None
    if c.time:
        try:
            hh, mm = [int(x) for x in c.time.split(":")]
            stated = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=IST).timestamp() + 30
        except Exception:  # noqa: BLE001
            raise HTTPException(422, "time must be HH:MM (IST)")
    dec = "." in f"{c.price}".rstrip("0").rstrip(".")
    claim = {"id": "typed", "type": "PERSONAL_TRADE", "role": "execution_price", "value": c.price, "tolerance": 0.05 if dec else 0.5,
             "tolerance_why": "typed price", "candidates": cands, "instrument_span": c.instrument, "quantity": c.quantity,
             "sentence": f"I {c.action} {c.quantity or ''} shares of {c.instrument} at {c.price} on {c.date}" + (f" at {c.time}" if c.time else ""),
             "why_type": ["typed by the user"]}
    r = verify_price_claim(claim, None, 0.0, m, Assumptions(), stated_time=stated, stated_date=d)
    r["claim"] = claim
    sym = r.get("instrument") or (cands[0] if cands else None)
    if sym and m.day_status(d) == "trading":
        a, b = m.session_bounds(d)
        t0, t1 = ((stated - 20 * 60, stated + 20 * 60) if stated else (a, b - 60))
        r["context_bars"] = [x.as_dict() for x in m.bars(sym, t0, t1) if x.lo == x.lo]
        r["context_symbol"] = sym
    r["user_supplied"] = True
    from verification.branches import MEANING, fill_branch
    fb = fill_branch([r])
    r["fill_branch"] = {"verdict": fb["items"][0]["verdict"] if fb["items"] else "ABSTAIN", "meaning": MEANING,
                        "item": fb["items"][0] if fb["items"] else None,
                        "note": None if fb["items"] else "No quantity was given, so fill conservation cannot be tested (price and time only)."}
    r["instrument_names"] = {s: m.instruments.get(s, {}).get("name", s) for s in cands}
    return JSONResponse(json.loads(json.dumps(r, default=str)))


@app.get("/api/regulation")
def regulation():
    txt = (ROOT / "data/regulatory/sebi_circular_2026-05-08.txt").read_text(encoding="utf-8")
    sha = (ROOT / "data/regulatory/sebi_circular_2026-05-08.pdf.sha256").read_text(encoding="utf-8").strip()
    return {"circular": "HO/47/17/12(11)2025-MRD-POD3/I/11107/2026", "date": "2026-05-08", "effective": "2026-07-01",
            "url": "https://www.sebi.gov.in/legal/circulars/may-2026/norms-for-sharing-and-usage-of-price-data-for-educational-purposes_101293.html",
            "pdf_sha256": sha, "text": txt}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), recorded_date: str | None = Form(None), recorded_time: str | None = Form(None)):
    if not upload_enabled():
        raise HTTPException(501, "Video upload runs speech recognition and OCR, which this hosted server does not have. "
                                 "Run the project locally (see README) to analyse your own video.")
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in (".mp4", ".mkv", ".webm", ".mov"):
        raise HTTPException(415, "please upload an .mp4, .mkv, .webm or .mov file")
    tmpdir = Path(tempfile.mkdtemp(prefix="upload_"))
    path = tmpdir / f"video{suffix}"
    with open(path, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    jid = _new_job("upload", file.filename or "uploaded video")
    threading.Thread(target=_run_upload, args=(jid, path, recorded_date, recorded_time), daemon=True).start()
    return {"job_id": jid}


def _run_upload(jid, path, recorded_date, recorded_time):
    from backend.local_pipeline import build_package_from_upload
    try:
        pkg = build_package_from_upload(path, recorded_date, recorded_time, _progress(jid))
        res = pipeline.analyze(pkg, _progress(jid))
        with LOCK:
            JOBS[jid]["result"] = res
            JOBS[jid]["status"] = "done"
    except Exception as e:  # noqa: BLE001
        with LOCK:
            JOBS[jid]["status"] = "error"
            JOBS[jid]["error"] = f"{type(e).__name__}: {e}"


@app.get("/media/{sample_id}/{name}")
def media(sample_id: str, name: str):
    p = (pipeline.SAMPLES / sample_id / "media" / name).resolve()
    if not str(p).startswith(str(pipeline.SAMPLES.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


@app.get("/media/{sample_id}/frames/{name}")
def frame_media(sample_id: str, name: str):
    p = (pipeline.SAMPLES / sample_id / "media" / "frames" / name).resolve()
    if not str(p).startswith(str(pipeline.SAMPLES.resolve())) or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend/index.html")
