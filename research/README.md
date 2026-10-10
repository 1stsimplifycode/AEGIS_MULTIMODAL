# Research notes for this project
- The scientific write-up is `../reports/RESEARCH_REPORT.md` (problem, prior work, formulation, contribution, results, ablations, limits).
- Upstream AEGIS-Market research reused as infrastructure (read-only, not modified):
  - tape-consistency dating;
  - capture-clock validation (`research_hipc_2026/.../validation.json`);
  - the frozen OCR symbol resolver (`research/icsc2027/src/symbol_resolve.py`);
  - truth-deleted reference findings (`research/benchmark_tdr/`), which motivated treating missing or uncertain evidence as an explicit
    assumption.
- Held-out evaluation artefacts: `../experiments/results/` (frozen v1 outputs, blind labels, confusion tables).
