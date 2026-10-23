# 01 · Corpus Analysis — What the pasted material actually is

Source: a Gemini conversation ("Trek Health POC Prompt", 2026-10-22) pasted by the user.
It contains three successive artifacts, each superseding the last:

| # | Artifact | Status |
|---|----------|--------|
| A | First "master prompt" — Validation + ROI Engine (Streamlit, DuckDB, openpyxl, agent, tests) | **Superseded** by B |
| B | Expanded "dossier prompt" — adds OpenPayer policy cross-check, CMA simulator, 6-KPI HUD, architecture tab, DNF sandbox, Pareto redline list | **Source of truth for the build** |
| C | Interview script + 4-minute demo script + curveball answers | Source for `DEMO_SCRIPT.md` (numbers re-derived from real engine output) |

## The situation (plain English)

- The user is interviewing for a **Sales Engineer (SE)** role at **Trek Health**, which positions itself as
  "the AI platform for payer performance" — helping hospitals see whether commercial insurers (payers)
  pay them fairly versus the market.
- Since 2022 the US **Transparency in Coverage (TiC)** rule forces insurers to publish every negotiated rate
  in huge **Machine-Readable Files (MRFs)**. Trek normalizes that into a warehouse.
- An SE's core pre-sales job: take a prospect hospital's **fee schedule** (what they're paid per CPT code per payer),
  **validate** it against the warehouse, handle codes that don't match ("**Data Not Found**", DNF),
  and hand the CFO a credible **ROI model** (usually Excel/Sheets).
- The POC is a miniature of exactly that motion, plus an **AI agent** driven by a **skill file**, because
  (per the corpus) the posting mentions configuring agents and authoring skill files.

## What the demo must prove (mapped to the 4 duties the corpus attributes to the job posting)

1. **Build a POC** → the whole app.
2. **Data validation** against a TiC warehouse, incl. DNF handling → Tabs 1–2.
3. **Excel/Sheets ROI model** with auditable live formulas → Tab 3 + `.xlsx`.
4. **Configure AI agents / author skill files** → Tab 4 + `skills/benchmark_analyst_skill.md`.

## Claims in the corpus I could NOT verify (treat as Gemini's assertions)

- That Trek's job posting literally names these four duties, uses the term "Data Not Found", or that
  "OpenPayer" is a Trek product. The `[cite: 1]` markers point to a dossier we don't have.
- Personal background lines in the interview script ("engineering and AI background at Duke", "MEng",
  "Open Dental API" project). **The user must confirm these are true before saying them.**
- All dollar figures in artifact C ($2.42M, $1.21M, $310K, 168% vs 224%, 25 days, 72%) were invented
  before any code existed. **They are replaced by numbers computed from the actual engine** — see
  `trek-validation-poc/DEMO_SCRIPT.md`, which is generated and test-checked.

## Deliberate deviations from the corpus spec (and why)

| Corpus says | Built as | Reason |
|-------------|----------|--------|
| Peer hospitals: Bon Secours, TriHealth, UHS, Covenant, CHRISTUS (real systems) | Fictional peers (one constant: `PEER_HOSPITALS` in `src/data_generator.py`) | Attributing invented negotiated rates to real, named hospitals in front of a price-transparency company is a credibility risk. Swap back in one line if desired. |
| `claude-3-7-sonnet-latest` / `claude-3-5-sonnet-latest` | `claude-opus-5-5` with server-side `fallbacks: "default"` | The named models are retired; current default model with automatic fallback. |
| Hardcoded demo-script numbers | `DEMO_SCRIPT.md` generated from engine output; test asserts they match | A demo that quotes numbers the screen doesn't show is fatal. |
| Fixed Excel ranges `K2:K53` | Ranges computed from row count (= `K2:K53` for the default file) | Custom-uploaded schedules have different row counts. |
| "Formulas verified by openpyxl" (only checks `=` prefix) | Also a mini formula evaluator in tests that recomputes the workbook and asserts it equals the engine's numbers | Proves the formulas are *right*, not just present. |
