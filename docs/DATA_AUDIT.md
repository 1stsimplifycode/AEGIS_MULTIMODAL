# Data audit (Phase A), 2026-10-10

| Source | Format | Dates | What it supports | What it does NOT support |
|---|---|---|---|---|
| Our live captures (`research_hipc_2026/.../live_capture/sessions/20261006T*/{ndtv,tv18}/capture.mkv`) | MKV 854×480, AAC audio, 20-min segments | 2026-10-06 12:46–15:31 IST (in session), 8 NDTV Profit + 8 CNBC-TV18 | real video, audio, ticker; air time from **our own** SNTP-corrected clock (`validation.json`: media→wall fit, p95 residual 3.4–3.7 s; HLS live-edge ±5 s) | the broadcaster's ingest delay (unknown; assumed 0–120 s) |
| Ticker OCR (`research_hipc_2026/data/streams/live_*/dense.jsonl`) | RapidOCR line boxes on the ticker band, 4 frames/s | same | on-screen (name, price) readings | reliable pairing on CNBC-TV18 (lot-size superscripts / second line), or on 7 of 8 NDTV recordings (layout check fails, 36–41 % plausible) |
| Our speech recognition (`data/transcripts/*.json`) | faster-whisper `base`, int8 CPU, word timestamps | 16 × 20 min = 18,626 s audio, 1,613 s runtime | spoken claims with timestamps | error-free text (e.g. "Nifty" heard as "if tea", "bought at a price" as "borrowed a prize") |
| YouTube auto-captions of 8 full-day live streams (`research/icsc2027/replays/*.json3`) | caption events + `release_timestamp` | 2026-09-29 … 10-05 | held-out evaluation (different speech recogniser, different days) | video frames (none stored); exact clock (±30 s assumed) |
| NSE 1-min low/high tape (`data/market/tape_lohi_*.npz`) | 427 instruments (424 equities + NIFTY 50, NIFTY BANK, SENSEX) | 2026-09-10 … 10-08 | price range per minute | trade-by-trade data; volume; filled minutes are carried forward (flagged) |
| NSE 1-min OHLCV (`data/market/ohlcv_1m_*.npz`, fetched 2026-10-10) | open/high/low/close/**volume**, no filling | 2026-09-29 … 10-08 (2 Oct = holiday, no bars) | price and volume bounds | **BSE** volume; individual trades; who traded |
| SEBI circular HO/47/17/12(11)2025-MRD-POD3/I/11107/2026 (`data/regulatory/`) | primary PDF text (sha256 recorded) | dated 2026-05-08, effective 2026-07-01 | scope, lag, effective date | any presenter's registration status |

**Absent, and not fabricated:**
- **trade-level (tick) records;**
- **any personal execution record (broker contract notes);**
- **any real "I bought N shares at P" claim** in the archive (business-news channels only).

Personal-trade checks therefore run only on clearly labelled synthetic claims or on claims typed by the user.

**Licensing:**
- Yahoo bars are for personal/research use (see README for the deployment decision).
- Broadcast excerpts are our own captures of public live streams, used as short research evidence.
- The SEBI circular is a public government document.

**Timestamps:** live-capture air times are independently established (our clock). Replay air times rely on YouTube's `release_timestamp`.
Uploaded videos have no trustworthy clock, and any date/time the user types is labelled "user-supplied".
