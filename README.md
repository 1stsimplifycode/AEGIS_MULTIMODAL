# Did That Trade Really Happen?
### Checking stock-market videos against the exchange's own public record (Capstone Review 2, PW26_SSS_08)

A working research system. The full path runs on real archived broadcasts:

**video + audio → market-time claims → three checks → an auditable impossibility certificate**

## Architecture (implemented stage by stage; the UI shows each stage's input, status, output and evidence)
```
VISUAL FRAME ENCODER  chart panel → day-high RATCHET (+ price) → video→market time τ(t) ± uncertainty, date identified from the picture
VISUAL TEXT ENCODER   trading panels, fill quantities, prices, names, on-screen clock, P&L        ┐
AUDIO ENCODER         spoken executions, quoted prices, quantities, speech times                  ├→ CLAIM SET WITH MARKET TIME
                                                                                                  ┘   (who · what · when · evidence)
ANONYMOUS EXCHANGE TAPE  NSE 1-minute price range + executed volume, resolution & completeness
   ├─ FILL CONSERVATION   claimed quantity vs maximum executed volume (venue/time assumptions explicit)
   ├─ KNOWABILITY         was the asserted observation observable at that market moment? (observation vs prediction)
   └─ DATA AGE            market-data date vs SEBI 30-day educational rule (scope explicit)
         → FINAL IMPOSSIBILITY CERTIFICATE   PASS / FAIL / ABSTAIN per check, assumptions, evidence, sources, steps
```

**Verdict meanings:**
- **PASS:** the tested constraint was satisfied. It never proves trade ownership, recording authenticity or compliance.
- **FAIL:** a contradiction was demonstrated under listed assumptions.
- **ABSTAIN:** essential observations are missing or no reliable conclusion is possible.

**Time is read from the video itself when possible.** On CNBC-TV18 the index chart's top label is the day's high so far, an up-ratchet.
Exact set-valued matching against the exchange record identifies the date among all trading days, and τ to about ±4 s. Our independent
SNTP capture clock is used only to check it.

**When ratchets cannot be used**, the stage says why:
- no chart panel on screen; or
- the time map is too loose: wider than ±90 s, or split into several stretches.

The claim set then uses our capture clock, labelled as such. It never silently substitutes file metadata.

## Quick start (local, desktop browser)
```bash
cd "CAPSTONE REVIEW 2_MULTIMODAL_PW26_SSS_08"
pip install -r requirements.txt
uvicorn backend.app:app --port 8000          # open http://localhost:8000
# own-video upload (OCR + speech recognition on this machine):
pip install -r requirements-local.txt && CAPSTONE_MODE=local uvicorn backend.app:app --port 8000
```

**Checks and reproduction:**
```bash
python -m pytest -q                                    # 26 tests: regressions R1–R26 + API smoke tests
python -m scripts.browser_check --base http://localhost:8000   # real Chromium walkthrough (desktop) → assets/screenshots
python -m experiments.run_experiments                  # E1–E4 → reports/experiments.json
python -m experiments.tau_validation                   # E5: chart-ratchet time map vs independent clock
python -m scripts.extract_frames --sample <id>         # offline OCR for a sample (frames + thumbnails)
python -m scripts.ppt_shots && python -m scripts.build_ppt   # Review-2 deck → demo/Capstone_Review2_DidThatTradeReallyHappen.pptx
```

## Folder map
| Path | What |
|---|---|
| `encoders/` | `frame_encoder.py` (ratchets, τ), `display_clock.py` (exact dating, controlled copy), `visual_text.py`, `visual.py` (ticker), `audio.py`, `claims.py`, `entities.py`, `clock.py`, `market.py` |
| `verification/` | `engine.py` (per-claim market tests), `branches.py` (three branches + certificate) |
| `backend/` | FastAPI app, architecture pipeline, local upload pipeline |
| `frontend/` | investigation-flow UI (desktop) |
| `demo/samples/` | 3 real packages (our 6 Oct 2026 captures: frames, transcript, clock) + 1 synthetic package; `DEMO_SCRIPT.md`; the PPT |
| `docs/` | `SPECIFICATION.md`, `DATA_AUDIT.md`, `REGRESSIONS.md` |
| `reports/` | research report, experiments, τ validation, browser check, UI audit, final audit |

## Deploying on Render
- **Ready:** `render.yaml`; build `pip install -r requirements.txt`; start `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`; about 140 MB RAM.
- **Not deployed from here.**
- **Decision needed before a public deployment:** the repository's `.gitignore` excludes broadcast media and Yahoo market bars. The options are a
  private repo, a no-video deployment (supported: the app degrades gracefully), or a licensed data feed.
- **Blueprint location:** the root `render.yaml` belongs to the earlier app and is untouched. Create the Web Service manually with Root Directory =
  this folder.

## Honest status
- **The full architecture runs on real video.**
  - **Time map:** identified from the chart on the Bank Nifty sample (±4 s, agreeing with the independent clock).
  - **Explicit fallbacks:** the 12:50 sample is WEAK (too few chart frames); the NDTV sample has no chart panel.
- **No real fill claims:** there are no real "I bought N shares" claims in our business-news archive, so Fill Conservation ABSTAINs on real
  videos. It is demonstrated on clearly labelled synthetic claims and on claims you type.
- **Data:** 1-minute NSE bars only (not trade-by-trade, no BSE); one 20-day market window.
- **Validation:** the repaired spoken-claim rules have no untouched test set left (see the report).
- **Layout:** desktop layout only for this review; the mobile layout is planned for the next review.
