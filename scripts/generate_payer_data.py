#!/usr/bin/env python3
"""
Healthcare Payer Simulated Data Generator
==========================================
Generates a daily-grain CSV of healthcare payer analytics data across
10 Contoso hospitals, 8 service lines, and 5 payer types.

Output: data/healthcare_payer_data.csv
Usage:  python scripts/generate_payer_data.py
"""

import os
import sys
import random
import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Reproducible randomness
# ---------------------------------------------------------------------------
SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# ---------------------------------------------------------------------------
# Output path — resolve relative to the repo root regardless of cwd
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(REPO_ROOT, "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "healthcare_payer_data.csv")

# ---------------------------------------------------------------------------
# Date range
# ---------------------------------------------------------------------------
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2025, 12, 31)

# ---------------------------------------------------------------------------
# Hospitals (from existing main.py HOSPITALS list)
# ---------------------------------------------------------------------------
HOSPITALS = [
    {"hospital_id": 1,  "name": "Contoso Medical Center",       "bed_count": 750, "specialty": "general"},
    {"hospital_id": 2,  "name": "Contoso University Hospital",  "bed_count": 650, "specialty": "general"},
    {"hospital_id": 3,  "name": "Contoso General Hospital",     "bed_count": 550, "specialty": "general"},
    {"hospital_id": 4,  "name": "Contoso Regional Hospital",    "bed_count": 400, "specialty": "general"},
    {"hospital_id": 5,  "name": "Contoso Community Hospital",   "bed_count": 350, "specialty": "general"},
    {"hospital_id": 6,  "name": "Contoso Heart Institute",      "bed_count": 280, "specialty": "cardiac"},
    {"hospital_id": 7,  "name": "Contoso Children's Hospital",  "bed_count": 320, "specialty": "pediatric"},
    {"hospital_id": 8,  "name": "Contoso Cancer Center",        "bed_count": 200, "specialty": "cancer"},
    {"hospital_id": 9,  "name": "Contoso Rehab Center",         "bed_count": 180, "specialty": "rehab"},
    {"hospital_id": 10, "name": "Contoso Diagnostic Center",    "bed_count": 120, "specialty": "specialty"},
]

# ---------------------------------------------------------------------------
# Monthly seasonality multipliers (from existing config.py — Jan=index 0)
# ---------------------------------------------------------------------------
HOSPITAL_MONTHLY = {
    "general":   [1.12, 1.08, 0.98, 0.92, 0.88, 0.85, 0.90, 0.93, 0.95, 1.00, 1.08, 1.18],
    "cardiac":   [1.38, 1.32, 1.08, 0.92, 0.85, 0.88, 0.87, 0.89, 0.95, 1.02, 1.18, 1.28],
    "pediatric": [1.35, 1.28, 0.95, 0.82, 0.78, 0.75, 0.85, 0.88, 0.92, 0.98, 1.18, 1.26],
    "cancer":    [1.05, 1.03, 1.02, 1.01, 0.98, 0.95, 0.94, 0.96, 1.00, 1.02, 1.04, 1.06],
    "rehab":     [1.04, 1.02, 1.08, 1.10, 1.01, 0.98, 0.92, 0.95, 1.05, 1.12, 1.06, 1.00],
    "specialty": [1.02, 1.01, 1.00, 0.99, 0.98, 0.96, 0.94, 0.96, 1.00, 1.02, 1.04, 1.05],
}

# Day-of-week multipliers (Mon=0 … Sun=6)  — from existing config.py
DAY_OF_WEEK_MULT = [1.06, 0.98, 0.96, 0.96, 1.00, 1.03, 1.02]

# Year-over-year growth (2025 vs 2024)
YOY_GROWTH = 1.025  # +2.5 %

# ---------------------------------------------------------------------------
# Payer mix  — from existing config.py
# ---------------------------------------------------------------------------
PAYER_MARKET_SHARE = {
    "Medicare":    0.36,
    "Medicaid":    0.20,
    "Commercial":  0.35,
    "Uninsured":   0.05,
    "Other":       0.04,
}

SPECIALTY_PAYER_ADJUST = {
    "pediatric": {"Medicaid": 1.35, "Commercial": 0.85, "Medicare": 0.20},
    "cardiac":   {"Medicare": 1.10, "Commercial": 1.05, "Medicaid": 0.90},
    "cancer":    {"Commercial": 1.10, "Medicare": 1.05, "Medicaid": 0.90},
    "rehab":     {"Medicare": 1.20, "Medicaid": 0.95, "Commercial": 0.90},
    "general":   {},
    "specialty": {},
}

