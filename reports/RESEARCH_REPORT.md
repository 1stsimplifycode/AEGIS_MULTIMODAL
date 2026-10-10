# Did That Trade Really Happen? Assumption-robust verification of financial-video claims against public market records
Capstone Review 2, PW26_SSS_08, 2026-10-10. All numbers come from `reports/experiments.json`, `experiments/results/*` and `reports/browser_check.json`.

## 1. Problem
Given a financial video, decide for each market claim it contains whether public exchange records:
- **support** it;
- **contradict** it;
- **cannot decide**.

Show the exact evidence, and never overstate. Three checks:
- **A:** price / trade compatibility;
- **B:** timing of the statement relative to the market;
- **C:** applicability of SEBI's 30-day educational data rule.

## 2. Motivation
Viewers cannot audit "it's trading at …", "I bought … at …" or "yesterday's high was …". The danger cuts both ways:
- a naive checker that "catches" errors will **accuse** speakers on the strength of its own extraction mistakes;
- a credulous one lends authority to claims it cannot check.

Section 10 measures how real the first danger is.

## 3. Existing work and its limits (not an exhaustive survey)
- **Claim verification against structured or tabular evidence:**
  - FEVER (Thorne et al. 2018);
  - TabFact (Chen et al. 2020);
  - FEVEROUS (Aly et al. 2021);
  - numerical claims, e.g. QuanTemp (2024).

  These verify **text** against **static** evidence. Ours has a **time** dimension (the claim is true *at air time*), a broadcast
  delay, and a reference (1-minute bars) that is incomplete by construction.
- **Multimodal misinformation** (e.g. out-of-context image–caption pairs, NewsCLIPpings 2021) detects inconsistency between modalities, not
  against an exchange record.
- **Abstention / selective prediction** (e.g. Geifman & El-Yaniv 2017) and **partial identification** (Manski 2003) provide the principle
  we apply: report a conclusion only if it holds over the whole set of assumptions not ruled out by the data.
- The parent AEGIS-Market work established tape-consistency dating of broadcasts, and its own limits (unidentifiable cases, missing reference days).

## 4. Data (full audit: `docs/DATA_AUDIT.md`)
- **Our live captures** (6 Oct 2026, 16 × 20 min, NDTV Profit and CNBC-TV18) with an independently established clock.
- **8 held-out full broadcast days** (29 Sep – 5 Oct) with YouTube captions.
- **Frozen NSE 1-minute bars:** low/high from 10 Sep, OHLCV with volume from 29 Sep.
- **SEBI circular** of 8 May 2026 (primary text).
- **Not available:** trade-level records, personal execution records, real first-person trade claims.

## 5. Architecture (implemented)
1. video → frames → **visual encoder** (ticker OCR, frame-stability filter, per-recording layout check);
2. audio → **audio encoder** (faster-whisper, word timestamps) → **claim encoder** (instrument, number, type, tolerance, binding, inequality, retraction);
3. **clock** (capture media→wall map, ±u);
4. **market encoder** (NSE bars, calendar, completeness);
5. **verification engine** (A/B/C, robust verdicts, certificates);
6. **explanation and audit**;
7. **UI** (7 screens).

Stages 1–2 run offline for the demo samples, with recorded cost shown in the UI; they run live for uploads in local mode. Stages 3–6 always run live.

## 6. Verification formulation (spec: `docs/SPECIFICATION.md`)
For a claim c and the declared assumption set 𝒜 = instruments × delay ∈ [0, 120] s × speaker look-back 180 s × clock ±u × rounding tolerance
(× claim-reading uncertainty):
- **Contradicted** ⇔ ∀a ∈ 𝒜: incompatible, and the data in the window is complete (≥ 90 % of minutes; a one-minute guard if incomplete).
- **Consistent** ⇔ ∃a: compatible (the most plausible instrument; ambiguity disclosed).
- **Not enough evidence** otherwise.

"Incompatible" for an exact claim P with tolerance τ: every bar in the window has [lo − τ, hi + τ] ∌ P. For "above X": every high < X − τ.

**Claim-reading uncertainty is part of 𝒜.** Contradiction additionally requires:
- *tight binding* (only locator words between the name and the number);
- the stock named in the same sentence;
- no retraction;
- no inequality misread.

**Certificate:** the minute(s) that decide the verdict, plus the quoted words.

**Quantity:** Σ NSE volume over compatible minutes is an upper bound on what could have executed on NSE. The claim as a whole stays
*Not enough evidence* because BSE is not in our data.

**Check B** classifies the first and last market occurrence of P relative to the window.

