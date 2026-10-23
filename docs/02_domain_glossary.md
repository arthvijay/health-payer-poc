# 02 · Domain Glossary (read this if healthcare pricing is new to you)

| Term | Meaning | Where it shows up in the demo |
|------|---------|-------------------------------|
| **Payer** | The insurer that pays the hospital (UnitedHealthcare, Aetna, Cigna, Anthem BCBS). | Payer filter, every table |
| **Provider / Health system** | The hospital. Trek's customer. "Summit Regional Health" is our synthetic prospect. | Prospect file |
| **CPT code** | 5-character code for a procedure (27447 = total knee replacement). Category III codes end in "T" (0408T) = emerging tech, often unpriced. | Everywhere |
| **Modifier** | 2-char suffix changing meaning. **-26 = professional component** (the radiologist's read only, not the machine/facility part). | DNF row 70551-26 |
| **Fee schedule** | The hospital's list of contracted rates per CPT per payer. The input file. | `prospect_fee_schedule.csv` |
| **Negotiated rate** | The dollar amount a payer agreed to pay a specific hospital for a code. | Warehouse `negotiated_rate` |
| **Transparency in Coverage (TiC)** | 2022 federal rule: insurers must publish all negotiated rates monthly. | Warehouse concept |
| **MRF (Machine-Readable File)** | The giant JSON files TiC produces (often multi-GB). Trek normalizes them. | `market_mrf_warehouse.csv` is a trimmed synthetic slice |
| **Medicare rate** | What Medicare pays. The universal yardstick. | `medicare_rate` |
| **% of Medicare** | Commercial rate ÷ Medicare rate. "We're at 168% of Medicare, market is 224%" is how managed-care people talk. | KPI HUD, scatter plot |
| **P50 / P75 / P90** | Median / 75th / 90th percentile of peer rates. P50 = "market rate"; P75 = aggressive target. | Benchmarks |
| **Percentile rank** | Where the prospect's rate sits among peers (0 = lowest). | Benchmark grid |
| **CMA (Competitive Market Analysis)** | Comparing your rates to competitors' to set negotiation targets. | Tab 1 / Tab 3 simulator |
| **DNF (Data Not Found)** | A fee-schedule line with no direct match in the warehouse. Mishandling these kills prospect trust. | Tab 2 |
| **Crosswalk / proxy** | Estimating a missing code's market rate from a related code that *is* in the warehouse, times a justified factor. | DNF resolver |
| **RVU (Relative Value Unit)** | CMS's measure of relative work/cost of a procedure. Ratio of RVUs between two codes justifies a proxy factor (27446 ≈ 0.82× 27447). | DNF 27446 |
| **Professional/technical split** | Global rate = professional (-26) + technical (-TC). ~38% professional is a typical imaging split. | DNF 70551-26 |
| **Low cell-size suppression** | Rates with too few claims may be withheld/unreliable in published data. | DNF 45385 |
| **Managed care / payer contracting team** | The hospital people who negotiate with payers. Our end users. | Persona |
| **Realization factor** | Share of the identified gap the hospital actually wins in negotiation (50% default = conservative). | ROI levers |
| **Payback period** | Months of realized uplift needed to cover the Trek subscription. | KPI HUD, Excel |
| **Prior authorization (PA)** | Payer must approve before the procedure; missing it → denial. | OpenPayer policy cards |
| **CARC denial codes** | Standard denial reasons: CO-197 (no precert), CO-50 (not medically necessary), CO-4 (modifier issue), CO-16 (missing info). | Policy cards |
| **Redline** | The specific contract changes you ask for in negotiation. | Pareto "redline list" |
| **SE (Sales Engineer)** | Technical pre-sales: discovery → validation → build → adoption. The role being interviewed for. | — |
