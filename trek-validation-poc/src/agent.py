"""'Ask Trek' agent: skill-file-governed, row-cited answers over the live validation state.

Two modes:
  * live           - Claude API (skill file as system prompt + serialized data context)
  * deterministic  - offline router that queries the same DataFrames and returns cited answers.
                     Also used automatically if the live call fails, so the demo cannot break.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills" / "benchmark_analyst_skill.md"

LIVE_MODEL = "claude-opus-5-5"

TECH_HEADER = "### 🔍 Technical Analyst Validation Note"
CFO_HEADER = "### 💼 Executive CFO Negotiation Mandate"

PRESET_PROMPTS = {
    "🔥 Top 5 Renegotiation Targets":
        "Which 5 CPT codes drive the largest annual dollar recovery across UHC and Aetna, and what are the exact peer MRF citations?",
    "🧩 Defend DNF Methodology":
        "A hospital data analyst is skeptical about the 'Data Not Found' lines. Walk through the exact RVU and modifier crosswalks used to validate them.",
    "🛡️ OpenPayer Policy + Rate Risk":
        "Cross-check our under-market Orthopedic and GI codes against OpenPayer policy rules—where are we getting hit by both low rates AND prior-auth/denial traps?",
    "📄 Draft CFO Board Memo":
        "Generate a two-altitude Executive Validation Memo & Redline Strategy for Summit Regional Health's CFO.",
}

SERVICE_LINE_ALIASES = {
    "Orthopedics": ["ortho"],
    "Radiology & Imaging": ["radiology", "imaging", "mri", "ct "],
    "Cardiology": ["cardio", "cardiac", "heart"],
    "Gastroenterology": ["gastro", " gi ", "gi ", "endoscopy", "colonoscopy"],
    "Emergency & E/M": ["emergency", " ed ", "e/m", "office visit"],
}
PAYER_ALIASES = {
    "UnitedHealthcare (UHC)": ["uhc", "united"],
    "Aetna": ["aetna"],
}
DENIAL_POINTS = {"High": 40, "Medium": 25, "Low": 10}


# --------------------------------------------------------------------------- skill file
def load_skill(path: Path = SKILL_PATH) -> tuple[dict, str]:
    """Split the skill file into (YAML metadata, Markdown instructions)."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, flags=re.S)
    if not m:
        raise ValueError(f"{path} has no YAML frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    return meta, m.group(2).strip()


# --------------------------------------------------------------------------- formatting
def _usd(x: float) -> str:
    return f"${x:,.0f}"


def _usd2(x: float) -> str:
    return f"${x:,.2f}"


def _short_payer(p: str) -> str:
    return "UHC" if p.startswith("UnitedHealthcare") else p


def cite(row: pd.Series) -> str:
    return f"[{row['sample_mrf_citation']} | {row['citation_hospital']} | {_short_payer(row['payer_name'])} | CPT {row['cpt_code']}]"


def cite_top(row: pd.Series) -> str:
    return f"[{row['top_peer_mrf_id']} | {row['top_peer_hospital']} | {_short_payer(row['payer_name'])} | CPT {row['cpt_code']}]"


def cite_dnf(row: pd.Series) -> str:
    if not row.get("proxy_mrf_citation"):
        return f"[no proxy | {_short_payer(row['payer_name'])} | CPT {row['cpt_code']}]"
    return (f"[{row['proxy_mrf_citation']} | {row['proxy_citation_hospital']} | {_short_payer(row['payer_name'])} | "
            f"CPT {row['proxy_cpt']} → proxy for {row['cpt_code']}]")


def _cell(text: str) -> str:
    """Escape pipes so citations survive inside markdown table cells."""
    return text.replace("|", "\\|")


# --------------------------------------------------------------------------- policy risk
def policy_risk_table(validated_df: pd.DataFrame, dnf_df: pd.DataFrame, policies: dict) -> pd.DataFrame:
    """Combine rate under-performance with policy denial exposure per CPT × payer."""
    rows = []
    for cpt, by_payer in policies.items():
        if cpt.startswith("_"):
            continue
        for payer, card in by_payer.items():
            v = validated_df[(validated_df["cpt_code"] == cpt) & (validated_df["payer_name"] == payer)]
            d = dnf_df[(dnf_df["cpt_code"] == cpt) & (dnf_df["payer_name"] == payer)] if len(dnf_df) else dnf_df
            if len(v):
                r = v.iloc[0]
                variance = float(r["raw_variance_pct"])
                gap = float(r["annual_uplift_p50"])
                citation = cite(r)
                desc = r["description"]
                sl = r["service_line"]
                source = "validated"
            elif len(d) and pd.notna(d.iloc[0]["estimated_market_rate"]):
                r = d.iloc[0]
                variance = (float(r["prospect_rate"]) - float(r["estimated_market_rate"])) / float(r["estimated_market_rate"]) * 100
                gap = float(r["annual_dnf_recovery"])
                citation = cite_dnf(r)
                desc = r["description"]
                sl = r["service_line"]
                source = "dnf"
            else:
                continue
            rate_points = min(60.0, max(0.0, -variance) * 2)
            score = rate_points + DENIAL_POINTS.get(card["denial_risk"], 10)
            rows.append({
                "cpt_code": cpt, "payer_name": payer, "description": desc, "service_line": sl, "source": source,
                "variance_pct": variance, "annual_gap": gap, "citation": citation,
                "prior_auth_required": card["prior_auth_required"], "denial_risk": card["denial_risk"],
                "common_denial_code": card["common_denial_code"], "common_denial_reason": card["common_denial_reason"],
                "policy_change_2026": card["policy_change_2026"],
                "medical_necessity_criteria": card["medical_necessity_criteria"],
                "combined_risk_score": round(score, 1),
                "double_exposure": variance <= -5 and (card["prior_auth_required"] or card["denial_risk"] == "High"),
            })
    cols = ["cpt_code", "payer_name", "description", "service_line", "source", "variance_pct", "annual_gap", "citation",
            "prior_auth_required", "denial_risk", "common_denial_code", "common_denial_reason", "policy_change_2026",
            "medical_necessity_criteria", "combined_risk_score", "double_exposure"]
    return pd.DataFrame(rows, columns=cols).sort_values("combined_risk_score", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------- deterministic answers
def _no_data(msg: str) -> str:
    return (f"{TECH_HEADER}\n\n{msg} No validated rows are in scope for the current filters, so there is "
            f"nothing to cite. Widen the payer / service-line filters in the sidebar.\n\n"
            f"{CFO_HEADER}\n\nNo recommendation until rows are back in scope.")


def answer_top_targets(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict, n: int = 5) -> str:
    if v.empty:
        return _no_data("Top-target ranking needs validated lines.")
    by_cpt = (v.groupby(["cpt_code", "description"], as_index=False)["annual_uplift_p50"].sum()
              .sort_values("annual_uplift_p50", ascending=False).head(n))
    total_gap = float(v["annual_uplift_p50"].sum())
    share = float(by_cpt["annual_uplift_p50"].sum()) / total_gap * 100 if total_gap else 0
    lines = [TECH_HEADER, "",
             f"Ranked by annual gap to market P50, formula `max(0, P50 − prospect) × annual volume`, payers combined. "
             f"These {len(by_cpt)} codes hold **{share:.1f}%** of the validated P50 gap ({_usd(total_gap)}).", "",
             "| # | CPT | Payer | Prospect % Mcare | Market P50 % Mcare | Variance | Pctile | Annual gap | Citation |",
             "|---|-----|-------|-----------------|--------------------|----------|--------|-----------|----------|"]
    for i, (_, c) in enumerate(by_cpt.iterrows(), start=1):
        for _, r in v[v["cpt_code"] == c["cpt_code"]].sort_values("annual_uplift_p50", ascending=False).iterrows():
            lines.append(
                f"| {i} | {r['cpt_code']} {r['description']} | {_short_payer(r['payer_name'])} | "
                f"{r['prospect_pct_medicare']:.1f}% | {r['market_p50_pct_medicare']:.1f}% | {r['raw_variance_pct']:+.1f}% | "
                f"P{r['market_percentile_rank']:.0f} | {_usd(r['annual_uplift_p50'])} | {_cell(cite(r))} |")
    lead = v.sort_values("annual_uplift_p50", ascending=False).iloc[0]
    lines += ["",
              f"Largest single line: CPT {lead['cpt_code']} with {_short_payer(lead['payer_name'])} at "
              f"{_usd2(lead['prospect_rate'])} vs. market P50 {_usd2(lead['market_p50'])} {cite(lead)}; "
              f"highest peer pays {_usd2(lead['top_peer_rate'])} {cite_top(lead)}.", "",
              CFO_HEADER, ""]
    rr = kpis.get("realization_rate", 0.5)
    top_val = float(by_cpt["annual_uplift_p50"].sum())
    lines.append(f"- **Ask:** reprice these {len(by_cpt)} codes to at least market median. Full capture = "
                 f"{_usd(top_val)}/yr; at {rr:.0%} realization = **{_usd(top_val * rr)}/yr**.")
    for _, c in by_cpt.iterrows():
        rows = v[v["cpt_code"] == c["cpt_code"]]
        asks = "; ".join(
            f"{_short_payer(r['payer_name'])} {r['prospect_pct_medicare']:.0f}% → ≥{r['market_p50_pct_medicare']:.0f}% of Medicare"
            for _, r in rows.iterrows() if r["annual_uplift_p50"] > 0)
        lines.append(f"- CPT {c['cpt_code']} ({c['description']}): {asks} — {_usd(c['annual_uplift_p50'])}/yr.")
    lines.append(f"- These alone cover the {_usd(kpis.get('annual_trek_subscription', 85000))} platform fee "
                 f"{top_val * rr / max(kpis.get('annual_trek_subscription', 85000), 1):.1f}x over.")
    return "\n".join(lines)


def answer_dnf(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict) -> str:
    if d.empty:
        return (f"{TECH_HEADER}\n\nEvery line in scope matched the warehouse directly — the DNF queue is empty "
                f"for the current filters.\n\n{CFO_HEADER}\n\nNo crosswalk assumptions are in the number.")
    lines = [TECH_HEADER, "",
             f"{len(d)} lines had no direct warehouse match. None were dropped. Each is resolved as "
             f"`estimated benchmark = proxy CPT market P50 (same payer) × adjustment factor`, then "
             f"`recovery = max(0, estimate − prospect rate) × volume`.", ""]
    for cpt, grp in d.groupby("cpt_code", sort=False):
        first = grp.iloc[0]
        lines.append(f"**CPT {cpt}{'-' + first['modifier'] if first['modifier'] != 'None' else ''} — "
                     f"{first['description']}**  ")
        lines.append(f"Reason `{first['dnf_reason_code']}`: {first['diagnostic_explanation']}  ")
        if first["proxy_cpt"]:
            lines.append(f"Method: {first['resolution_methodology']} Basis: {first['factor_basis']}. "
                         f"Confidence: {first['confidence_tier']}.")
        for _, r in grp.iterrows():
            if pd.notna(r["estimated_market_rate"]):
                lines.append(f"- {_short_payer(r['payer_name'])}: {_usd2(r['proxy_market_p50'])} × {r['adjustment_factor']:.2f} = "
                             f"{_usd2(r['estimated_market_rate'])} vs. prospect {_usd2(r['prospect_rate'])} × {int(r['annual_volume'])} "
                             f"→ {_usd(r['annual_dnf_recovery'])}/yr {cite_dnf(r)}")
            else:
                lines.append(f"- {_short_payer(r['payer_name'])}: no crosswalk defined — routed to manual review.")
        lines.append("")
    lines += ["How an analyst can challenge it: every factor is editable in the DNF Workbench sandbox and in "
              "column L of the `Data_Not_Found_Resolution` sheet; the estimate and recovery recalculate live.", "",
              CFO_HEADER, ""]
    rec = float(d["annual_dnf_recovery"].sum())
    rr = kpis.get("realization_rate", 0.5)
    lines += [f"- DNF lines add **{_usd(rec)}/yr** of gross opportunity ({_usd(rec * rr)} at {rr:.0%} realization) "
              f"that a match-only analysis would have silently dropped.",
              f"- High-confidence crosswalks (RVU and modifier split) carry "
              f"{_usd(float(d[d['confidence_tier'].str.startswith('High')]['annual_dnf_recovery'].sum()))} of it; "
              f"medium-confidence lines can be excluded with one toggle if the CFO wants a floor case.",
              "- **Ask:** add explicit rates for these codes to the renewal (codes absent from the payer file are "
              "typically paid off a default % of charges or a fallback schedule)."]
    return "\n".join(lines)


def answer_policy(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict,
                  service_lines: list[str] | None = None) -> str:
    risk = policy_risk_table(v, d, policies)
    service_lines = service_lines or ["Orthopedics", "Gastroenterology"]
    scoped = risk[risk["service_line"].isin(service_lines)]
    if scoped.empty:
        scoped = risk
    if scoped.empty:
        return _no_data("No policy-carded codes are in scope.")
    dbl = scoped[scoped["double_exposure"]]
    lines = [TECH_HEADER, "",
             "Joined rate variance (vs. market P50, or vs. crosswalk estimate for DNF lines) with simulated OpenPayer "
             "policy cards. Combined risk score = rate points (2 × % under market, cap 60) + denial points "
             "(High 40 / Medium 25 / Low 10).", "",
             "| CPT | Payer | Variance | Prior auth | Denial risk | Denial code | Score | Citation |",
             "|-----|-------|----------|-----------|-------------|-------------|-------|----------|"]
    for _, r in scoped.iterrows():
        lines.append(f"| {r['cpt_code']} {r['description']} | {_short_payer(r['payer_name'])} | {r['variance_pct']:+.1f}% | "
                     f"{'Yes' if r['prior_auth_required'] else 'No'} | {r['denial_risk']} | {r['common_denial_code']} | "
                     f"{r['combined_risk_score']:.0f} | {_cell(r['citation'])} |")
    lines.append("")
    lines.append(f"**Double exposure (under-paid AND policy-gated): {len(dbl)} line(s).**")
    for _, r in dbl.iterrows():
        lines.append(f"- CPT {r['cpt_code']} / {_short_payer(r['payer_name'])}: {abs(r['variance_pct']):.1f}% under market "
                     f"{r['citation']}. Policy: {r['policy_change_2026']} Criteria: {r['medical_necessity_criteria']} "
                     f"Typical denial {r['common_denial_code']} ({r['common_denial_reason']}).")
    lines += ["", CFO_HEADER, ""]
    exposed = float(dbl["annual_gap"].sum())
    lines.append(f"- {len(dbl)} code/payer pairs lose money twice: below-market rates **and** prior-auth or denial friction. "
                 f"Rate gap on those lines alone: **{_usd(exposed)}/yr**, before counting denial write-offs.")
    if len(dbl):
        top = dbl.iloc[0]
        lines.append(f"- Lead with CPT {top['cpt_code']} at {_short_payer(top['payer_name'])}: ask for the rate move to market "
                     f"median **plus** policy relief (PA gold-carding or a carve-out for documented conservative-therapy "
                     f"cases) — {top['common_denial_code']} denials are the payer's hidden discount on an already low rate.")
    lines.append("- Track denial rates on these codes for 90 days post-renewal; Trek's payer-performance view closes that loop.")
    return "\n".join(lines)


def answer_memo(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict) -> str:
    if v.empty:
        return _no_data("The memo needs validated lines.")
    rr = kpis.get("realization_rate", 0.5)
    top = (v.groupby(["cpt_code", "description"], as_index=False)["annual_uplift_p50"].sum()
           .sort_values("annual_uplift_p50", ascending=False).head(5))
    lead = v.sort_values("annual_uplift_p50", ascending=False).iloc[0]
    risk = policy_risk_table(v, d, policies)
    dbl = risk[risk["double_exposure"]]
    fc = kpis.get("flag_counts", {})
    payer_gap = v.groupby("payer_name")["annual_uplift_p50"].sum().sort_values(ascending=False)
    lines = [
        "**MEMO — Fee Schedule Validation & Redline Strategy**  ",
        "To: CFO, Summit Regional Health System · From: Trek Health Solutions Engineering · Data: TiC MRF slice 2026-Q3 (synthetic demo)",
        "", TECH_HEADER, "",
        f"- Scope: {kpis['total_lines']} fee-schedule lines; {kpis['matched_lines']} matched directly "
        f"({kpis['match_rate_pct']:.1f}%), {kpis['dnf_lines']} resolved via documented crosswalks "
        f"({kpis['coverage_with_dnf_pct']:.0f}% coverage).",
        f"- Variance mix: {fc.get('CRITICAL_UNDER_MARKET', 0)} critical (≤ −20%), {fc.get('MODERATE_UNDER_MARKET', 0)} moderate, "
        f"{fc.get('COMPETITIVE_BAND', 0)} competitive, {fc.get('ABOVE_MARKET', 0)} above market.",
        f"- Volume-weighted portfolio: prospect at **{kpis['prospect_pct_medicare']:.1f}%** of Medicare vs. market median "
        f"**{kpis['market_pct_medicare']:.1f}%** ({kpis['prospect_pct_medicare'] - kpis['market_pct_medicare']:+.1f} pts).",
        f"- Largest line: CPT {lead['cpt_code']} {_short_payer(lead['payer_name'])} at {lead['prospect_pct_medicare']:.1f}% vs. "
        f"{lead['market_p50_pct_medicare']:.1f}% of Medicare, P{lead['market_percentile_rank']:.0f} {cite(lead)}.",
        "- Gap by payer (P50): " + "; ".join(f"{_short_payer(p)} {_usd(g)}" for p, g in payer_gap.items()) + ".",
        f"- DNF crosswalks contribute {_usd(kpis['dnf_recovery'])}; methods: RVU ratio, modifier-26 split, complexity, specialty index.",
    ]
    if len(d) and d["proxy_mrf_citation"].astype(bool).any():
        r = d[d["proxy_mrf_citation"].astype(bool)].iloc[0]
        lines.append(f"  e.g. CPT {r['cpt_code']}: {_usd2(r['proxy_market_p50'])} × {r['adjustment_factor']:.2f} {cite_dnf(r)}.")
    if len(dbl):
        lines.append(f"- Policy double exposure on {len(dbl)} line(s), led by CPT {dbl.iloc[0]['cpt_code']} "
                     f"({dbl.iloc[0]['common_denial_code']}) {dbl.iloc[0]['citation']}.")
    lines += ["", CFO_HEADER, "",
              f"1. **Opportunity:** {_usd(kpis['total_addressable'])}/yr addressable vs. {kpis['target_benchmark']}"
              f"{' incl. DNF' if kpis['include_dnf_recovery'] else ''}; at {rr:.0%} realization = "
              f"**{_usd(kpis['realized_uplift'])}/yr**.",
              f"2. **Return:** {kpis['roi_multiple']:.1f}x first-year ROI on a {_usd(kpis['annual_trek_subscription'])} "
              f"platform fee; payback {kpis['payback_months']:.1f} months; 3-year net {_usd(kpis['three_year_net_value'])}.",
              "3. **Redline list (lead asks):**"]
    for _, c in top.iterrows():
        lines.append(f"   - CPT {c['cpt_code']} {c['description']}: reprice to ≥ market median — {_usd(c['annual_uplift_p50'])}/yr")
    lines += [f"4. **Sequence:** open with {_short_payer(payer_gap.index[0])} (largest gap); protect the "
              f"{fc.get('ABOVE_MARKET', 0)} above-market lines; pair rate asks with PA relief on double-exposure codes.",
              "5. **Decision requested:** approve the redline list for the next renewal cycle and a 30-day validation on the full fee schedule."]
    return "\n".join(lines)


def answer_service_line_compare(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict, lines_req: list[str]) -> str:
    if v.empty:
        return _no_data("Service-line comparison needs validated lines.")
    lines_req = lines_req or ["Orthopedics", "Radiology & Imaging"]
    out = [TECH_HEADER, "",
           "Volume-weighted % of Medicare = Σ(rate × volume) / Σ(Medicare × volume).", "",
           "| Service line | Payer | Prospect % Mcare | Market P50 % Mcare | Gap (pts) | Annual gap (P50) |",
           "|--------------|-------|-----------------|--------------------|-----------|------------------|"]
    for sl in lines_req:
        sub = v[v["service_line"] == sl]
        for payer, g in sub.groupby("payer_name"):
            mw = (g["medicare_rate"] * g["annual_volume"]).sum()
            pp = (g["prospect_rate"] * g["annual_volume"]).sum() / mw * 100
            mp = (g["market_p50"] * g["annual_volume"]).sum() / mw * 100
            out.append(f"| {sl} | {_short_payer(payer)} | {pp:.1f}% | {mp:.1f}% | {pp - mp:+.1f} | {_usd(g['annual_uplift_p50'].sum())} |")
    out.append("")
    for sl in lines_req:
        sub = v[v["service_line"] == sl].sort_values("raw_variance_pct")
        if len(sub):
            r = sub.iloc[0]
            out.append(f"- Deepest {sl} gap: CPT {r['cpt_code']} {r['description']} / {_short_payer(r['payer_name'])} at "
                       f"{r['prospect_pct_medicare']:.1f}% vs. {r['market_p50_pct_medicare']:.1f}% of Medicare {cite(r)}.")
    out += ["", CFO_HEADER, ""]
    for sl in lines_req:
        sub = v[v["service_line"] == sl]
        if len(sub):
            out.append(f"- **{sl}:** {_usd(sub['annual_uplift_p50'].sum())}/yr to market median across "
                       f"{int((sub['annual_uplift_p50'] > 0).sum())} under-market lines.")
    out.append("- Negotiate the service line with the larger gap first; use the other as a trade-off bargaining chip.")
    return "\n".join(out)


def answer_payer_compare(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict, service_line: str | None) -> str:
    sub = v if not service_line else v[v["service_line"] == service_line]
    if sub.empty:
        return _no_data("Payer comparison needs validated lines.")
    scope = service_line or "all service lines"
    out = [TECH_HEADER, "", f"Payer comparison across {scope}.", "",
           "| Payer | Lines | Critical | Prospect % Mcare | Market % Mcare | Annual gap (P50) |",
           "|-------|-------|----------|-----------------|----------------|------------------|"]
    for payer, g in sub.groupby("payer_name"):
        mw = (g["medicare_rate"] * g["annual_volume"]).sum()
        out.append(f"| {_short_payer(payer)} | {len(g)} | {int((g['variance_flag'] == 'CRITICAL_UNDER_MARKET').sum())} | "
                   f"{(g['prospect_rate'] * g['annual_volume']).sum() / mw * 100:.1f}% | "
                   f"{(g['market_p50'] * g['annual_volume']).sum() / mw * 100:.1f}% | {_usd(g['annual_uplift_p50'].sum())} |")
    out.append("")
    for payer, g in sub.groupby("payer_name"):
        r = g.sort_values("annual_uplift_p50", ascending=False).iloc[0]
        out.append(f"- {_short_payer(payer)} biggest line: CPT {r['cpt_code']} {r['description']}, {r['raw_variance_pct']:+.1f}% vs. P50, "
                   f"{_usd(r['annual_uplift_p50'])}/yr {cite(r)}.")
    gaps = sub.groupby("payer_name")["annual_uplift_p50"].sum().sort_values(ascending=False)
    out += ["", CFO_HEADER, "",
            f"- {_short_payer(gaps.index[0])} carries the larger gap ({_usd(gaps.iloc[0])}/yr) — schedule that renewal conversation first.",
            "- Use the better-paying payer's rates on the same codes as an internal anchor; never share them externally."]
    return "\n".join(out)


def answer_cpt(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict, cpt: str) -> str:
    rows = v[v["cpt_code"] == cpt]
    drows = d[d["cpt_code"] == cpt] if len(d) else d
    if rows.empty and drows.empty:
        return (f"{TECH_HEADER}\n\nCPT {cpt} is not in the prospect fee schedule within the current filters, so I "
                f"cannot cite a benchmark for it. Codes in scope: {', '.join(sorted(set(v['cpt_code'])) [:12])}…\n\n"
                f"{CFO_HEADER}\n\nNo recommendation for CPT {cpt} without data.")
    out = [TECH_HEADER, ""]
    for _, r in rows.iterrows():
        out.append(f"**CPT {cpt} {r['description']} — {_short_payer(r['payer_name'])}** {cite(r)}  ")
        out.append(f"Prospect {_usd2(r['prospect_rate'])} ({r['prospect_pct_medicare']:.1f}% of Medicare {_usd2(r['medicare_rate'])}). "
                   f"Market P25 {_usd2(r['market_p25'])} · P50 {_usd2(r['market_p50'])} · P75 {_usd2(r['market_p75'])} · "
                   f"P90 {_usd2(r['market_p90'])} (n = {int(r['sample_size'])}). Variance {r['raw_variance_pct']:+.1f}% → "
                   f"`{r['variance_flag']}`, percentile rank P{r['market_percentile_rank']:.0f}. "
                   f"Highest peer {_usd2(r['top_peer_rate'])} {cite_top(r)}. Annual gap to P50 {_usd(r['annual_uplift_p50'])} "
                   f"on {int(r['annual_volume'])} cases.")
        out.append("")
    for _, r in drows.iterrows():
        out.append(f"**CPT {cpt} — {_short_payer(r['payer_name'])} (Data Not Found)**: `{r['dnf_reason_code']}`. "
                   f"{r['resolution_methodology']} Estimate {_usd2(r['estimated_market_rate']) if pd.notna(r['estimated_market_rate']) else 'n/a'} "
                   f"vs. prospect {_usd2(r['prospect_rate'])} → {_usd(r['annual_dnf_recovery'])}/yr {cite_dnf(r)}.")
        out.append("")
    card = policies.get(cpt)
    if card:
        for payer, c in card.items():
            out.append(f"OpenPayer ({_short_payer(payer)}): PA {'required' if c['prior_auth_required'] else 'not required'}; "
                       f"{c['policy_change_2026']} Denial risk {c['denial_risk']} ({c['common_denial_code']}).")
        out.append("")
    out += [CFO_HEADER, ""]
    total = float(rows["annual_uplift_p50"].sum()) + (float(drows["annual_dnf_recovery"].sum()) if len(drows) else 0.0)
    rr = kpis.get("realization_rate", 0.5)
    if total > 0:
        out.append(f"- CPT {cpt} is worth **{_usd(total)}/yr** at market median ({_usd(total * rr)} at {rr:.0%} realization).")
        for _, r in rows[rows["annual_uplift_p50"] > 0].iterrows():
            out.append(f"- **Ask {_short_payer(r['payer_name'])}:** move from {r['prospect_pct_medicare']:.0f}% to ≥ "
                       f"{r['market_p50_pct_medicare']:.0f}% of Medicare ({_usd2(r['market_p50'])}).")
    else:
        out.append(f"- CPT {cpt} is at or above market — protect this rate; expect the payer to push back on it.")
    return "\n".join(out)


def answer_overview(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict) -> str:
    if v.empty:
        return _no_data("Overview needs validated lines.")
    lead = v.sort_values("annual_uplift_p50", ascending=False).iloc[0]
    return "\n".join([
        TECH_HEADER, "",
        f"{kpis['matched_lines']} validated lines and {kpis['dnf_lines']} DNF lines in scope. Volume-weighted prospect "
        f"{kpis['prospect_pct_medicare']:.1f}% vs. market {kpis['market_pct_medicare']:.1f}% of Medicare. "
        f"Largest gap: CPT {lead['cpt_code']} {_short_payer(lead['payer_name'])} {cite(lead)}.", "",
        "I can answer, with citations: a specific CPT (e.g. *\"Tell me about 27447\"*), payer comparisons "
        "(*\"Compare UHC vs Aetna in Radiology\"*), service-line comparisons, DNF crosswalks, OpenPayer policy risk, "
        "top renegotiation targets, or a CFO memo.", "",
        CFO_HEADER, "",
        f"- {_usd(kpis['total_addressable'])}/yr addressable; {_usd(kpis['realized_uplift'])}/yr at "
        f"{kpis['realization_rate']:.0%} realization; payback {kpis['payback_months']:.1f} months.",
    ])


def _service_lines_in(q: str) -> list[str]:
    ql = f" {q.lower()} "
    return [sl for sl, al in SERVICE_LINE_ALIASES.items() if sl.lower() in ql or any(a in ql for a in al)]


def route(query: str, v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict) -> tuple[str, str]:
    """Return (intent, markdown answer)."""
    q = query.lower()
    sls = _service_lines_in(query)
    if any(k in q for k in ("memo", "board", "cfo executive", "executive validation")):
        return "cfo_memo", answer_memo(v, d, kpis, policies)
    if any(k in q for k in ("data not found", "dnf", "crosswalk", "unmatched", "skeptical")):
        return "dnf_defense", answer_dnf(v, d, kpis, policies)
    if any(k in q for k in ("openpayer", "policy", "prior-auth", "prior auth", "denial")):
        return "policy_cross_check", answer_policy(v, d, kpis, policies, sls or None)
    if any(k in q for k in ("top", "largest", "biggest", "drive", "priorit", "renegotiat")):
        m = re.search(r"\btop\s+(\d+)", q)
        return "top_targets", answer_top_targets(v, d, kpis, policies, int(m.group(1)) if m else 5)
    cpt = re.search(r"\b(\d{4}[0-9T])\b", query.upper())
    if cpt:
        return "cpt_lookup", answer_cpt(v, d, kpis, policies, cpt.group(1))
    payers = [p for p, al in PAYER_ALIASES.items() if any(a in q for a in al)]
    if len(payers) >= 2 or (payers and "compare" in q) or " vs" in q and payers:
        return "payer_compare", answer_payer_compare(v, d, kpis, policies, sls[0] if sls else None)
    if sls and any(k in q for k in ("compare", "vs", "against", "how", "rates")):
        return "service_line_compare", answer_service_line_compare(v, d, kpis, policies, sls)
    return "overview", answer_overview(v, d, kpis, policies)


# --------------------------------------------------------------------------- live mode
def _context_markdown(v: pd.DataFrame, d: pd.DataFrame, kpis: dict, policies: dict) -> str:
    vcols = ["prospect_row_id", "payer_name", "cpt_code", "description", "service_line", "prospect_rate", "medicare_rate",
             "market_p25", "market_p50", "market_p75", "market_p90", "sample_size", "prospect_pct_medicare",
             "market_p50_pct_medicare", "raw_variance_pct", "market_percentile_rank", "variance_flag", "annual_volume",
             "annual_uplift_p50", "annual_uplift_p75", "sample_mrf_citation", "citation_hospital", "top_peer_mrf_id",
             "top_peer_hospital", "top_peer_rate"]
    dcols = ["prospect_row_id", "payer_name", "cpt_code", "modifier", "description", "prospect_rate", "annual_volume",
             "dnf_reason_code", "diagnostic_explanation", "proxy_cpt", "proxy_market_p50", "adjustment_factor",
             "factor_basis", "estimated_market_rate", "annual_dnf_recovery", "confidence_tier", "proxy_mrf_citation",
             "proxy_citation_hospital"]
    k = {key: (round(val, 2) if isinstance(val, float) else val) for key, val in kpis.items()
         if not isinstance(val, pd.DataFrame)}
    vtxt = v[vcols].round(2).to_csv(index=False) if len(v) else "(none in scope)"
    dtxt = d[dcols].round(2).to_csv(index=False) if len(d) else "(none in scope)"
    import json
    return (f"<kpis>\n{json.dumps(k, indent=1, default=str)}\n</kpis>\n\n"
            f"<validated_rates format=\"csv\">\n{vtxt}</validated_rates>\n\n"
            f"<dnf_queue format=\"csv\">\n{dtxt}</dnf_queue>\n\n"
            f"<openpayer_policies>\n{json.dumps(policies, indent=1)}\n</openpayer_policies>")


def _ask_live(query: str, system_prompt: str, context: str, api_key: str) -> tuple[str, dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.beta.messages.create(
        model=LIVE_MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium"},
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"Data context for this validation (synthetic demo data):\n\n{context}\n\nQuestion: {query}",
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Model declined the request")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Empty response")
    usage = response.usage
    return text, {"model": response.model, "tokens": int(usage.input_tokens + usage.output_tokens)}


# --------------------------------------------------------------------------- public API
def ask_benchmark_agent(query: str, validated_df: pd.DataFrame, dnf_df: pd.DataFrame, kpis: dict,
                        policies_dict: dict, api_key: str | None = None) -> tuple[str, dict]:
    """Answer a question per the skill file. Returns (markdown, metadata)."""
    meta, instructions = load_skill()
    t0 = time.perf_counter()
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    info = {
        "skill_name": meta.get("name"),
        "skill_version": meta.get("version"),
        "mode_used": "deterministic",
        "model": "deterministic-cited-engine",
        "intent": None,
        "fallback_reason": None,
    }
    if key:
        try:
            text, live = _ask_live(query, instructions, _context_markdown(validated_df, dnf_df, kpis, policies_dict), key)
            info.update(mode_used="live", model=live["model"], tokens_or_rows_scanned=live["tokens"], intent="llm")
            info["citations_count"] = text.count("[MRF-")
            info["latency_ms"] = round((time.perf_counter() - t0) * 1000)
            return text, info
        except Exception as exc:  # demo must never break: fall back to the cited engine
            info["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:300]
    intent, text = route(query, validated_df, dnf_df, kpis, policies_dict)
    info["intent"] = intent
    info["tokens_or_rows_scanned"] = int(len(validated_df) + len(dnf_df))
    info["citations_count"] = text.count("[MRF-")
    info["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    return text, info
