"""DuckDB validation engine: market aggregation, fee-schedule validation, DNF resolution, CMA scenarios."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from src.data_generator import DATA_DIR, MRF_PATH, POLICIES_PATH, PROSPECT_PATH, ensure_data

REQUIRED_PROSPECT_COLUMNS = [
    "prospect_row_id", "payer_name", "cpt_code", "modifier", "description",
    "service_line", "prospect_rate", "annual_volume",
]

FLAG_ORDER = ["CRITICAL_UNDER_MARKET", "MODERATE_UNDER_MARKET", "COMPETITIVE_BAND", "ABOVE_MARKET"]

TARGET_P50 = "Market P50 (Median)"
TARGET_P75 = "Market P75 (Upper Quartile)"
TARGET_FLOOR = "Custom % of Medicare Floor"
TARGET_OPTIONS = [TARGET_P50, TARGET_P75, TARGET_FLOOR]

DEFAULT_SUBSCRIPTION = 85_000.0
DEFAULT_REALIZATION = 0.50
DEFAULT_FLOOR_PCT = 195.0

# SE crosswalk playbook: how each known DNF pattern is resolved.
CROSSWALK_LIBRARY = {
    "27446": {
        "dnf_reason_code": "CODE_ABSENT_FROM_PAYER_MRF",
        "diagnostic_explanation": "Neither payer publishes a negotiated rate for partial knee arthroplasty in its TiC MRF for this region.",
        "proxy_cpt": "27447",
        "adjustment_factor": 0.82,
        "factor_basis": "CMS RVU ratio 27446 : 27447",
        "resolution_methodology": "RVU crosswalk: 27447 (Total Knee) market P50 × 0.82 work/practice-expense RVU ratio.",
        "confidence_tier": "High — RVU Crosswalk",
    },
    "70551": {
        "dnf_reason_code": "MODIFIER_26_SPLIT_MISSING",
        "diagnostic_explanation": "Prospect line is billed with modifier 26 (professional read only); payer MRFs publish global facility rates only.",
        "proxy_cpt": "70553",
        "adjustment_factor": 0.38,
        "factor_basis": "Professional-component share of global MRI rate",
        "resolution_methodology": "Modifier split: 70553 (MRI Brain global) market P50 × 0.38 professional-component ratio.",
        "confidence_tier": "High — Modifier Split",
    },
    "45385": {
        "dnf_reason_code": "LOW_VOLUME_SUPPRESSED_IN_TIC",
        "diagnostic_explanation": "Snare polypectomy rates fall below the minimum cell size and are suppressed in the normalized warehouse.",
        "proxy_cpt": "45380",
        "adjustment_factor": 1.14,
        "factor_basis": "Relative procedural complexity vs. biopsy colonoscopy",
        "resolution_methodology": "Complexity crosswalk: 45380 (Colonoscopy w/ Biopsy) market P50 × 1.14.",
        "confidence_tier": "Medium — Complexity Crosswalk",
    },
    "0408T": {
        "dnf_reason_code": "EMERGING_CAT_III_NO_MRF_RATE",
        "diagnostic_explanation": "Category III emerging-technology code; payers have not published a negotiated rate.",
        "proxy_cpt": "93458",
        "adjustment_factor": 1.20,
        "factor_basis": "Regional cardiology specialty index",
        "resolution_methodology": "Specialty index: 93458 (Left Heart Cath) market P50 × 1.20 cardiology index.",
        "confidence_tier": "Medium — Specialty Index",
    },
}

MARKET_AGG_SQL = """
SELECT
    cpt_code,
    payer_name,
    ANY_VALUE(description)                        AS market_description,
    MEDIAN(medicare_rate)                         AS medicare_rate,
    QUANTILE_CONT(negotiated_rate, 0.25)          AS market_p25,
    MEDIAN(negotiated_rate)                       AS market_p50,
    QUANTILE_CONT(negotiated_rate, 0.75)          AS market_p75,
    QUANTILE_CONT(negotiated_rate, 0.90)          AS market_p90,
    AVG(negotiated_rate)                          AS market_mean,
    COUNT(*)                                      AS sample_size,
    MEDIAN(negotiated_rate) / MEDIAN(medicare_rate) * 100 AS market_pct_of_medicare
