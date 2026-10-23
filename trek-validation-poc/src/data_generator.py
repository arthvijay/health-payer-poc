"""Deterministic synthetic data for the POC (seed 42).

Writes three artifacts into data/:
  * market_mrf_warehouse.csv   - normalized slice of TiC MRF negotiated rates (~620 rows)
  * prospect_fee_schedule.csv  - 60-line synthetic prospect fee schedule (52 matchable + 8 DNF)
  * openpayer_policies.json    - simulated payer policy intelligence per CPT

All entities are fictional. Rates are synthetic but shaped like real commercial
contracting (145%-330% of Medicare, payer/hospital spread).

Run:  python -m src.data_generator
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MRF_PATH = DATA_DIR / "market_mrf_warehouse.csv"
PROSPECT_PATH = DATA_DIR / "prospect_fee_schedule.csv"
POLICIES_PATH = DATA_DIR / "openpayer_policies.json"

PROSPECT_NAME = "Summit Regional Health System (Synthetic Validation File)"

# Fictional peer systems. Swap names here if you want different peers on screen.
PEER_HOSPITALS = [
    ("Bayview Metro Medical Center", "84-1029384", 1.07),
    ("TriCounty Regional Hospital", "84-2290117", 0.97),
    ("Valley Crest Medical", "84-3378201", 1.12),
    ("Covenant Ridge Health Center", "84-4410923", 0.91),
    ("St. Anselm Vincent Hospital", "84-5582046", 1.01),
]

# payer -> relative rate posture
PAYERS = {
    "UnitedHealthcare (UHC)": 1.00,
    "Aetna": 1.04,
    "Anthem BCBS": 0.95,
    "Cigna": 1.08,
}
PROSPECT_PAYERS = ["UnitedHealthcare (UHC)", "Aetna"]

# service line -> center multiple of Medicare
SERVICE_LINE_CENTER = {
    "Orthopedics": 2.25,
    "Radiology & Imaging": 2.55,
    "Cardiology": 2.30,
    "Gastroenterology": 2.15,
    "Emergency & E/M": 1.95,
}

# cpt, description, service line, medicare rate, billing class
CPT_CATALOG = [
    ("27447", "Total Knee Arthroplasty", "Orthopedics", 1320, "professional"),
    ("27130", "Total Hip Arthroplasty", "Orthopedics", 1290, "professional"),
    ("29881", "Knee Arthroscopy/Meniscectomy", "Orthopedics", 585, "professional"),
    ("29827", "Arthroscopic Rotator Cuff Repair", "Orthopedics", 940, "professional"),
    ("22551", "Cervical Discectomy & Fusion", "Orthopedics", 1580, "professional"),
    ("70553", "MRI Brain w/ & w/o Contrast", "Radiology & Imaging", 410, "institutional"),
    ("73721", "MRI Lower Extremity Joint w/o Contrast", "Radiology & Imaging", 265, "institutional"),
    ("74177", "CT Abdomen & Pelvis w/ Contrast", "Radiology & Imaging", 315, "institutional"),
    ("71260", "CT Thorax w/ Contrast", "Radiology & Imaging", 245, "institutional"),
    ("76700", "Ultrasound Abdominal Complete", "Radiology & Imaging", 125, "institutional"),
    ("77067", "Screening Mammography Bilateral", "Radiology & Imaging", 140, "institutional"),
    ("93306", "Echocardiogram Transthoracic Complete", "Cardiology", 230, "institutional"),
    ("93000", "Electrocardiogram Complete", "Cardiology", 25, "professional"),
    ("93458", "Left Heart Catheterization", "Cardiology", 1080, "institutional"),
    ("33249", "Insertion of Pacemaker/ICD Defibrillator", "Cardiology", 1650, "institutional"),
    ("45378", "Diagnostic Colonoscopy", "Gastroenterology", 355, "institutional"),
    ("45380", "Colonoscopy w/ Biopsy", "Gastroenterology", 435, "institutional"),
    ("43239", "Upper GI Endoscopy w/ Biopsy", "Gastroenterology", 310, "institutional"),
    ("47562", "Laparoscopic Cholecystectomy", "Gastroenterology", 780, "professional"),
    ("99283", "ED Visit Level 3", "Emergency & E/M", 145, "institutional"),
    ("99284", "ED Visit Level 4", "Emergency & E/M", 265, "institutional"),
    ("99285", "ED Visit Level 5", "Emergency & E/M", 420, "institutional"),
    ("99213", "Office Visit Est Level 3", "Emergency & E/M", 92, "professional"),
    ("99214", "Office Visit Est Level 4", "Emergency & E/M", 130, "professional"),
    ("99215", "Office Visit Est Level 5", "Emergency & E/M", 185, "professional"),
    ("36415", "Routine Venipuncture", "Emergency & E/M", 9, "institutional"),
]

# Target pricing posture for each matched prospect line: (UHC tier, Aetna tier)
# C = critical under (-24..-36%), M = moderate under (-9..-17%), P = competitive (±3%), A = above (+8..+16%)
TIER_PLAN = {
    "27447": ("C", "C"), "27130": ("C", "M"), "29881": ("M", "P"), "29827": ("C", "M"), "22551": ("M", "A"),
    "70553": ("C", "C"), "73721": ("M", "C"), "74177": ("C", "M"), "71260": ("P", "M"), "76700": ("P", "A"),
    "77067": ("A", "P"),
    "93306": ("M", "P"), "93000": ("P", "A"), "93458": ("C", "M"), "33249": ("M", "C"),
    "45378": ("P", "M"), "45380": ("C", "C"), "43239": ("M", "P"), "47562": ("C", "A"),
    "99283": ("P", "M"), "99284": ("C", "M"), "99285": ("M", "P"), "99213": ("A", "P"), "99214": ("M", "P"),
    "99215": ("A", "A"), "36415": ("P", "M"),
}
TIER_RANGES = {"C": (-0.36, -0.24), "M": (-0.17, -0.09), "P": (-0.03, 0.03), "A": (0.08, 0.16)}

# Annual UHC volume per CPT; Aetna runs at ~80% of UHC volume.
ANNUAL_VOLUME = {
    "27447": 85, "27130": 65, "29881": 115, "29827": 70, "22551": 35,
    "70553": 370, "73721": 470, "74177": 810, "71260": 540, "76700": 660, "77067": 1440,
    "93306": 780, "93000": 2520, "93458": 125, "33249": 40,
    "45378": 420, "45380": 490, "43239": 455, "47562": 110,
    "99283": 1560, "99284": 1740, "99285": 900, "99213": 4320, "99214": 3360, "99215": 1020, "36415": 7200,
}
AETNA_VOLUME_SHARE = 0.8

# The four "Data Not Found" lines (rates are what the prospect currently gets paid).
DNF_LINES = [
    # cpt, modifier, description, service line, {payer: rate}, {payer: volume}
    ("27446", "None", "Unicompartmental (Partial) Knee Arthroplasty", "Orthopedics",
     {"UnitedHealthcare (UHC)": 1780.0, "Aetna": 1925.0}, {"UnitedHealthcare (UHC)": 55, "Aetna": 44}),
    ("70551", "26", "MRI Brain w/o Contrast — Professional Component", "Radiology & Imaging",
     {"UnitedHealthcare (UHC)": 298.0, "Aetna": 322.0}, {"UnitedHealthcare (UHC)": 520, "Aetna": 410}),
    ("45385", "None", "Colonoscopy w/ Lesion Removal by Snare", "Gastroenterology",
     {"UnitedHealthcare (UHC)": 810.0, "Aetna": 865.0}, {"UnitedHealthcare (UHC)": 430, "Aetna": 345}),
    ("0408T", "None", "Cat III Cardiac Ablation — Emerging Technology", "Cardiology",
     {"UnitedHealthcare (UHC)": 2350.0, "Aetna": 2480.0}, {"UnitedHealthcare (UHC)": 34, "Aetna": 26}),
]

CONTRACT_RENEWAL = {"UnitedHealthcare (UHC)": "2027-03-31", "Aetna": "2027-06-30"}


def build_market_warehouse(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    rec = 1001
    for hosp_name, ein, hosp_factor in PEER_HOSPITALS:
        for payer, payer_factor in PAYERS.items():
            for cpt, desc, sl, medicare, billing in CPT_CATALOG:
                plan_types = ["PPO"]
                if rng.random() < 0.20:
                    plan_types.append("HMO")
                for plan in plan_types:
                    plan_factor = 1.0 if plan == "PPO" else 0.93
                    noise = rng.lognormal(mean=0.0, sigma=0.08)
                    multiple = SERVICE_LINE_CENTER[sl] * hosp_factor * payer_factor * plan_factor * noise
                    multiple = float(np.clip(multiple, 1.45, 3.30))
                    rate = round(medicare * multiple, 2)
                    rows.append({
                        "mrf_record_id": f"MRF-{rec}",
                        "hospital_name": hosp_name,
                        "ein_npi": ein,
                        "payer_name": payer,
                        "plan_type": plan,
                        "cpt_code": cpt,
                        "description": desc,
                        "service_line": sl,
                        "billing_class": billing,
                        "medicare_rate": float(medicare),
                        "negotiated_rate": rate,
                        "pct_of_medicare": round(rate / medicare * 100, 1),
                        "mrf_schema_version": "2.0",
                        "last_updated": "2026-Q3",
                    })
                    rec += 1
    return pd.DataFrame(rows)


def build_prospect_schedule(rng: np.random.Generator, market: pd.DataFrame) -> pd.DataFrame:
    medians = market.groupby(["cpt_code", "payer_name"])["negotiated_rate"].median()
    rows = []
    line = 1
    for cpt, desc, sl, _medicare, _billing in CPT_CATALOG:
        for i, payer in enumerate(PROSPECT_PAYERS):
            lo, hi = TIER_RANGES[TIER_PLAN[cpt][i]]
            variance = rng.uniform(lo, hi)
            rate = round(float(medians[(cpt, payer)]) * (1 + variance), 2)
            vol = ANNUAL_VOLUME[cpt] if i == 0 else int(round(ANNUAL_VOLUME[cpt] * AETNA_VOLUME_SHARE))
            rows.append({
                "prospect_row_id": f"SRH-{line:03d}",
                "payer_name": payer,
                "cpt_code": cpt,
                "modifier": "None",
                "description": desc,
                "service_line": sl,
                "prospect_rate": rate,
                "annual_volume": vol,
                "contract_renewal_date": CONTRACT_RENEWAL[payer],
            })
            line += 1
    for cpt, mod, desc, sl, rates, vols in DNF_LINES:
        for payer in PROSPECT_PAYERS:
            rows.append({
                "prospect_row_id": f"SRH-{line:03d}",
                "payer_name": payer,
                "cpt_code": cpt,
                "modifier": mod,
                "description": desc,
                "service_line": sl,
                "prospect_rate": rates[payer],
                "annual_volume": vols[payer],
                "contract_renewal_date": CONTRACT_RENEWAL[payer],
            })
            line += 1
    return pd.DataFrame(rows)


def build_policies() -> dict:
    """Simulated OpenPayer-style policy intelligence (illustrative, not real payer policy)."""
    def card(prior_auth, necessity, change, denial_code, denial_reason, risk):
        return {
            "prior_auth_required": prior_auth,
            "medical_necessity_criteria": necessity,
            "policy_change_2026": change,
            "common_denial_code": denial_code,
            "common_denial_reason": denial_reason,
            "denial_risk": risk,
        }

    uhc, aetna = "UnitedHealthcare (UHC)", "Aetna"
    return {
        "_meta": {
            "source": "Simulated OpenPayer policy intelligence (synthetic, for demo only)",
            "as_of": "2026-Q3",
        },
        "27447": {
            uhc: card(True, "BMI < 40 documented; radiographic Kellgren-Lawrence grade 3-4; 6 weeks of documented conservative therapy (PT, NSAIDs, injections).",
                      "2026-04 bulletin: conservative-therapy documentation window extended from 3 to 6 weeks; site-of-service review now applies to outpatient TKA.",
                      "CO-197", "Precertification/authorization absent", "High"),
            aetna: card(True, "Failed 3 months non-surgical management; functional limitation score documented.",
                        "2026-01: added mandatory pre-op shared decision-making attestation.",
                        "CO-50", "Not deemed medically necessary", "Medium"),
        },
        "27446": {
            uhc: card(True, "Isolated single-compartment OA; intact ACL; ROM > 90°.",
                      "2026-02: partial knee moved under the same PA program as 27447.",
                      "CO-197", "Precertification/authorization absent", "High"),
            aetna: card(True, "Single-compartment disease confirmed by weight-bearing imaging.",
                        "No 2026 change.", "CO-50", "Not deemed medically necessary", "Medium"),
        },
        "29827": {
            uhc: card(True, "Full-thickness tear on MRI or failed 6 weeks of PT for partial tear.",
                      "2026-03: MRI report must be attached at PA submission.",
                      "CO-16", "Claim lacks information needed for adjudication", "Medium"),
            aetna: card(False, "Standard clinical documentation.", "No 2026 change.",
                        "CO-4", "Procedure code inconsistent with modifier", "Low"),
        },
        "70553": {
            uhc: card(True, "Advanced imaging PA via radiology benefit manager; neuro symptoms or known lesion follow-up.",
                      "2026-01: RBM program expanded to hospital outpatient departments.",
                      "CO-197", "Precertification/authorization absent", "High"),
            aetna: card(True, "Clinical decision support score required for ordering provider.",
                        "2026-05: CDS appropriate-use criteria enforcement began.",
                        "CO-50", "Not deemed medically necessary", "Medium"),
        },
        "45380": {
            uhc: card(False, "Screening-to-diagnostic conversion must be coded with PT modifier.",
                      "2026-02: tightened edits on screening-to-diagnostic conversion.",
                      "CO-4", "Procedure code inconsistent with modifier", "Medium"),
            aetna: card(False, "Standard.", "No 2026 change.",
                        "CO-16", "Claim lacks information needed for adjudication", "Low"),
        },
        "45385": {
            uhc: card(False, "Pathology report must support lesion removal by snare.",
                      "2026-02: same screening-conversion edits as 45380.",
                      "CO-4", "Procedure code inconsistent with modifier", "Medium"),
            aetna: card(False, "Standard.", "No 2026 change.",
                        "CO-16", "Claim lacks information needed for adjudication", "Low"),
        },
        "93458": {
            uhc: card(True, "Positive stress test or high-risk ACS presentation documented.",
                      "2026-06: elective diagnostic caths require non-invasive testing first.",
                      "CO-50", "Not deemed medically necessary", "High"),
            aetna: card(True, "Appropriate-use criteria score >= 7.",
                        "No 2026 change.", "CO-197", "Precertification/authorization absent", "Medium"),
        },
    }


def generate_all(data_dir: Path = DATA_DIR) -> dict[str, Path]:
    rng = np.random.default_rng(SEED)
    data_dir.mkdir(parents=True, exist_ok=True)
    market = build_market_warehouse(rng)
    prospect = build_prospect_schedule(rng, market)
    paths = {
        "mrf": data_dir / MRF_PATH.name,
        "prospect": data_dir / PROSPECT_PATH.name,
        "policies": data_dir / POLICIES_PATH.name,
    }
    market.to_csv(paths["mrf"], index=False)
    prospect.to_csv(paths["prospect"], index=False)
    paths["policies"].write_text(json.dumps(build_policies(), indent=2))
    return paths


def ensure_data(data_dir: Path = DATA_DIR) -> None:
    if not all((data_dir / p.name).exists() for p in (MRF_PATH, PROSPECT_PATH, POLICIES_PATH)):
        generate_all(data_dir)


if __name__ == "__main__":
    out = generate_all()
    m = pd.read_csv(out["mrf"], dtype={"cpt_code": str})
    p = pd.read_csv(out["prospect"], dtype={"cpt_code": str})
    print(f"market_mrf_warehouse.csv : {len(m)} rows")
    print(f"prospect_fee_schedule.csv: {len(p)} rows")
    print(f"openpayer_policies.json  : {len(json.loads(out['policies'].read_text())) - 1} CPT policy cards")
