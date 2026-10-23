"""Single source of truth for the slide deck and the spoken talk track.

The app renders SLIDES as live slides (speaker notes filled with live numbers);
`python -m src.demo_script` writes DEMO_SCRIPT.md from the default scenario, so
every number you say out loud is a number the screen shows.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.engine import TARGET_P50, compute_kpis, pareto_table

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "DEMO_SCRIPT.md"


def _usd(x: float) -> str:
    return f"${x:,.0f}"


def _usd_short(x: float) -> str:
    if abs(x) >= 1_000_000:
        return f"${x / 1_000_000:.2f}M"
    if abs(x) >= 1_000:
        return f"${x / 1_000:.0f}K"
    return f"${x:,.0f}"


def _payer(p: str) -> str:
    return "UHC" if p.startswith("UnitedHealthcare") else p


def build_facts(validated_df: pd.DataFrame, dnf_df: pd.DataFrame, kpis: dict, policies: dict,
                warehouse_rows: int, peer_count: int) -> dict:
    """Every number the talk track quotes, computed from live state."""
    from src.agent import policy_risk_table

    v, d, k = validated_df, dnf_df, kpis
    f: dict[str, str] = {
        "total_lines": str(k["total_lines"]),
        "matched": str(k["matched_lines"]),
        "dnf_n": str(k["dnf_lines"]),
        "dnf_codes": str(d["cpt_code"].nunique()) if len(d) else "0",
        "match_rate": f"{k['match_rate_pct']:.1f}%",
        "coverage": f"{k['coverage_with_dnf_pct']:.0f}%",
        "addressable": _usd_short(k["total_addressable"]),
        "realized": _usd_short(k["realized_uplift"]),
        "realization": f"{k['realization_rate']:.0%}",
        "subscription": _usd_short(k["annual_trek_subscription"]),
        "roi": f"{k['roi_multiple']:.1f}x",
        "payback_months": f"{k['payback_months']:.1f}",
        "payback_days": f"{k['payback_months'] * 30.4:.0f}",
        "three_year": _usd_short(k["three_year_net_value"]),
        "prospect_pct": f"{k['prospect_pct_medicare']:.0f}%",
        "market_pct": f"{k['market_pct_medicare']:.0f}%",
        "pct_gap_pts": f"{k['market_pct_medicare'] - k['prospect_pct_medicare']:.0f}",
        "n_critical": str(k["flag_counts"].get("CRITICAL_UNDER_MARKET", 0)),
        "n_moderate": str(k["flag_counts"].get("MODERATE_UNDER_MARKET", 0)),
        "n_above": str(k["flag_counts"].get("ABOVE_MARKET", 0)),
        "dnf_recovery": _usd_short(k["dnf_recovery"]),
        "warehouse_rows": f"{warehouse_rows:,}",
        "peer_count": str(peer_count),
    }
    if len(v):
        lead = v.sort_values("annual_uplift_p50", ascending=False).iloc[0]
        f.update(lead_cpt=lead["cpt_code"], lead_desc=lead["description"], lead_payer=_payer(lead["payer_name"]),
                 lead_prospect_pct=f"{lead['prospect_pct_medicare']:.0f}%",
                 lead_market_pct=f"{lead['market_p50_pct_medicare']:.0f}%",
                 lead_gap=_usd_short(lead["annual_uplift_p50"]))
        knee = v[(v["cpt_code"] == "27447") & (v["payer_name"].str.startswith("UnitedHealthcare"))]
        if len(knee):
            r = knee.iloc[0]
            f.update(knee_prospect_pct=f"{r['prospect_pct_medicare']:.0f}%", knee_market_pct=f"{r['market_p50_pct_medicare']:.0f}%",
                     knee_gap=_usd_short(r["annual_uplift_p50"]),
                     knee_pctile=("below every published peer rate" if r["market_percentile_rank"] == 0
                                  else f"at the {r['market_percentile_rank']:.0f}th percentile of peers"),
                     knee_cite=r["sample_mrf_citation"])
        par = pareto_table(v, v["annual_uplift_p50"])
        if len(par):
            n70 = int((par["cumulative_share_pct"] < 70).sum()) + 1
            n70 = min(n70, len(par))
            f.update(pareto_n=str(n70), pareto_share=f"{par['cumulative_share_pct'].iloc[n70 - 1]:.0f}%",
                     pareto_total_codes=str(len(par)))
    if len(d):
        for cpt in ("27446", "70551"):
            row = d[d["cpt_code"] == cpt]
            if len(row) and pd.notna(row.iloc[0]["adjustment_factor"]):
                f[f"factor_{cpt}"] = f"{row.iloc[0]['adjustment_factor']:.2f}"
    # same scope as the agent's OpenPayer preset (Orthopedics + GI)
    risk = policy_risk_table(v, d, policies)
    risk = risk[risk["service_line"].isin(["Orthopedics", "Gastroenterology"])]
    dbl = risk[risk["double_exposure"]]
    f["double_n"] = str(len(dbl))
    if len(dbl):
        top = dbl.iloc[0]
        f.update(double_cpt=top["cpt_code"], double_payer=_payer(top["payer_name"]),
                 double_variance=f"{abs(top['variance_pct']):.0f}%", double_denial=top["common_denial_code"])
    defaults = {"lead_cpt": "—", "lead_desc": "—", "lead_payer": "—", "lead_prospect_pct": "—", "lead_market_pct": "—",
                "lead_gap": "—", "knee_prospect_pct": "—", "knee_market_pct": "—", "knee_gap": "—", "knee_pctile": "—",
                "knee_cite": "—", "pareto_n": "—", "pareto_share": "—", "pareto_total_codes": "—",
                "factor_27446": "0.82", "factor_70551": "0.38", "double_cpt": "—", "double_payer": "—",
                "double_variance": "—", "double_denial": "—"}
    for key, val in defaults.items():
        f.setdefault(key, val)
    return f


# Each slide: id, nav label, title, takeaway (one line on screen), duration, DO (actions), SAY (talk track).
SLIDES = [
    {
        "id": "hook", "nav": "1 · Hook", "minutes": "0:00–0:45",
        "title": "Where is Summit Regional leaving money on the table — and can we prove it?",
        "takeaway": "{total_lines} fee-schedule lines in · {addressable}/yr addressable gap · {roi} first-year ROI at {realization} capture",
        "do": ["Share this browser tab only (full screen, zoom 110%).",
               "Point at the six KPI tiles left to right. Do not click anything yet."],
        "say": [
            "Here's a miniature of the pre-sales validation motion your team runs. Our prospect is a synthetic "
            "hospital, Summit Regional Health. They've sent {total_lines} lines of their fee schedule for UnitedHealthcare and Aetna, "
            "and their VP of Managed Care is asking two things: where are we underpaid, and can you prove your data is right?",
            "Top line: {matched} lines matched the TiC warehouse directly. The other {dnf_n} went into a Data Not Found queue, "
            "and I resolved those rather than dropping them. Against the market median there's {addressable} a year in "
            "addressable rate gap. If their contracting team only wins {realization} of it, that's {realized} a year, "
            "so the {subscription} platform fee pays back in about {payback_days} days.",
        ],
    },
    {
        "id": "motion", "nav": "2 · Motion", "minutes": "0:45–1:30",
        "title": "The SE validation motion — in code",
        "takeaway": "Ingest → Benchmark → Resolve DNF → Model ROI → Arm the buyer. Every step is live in this app.",
        "do": ["Walk the five boxes left to right with the cursor.",
               "Point to the data panel: warehouse rows, peers, payers."],
        "say": [
            "Transparency in Coverage made the rates public, but the files are huge and messy, and nobody can use them without "
            "an interpretation layer. That's the gap your platform fills, and the SE sits right on top of it.",
            "This app runs the five steps of that motion: ingest the prospect file, benchmark against {warehouse_rows} normalized MRF "
            "rates from {peer_count} regional peers, resolve the Data Not Found lines, model ROI in a spreadsheet the CFO can audit, "
            "and arm both buyers with an AI agent that cites its sources. It's all synthetic data and it runs offline, "
            "so nothing here is real pricing.",
        ],
    },
    {
        "id": "market", "nav": "3 · Market", "minutes": "1:30–2:30",
        "title": "Market intelligence: where the underpayment concentrates",
        "takeaway": "Portfolio at {prospect_pct} of Medicare vs. market {market_pct} (−{pct_gap_pts} pts) · {n_critical} lines critically under market",
        "do": ["Hover the darkest heatmap cell.",
               "On the scatter, hover the biggest red bubble below the parity line."],
        "say": [
            "Here's the macro picture. The heatmap shows where the dollars are, by service line and payer. On the scatter, "
            "every bubble is a code, sized by Summit's volume. Anything below the diagonal is paid under market, and the red "
            "ones are more than 20% under.",
            "Volume-weighted, Summit is at {prospect_pct} of Medicare against a market median of {market_pct}. That's "
            "{pct_gap_pts} points, which is the number a managed-care VP actually thinks in.",
        ],
    },
    {
        "id": "deepdive", "nav": "4 · Deep-Dive", "minutes": "2:30–3:15",
        "title": "Prove it: one code against every named peer",
        "takeaway": "27447 Total Knee · UHC: Summit {knee_prospect_pct} of Medicare vs. peer median {knee_market_pct} · {knee_gap}/yr",
        "do": ["Leave 27447 selected. Hover the Summit diamond, then a peer dot.",
               "Open 'View the DuckDB SQL' for two seconds, then close it."],
        "say": [
            "This is where trust gets built. Take total knee replacement with UHC: Summit is at {knee_prospect_pct} of Medicare, "
            "and the peer median is {knee_market_pct}. That puts them {knee_pctile}, which is "
            "worth {knee_gap} a year on that one line.",
            "And it's not a black box. Every dot is a cited MRF record, and here's the exact DuckDB SQL behind the percentiles. "
            "If their analyst wants to audit the math, they can.",
        ],
    },
    {
        "id": "dnf", "nav": "5 · DNF", "minutes": "3:15–4:30",
        "title": "Data Not Found: the make-or-break step",
        "takeaway": "{dnf_n} unmatched lines · {dnf_codes} root causes · 0 dropped · {dnf_recovery}/yr recovered with documented crosswalks",
        "do": ["Point at the reason codes column.",
               "In the sandbox pick 27446 and drag the multiplier down to 0.70, then back up. Watch the recovery change."],
        "say": [
            "This is the moment that makes or breaks a hospital validation. Some lines never match a payer's public file. "
            "If you quietly drop them, the analyst notices, and you've lost the deal's credibility.",
            "So every unmatched line gets a reason code and a crosswalk you can defend. Partial knee, 27446, isn't in the payer "
            "file, so it's proxied off total knee at the CMS RVU ratio of {factor_27446}. The MRI read with modifier 26 only exists "
            "as a global rate in the file, so I applied a {factor_70551} professional split. That brings back {dnf_recovery} a year "
            "that a match-only analysis would have thrown away. And if their analyst thinks I'm being aggressive, they can "
            "drag the multiplier and watch the number change live.",
        ],
    },
    {
        "id": "roi", "nav": "6 · ROI", "minutes": "4:30–5:30",
        "title": "The CFO business case: conservative by default",
        "takeaway": "{realized}/yr realized at {realization} capture · {roi} ROI · {payback_months}-month payback · top {pareto_n} codes = {pareto_share} of the gap",
        "do": ["Drag Realization from 50% down to 25%. Let the HUD and matrix recalculate.",
               "Point at the Pareto chart's highlighted bars."],
        "say": [
            "A CFO won't sign off on 100% capture, so the default is 50%, and I'll drag it down to 25% right now. "
            "Even at that level the platform pays for itself many times over. The sensitivity matrix shows median, "
            "75th percentile, and a percent-of-Medicare floor next to each other.",
            "Just as important is the ask. Renegotiating just {pareto_n} codes captures {pareto_share} of the gap. "
            "That gives their payer negotiator a short, specific redline list instead of a 60-line spreadsheet.",
        ],
    },
    {
        "id": "excel", "nav": "7 · Excel", "minutes": "5:30–6:15",
        "title": "Auditable Excel model: live formulas, not pasted numbers",
        "takeaway": "3 tabs · every $ output is a formula · change one yellow cell and the whole case recalculates",
        "do": ["Click Download. Optionally open it in Excel or Sheets and change C7 from 50% to 25%.",
               "Otherwise point at the formula-vs-value preview table."],
        "say": [
            "Hospitals don't sign off on a dashboard screenshot. The CFO needs a model to take to their finance committee. "
            "This exports a three-tab workbook in which every dollar figure is a live Excel formula.",
            "If the CFO changes the realization assumption in the yellow cell, the net benefit, payback, and three-year value "
            "all recalculate. My test suite independently recomputes every formula and checks the result against the engine, "
            "to the cent.",
        ],
    },
    {
        "id": "agent", "nav": "8 · Agent", "minutes": "6:15–7:30",
        "title": "'Ask Trek': an agent governed by a skill file",
        "takeaway": "Skill file → system prompt · every claim cites an MRF record · two altitudes: analyst note + CFO mandate",
        "do": ["Click '🛡️ OpenPayer Policy + Rate Risk'.",
               "Scroll to 'Double exposure', then open the Skill File Inspector for five seconds."],
        "say": [
            "On agents and skill files: I wrote the skill file that governs this agent. It has four rules. Cite an MRF "
            "record for every rate claim. Answer at two altitudes, an analyst note and a CFO mandate. Never hide a "
            "Data Not Found line. And link rates to payer policy.",
            "Watch this policy cross-check. It flags {double_n} code and payer pairs that are hit twice. For example, CPT "
            "{double_cpt} with {double_payer} is {double_variance} under market, and it also carries a prior-auth policy "
            "with {double_denial} denials. That takes the conversation past rate benchmarking to payer performance: rates, "
            "policy, and recovery in one strategy. It runs offline in a deterministic, cited mode, and the same skill file "
            "drives a live Claude call when there's an API key.",
        ],
    },
    {
        "id": "close", "nav": "9 · Close", "minutes": "7:30–8:30",
        "title": "How it's built, and how I'd run this on day one",
        "takeaway": "DuckDB · pandas · openpyxl · Streamlit · Claude · tests verify data, math, formulas, agent and UI",
        "do": ["Point at the four layers once.", "Stop sharing and look at the camera for the close."],
        "say": [
            "Four layers: deterministic data, a DuckDB engine, Excel and agent outputs that both read from that one engine, "
            "and this UI. An automated suite checks the partition, the dollar math, every Excel formula, the agent's "
            "citations, and the UI itself.",
            "That's the whole pre-sales motion in code: validate transparently, resolve Data Not Found lines instead of "
            "hiding them, hand the CFO an auditable model, and use agents to turn intelligence into leverage. That's how "
            "I'd run technical evaluations from day one. How does your team handle Data Not Found lines in live deals today?",
        ],
    },
]


INTERVIEW_SECTION = """\
## Part 1 — Interview flow (before and after the demo)

