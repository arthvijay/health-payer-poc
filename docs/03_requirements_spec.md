# 03 · Consolidated Requirements Spec (build checklist)

Distilled from corpus artifact B. ✅ = must be verifiable by `tests/verify_poc.py`.

## Data (`src/data_generator.py`, seed 42, deterministic)
- ✅ `market_mrf_warehouse.csv` ≥ 500 rows (~620): 5 peer hospitals × 4 payers (UHC, Aetna, Anthem BCBS, Cigna) × 26 CPTs, PPO + some HMO rows.
  Columns: `mrf_record_id, hospital_name, ein_npi, payer_name, plan_type, cpt_code, description, service_line, billing_class, medicare_rate, negotiated_rate, pct_of_medicare, mrf_schema_version, last_updated`.
  Negotiated rates 145%–330% of Medicare.
- ✅ `prospect_fee_schedule.csv` exactly 60 rows = 30 CPTs × {UHC, Aetna}; 52 matchable + 8 DNF.
  Columns: `prospect_row_id, payer_name, cpt_code, modifier, description, service_line, prospect_rate, annual_volume, contract_renewal_date`.
  Matched mix ≈ 60% under-market (critical/moderate), 25% competitive, 15% above.
- ✅ `openpayer_policies.json`: policy cards for 27447, 70553, 45380, 93458, 29827, 27446, 45385 × {UHC, Aetna}.

## DNF cases (fixed)
| CPT | Mod | Reason code | Proxy | Factor | Confidence |
|-----|-----|-------------|-------|--------|------------|
| 27446 | None | CODE_ABSENT_FROM_PAYER_MRF | 27447 | 0.82 (RVU ratio) | High — RVU Crosswalk |
| 70551 | 26 | MODIFIER_26_SPLIT_MISSING | 70553 | 0.38 (prof. split) | High — Modifier Split |
| 45385 | None | LOW_VOLUME_SUPPRESSED_IN_TIC | 45380 | 1.14 (complexity) | Medium — Complexity Crosswalk |
| 0408T | None | EMERGING_CAT_III_NO_MRF_RATE | 93458 | 1.20 (specialty index) | Medium — Specialty Index |

## Engine (`src/engine.py`, class `TrekValidationEngine`)
- In-memory DuckDB; `get_sql_query_preview()` returns the percentile SQL.
- ✅ `run_validation()` → 52 validated + 8 DNF, zero dropped.
- Validated metrics: `prospect_pct_medicare, market_p50_pct_medicare, unit_gap_to_p50/p75, raw_variance_pct, market_percentile_rank, variance_flag, current_annual_rev, annual_uplift_p50/p75, sample_mrf_citation`.
- Flags: CRITICAL ≤ −20% < MODERATE < −5% ≤ COMPETITIVE ≤ +5% < ABOVE.
- ✅ DNF resolver: proxy P50 from DuckDB × factor; recovery ≥ 0; reason, methodology, confidence, citation.
- Scenario simulator: target (P50 / P75 / custom %-of-Medicare floor), realization 10–100%, include DNF, subscription ($85K).
- ✅ Total addressable (P50 + DNF) between $1M and $10M (designed to land ~$2–3M).

## Excel (`src/excel_exporter.py`)
- ✅ Sheets exactly: `Executive_ROI_Business_Case`, `Fee_Schedule_Benchmark`, `Data_Not_Found_Resolution`.
- ✅ Exec C6:C9 assumptions (values), C12:C21 formulas. Benchmark J/K/L/O/P/Q formulas + totals row. DNF F/K/M formulas + totals row.
- ✅ (added) Recomputed workbook values == engine values.

## Agent (`skills/benchmark_analyst_skill.md`, `src/agent.py`)
- ✅ YAML frontmatter `name: trek-benchmark-validation-analyst`, v2.1.0, 4 tools, `citation_policy: strict_mrf_record_id`.
- ✅ `ask_benchmark_agent(query, validated_df, dnf_df, kpis, policies, api_key=None)` → `(markdown, metadata)`.
- ✅ Every preset answer contains both altitude headers, `[MRF-` citations, and CPT codes.
- Live mode when a key is present (Claude API); deterministic cited mode otherwise; live failures fall back to deterministic.

## UI (`app.py`, Streamlit)
- Sidebar: data source (built-in / upload + sample download), payer & service-line filters, target tier, realization slider, include-DNF, subscription, agent status + API key.
- HUD: 6 KPIs (addressable gap, realized uplift, % of Medicare prospect vs market, match rate, ROI multiple, payback).
- Tabs: 01 Market Intelligence · 02 DNF Workbench · 03 CFO ROI & Excel · 04 Ask Trek + OpenPayer + Skill Inspector · 05 Architecture & Talk Track.
- ✅ (added) Headless `AppTest` run with no exceptions.