FROM mrf_warehouse
GROUP BY cpt_code, payer_name
""".strip()

CITATION_SQL = """
SELECT
    m._rowkey,
    AVG(CASE WHEN w.negotiated_rate <= m.prospect_rate THEN 1.0 ELSE 0.0 END) * 100        AS market_percentile_rank,
    ARG_MIN(w.mrf_record_id,  (ABS(w.negotiated_rate - m.market_p50), w.mrf_record_id))  AS sample_mrf_citation,
    ARG_MIN(w.hospital_name,  (ABS(w.negotiated_rate - m.market_p50), w.mrf_record_id))  AS citation_hospital,
    ARG_MIN(w.negotiated_rate, (ABS(w.negotiated_rate - m.market_p50), w.mrf_record_id)) AS citation_rate,
    ARG_MAX(w.mrf_record_id,  w.negotiated_rate)                                          AS top_peer_mrf_id,
    ARG_MAX(w.hospital_name,  w.negotiated_rate)                                          AS top_peer_hospital,
    MAX(w.negotiated_rate)                                                                AS top_peer_rate
FROM matched_lines m
JOIN mrf_warehouse w ON w.cpt_code = m.cpt_code AND w.payer_name = m.payer_name
GROUP BY m._rowkey
""".strip()

VALIDATION_JOIN_SQL = """
SELECT p.*, m.* EXCLUDE (cpt_code, payer_name)
FROM prospect p
LEFT JOIN market_cohort m
  ON  p.cpt_code   = m.cpt_code
  AND p.payer_name = m.payer_name
  AND p.modifier   = 'None'
