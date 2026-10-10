# Specification: what is checked, under which assumptions, and what each verdict means

Version `verifier 1.0` (2026-10-10). The code in `verification/engine.py` implements exactly this document. If the two disagree, that is a bug.

## 1. Inputs
| Modality | Source | What we extract |
|---|---|---|
| Speech | capture audio, faster-whisper `base` (CPU, int8), word timestamps | sentences with media times; stock/index mentions; numbers; claim type |
| Screen | ticker-band OCR (RapidOCR) of the capture frames | displayed (name, price) pairs with media times |
| Clock | the capture's own `validation.json`: SNTP-corrected wall clock + fitted media→wall map (p95 residual ≈ 4 s) | air time of every utterance and frame |
| Market | frozen NSE 1-minute bars: low/high (2026-09-10 … 10-08, 427 symbols) and OHLCV with volume (09-29 … 10-08) | price range and volume per minute |
| Regulation | SEBI circular HO/47/17/12(11)2025-MRD-POD3/I/11107/2026 dated 2026-05-08 (primary text in `data/regulatory/`) | scope, lag, effective date |

**The market data is 1-minute bars, not trade-by-trade records.** Nothing here is trade-level verification.

## 2. Claim types (from speech)
| Type | Example | Checked how |
|---|---|---|
| `QUOTE` (current price) | "Grasim is trading at 2,953" | Check A (price compatible) + Check B (timing) |
| `CALL` (recommendation) | "sell with a stop at 4,365, targets of 4,200" | Check A on the entry price if one is stated; after-call outcome (target/stop reached?), shown as information, never as causation |
| `TARGET` (forecast) | "my target price is 2,425" | not a current-price claim; outcome only |
| `HISTORICAL` | "closed at 1,410 yesterday" | Check A against the referenced day if it is identifiable, else not checked |
| `PERSONAL_TRADE` | "I bought 1,800 shares at 245.50" | Check A (price, time, quantity vs. NSE volume) + identity statement |
| `HYPOTHETICAL` / unclear | "if it goes to 300 …" | not checked; listed as "not a checkable claim" |

## 3. Declared assumption set 𝒜 (shown to the user with every verdict)
1. **Instrument:** every plausible candidate for the spoken or displayed name (resolver score ≥ 85, or exact alias). Ambiguous names keep all candidates.
2. **Timing:**
   - Air time = capture wall time ± (clock p95 residual + 5 s HLS live edge).
   - Broadcaster delay δ ∈ [0, 120] s.
   - A speaker quoting "now" may refer to a price seen up to λ = 180 s earlier.
   - Reference window for a quote: [t_air − 120 − 180 − u, t_air + u].
3. **Price convention:**
   - Tolerance = max(0.05, ½ × rounding unit of the spoken number). The rounding unit is inferred from trailing zeros and from words like "around" or "about".
   - A number is treated as a price only if it lies within [0.5×, 2×] of the instrument's price that day; otherwise the number is "not a price of this stock".
4. **Market:**
   - NSE regular session 09:15–15:30 IST.
   - Volume is NSE only (BSE not included).
   - Market holidays come from the exchange calendar implied by the data (no bars at all for that day).

## 4. Verdict rule (assumption-robust, three-valued)
For a claim c, let V(c, a) ∈ {compatible, incompatible, unknown} be the verdict under one assumption a ∈ 𝒜.
- **Contradicted by available records** ⇔ V(c, a) = incompatible for **every** a ∈ 𝒜, and every minute of every reference window has data.
- **Consistent with available records** ⇔ V(c, a) = compatible for **at least one** a, and for the most plausible instrument.
- **Not enough evidence** ⇔ otherwise (missing bars, unresolved instrument, no time, number not a price, holiday without an exchange stated, …).

Every Consistent or Contradicted verdict carries a **certificate**: the smallest set of market minutes (time, low, high, volume) plus the
extracted words or OCR text that by themselves imply the verdict. The UI shows the certificate. `audit.json` records it with
the data file hashes.

## 5. Check B (timing), for QUOTE claims
- **Timing consistent:** the price is inside the bar range somewhere in the reference window.
- **Price seen only later:** it is outside the window at every assumption, and first appears in the bars at t₁ > window end. Reported as
  "a timing inconsistency under the displayed assumptions", never as fabrication.
- **Matches an earlier price only:** the most recent match is before the window, so the quote is stale or historical.
- **Not observed that day:** possibly a misstatement or a speech-recognition error (the word confidences are shown).
- A price's first appearance in 1-minute bars does not prove it was unknowable earlier: bars are 1-minute ranges, and
  pre-open and other venues are not covered.

## 6. Check C (SEBI 30-day lag)
- **Rule (FAQ Q8 as modified, circular dated 2026-05-08, effective 2026-07-01):** a *person engaged solely in education* should not use market
  price data of the preceding 30 days to name a security while indicating future price, advice or recommendation.