# ---------------------------------------------------------------------------
# Service line reference data
# ---------------------------------------------------------------------------
SERVICE_LINES = {
    "Emergency Medicine": {
        "base_cmi": 1.20, "base_acuity": 3.2, "base_revenue": 4500,
        "admission_rate": 0.20, "base_los": 1.8, "readmit_rate": 0.08,
    },
    "Cardiology": {
        "base_cmi": 2.10, "base_acuity": 3.8, "base_revenue": 18000,
        "admission_rate": 0.72, "base_los": 4.5, "readmit_rate": 0.12,
    },
    "Orthopedics": {
        "base_cmi": 1.80, "base_acuity": 2.8, "base_revenue": 14000,
        "admission_rate": 0.35, "base_los": 3.2, "readmit_rate": 0.05,
    },
    "Oncology": {
        "base_cmi": 2.40, "base_acuity": 3.5, "base_revenue": 22000,
        "admission_rate": 0.96, "base_los": 5.8, "readmit_rate": 0.14,
    },
    "General Medicine": {
        "base_cmi": 1.00, "base_acuity": 2.2, "base_revenue": 6000,
        "admission_rate": 0.18, "base_los": 3.0, "readmit_rate": 0.10,
    },
    "Pediatrics": {
        "base_cmi": 0.90, "base_acuity": 2.0, "base_revenue": 3800,
        "admission_rate": 0.12, "base_los": 1.2, "readmit_rate": 0.04,
    },
    "Neurology": {
        "base_cmi": 1.60, "base_acuity": 3.0, "base_revenue": 12000,
        "admission_rate": 0.30, "base_los": 3.8, "readmit_rate": 0.09,
    },
    "Rehabilitation": {
        "base_cmi": 0.80, "base_acuity": 1.5, "base_revenue": 8000,
        "admission_rate": 0.85, "base_los": 12.0, "readmit_rate": 0.06,
    },
}

# Which service lines each hospital offers + share of that hospital's daily encounters
FACILITY_SERVICE_LINES = {
    # General hospitals (1-5): broad mix
    1: {"Emergency Medicine": 0.25, "Cardiology": 0.15, "Orthopedics": 0.12,
        "General Medicine": 0.25, "Neurology": 0.10, "Rehabilitation": 0.13},
    2: {"Emergency Medicine": 0.25, "Cardiology": 0.12, "Orthopedics": 0.15,
        "General Medicine": 0.25, "Neurology": 0.13, "Rehabilitation": 0.10},
    3: {"Emergency Medicine": 0.28, "Cardiology": 0.10, "Orthopedics": 0.12,
        "General Medicine": 0.30, "Neurology": 0.08, "Rehabilitation": 0.12},
    4: {"Emergency Medicine": 0.30, "General Medicine": 0.35,
        "Orthopedics": 0.15, "Neurology": 0.08, "Rehabilitation": 0.12},
    5: {"Emergency Medicine": 0.32, "General Medicine": 0.38,
        "Orthopedics": 0.12, "Rehabilitation": 0.18},
    # Heart Institute
    6: {"Cardiology": 0.70, "Rehabilitation": 0.30},
    # Children's Hospital
    7: {"Pediatrics": 0.60, "Emergency Medicine": 0.40},
    # Cancer Center
    8: {"Oncology": 1.00},
    # Rehab Center
    9: {"Rehabilitation": 1.00},
    # Diagnostic Center (outpatient only — smaller volume, no inpatient)
    10: {"General Medicine": 1.00},
}

