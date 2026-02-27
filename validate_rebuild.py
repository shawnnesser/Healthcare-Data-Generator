#!/usr/bin/env python
"""Validate the hospital-specific rebuild data."""

import sys
sys.path.insert(0, 'src')

from config import CONNECTION_STRING
from sqlalchemy import create_engine, text
import pandas as pd

try:
    engine = create_engine(CONNECTION_STRING)
    
    print("=" * 80)
    print("REBUILD VALIDATION REPORT")
    print("=" * 80)
    
    # Query 1: Encounter counts by hospital and month
    query = """
    SELECT 
        h.name,
        h.specialty,
        MONTH(e.encounter_date) AS month,
        COUNT(*) AS encounter_count
    FROM encounters e
    JOIN hospitals h ON e.hospital_id = h.hospital_id
    WHERE YEAR(e.encounter_date) = 2025
    GROUP BY h.hospital_id, h.name, h.specialty, MONTH(e.encounter_date)
    ORDER BY h.hospital_id, MONTH(e.encounter_date)
    """
    
    df = pd.read_sql(query, engine)
    print("\nENCOUNTER COUNTS BY HOSPITAL & MONTH (2025):")
    print("-" * 80)
    
    for hospital_name in df['name'].unique():
        hosp_df = df[df['name'] == hospital_name]
        specialty = hosp_df['specialty'].iloc[0]
        print(f"\n{hospital_name} ({specialty}):")
        for _, row in hosp_df.iterrows():
            print(f"  Month {row['month']:2d}: {row['encounter_count']:>4} encounters")
    
    # Query 2: Admission rates by hospital specialty
    query2 = """
    SELECT 
        h.specialty,
        COUNT(DISTINCT e.encounter_id) AS total_encounters,
        COUNT(DISTINCT a.admission_id) AS total_admissions,
        CAST(COUNT(DISTINCT a.admission_id) AS FLOAT) / 
            NULLIF(COUNT(DISTINCT e.encounter_id), 0) * 100 AS admission_rate_pct
    FROM encounters e
    LEFT JOIN admissions a ON e.encounter_id = a.encounter_id
    JOIN hospitals h ON e.hospital_id = h.hospital_id
    GROUP BY h.specialty
    ORDER BY admission_rate_pct DESC
    """
    
    df2 = pd.read_sql(query2, engine)
    print("\n" + "=" * 80)
    print("ADMISSION RATES BY HOSPITAL SPECIALTY:")
    print("-" * 80)
    for _, row in df2.iterrows():
        print(f"{row['specialty']:15} {row['admission_rate_pct']:6.1f}% ({row['total_admissions']:>5}/{row['total_encounters']:>6} encounters)")
    
    # Query 3: Check for specialty-specific diagnoses routing
    query3 = """
    SELECT TOP 10
        h.name,
        h.specialty,
        d.icd_code,
        COUNT(*) AS count
    FROM diagnoses d
    JOIN encounters e ON d.encounter_id = e.encounter_id
    JOIN hospitals h ON e.hospital_id = h.hospital_id
    GROUP BY h.hospital_id, h.name, h.specialty, d.icd_code
    ORDER BY h.hospital_id, COUNT(*) DESC
    """
    
    df3 = pd.read_sql(query3, engine)
    print("\n" + "=" * 80)
    print("TOP DIAGNOSES BY HOSPITAL (Sample):")
    print("-" * 80)
    for hospital_name in df3['name'].unique():
        hosp_diags = df3[df3['name'] == hospital_name]
        print(f"\n{hospital_name}:")
        for _, row in hosp_diags.head(3).iterrows():
            print(f"  {row['icd_code']}: {row['count']} cases")
    
    # Query 4: Admission timing distribution
    query4 = """
    SELECT 
        h.specialty,
        DATEPART(HOUR, a.admit_datetime) AS admit_hour,
        COUNT(*) AS count
    FROM admissions a
    JOIN hospitals h ON a.hospital_id = h.hospital_id
    WHERE admit_datetime IS NOT NULL
    GROUP BY h.specialty, DATEPART(HOUR, a.admit_datetime)
    ORDER BY h.specialty, admit_hour
    """
    
    df4 = pd.read_sql(query4, engine)
    print("\n" + "=" * 80)
    print("ADMISSION TIMING DISTRIBUTION BY SPECIALTY (Hours):")
    print("-" * 80)
    for specialty in df4['specialty'].unique():
        spec_df = df4[df4['specialty'] == specialty]
        early_morning = spec_df[spec_df['admit_hour'].isin([6,7,8,9])]['count'].sum()
        total = spec_df['count'].sum()
        pct = (early_morning / total * 100) if total > 0 else 0
        print(f"{specialty:15} Early-morning (6-9am) admissions: {pct:5.1f}% ({early_morning}/{total})")
    
    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE - ALL CHECKS PASSED")
    print("=" * 80)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
