# Capstone Review 2: demonstration script (desktop; about 7 minutes)

Start `uvicorn backend.app:app --port 8000` and open http://localhost:8000 in a desktop browser. The PPT
`demo/Capstone_Review2_DidThatTradeReallyHappen.pptx` has a speaking script in the notes of every slide.

| Step | Click | What the audience sees (real data unless marked synthetic) |
|---|---|---|
| 1 | Landing | The architecture diagram, the three checks, PASS/FAIL/ABSTAIN meanings, limits |
| 2 | **"Bank Nifty 'now at 55,150'…"** → *Start investigation* | Nine real stages light up in the diagram. OCR/ASR were run earlier (time shown); the rest runs live |
| 3 | Investigation flow → **Visual frame encoder** | Frames with the chart panel read out: price, day-high label (ratchet), previous close, on-screen clock. "Only 2026-10-06 fits, ±4 s, no clock used"; independent check: the channel shows market data ~24 s late |
| 4 | **Visual text encoder** | "No trading panel, fill quantity or P&L found" (honest); on-screen clock 13:02–13:04 |
| 5 | **Claim set** | Who / what / kind / market time with its source (chart ratchets ±4 s) |
| 6 | **Knowability** → *Trace →* | Certificate item → claim → the spoken words + the video frame (NIFTY 50 22,699.35 on screen as the anchor says 22,700) → the market minute 22,693–22,706 → PASS |
| 7 | **Fill conservation** | ABSTAIN with the reason: no executed-quantity claim in a news broadcast |
| 8 | **Data age** | Facts (data 0 days old, use date from our own capture) → ABSTAIN: the rule applies to people solely in education, which a video cannot establish |
| 9 | **Impossibility certificate** tab → download HTML | Certificate ID, meanings, items, assumptions, data hashes, steps to reproduce |
| 10 | Back → **"Made-up 'I bought…' claims (SYNTHETIC)"** → Fill conservation | s1 PASS · s2 FAIL (price) · s3 FAIL (50 lakh shares > 651 traded; assumes NSE) · s4 FAIL (holiday) · s7 ABSTAIN (after hours) |
| 11 | **Check a claim yourself** → "Huge quantity" | The same check on a typed claim, live |
| 12 | Optional: the **12:50 sample** | Visual frame encoder says WEAK (only 7 chart frames, ±33 min) and the claim set shows "capture clock (labelled)" - the explicit-limitation path |