# ---------------------------------------------------------------------------
# Payer-specific financial behaviour
# ---------------------------------------------------------------------------
PAYER_PROFILES = {
    "Medicare": {
        "cmi_mult": 1.15,          # older, sicker → higher CMI
        "acuity_mult": 1.10,
        "allowed_pct": 0.55,       # allowed = 55 % of gross (Medicare fee schedule)
        "collection_rate": 0.80,   # 80 % of allowed amount collected
        "denial_rate": 0.06,       # 6 % denial rate
        "los_mult": 1.15,          # longer stays
    },
    "Medicaid": {
        "cmi_mult": 1.05,
        "acuity_mult": 1.05,
        "allowed_pct": 0.42,
        "collection_rate": 0.65,
        "denial_rate": 0.10,
        "los_mult": 1.10,
    },
    "Commercial": {
        "cmi_mult": 0.90,
        "acuity_mult": 0.92,
        "allowed_pct": 0.72,
        "collection_rate": 0.90,
        "denial_rate": 0.08,
        "los_mult": 0.90,
    },
    "Uninsured": {
        "cmi_mult": 1.00,
        "acuity_mult": 1.00,
        "allowed_pct": 1.00,       # no contractual discount
        "collection_rate": 0.25,   # high bad-debt
        "denial_rate": 0.00,       # no payer to deny — bad debt instead
        "los_mult": 0.85,          # tend to leave sooner
    },
    "Other": {
        "cmi_mult": 1.00,
        "acuity_mult": 1.00,
        "allowed_pct": 0.60,
        "collection_rate": 0.75,
        "denial_rate": 0.07,
        "los_mult": 1.00,
    },
}

