# UI audit: heuristic, NOT a user study
No user-testing participants were available. This is an **explicitly labelled heuristic audit**:
- **Method:** the 10 "no-third-person" questions, answered by inspecting the real rendered screens in `assets/screenshots/`. The screens were
  captured by `scripts/browser_check.py` from the running app at 1366×900 and 390×844.
- **Heuristics:** Nielsen's usability heuristics.
- **No participants or scores are invented.**

| # | Question a first-time visitor must be able to answer | Where the screen answers it | Status |
|---|---|---|---|
| 1 | What does this application do? | Landing H1 + subheading + "What we check" A/B/C | answered |
| 2 | What video is being analysed? | Result header: title, channel, recorded time (IST), source capture; tag "Real broadcast recording" or "Synthetic test claims" | answered |
| 3 | Which claim is being examined? | Claim page: section title by type ("Current price: claim vs market record") + quoted words + video time ("Play this moment") | answered |
| 4 | What evidence supports or contradicts it? | "Claim vs market record" table; "Evidence" (decisive minutes, ranges, volume, source); chart with tolerance band and time window | answered (after fixes R19/R20) |
| 5 | What does the final verdict mean? | "What this means" box under every table; verdict badge with fixed vocabulary | answered |
| 6 | How certain is the result? | the tolerance and its reason; % of minutes with data; clock ±s and delay assumptions; speech-recognition confidence of the number | partially: certainty is shown as assumptions and coverage, not as a single probability (by design; no calibrated probability exists) |
| 7 | What information is missing? | "What we cannot establish" and "What would be needed…" on every claim; the overview footer; the audit's "Missing evidence" | answered |
| 8 | Can the application prove the presenter executed the trade? | landing limits box; every personal-trade claim shows "Claimed execution not independently verified"; footer | answered (no) |
| 9 | Which market records were used? | evidence table "Source"; audit: files + sha256, granularity "1-minute bars (NOT trade-by-trade)", provider | answered |
| 10 | What should the viewer do with the result? | "What would be needed for stronger verification" (broker contract note, official statistics); "Not enough evidence is common and honest" | partially: no explicit "next step for a viewer" sentence beyond verification needs |

## Heuristic findings (from screenshots) and status
- **Fixed:**
  - "contains 22,700" wording for a bar at 22,708–22,713;
  - the chart had no tolerance band;
  - claim times shown in recording time rather than clip time;
  - transcript auto-scroll moved the whole page;
  - the empty ticker lane was unexplained;
  - an orange focus ring around the main area;
  - real samples now listed before synthetic;
  - the synthetic card's blank thumbnail;
  - the "recommendation/forecast" text shown for an unclear number;
  - index volume shown as 0;
  - the quantity case headlined "Consistent".
- **Accessibility:** semantic headings, verdict text in badges (not colour alone), `aria-label` on timeline markers, keyboard-focusable markers and
  transcript lines, `prefers-reduced-motion` respected, light and dark themes.
- **Open:**
  - "Volume" and "points" may still need a one-line glossary for complete novices;
  - the timeline track is dense on 4-minute clips with many speech markers;
  - question 10 deserves an explicit "what to do" line.