> ⚠️ **Check every personal claim below before you say it.** These lines came from the Gemini draft.
> Replace anything that isn't exactly true for you (school, degree, past projects).

### 1. "Tell me about yourself / Why us?" (≈60 sec)
- **Do:** Look at the camera, slow down, and move to *their* business within 20 seconds.
- **Say:** "My background is engineering and AI *[verify: Duke MEng]*. What drew me here is that this isn't really
  a software-demo job, it's a data-validation job. Hospitals negotiate payer contracts with almost no visibility.
  Transparency in Coverage made the data public, but it's huge and messy and unusable without an interpretation
  layer. The SE sits right where that friction is: taking a prospect's messy fee schedule, proving it against the
  warehouse, and giving their CFO an ROI case they can't argue with. So rather than just talk through the job
  description, I built a small working version of that validation motion. Could I take five or six minutes to walk you through it?"

### 2. "You don't have enterprise SE experience" (≈45 sec)
- **Do:** Answer with the deal framework: Discovery → Validation → Build → Adoption.
- **Say:** "To me, pre-sales is consultative problem-solving backed by technical proof. On *[verify: my Open Dental
  API project]* it was the same motion: find the clinic's real bottleneck, check that a messy third-party schema
  could actually support the workflow, build the layer, then drive adoption. Add the agent and skill-file work I've done,
  and I can sit with a hospital data analyst on code mappings at 10:00 and walk the CFO through payback at 10:30."