**Check C** reports facts (data date, use date and its provenance, age, the rule's scope) and never "violation".

## 7. Proposed contribution, and what is established
The contribution is a **verdict discipline for incomplete, time-sensitive public evidence**:
1. assumption-robust, three-valued verdicts in which *the reading of the claim itself* is among the assumptions (binding, type, retraction,
   inequality), not only the data;
2. a minimal, checkable certificate for every decisive verdict;
3. separation of price, quantity, identity and regulatory scope, so that "the price existed" is never conflated with "this person traded" or
   "this broke a rule";
4. evidence-quality gates learned from real failures: vendor-extreme allowance, OCR frame stability, a per-recording layout check that uses only
   price magnitude.

**Honest originality assessment:** every ingredient is established (partial identification, abstention, claim verification against
structured data). What is specific here is the combination for time-indexed broadcast claims, and **the measurement that it is necessary**
(section 10). We do not claim novelty ≥ 9 or inventiveness ≥ 9 by NeurIPS/AAAI standards. The evidence base (2 channels, 9 days, one
market window) is far below what a main-track empirical claim would need.

## 8. Baselines
- **Naive verifier (v1 frozen):** the same extractor without the reading-uncertainty rules; it contradicts whenever the number misses the range.
- **Per-channel screen rule** (before the per-recording check).
- **A blind independent annotator (LLM subagent)** as the reference for what each sentence asserts (not a human gold standard).

## 9. Methodology
- **Development:** the 16 captures (rules written while inspecting them).
- **Held-out round:** 8 unseen broadcast days, v1 frozen, scored against blind labels of all 105 decisive verdicts (the first labelling round
  was invalid because we truncated sentences; it was redone with number-centred windows).
- **Repair:** fixes derived from the held-out round. The repaired version is therefore **in-sample** on those days and reported as such.
- **Stress test (synthetic, separate):** alter blind-confirmed genuine quotes.
- **Resources:** measured on this laptop's CPU.
- **UI:** real Chromium (Playwright) at 1366×900 and 390×844.

## 10. Results
**E2, spoken claims on held-out days** (decisive verdicts vs blind labels):
| Version | Contradictions | of which genuine current-price statements | Consistent | of which genuine current prices |
|---|---|---|---|---|
| v1 frozen (true held-out) | 37 | **2 (5.4 %)** | 68 | 48 |
| v2.1 repaired (**in-sample**) | **1** | **1 (100 %)** | 62 | 43 |

Of the genuine current-price statements, v2.1 classed 43 consistent, 1 contradicted (a real misstatement: "Nifty50 24,616.6" when the Nifty was
about 22,600), 4 not enough evidence and 2 not checkable. The cost is coverage: 4 genuine statements are no longer decided.

**Development captures:** 225 → 86 number–stock links after repairs; 14 checkable; **0 contradictions**. Every one of the 15 earlier
contradictions was an extraction error.

**E3, controlled manipulations** (50 blind-confirmed genuine quotes, synthetic alterations):
| Alteration | Caught (contradicted) | False support (still consistent) |
|---|---|---|
| unaltered | 0 (no false contradictions) | – |
| shifted within the spoken rounding | 0 (no false contradictions) | – |
| exact quote ±2 %, +5 % (29) | 100 % | 0 % |
| inequality falsified by 2–5 % (21) | 95 % | 5 % |
| previous trading day, exact (29) | 93 % | 7 % (price recurrence: unidentifiable) |
| previous trading day, inequality (21) | 57 % | 43 % |
| wrong instrument (48) | abstains on all ("not a price of this stock") | 0 % |

**E1, screen evidence:**
- **Validated recording:** 240 of 247 stable NDTV ticker readings are consistent.
- **Other recordings:** the per-channel rule would have used 7 other NDTV recordings with about 27 % consistent and 12 % contradicted.
- **Per-recording layout check:** passes only the validated recording (97 % plausible vs 36–41 %). Screen evidence is therefore usable in
  1 of 8 NDTV recordings and 0 of 8 CNBC-TV18 recordings.

**E4, resources (CPU laptop):**
| Item | Cost |
|---|---|
| Market data load | 0.65 s (100 MB peak) |
| Live analysis per sample | 0.16–0.61 s, peak traced memory under 2 MB |
| Server process | about 140 MB RSS |
| Offline speech recognition | real-time factor 0.087 (5.2 h of audio in 27 min) |
| Offline ticker OCR (prorated to the demo clips) | 6.5–28.8 min of CPU per clip, the dominant cost |
| Storage | market data 20 MB; demo 12 MB; code 156 kB |

**Frontend:**
- all screens render at both widths;
- no console errors and no horizontal overflow;
- timeline markers seek the video (0 → 90.65 s);
- both exports download and the JSON parses;
- typed-claim checks return the expected verdicts.

## 11. Ablations
- **Remove reading uncertainty (= v1):** contradiction precision falls from 1/1 to 2/37.
- **Remove the vendor allowance:** R1 becomes a false contradiction.
- **Remove frame stability:** single-frame misreads (e.g. Titan 5,080 vs a 4,530–4,599 range) become screen contradictions.
- **Per-channel instead of per-recording layout:** about 12 % of used screen readings become contradictions on held-out recordings.
- **Ignore quantity in the overall verdict:** an impossible 5,000,000-share NSE trade is headlined "Consistent".

Each is pinned as a regression test.

## 12. Failure analysis
See `docs/REGRESSIONS.md` (R1–R20). Dominant cause: **the claim was misread, not the market data**. That covers levels, viewer
holdings, strikes, retractions, inequalities, run-on sentences and context carry-over.

Remaining known weaknesses:
- extraction recall is not measured (only decisive verdicts were labelled);
- consistent verdicts on levels that coincide with the price: 17 of 62 (the statement "the market traded there" is true, but the
  claim was not a current-price claim);
- CNBC-TV18 ticker unsupported;
- ASR word confidence is low for some numbers (e.g. 40 %).

## 13. Limitations
- Only 1-minute bars: no trade-level checks.
- NSE only.
- One 20-day market window (one regime).
- Business-news channels only: no real first-person trade claims, and no influencer videos.
- The annotator is an LLM, not human experts.
- The repaired version has no untouched test set.
- Broadcaster delay is assumed (0–120 s), not measured.
- The demo clips' OCR and ASR were run offline.

## 14. Financial GRC relevance
| Property | How it is handled |
|---|---|
| False-accusation control | contradictions only under every plausible reading and assumption; measured 1 decisive contradiction, which is genuine, after repair |
| Evidence faithfulness and auditability | certificates, quoted words, data hashes, algorithm version, assumptions, exportable audit report |
| Identity | never inferred ("Claimed execution not independently verified") |
| Regulatory scope | SEBI circular quoted from primary text; applicability left open when it depends on facts a video cannot show |
| Admissibility hygiene | independently established clock for our captures; user-supplied times labelled |

Domain-specific: exchange calendars, NSE/BSE split, the SEBI rule. General: the robust-verdict discipline and certificate design for any
claim checked against an incomplete, time-indexed public record (e.g. weather, sports scores, election tallies).

## 15. Reproducibility
`README.md` gives every command. Market files are frozen (sha256 in every audit report) and the seeds are fixed.

The held-out evaluation needs the parent repository's caption files. Blind labels are stored in
`experiments/results/annotation_heldout_v1b_*`.

Tests: `python -m pytest -q` (21 pass). Browser check: `python -m scripts.browser_check`.

## Addendum (2026-10-10): E6, ratchet ablation (`python -m experiments.ablation_ratchet` → `reports/ablation_ratchet.json`)
Same frames, market record and algorithm; only the day-high ratchet constraint is removed (price-only).
| Input | With ratchet | Price only |
|---|---|---|
| 4 full 20-min CNBC-TV18 recordings (1 frame / 10 s) | 3 IDENTIFIED (±15–30 s), 1 ABSTAIN | identical (no change) |
| Demo clip Bank Nifty 13:01 (110 s, 1 fps) | IDENTIFIED ±4 s | WEAK: 2 stretches, ±732 s |
| Demo clip 12:50 (7 chart frames) | WEAK, one day (6 Oct) | ABSTAIN: 3 candidate days |

Reading: with many frames spread over 20 minutes, price alone identifies the time; the ratchet is what makes short clips datable.

## Corrections (2026-10-10, after an external review of the Review-2 deck)
- **"Nifty50 24,616.6" (R28):**
  - The recorded NIFTY 50 at 15:16–15:19 on 30 Sep was 22,616.6, so the caption number differs from the record in a single digit.
  - It is most likely a caption/ASR error or a slip of the tongue. Earlier text calling it "a real misstatement" overstated what the record shows.
  - The contradiction of the *transcript* is correct.
- **Held-out first version (R30):**
  - "2 genuine" referred to claim type (blind label CURRENT_PRICE).
  - On inspection, 1 of the 37 FAILs was correct; the other current-price FAIL was R7 (an inequality checked as an equality).
- **E3 "unaltered → 0 false contradictions" (R29):**
  - This is circular: the base quotes were chosen among quotes already judged consistent.
  - It is a sanity check, not a false-alarm rate.
- **Index wording (R27):** an index level is recorded, not traded. Verdict text changed accordingly.
- **Data provenance:** the reference is NSE instruments' 1-minute bars from Yahoo Finance (vendor data), not NSE's own trade-by-trade record.
