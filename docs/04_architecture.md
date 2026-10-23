# 04 · Architecture & How Each Part Shows Up in the Demo

```
 LAYER 1  DATA                     src/data_generator.py  (seed 42)
          market_mrf_warehouse.csv · prospect_fee_schedule.csv · openpayer_policies.json
                                   │
 LAYER 2  ENGINE                   src/engine.py · TrekValidationEngine
          DuckDB in-memory  ──► cohort percentiles (P25/P50/P75/P90) per CPT×Payer
          prospect LEFT JOIN cohort ──► validated_df (52)  |  dnf_df (8)
          DNF resolver: proxy CPT P50 (DuckDB) × factor ──► recovery $
          Scenario simulator: target tier × realization × DNF toggle × fee ──► KPIs
                    │                                   │
 LAYER 3A EXCEL      src/excel_exporter.py     LAYER 3B AGENT   src/agent.py + skills/*.md
          3 tabs, every $ output a formula              skill file → system prompt
                                                        live Claude  |  deterministic cited router
                    └──────────────┬────────────────────┘
 LAYER 4  UI                       app.py (Streamlit + Plotly), 5 tabs + HUD
```

## Data flow for one sidebar change
1. Sidebar lever changes → Streamlit reruns.
2. Engine is cached (`st.cache_resource`); validation result cached per input file hash.
3. `simulate_negotiation_scenario()` recomputes KPIs on the filtered frame (pure pandas, ms).
4. HUD, charts, sensitivity matrix, Excel bytes and agent context all read the same result → one source of truth.

## Component ↔ UI ↔ talking point
| Component | UI location | What you say it proves |
|-----------|-------------|------------------------|
| `data_generator` | Sidebar "Download sample CSV"; Tab 5 telemetry | Self-contained, reproducible; real MRFs are GB-scale |
| DuckDB aggregation SQL | Tab 1 expander "View underlying SQL" | No black box; analyst can audit percentile math |
| Validation join + flags | HUD, Tab 1 heatmap / scatter / grid | Where money is left on the table |
| CPT deep-dive | Tab 1 box plot | Prospect vs each named peer for one code |
| DNF resolver | Tab 2 table + multiplier sandbox | Trust: nothing silently dropped, assumptions adjustable |
| Scenario simulator | Sidebar levers, Tab 3 sensitivity matrix | CFO-grade, conservative-by-default math |
| Pareto redline | Tab 3 | A surgical negotiation ask |
| Excel exporter | Tab 3 download + formula preview | Auditable live formulas |
| Skill file + agent | Tab 4 presets, chat, skill inspector | Agent config + skill authoring, cited answers |
| OpenPayer JSON | Tab 4 policy explorer, preset 3 | Rates + policy = "payer performance" |
| Architecture/talk track | Tab 5 | Technical transparency, demo control |

## Key design choices
- **DuckDB** — in-process vectorized SQL, zero infra, ms latency on the slice.
- **Agent dual mode** — the demo cannot fail offline; live mode uses the identical skill file and data context.
- **Generated DEMO_SCRIPT.md** — numbers quoted aloud always equal numbers on screen.
