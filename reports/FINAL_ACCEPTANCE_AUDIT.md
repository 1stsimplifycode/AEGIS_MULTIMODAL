# Final acceptance audit (directive §19), 2026-10-10. Evidence for every answer is in this folder.

| Question | Answer | Evidence |
|---|---|---|
| Does the backend run? | **Yes** | `uvicorn backend.app:app`; `/api/health`; 21/21 tests |
| Does the frontend run? | **Yes** | `reports/browser_check.json`: 12 screens × 2 viewports, 0 console errors, 0 overflow |
| Can the user load a real prerecorded video? | **Yes** for the 3 real samples (our captures). Own-video upload: **local mode only** (OCR+ASR on this machine). On the hosted server the upload control is replaced by an explanation (API returns 501) | `backend/app.py`, `backend/local_pipeline.py`; upload **verified end-to-end** (60 s real excerpt: 154 s CPU, OCR 144 s + ASR 8 s; reproduced the stored sample's findings; the typed time is labelled user-supplied) |
| Real multimodal evidence? | **Yes**: speech (faster-whisper, 16 recordings), ticker OCR (RapidOCR), capture clock, market bars | `data/transcripts`, `demo/samples/*/package.json` |
| Market comparison uses real records? | **Yes**: frozen NSE 1-min bars (low/high and OHLCV with volume), sha256 in every audit | `data/market/*.npz` |
| Strong claims withheld when data is insufficient? | **Yes**: robust rule; vendor allowance; binding/inequality/retraction; holidays; BSE caveat | R1–R20, E2, E3 |
| Do all visible controls work? | **Yes**, every button/link exercised by the browser check (start, tabs, markers, transcript, both downloads, form, example buttons) | `scripts/browser_check.py` |
| Timelines synchronised? | **Yes**: marker → `video.currentTime` (0 → 90.65 s); playback highlights the transcript sentence (scrolls only the transcript box). Times are clip-relative; air time IST in tooltips | browser check |
| Each verdict includes evidence? | **Yes**: certificate minutes + quoted words + chart; "cannot establish" and "needed" sections | claim page |
| Can a first-time viewer understand it? | **Heuristic audit only** (no participants): 8 of 10 questions fully answered, 2 partially | `reports/UI_HEURISTIC_AUDIT.md` |
| Screenshots from the actual app? | **Yes**: all in `assets/screenshots/` were captured by Playwright from the running server | browser check |
| Experiments reproducible? | **Yes**, with frozen data and fixed seeds. The held-out run needs the parent repo's caption files | README |
| Failures and limitations disclosed? | **Yes** | `docs/REGRESSIONS.md`, report §12–13 |
| Substantive research contribution beyond combining tools? | **Modest.** An assumption-robust, certificate-backed verdict discipline that treats claim-reading uncertainty as an assumption, with measured necessity (contradiction precision 2/37 → 1/1). The ingredients are established; novelty and inventiveness do **not** reach the internal 9/9 target; GRC alignment is the strongest dimension | report §7 |

## What failed or remains open
- **Render:** not deployed from here (no account access). Config and instructions are ready.
  - A public deployment needs a decision on broadcast clips and Yahoo data (repository policy excludes both from git).
  - Untested: whether Render accepts the space in the directory name.
- **No untouched test set** remains for the repaired verifier (v2.1). The 8 held-out days became in-sample when we repaired on them.
- **Extraction recall is not measured.**
- **Screen evidence:**
  - NDTV ticker usable in 1 of 8 recordings;
  - CNBC-TV18 ticker layout unsupported.
- **No real first-person trade claims** exist in the data; Check A's trade/quantity logic is demonstrated on labelled synthetic claims only.
- **Uploaded videos:** the screen readings are never used as evidence (no layout validation), and the clock is user-supplied.
- **Disk:** about 200 MB free on C:. Further captures or models do not fit.

## Architecture fidelity audit (directive "no component may be omitted"), 2026-10-10
| Component | Implemented | Verified on real data |
|---|---|---|
| Visual frame encoder: chart high/low extension events (ratchets) + τ(t) with uncertainty | `encoders/frame_encoder.py` (day-high up-ratchet; set-valued dating over all trading days) | τ identified on 4 recordings (Bank Nifty sample ±4 s; 3 full recordings ±15–30 s), date correct every time. 1 recording rejected → ABSTAIN. 1 sample WEAK (±33 min) → labelled fallback. **No extension EVENT occurred in the analysed windows** (the day high was set earlier); the detector is unit-tested (R26). Day-LOW ratchets are not shown on this channel's chart (its bottom label is the previous close) |
| Visual text encoder | `encoders/visual_text.py` | runs on every frame; finds on-screen clocks and name–price pairs; **no trading panels or fills exist** in these news videos (reported, not invented) |
| Audio encoder | `encoders/audio.py`, `encoders/claims.py` | 16 recordings + 8 held-out days |
| Claim set with market time | `backend/pipeline.py` stage 4 | who / what / kind / market time / time source / evidence pointers |
| Anonymous exchange tape | `encoders/market.py` | resolution and completeness shown; hashes in the certificate |
| Fill conservation · Knowability · Data age | `verification/branches.py` | PASS / FAIL / ABSTAIN with fixed meanings. Fill demonstrated on synthetic and typed claims only (no real fill claims exist) |
| Final impossibility certificate | `verification/branches.py`, `/api/analyses/{id}/report.{html,json}` | downloads verified in the browser |
| UI renders the architecture; every stage shows input, status, output, evidence; verdict → trace to frames, transcript, market minutes | `frontend/app.js` | Playwright: all 9 nodes open, trace shows the real frame and market minutes, 0 console errors (desktop 1440×900) |
| Deck | `demo/Capstone_Review2_DidThatTradeReallyHappen.pptx`, 16 slides with a speaker script in the notes, built from real app screenshots | rendered and inspected |
