# Trek Health — Payer Performance, Fee Schedule Validation & AI ROI Engine (POC)

A small working version of a payer-performance Sales Engineer's validation motion, built as **clickable live slides** for a 5–10 minute
screen-share. It runs fully offline. All data is synthetic, and the peer hospitals are fictional.

```bash
./run_demo.sh          # first run installs deps; then: generate data → write DEMO_SCRIPT.md → run 33 checks → launch
# open http://localhost:8501
```

**Presenting:** read `DEMO_SCRIPT.md`. It has the interview flow, what to click and what to say on each slide, and curveball answers.
Its numbers are generated from the engine, and a test fails if they ever drift from what the screen shows.

## What's inside

| Path | What it does |
|------|--------------|
| `src/data_generator.py` | Deterministic (seed 42) TiC MRF warehouse (636 rows, 5 peers × 4 payers × 26 CPTs), 60-line prospect file (52 matchable + 8 DNF), simulated OpenPayer policy cards |
| `src/engine.py` | `TrekValidationEngine`: in-memory DuckDB percentiles, validation join, variance flags, percentile ranks + MRF citations (one SQL pass), DNF crosswalk resolver, scenario/KPI math, Pareto, sensitivity |
| `src/excel_exporter.py` | 3-tab CFO workbook. Every dollar output is a live Excel formula (354 formulas) |
| `src/formula_audit.py` | Independent evaluator that recomputes the workbook so the UI and tests can show the formulas produce the engine's numbers |
| `skills/benchmark_analyst_skill.md` | Agent skill file: YAML config + 4 rules (citations, two altitudes, DNF transparency, policy linkage) |
| `src/agent.py` | "Ask Trek": live Claude (`claude-opus-5-5`, server-side fallback) when an API key is given, otherwise a deterministic cited engine; live failures fall back automatically |
| `src/demo_script.py` | Single source for the slide titles and talk track; writes `DEMO_SCRIPT.md` |
| `app.py` | Streamlit UI: **🎞️ Live Slides** (9 slides, PageUp/PageDown or a clicker) and **🧰 Workbench** (5 tabs) |
| `tests/verify_poc.py` | 33 checks: schemas, determinism, 52/8 partition, DuckDB vs pandas percentiles, dollar math, citations resolve to real records, workbook recompute equals engine, CFO-edit recalculation, agent presets, script sync, headless UI on every slide |

## Slides (≈8–9 min; skip 2, 4 and 7 for a 5-minute version)

1. Hook: KPI strip · 2. The motion · 3. Market heatmap + %-of-Medicare scatter · 4. CPT deep-dive vs named peers + SQL ·
5. Data Not Found workbench + crosswalk sandbox · 6. CFO ROI levers, sensitivity, Pareto redline list ·
7. Live-formula Excel export · 8. Ask Trek agent + OpenPayer + skill inspector · 9. Architecture and close

## Offline guarantees
- No web fonts, CDNs, or telemetry (`browser.gatherUsageStats = false`); the server binds to `localhost` only.
- The agent defaults to offline deterministic mode. Live mode only runs if you paste an API key in the sidebar.

## Re-run checks only
```bash
.venv/bin/python tests/verify_poc.py
```