# ---------------------------------------------------------------------------
# Helper: compute adjusted payer shares for a given hospital specialty
# ---------------------------------------------------------------------------
def get_payer_shares(specialty: str) -> dict:
    """Return normalised {payer: share} for a hospital specialty."""
    adjustments = SPECIALTY_PAYER_ADJUST.get(specialty, {})
    raw = {}
    for payer, base in PAYER_MARKET_SHARE.items():
        raw[payer] = base * adjustments.get(payer, 1.0)
    total = sum(raw.values())
    return {p: v / total for p, v in raw.items()}


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------
def generate_payer_data() -> pd.DataFrame:
    """Build the full dataset and return as a DataFrame."""

    rows: list[dict] = []
    current = START_DATE

    total_days = (END_DATE - START_DATE).days + 1
    print(f"Generating {total_days} days of data across {len(HOSPITALS)} facilities …")

    while current <= END_DATE:
        month_idx = current.month - 1          # 0-based
        dow = current.weekday()                # 0=Mon … 6=Sun
        year_mult = YOY_GROWTH if current.year >= 2025 else 1.0

        for hosp in HOSPITALS:
            hid = hosp["hospital_id"]
            specialty = hosp["specialty"]
            bed_count = hosp["bed_count"]

            # Base daily encounter volume ∝ bed_count
            base_daily = bed_count * 0.08

            # Seasonality
            monthly_mult = HOSPITAL_MONTHLY[specialty][month_idx]
            dow_mult = DAY_OF_WEEK_MULT[dow]

            payer_shares = get_payer_shares(specialty)

            for svc_name, svc_share in FACILITY_SERVICE_LINES[hid].items():
                svc = SERVICE_LINES[svc_name]

                for payer, payer_share in payer_shares.items():
                    pp = PAYER_PROFILES[payer]

                    # --- Encounter volume ---
                    raw_enc = (
                        base_daily
                        * svc_share
                        * payer_share
                        * monthly_mult
                        * dow_mult
                        * year_mult
                    )
                    # Add ±8 % noise
                    noise = np.random.normal(1.0, 0.08)
                    raw_enc *= max(noise, 0.5)

                    encounters = max(1, int(round(raw_enc)))

                    # --- Acuity & CMI ---
                    acuity = svc["base_acuity"] * pp["acuity_mult"] * np.random.normal(1.0, 0.04)
                    acuity = round(np.clip(acuity, 1.0, 5.0), 2)

                    cmi = svc["base_cmi"] * pp["cmi_mult"] * np.random.normal(1.0, 0.05)
                    cmi = round(max(0.50, cmi), 2)

                    # --- Revenue ---
                    gross_per_enc = svc["base_revenue"] * (cmi / svc["base_cmi"]) * np.random.normal(1.0, 0.06)
                    gross_revenue = round(max(encounters * gross_per_enc, 0), 2)

                    allowed_amount = round(gross_revenue * pp["allowed_pct"], 2)
                    adjustments = round(gross_revenue - allowed_amount, 2)
                    paid_amount = round(allowed_amount * pp["collection_rate"], 2)

                    # --- Denials ---
                    denial_rate = pp["denial_rate"] * np.random.normal(1.0, 0.15)
                    denial_rate = round(np.clip(denial_rate, 0.0, 0.40), 4)
                    denials = max(0, int(round(encounters * denial_rate)))

                    # --- Inpatient metrics ---
                    discharges = max(0, int(round(encounters * svc["admission_rate"]
                                                  * np.random.normal(1.0, 0.06))))
                    avg_los = svc["base_los"] * pp["los_mult"] * np.random.normal(1.0, 0.08)
                    avg_los = round(max(0.5, avg_los), 1)
                    patient_days = max(0, int(round(discharges * avg_los)))

                    readmit_rate = svc["readmit_rate"] * np.random.normal(1.0, 0.15)
                    readmit_rate = round(np.clip(readmit_rate, 0.0, 0.35), 4)
                    readmissions = max(0, min(discharges, int(round(discharges * readmit_rate))))

                    rows.append({
                        "Date":               current.strftime("%Y-%m-%d"),
                        "Facility_ID":        hid,
                        "Facility":           hosp["name"],
                        "Specialty":          specialty.title(),
                        "Service_Line":       svc_name,
                        "Payer":              payer,
                        "Encounters":         encounters,
                        "Acuity_Index":       acuity,
                        "CMI":                cmi,
                        "Gross_Revenue":      gross_revenue,
                        "Allowed_Amount":     allowed_amount,
                        "Paid_Amount":        paid_amount,
                        "Adjustments":        adjustments,
                        "Denials":            denials,
                        "Denial_Rate":        denial_rate,
                        "Patient_Days":       patient_days,
                        "Discharges":         discharges,
                        "Avg_Length_of_Stay": avg_los,
                        "Readmissions":       readmissions,
                        "Readmission_Rate":   readmit_rate,
                    })

        current += timedelta(days=1)

    df = pd.DataFrame(rows)
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Healthcare Payer Data Generator")
    print("=" * 60)

    df = generate_payer_data()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅  Wrote {len(df):,} rows to {OUTPUT_FILE}")

    # Summary
    print(f"\n--- Summary ---")
    print(f"Date range       : {df['Date'].min()} → {df['Date'].max()}")
    print(f"Facilities       : {df['Facility'].nunique()}")
    print(f"Service Lines    : {df['Service_Line'].nunique()}  {sorted(df['Service_Line'].unique())}")
    print(f"Payers           : {df['Payer'].nunique()}  {sorted(df['Payer'].unique())}")
    print(f"Total rows       : {len(df):,}")
    print(f"Total encounters : {df['Encounters'].sum():,}")
    print(f"Total gross rev  : ${df['Gross_Revenue'].sum():,.0f}")
    print(f"Total paid       : ${df['Paid_Amount'].sum():,.0f}")
    print(f"File size        : {os.path.getsize(OUTPUT_FILE) / 1024 / 1024:.1f} MB")

    # Spot-check table
    print(f"\n--- Avg metrics by Payer ---")
    payer_agg = df.groupby("Payer").agg(
        Avg_Encounters=("Encounters", "mean"),
        Avg_CMI=("CMI", "mean"),
        Avg_Acuity=("Acuity_Index", "mean"),
        Avg_Denial_Rate=("Denial_Rate", "mean"),
        Avg_LOS=("Avg_Length_of_Stay", "mean"),
    ).round(3)
    print(payer_agg.to_string())

    print(f"\n--- Avg encounters by Service Line ---")
    svc_agg = df.groupby("Service_Line").agg(
        Avg_Enc=("Encounters", "mean"),
        Avg_CMI=("CMI", "mean"),
        Avg_Revenue=("Gross_Revenue", "mean"),
    ).round(2)
    print(svc_agg.to_string())

    # Seasonality check: Jan vs Jul encounters for cardiac
    cardiac = df[df["Service_Line"] == "Cardiology"]
    jan_enc = cardiac[cardiac["Date"].str.startswith("2024-01")]["Encounters"].sum()
    jul_enc = cardiac[cardiac["Date"].str.startswith("2024-07")]["Encounters"].sum()
    print(f"\n--- Seasonality check (Cardiology) ---")
    print(f"Jan 2024 encounters: {jan_enc:,}  |  Jul 2024 encounters: {jul_enc:,}  |  Ratio: {jan_enc/max(jul_enc,1):.2f}x")

    print("\nDone ✓")


if __name__ == "__main__":
    main()