- **Separate rule:** the 30-day sharing lag binds exchanges and intermediaries (para 2(iii)).
- **Computed:**
  - market-data date (the day the prices match);
  - use date (our own capture date, independently established);
  - age in days;
  - whether the segment names a security together with a call or target.
- **Not computable from video:** whether the presenter is "engaged solely in education", a registered RA/IA, or a news broadcaster.
- **Output:** "Regulatory applicability requires further information", unless the age is ≥ 30 days ("meets the 30-day lag") or the use date is before 2026-07-01 ("rule not yet in force").
- **Never output:** "violation".

## 7. Identity
Public bars cannot link an execution to a person. Every `PERSONAL_TRADE` claim additionally gets **"Claimed execution not independently verified"**.
Stronger verification needs a broker contract note, or exchange trade-level records obtained through an authorised channel.

## 8. Addendum v2.1 (2026-10-10): rules added after the held-out round. The code implements these; see REGRESSIONS.md
- **Claim-reading uncertainty is part of 𝒜.** A spoken QUOTE may be *Contradicted* only if all of the following hold:
  - the words between the stock name and the number are locator words ("strong binding");
  - the stock is named in the same sentence (not carried from an earlier sentence);
  - the number is not retracted ("… pardon …");
  - the number is attached within about 90 characters.

  Otherwise the outcome is at most *Not enough evidence*.
- **Inequalities:** "above / over / crossed X" (before or after the number) is checked as ≥ X; "below / under X" as ≤ X. No timing check for inequalities.
- **Trading calls** (buy/sell … at/target/stop) are recommendations: *Not a checkable claim*, plus after-the-fact outcome information (no causation).
- **Day statistics:**
  - "today's / the day's / the low|high" is checked against the session low/high up to the air time;
  - "yesterday's high/low/close/open" against the previous trading day;
  - cue words must be near the number;
  - contradiction only beyond 0.25 % (vendor allowance).
- **Past purchases** ("bought at a price of", "holding N shares … at") are past prices with no date: *Not enough evidence*.
- **Quantity:** if the price is consistent but the quantity exceeds all NSE volume at compatible minutes, the overall verdict is
  *Not enough evidence* (BSE not in data). The price verdict is shown separately.
- **Screen readings:** used only if read in ≥ 2 frames AND the recording passes the per-recording layout check (≥ 90 % of stable, resolved
  readings are plausible-magnitude prices for the named stock; exact-time agreement is not used by the check).

## 9. Architecture v3 (2026-10-10): mandated end-to-end architecture, implemented stage by stage in `backend/pipeline.py`
| Stage | Implementation | Output |
|---|---|---|
| Visual frame encoder | `encoders/frame_encoder.py`: full-frame OCR (1 frame/s) → chart-panel parser (index name, price, change, y-axis: **top = day high so far (up-ratchet)**, middle = (top + bottom)/2 as a layout self-check, bottom = previous close) → ratchet events → **τ(t)** by exact set-valued dating (`encoders/display_clock.py`, a controlled copy of the parent project's module, T2b joint price + ratchet feasibility per 1-minute bar) intersected over frames and searched over **every** trading day with OHLCV bars | τ interval + day, or **WEAK** (wider than ±90 s or in pieces) / **ABSTAIN** (no panel / model rejected), with the reason. Never falls back silently |
| Visual text encoder | `encoders/visual_text.py` | trading-panel frames, fill quantities, P&L (explicit label, or profit/loss + ₹), on-screen clock, name–price pairs; "none found" when none |
| Audio encoder | `encoders/audio.py` + `encoders/claims.py` | spoken observations, recalls, predictions, recommendations, executions, conditionals with speech times |
| Claim set with market time | pipeline stage 4 | who (unidentified speaker / on-screen graphic / typed / synthetic), what, kind, market time, **time source** (chart ratchets; else our SNTP capture clock, labelled; else none), uncertainty, evidence pointers (sentence id, nearest frame) |
| Anonymous exchange tape | `encoders/market.py` | NSE 1-minute low/high/volume, resolution and completeness per window, file hashes |
| Fill conservation | `verification/branches.py` | PASS: price traded in the window and quantity ≤ Σ NSE volume of compatible minutes. FAIL: quantity > that bound (assumption: NSE venue), price impossible in the window, or a holiday. ABSTAIN otherwise. ABSTAIN with a note when there is no fill claim |
| Knowability | same | PASS: the asserted observation was observable in market time (look-back 180 s). FAIL: a robust contradiction (incl. "seen only later"). ABSTAIN: predictions, recommendations, conditionals, or insufficient data. Chart prices used to infer τ are not re-tested (that would be circular) |
| Data age | same | PASS: data ≥ 30 days old, or the rule was not in force on the use date. ABSTAIN otherwise (scope is not establishable from video). Never FAIL from video alone |
| Certificate | same | per-check PASS/FAIL/ABSTAIN with fixed meanings, items, assumptions, evidence, sources, steps, content-hash ID |

With a chart-derived τ the knowability window drops the 0–120 s broadcast-delay assumption, because τ already contains it.