### 3. Location (≈15 sec)
- **Say:** "Yes. I'm ready to relocate and to travel to customer sites and conferences. Early on, sitting with the
  founding and engineering team is where an SE adds the most speed." *[verify]*

### 4. Transition into the demo
- **Say:** "Let me share one browser tab." → open the app in **Live Slides** mode at slide 1.

### Curveballs
- **"A consulting firm or another pricing tool already gave them a study. Why us?"**
  "A consulting study is a static PDF that's stale the day it arrives, and a raw transparency tool gives you numbers
  with no context. A platform that refreshes from payer MRFs and ties the contracted rate to payer policy and revenue
  recovery gives managed care a workflow for every renewal, not a one-off benchmark."
- **"Why DuckDB instead of Snowflake or Postgres?"**
  "For an SE validation loop, DuckDB is in-process, vectorized SQL over CSV and Parquet with no infrastructure. Percentiles
  over hundreds of thousands of MRF rows come back in milliseconds, so I can iterate live in front of the client.
  In production the same semantic layer would sit on your cloud warehouse."
- **"Will the Excel break in Google Sheets?"**
  "No. It's plain OpenXML formulas: SUM, AVERAGE, IF, and cross-sheet references. No macros and no dynamic arrays.
  The test suite parses the workbook and recomputes every formula against the engine."