""".strip()


def _normalize_prospect(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_PROSPECT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Prospect file is missing required columns: {', '.join(missing)}")
    out = df.copy()
    out["cpt_code"] = out["cpt_code"].astype(str).str.strip().str.upper()
    out["payer_name"] = out["payer_name"].astype(str).str.strip()
    out["modifier"] = (
        out["modifier"].fillna("None").astype(str).str.strip()
        .replace({"": "None", "nan": "None", "NaN": "None", "none": "None"})
    )
    out["prospect_rate"] = pd.to_numeric(out["prospect_rate"], errors="raise").astype(float)
    out["annual_volume"] = pd.to_numeric(out["annual_volume"], errors="raise").astype(int)
    out["prospect_row_id"] = out["prospect_row_id"].astype(str)
    out["description"] = out["description"].astype(str)
    out["service_line"] = out["service_line"].astype(str)
    if "contract_renewal_date" not in out.columns:
        out["contract_renewal_date"] = ""
    return out


def load_prospect_csv(path_or_buffer) -> pd.DataFrame:
    df = pd.read_csv(path_or_buffer, dtype={"cpt_code": str, "modifier": str}, keep_default_na=False)
    return _normalize_prospect(df)


def variance_flag(raw_variance_pct: float) -> str:
    if raw_variance_pct <= -20:
        return "CRITICAL_UNDER_MARKET"
    if raw_variance_pct < -5:
        return "MODERATE_UNDER_MARKET"
    if raw_variance_pct <= 5:
        return "COMPETITIVE_BAND"
    return "ABOVE_MARKET"


@dataclass
class ValidationResult:
    validated_df: pd.DataFrame
    dnf_df: pd.DataFrame
    total_lines: int
    query_ms: float
    sql_preview: str = field(default=MARKET_AGG_SQL)


class TrekValidationEngine:
    """In-memory DuckDB warehouse over the normalized TiC MRF slice."""

    def __init__(self, data_dir: Path = DATA_DIR):
        ensure_data(data_dir)
        self.data_dir = data_dir
        self.con = duckdb.connect(database=":memory:")
        # Streamlit sessions share this engine across threads; DuckDB connections are not thread-safe.
        self._lock = threading.RLock()
        mrf_path = (data_dir / MRF_PATH.name).as_posix()
        self.con.execute(
            "CREATE TABLE mrf_warehouse AS SELECT * FROM read_csv_auto(?, types={'cpt_code': 'VARCHAR'})",
            [mrf_path],
        )
        self.con.execute(f"CREATE TABLE market_cohort AS {MARKET_AGG_SQL}")
        self.mrf_df = self.con.execute("SELECT * FROM mrf_warehouse ORDER BY mrf_record_id").df()
        self.cohort_df = self.con.execute("SELECT * FROM market_cohort ORDER BY cpt_code, payer_name").df()
        self.policies = json.loads((data_dir / POLICIES_PATH.name).read_text())
        self.last_query_ms = 0.0

    def _df(self, sql: str, params: list | None = None) -> pd.DataFrame:
        with self._lock:
            return self.con.execute(sql, params or []).df()

    def _rows(self, sql: str, params: list | None = None) -> list[tuple]:
        with self._lock:
            return self.con.execute(sql, params or []).fetchall()

    # ------------------------------------------------------------------ metadata
    def get_sql_query_preview(self) -> str:
        return MARKET_AGG_SQL + ";\n\n-- Fee-schedule validation join\n" + VALIDATION_JOIN_SQL + ";"

    def warehouse_row_count(self) -> int:
        return int(self._rows("SELECT COUNT(*) FROM mrf_warehouse")[0][0])

    def default_prospect(self) -> pd.DataFrame:
        return load_prospect_csv(self.data_dir / PROSPECT_PATH.name)

    def peer_rates(self, cpt_code: str, payer_name: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM mrf_warehouse WHERE cpt_code = ?"
        params: list = [cpt_code]
        if payer_name:
            sql += " AND payer_name = ?"
            params.append(payer_name)
        return self._df(sql + " ORDER BY negotiated_rate", params)

    def _cohort(self, cpt_code: str, payer_name: str) -> dict | None:
        row = self._df("SELECT * FROM market_cohort WHERE cpt_code = ? AND payer_name = ?", [cpt_code, payer_name])
        return None if row.empty else row.iloc[0].to_dict()

    def _median_citation(self, cpt_code: str, payer_name: str, p50: float) -> tuple[str, str, float]:
        """The peer record whose rate sits closest to the cohort median (for auditable citation)."""
        row = self._rows(
            """SELECT mrf_record_id, hospital_name, negotiated_rate FROM mrf_warehouse
               WHERE cpt_code = ? AND payer_name = ?
               ORDER BY ABS(negotiated_rate - ?), mrf_record_id LIMIT 1""",
            [cpt_code, payer_name, p50],
        )[0]
        return row[0], row[1], float(row[2])

    # ------------------------------------------------------------------ pipeline
    def run_validation(self, prospect_df: pd.DataFrame) -> ValidationResult:
        t0 = time.perf_counter()
        prospect = _normalize_prospect(prospect_df)
        with self._lock:
            self.con.register("prospect", prospect)
            try:
                joined = self.con.execute(VALIDATION_JOIN_SQL).df()
            finally:
                self.con.unregister("prospect")
        # restore original file order
        order = {rid: i for i, rid in enumerate(prospect["prospect_row_id"])}
        joined = joined.sort_values("prospect_row_id", key=lambda s: s.map(order)).reset_index(drop=True)

        matched_mask = joined["market_p50"].notna()
        validated = self._enrich_validated(joined[matched_mask].copy())
        dnf = self.resolve_dnf_queue(joined[~matched_mask][prospect.columns].copy())
        self.last_query_ms = (time.perf_counter() - t0) * 1000
        return ValidationResult(validated, dnf, len(prospect), self.last_query_ms)

    def _enrich_validated(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.assign(**{c: pd.Series(dtype=float) for c in [
                "prospect_pct_medicare", "market_p50_pct_medicare", "unit_gap_to_p50", "unit_gap_to_p75",
                "raw_variance_pct", "market_percentile_rank", "current_annual_rev", "annual_uplift_p50",
                "annual_uplift_p75"]}, variance_flag=pd.Series(dtype=str))
        df["prospect_pct_medicare"] = df["prospect_rate"] / df["medicare_rate"] * 100
        df["market_p50_pct_medicare"] = df["market_p50"] / df["medicare_rate"] * 100
        df["unit_gap_to_p50"] = np.maximum(0.0, df["market_p50"] - df["prospect_rate"])
        df["unit_gap_to_p75"] = np.maximum(0.0, df["market_p75"] - df["prospect_rate"])
        df["raw_variance_dollars"] = df["prospect_rate"] - df["market_p50"]
        df["raw_variance_pct"] = (df["prospect_rate"] - df["market_p50"]) / df["market_p50"] * 100
        df["variance_flag"] = df["raw_variance_pct"].map(variance_flag)
        df["current_annual_rev"] = df["prospect_rate"] * df["annual_volume"]
        df["annual_uplift_p50"] = df["unit_gap_to_p50"] * df["annual_volume"]
        df["annual_uplift_p75"] = df["unit_gap_to_p75"] * df["annual_volume"]

        # percentile rank + auditable citations for every line in one set-based query
        keys = df[["cpt_code", "payer_name", "prospect_rate", "market_p50"]].reset_index(drop=True)
        keys.insert(0, "_rowkey", range(len(keys)))
        with self._lock:
            self.con.register("matched_lines", keys)
            try:
                cit = self.con.execute(CITATION_SQL).df().sort_values("_rowkey")
            finally:
                self.con.unregister("matched_lines")
        df = df.reset_index(drop=True)
        for col in ("market_percentile_rank", "sample_mrf_citation", "citation_hospital", "citation_rate",
                    "top_peer_mrf_id", "top_peer_hospital", "top_peer_rate"):
            df[col] = cit[col].to_numpy()
        return df.reset_index(drop=True)

    def resolve_dnf_queue(self, dnf_df: pd.DataFrame, factor_overrides: dict[str, float] | None = None) -> pd.DataFrame:
        factor_overrides = factor_overrides or {}
        records = []
        for _, r in dnf_df.iterrows():
            rec = r.to_dict()
            rule = CROSSWALK_LIBRARY.get(r["cpt_code"])
            cohort = self._cohort(rule["proxy_cpt"], r["payer_name"]) if rule else None
            if rule and cohort:
                factor = float(factor_overrides.get(r["prospect_row_id"], rule["adjustment_factor"]))
                est = float(cohort["market_p50"]) * factor
                cite_id, cite_hosp, _ = self._median_citation(rule["proxy_cpt"], r["payer_name"], cohort["market_p50"])
                rec.update({
                    "dnf_reason_code": rule["dnf_reason_code"],
                    "diagnostic_explanation": rule["diagnostic_explanation"],
                    "proxy_cpt": rule["proxy_cpt"],
                    "proxy_description": cohort["market_description"],
                    "proxy_market_p50": float(cohort["market_p50"]),
                    "proxy_medicare_rate": float(cohort["medicare_rate"]),
                    "adjustment_factor": factor,
                    "default_adjustment_factor": rule["adjustment_factor"],
                    "factor_basis": rule["factor_basis"],
                    "estimated_market_rate": est,
                    "resolution_methodology": rule["resolution_methodology"],
                    "confidence_tier": rule["confidence_tier"],
                    "proxy_mrf_citation": cite_id,
                    "proxy_citation_hospital": cite_hosp,
                })
            else:
                in_warehouse = self._rows("SELECT COUNT(*) FROM mrf_warehouse WHERE cpt_code = ?", [r["cpt_code"]])[0][0]
                reason = "MODIFIER_MISMATCH_GLOBAL_ONLY" if in_warehouse and r["modifier"] != "None" else (
                    "PAYER_NOT_IN_WAREHOUSE" if in_warehouse else "NO_CROSSWALK_DEFINED")
                rec.update({
                    "dnf_reason_code": reason,
                    "diagnostic_explanation": "No playbook crosswalk exists yet; routed to SE manual review and data-engineering feedback loop.",
                    "proxy_cpt": "",
                    "proxy_description": "",
                    "proxy_market_p50": np.nan,
                    "proxy_medicare_rate": np.nan,
                    "adjustment_factor": np.nan,
                    "default_adjustment_factor": np.nan,
                    "factor_basis": "",
                    "estimated_market_rate": np.nan,
                    "resolution_methodology": "Manual review required",
                    "confidence_tier": "Unresolved — Manual Review",
                    "proxy_mrf_citation": "",
                    "proxy_citation_hospital": "",
                })
            gap = rec["estimated_market_rate"] - rec["prospect_rate"]
            rec["unit_recovery_gap"] = 0.0 if pd.isna(gap) else max(0.0, float(gap))
            rec["annual_dnf_recovery"] = rec["unit_recovery_gap"] * int(rec["annual_volume"])
            rec["current_annual_rev"] = float(rec["prospect_rate"]) * int(rec["annual_volume"])
            records.append(rec)
        cols = list(dnf_df.columns) + [
            "dnf_reason_code", "diagnostic_explanation", "proxy_cpt", "proxy_description", "proxy_market_p50",
            "proxy_medicare_rate", "adjustment_factor", "default_adjustment_factor", "factor_basis",
            "estimated_market_rate", "resolution_methodology", "confidence_tier", "proxy_mrf_citation",
            "proxy_citation_hospital", "unit_recovery_gap", "annual_dnf_recovery", "current_annual_rev"]
        return pd.DataFrame(records, columns=cols).reset_index(drop=True)

    # ------------------------------------------------------------------ scenarios
    @staticmethod
    def scenario_gap(validated_df: pd.DataFrame, target_benchmark: str, floor_pct: float = DEFAULT_FLOOR_PCT) -> pd.Series:
        """Annual $ gap per validated line for the chosen negotiation target."""
        if validated_df.empty:
            return pd.Series(dtype=float)
        if target_benchmark == TARGET_P75:
            target = validated_df["market_p75"]
        elif target_benchmark == TARGET_FLOOR:
            target = validated_df["medicare_rate"] * floor_pct / 100
        else:
            target = validated_df["market_p50"]
        return np.maximum(0.0, target - validated_df["prospect_rate"]) * validated_df["annual_volume"]

    def simulate_negotiation_scenario(
        self,
        validated_df: pd.DataFrame,
        dnf_df: pd.DataFrame,
        target_benchmark: str = TARGET_P50,
        realization_rate: float = DEFAULT_REALIZATION,
        include_dnf_recovery: bool = True,
        annual_trek_subscription: float = DEFAULT_SUBSCRIPTION,
        floor_pct: float = DEFAULT_FLOOR_PCT,
        total_lines: int | None = None,
    ) -> dict:
        return compute_kpis(validated_df, dnf_df, target_benchmark, realization_rate, include_dnf_recovery,
                            annual_trek_subscription, floor_pct, total_lines)


def compute_kpis(
    validated_df: pd.DataFrame,
    dnf_df: pd.DataFrame,
    target_benchmark: str = TARGET_P50,
    realization_rate: float = DEFAULT_REALIZATION,
    include_dnf_recovery: bool = True,
    annual_trek_subscription: float = DEFAULT_SUBSCRIPTION,
    floor_pct: float = DEFAULT_FLOOR_PCT,
    total_lines: int | None = None,
) -> dict:
    v, d = validated_df, dnf_df
    matched = len(v)
    dnf_n = len(d)
    total = total_lines if total_lines is not None else matched + dnf_n
    gap = TrekValidationEngine.scenario_gap(v, target_benchmark, floor_pct)
    validated_gap = float(gap.sum()) if len(gap) else 0.0
    dnf_recovery = float(d["annual_dnf_recovery"].sum()) if dnf_n else 0.0
    dnf_resolved = int(d["estimated_market_rate"].notna().sum()) if dnf_n else 0
    addressable = validated_gap + (dnf_recovery if include_dnf_recovery else 0.0)
    realized = addressable * realization_rate
    medicare_w = float((v["medicare_rate"] * v["annual_volume"]).sum()) if matched else 0.0
    prospect_pct = float((v["prospect_rate"] * v["annual_volume"]).sum()) / medicare_w * 100 if medicare_w else 0.0
    market_pct = float((v["market_p50"] * v["annual_volume"]).sum()) / medicare_w * 100 if medicare_w else 0.0
    current_rev = (float(v["current_annual_rev"].sum()) if matched else 0.0) + (
        float(d["current_annual_rev"].sum()) if dnf_n else 0.0)

    by_sl = pd.DataFrame()
    by_payer = pd.DataFrame()
    if matched:
        tmp = v.assign(scenario_gap=gap)
        by_sl = tmp.groupby("service_line", as_index=False)["scenario_gap"].sum().sort_values("scenario_gap", ascending=False)
        by_payer = tmp.groupby("payer_name", as_index=False)["scenario_gap"].sum().sort_values("scenario_gap", ascending=False)

    return {
        "target_benchmark": target_benchmark,
        "realization_rate": realization_rate,
        "include_dnf_recovery": include_dnf_recovery,
        "annual_trek_subscription": annual_trek_subscription,
        "floor_pct": floor_pct,
        "total_lines": total,
        "matched_lines": matched,
        "dnf_lines": dnf_n,
        "dnf_resolved": dnf_resolved,
        "match_rate_pct": matched / total * 100 if total else 0.0,
        "coverage_with_dnf_pct": (matched + dnf_resolved) / total * 100 if total else 0.0,
        "current_contracted_revenue": current_rev,
        "validated_uplift_p50": float(v["annual_uplift_p50"].sum()) if matched else 0.0,
        "validated_uplift_p75": float(v["annual_uplift_p75"].sum()) if matched else 0.0,
        "validated_scenario_gap": validated_gap,
        "dnf_recovery": dnf_recovery,
        "total_addressable": addressable,
        "realized_uplift": realized,
        "year1_net_benefit": realized - annual_trek_subscription,
        "roi_multiple": realized / annual_trek_subscription if annual_trek_subscription else 0.0,
        "payback_months": annual_trek_subscription / realized * 12 if realized else float("inf"),
        "three_year_net_value": realized * 3 - annual_trek_subscription * 3,
        "prospect_pct_medicare": prospect_pct,
        "market_pct_medicare": market_pct,
        "flag_counts": {f: int((v["variance_flag"] == f).sum()) if matched else 0 for f in FLAG_ORDER},
        "by_service_line": by_sl,
        "by_payer": by_payer,
    }


def pareto_table(validated_df: pd.DataFrame, gap: pd.Series) -> pd.DataFrame:
    """CPT-level ranking (payers combined) with cumulative share of the gap."""
    if validated_df.empty:
        return pd.DataFrame(columns=["cpt_code", "description", "annual_gap", "cumulative_share_pct", "rank"])
    t = (validated_df.assign(annual_gap=gap)
         .groupby(["cpt_code", "description"], as_index=False)["annual_gap"].sum()
         .sort_values("annual_gap", ascending=False).reset_index(drop=True))
    t = t[t["annual_gap"] > 0].reset_index(drop=True)
    total = t["annual_gap"].sum()
    t["cumulative_share_pct"] = t["annual_gap"].cumsum() / total * 100 if total else 0.0
    t["rank"] = np.arange(1, len(t) + 1)
    return t


def sensitivity_matrix(validated_df: pd.DataFrame, dnf_df: pd.DataFrame, subscription: float,
                       include_dnf: bool = True, floor_pct: float = 190.0) -> pd.DataFrame:
    rows = []
    for tgt, label in [(TARGET_P50, "Market P50"), (TARGET_P75, "Market P75"), (TARGET_FLOOR, f"{floor_pct:.0f}% of Medicare floor")]:
        for r in (0.25, 0.50, 0.75, 1.00):
            k = compute_kpis(validated_df, dnf_df, tgt, r, include_dnf, subscription, floor_pct)
            rows.append({
                "Target": label,
                "Realization": f"{r:.0%}",
                "Annual Uplift ($)": k["realized_uplift"],
                "Net Year-1 Benefit ($)": k["year1_net_benefit"],
                "ROI Multiple (x)": k["roi_multiple"],
                "Payback (months)": k["payback_months"],
                "3-Year Net Value ($)": k["three_year_net_value"],
            })
    return pd.DataFrame(rows)