- **"Is this real data?"**
  "No. It's all synthetic and generated deterministically, with fictional hospitals and simulated policy cards.
  It's shaped like real contracting, 145 to 330 percent of Medicare, but on purpose it isn't anyone's actual pricing."
- **"How would the DNF crosswalks hold up with a real analyst?"**
  "Every factor has a stated basis and a confidence tier, it's editable live, and it's a yellow input cell in the
  workbook. I'd rather start conservative and let the analyst push the factor up than the other way around."
"""


def render_markdown(facts: dict) -> str:
    out = [
        "# Trek Health POC — Interview & Live-Slides Demo Script",
        "",
        "_Generated by `python -m src.demo_script` from the default scenario (Market P50, "
        f"{facts['realization']} realization, {facts['subscription']} platform fee, all payers and service lines). "
        "The numbers match what the app shows on first load. Regenerate this file after changing the data._",
        "",
        "**Total runtime: ~8–9 min** (9 slides). Keep it to 5 min by skipping slides 2, 4 and 7.",
        "",
        "## Pre-flight (5 minutes before)",
        "1. `cd trek-validation-poc && ./run_demo.sh` and the browser opens at http://localhost:8501.",
        "2. Turn Wi-Fi off once to confirm it runs offline, then back on for the call.",
        "3. Mode = **🎞️ Live Slides**, slide 1. Collapse the sidebar (`<` arrow). Browser zoom 110%.",
        "4. Keep this script on a second screen, or turn on **Presenter notes** in the sidebar (they then show on the shared screen too).",
        "5. Optional: have the exported `.xlsx` already open in Excel or Google Sheets in another window.",
        "",
        INTERVIEW_SECTION,
        "",
        "## Part 2 — Live-slides demo: what to click, what to say",
        "",
    ]
    for s in SLIDES:
        out.append(f"### Slide {s['nav']} ({s['minutes']}) — {s['title']}")
        out.append(f"**On screen:** {s['takeaway'].format(**facts)}")
        out.append("")
        out.append("**Do:**")
        out += [f"- {a}" for a in s["do"]]
        out.append("")
        out.append("**Say:**")
        out += [f"> {p.format(**facts)}" for p in s["say"]]
        out.append("")
    out += [
        "## Part 3 — If they want to drive",
        "- Switch the sidebar to **🧰 Workbench** for all five tabs at once.",
        "- **Upload test:** sidebar → *Download sample CSV*, edit a rate, upload it, and everything recalculates.",
        "- **Free-form agent questions that work offline:** \"Tell me about 27447\", \"Compare UHC vs Aetna in Radiology\", "
        "\"Top 8 renegotiation targets\", \"Explain 0408T\".",
        "",
    ]
    return "\n".join(out)


def default_facts() -> dict:
    from src.engine import TrekValidationEngine

    eng = TrekValidationEngine()
    res = eng.run_validation(eng.default_prospect())
    kpis = compute_kpis(res.validated_df, res.dnf_df, TARGET_P50, 0.5, True, 85_000.0, total_lines=res.total_lines)
    return build_facts(res.validated_df, res.dnf_df, kpis, eng.policies, eng.warehouse_row_count(),
                       eng.mrf_df["hospital_name"].nunique())


def write_script(path: Path = SCRIPT_PATH) -> Path:
    path.write_text(render_markdown(default_facts()), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(f"Wrote {write_script()}")
