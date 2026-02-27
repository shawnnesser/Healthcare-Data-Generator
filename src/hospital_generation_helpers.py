"""
Hospital-specific data generation enhancements.
Provides hospital-type-aware encounter, diagnosis, and occupancy generation.

Sources:
- CDC NHAMCS 2022
- American Heart Association Cardiovascular Disease Statistics
- NIH Seasonal Infectious Disease Patterns
- National Cancer Institute SEER Database
- APTA Rehabilitation Statistics
- ACEP ED Operations Data
"""

import pandas as pd
import random
from datetime import datetime, timedelta
from faker import Faker
import math

fake = Faker()

# Base configuration
HOSPITALS = [
    {'hospital_id': 1, 'name': 'Contoso Medical Center', 'bed_count': 750, 'specialty': 'general'},
    {'hospital_id': 2, 'name': 'Contoso University Hospital', 'bed_count': 650, 'specialty': 'general'},
    {'hospital_id': 3, 'name': 'Contoso General Hospital', 'bed_count': 550, 'specialty': 'general'},
    {'hospital_id': 4, 'name': 'Contoso Regional Hospital', 'bed_count': 400, 'specialty': 'general'},
    {'hospital_id': 5, 'name': 'Contoso Community Hospital', 'bed_count': 350, 'specialty': 'general'},
    {'hospital_id': 6, 'name': 'Contoso Heart Institute', 'bed_count': 280, 'specialty': 'cardiac'},
    {'hospital_id': 7, 'name': 'Contoso Children\'s Hospital', 'bed_count': 320, 'specialty': 'pediatric'},
    {'hospital_id': 8, 'name': 'Contoso Cancer Center', 'bed_count': 200, 'specialty': 'cancer'},
    {'hospital_id': 9, 'name': 'Contoso Rehab Center', 'bed_count': 180, 'specialty': 'rehab'},
    {'hospital_id': 10, 'name': 'Contoso Diagnostic Center', 'bed_count': 120, 'specialty': 'specialty'}
]

# Monthly encounter multipliers by hospital specialty (Jan-Dec)
HOSPITAL_MONTHLY = {
    'general': [1.12, 1.08, 0.98, 0.92, 0.88, 0.85, 0.90, 0.93, 0.95, 1.00, 1.08, 1.18],
    'pediatric': [1.35, 1.28, 0.95, 0.82, 0.78, 0.75, 0.85, 0.88, 0.92, 0.98, 1.18, 1.26],
    'cardiac': [1.38, 1.32, 1.08, 0.92, 0.85, 0.88, 0.87, 0.89, 0.95, 1.02, 1.18, 1.28],
    'cancer': [1.05, 1.03, 1.02, 1.01, 0.98, 0.95, 0.94, 0.96, 1.00, 1.02, 1.04, 1.06],
    'rehab': [1.04, 1.02, 1.08, 1.10, 1.01, 0.98, 0.92, 0.95, 1.05, 1.12, 1.06, 1.00],
    'specialty': [1.12, 1.08, 0.98, 0.92, 0.88, 0.85, 0.90, 0.93, 0.95, 1.00, 1.08, 1.18]
}

# Hourly ED occupancy (% of beds, 0-23)
HOURLY_ED_OCCUPANCY = [
    45, 42, 40, 38, 40, 45, 50, 58, 68, 75, 82, 85,  # 0-11
    88, 87, 88, 89, 88, 85, 82, 80, 78, 75, 70, 62   # 12-23
]

# Day-of-week occupancy multiplier
DAY_OCCUPANCY_MULT = {
    'Monday': 1.02, 'Tuesday': 1.01, 'Wednesday': 1.00,
    'Thursday': 1.02, 'Friday': 1.04, 'Saturday': 0.97, 'Sunday': 0.96
}

def get_hospital_monthly_encounters(hospital_specialty, month, base_encounters=300):
    """Calculate encounters for a hospital on a given month.
    
    Args:
        hospital_specialty: 'general', 'pediatric', 'cardiac', 'cancer', 'rehab', 'specialty'
        month: 1-12 (Jan-Dec)
        base_encounters: baseline daily encounters (300)
    
    Returns:
        Adjusted encounter count for the month
    """
    multiplier = HOSPITAL_MONTHLY[hospital_specialty][month - 1]  # Convert 1-12 to 0-11
    return int(base_encounters * multiplier)

def get_specialty_diagnoses(hospital_specialty):
    """Get diagnosis weights appropriate to hospital specialty.
    
    Pediatric: URI, otitis media, asthma, fractures, pneumonia
    Cardiac: ACS, heart failure, AFib, arrhythmia
    Cancer: acute leukemia, lymphoma, metastatic disease, febrile neutropenia
    Rehab: stroke sequelae, post-surgical, orthopedic rehab, cardiac rehab
    General: mixed diagnoses
    """
    diagnoses = {
        'pediatric': {
            'J00': 0.22, 'H66.001': 0.18, 'J45.9': 0.12, 'S72.1': 0.15, 'J18.9': 0.08,
            'A08.39': 0.10, 'R50.9': 0.08, 'G40.9': 0.03, 'K37': 0.02, 'R10.9': 0.02
        },
        'cardiac': {
            'I21.9': 0.20, 'I21.0': 0.15, 'I20.0': 0.10, 'I50.9': 0.22, 'I48.91': 0.18,
            'I47.9': 0.07, 'I71.0': 0.02, 'I26.9': 0.03, 'I10': 0.03
        },
        'cancer': {
            'C92.0': 0.12, 'C91.0': 0.08, 'C82.9': 0.10, 'C85.9': 0.08, 'C80.1': 0.18,
            'C34.9': 0.08, 'C50.9': 0.08, 'R50.82': 0.20, 'R65.21': 0.15, 'Z51.0': 0.05
        },
        'rehab': {
            'I69.3': 0.25, 'M17.11': 0.15, 'M16.1': 0.12, 'Z54': 0.20, 'Z50.1': 0.15,
            'Z50.0': 0.08, 'G81.9': 0.03, 'R26': 0.02
        },
        'general': {
            'I10': 0.15, 'E11.9': 0.12, 'J00': 0.10, 'I21.9': 0.08, 'I50.9': 0.07,
            'S72.9': 0.08, 'J18.9': 0.06, 'K21.9': 0.05, 'M54.5': 0.05, 'F41.9': 0.06
        }
    }
    return diagnoses.get(hospital_specialty, diagnoses['general'])

def get_admission_rate(hospital_specialty):
    """Get baseline admission rate by hospital specialty."""
    rates = {
        'pediatric': 0.12,    # 12-15%
        'cardiac': 0.72,      # 70-75%
        'cancer': 0.96,       # 95-98%
        'rehab': 0.85,        # High admission
        'general': 0.20,      # ~20%
        'specialty': 0.15     # ~15%
    }
    return rates.get(hospital_specialty, 0.20)

def get_average_los(hospital_specialty):
    """Get average length of stay (days) by hospital specialty."""
    los = {
        'pediatric': 1.2,
        'cardiac': 3.5,
        'cancer': 7.4,
        'rehab': 21.0,
        'general': 3.8,
        'specialty': 2.0
    }
    return los.get(hospital_specialty, 3.0)

def calculate_er_occupancy_at_hour(hospital_id, hour_of_day, day_of_week):
    """Calculate ER occupancy percentage at a specific hour.
    
    Returns % of ER beds occupied (0-100).
    """
    base_occupancy = HOURLY_ED_OCCUPANCY[hour_of_day]
    day_mult = DAY_OCCUPANCY_MULT.get(day_of_week, 1.00)
    
    # Add some noise (±5%)
    noise = random.uniform(-0.05, 0.05)
    final_occupancy = base_occupancy * day_mult * (1 + noise)
    return min(100, max(0, final_occupancy))

def get_admission_times_by_specialty(hospital_specialty, num_admissions):
    """Generate realistic admission times for a hospital specialty.
    
    Returns list of hours (0-23) when admissions typically occur.
    """
    times = []
    
    if hospital_specialty == 'cardiac':
        # Cardiac: 6-10am early morning peak (35%), 2-6pm afternoon peak (28%)
        for _ in range(int(num_admissions * 0.35)):
            times.append(random.randint(6, 9))
        for _ in range(int(num_admissions * 0.28)):
            times.append(random.randint(14, 17))
        for _ in range(int(num_admissions * 0.37)):
            times.append(random.randint(0, 23))
    
    elif hospital_specialty == 'pediatric':
        # Pediatric: 8-10am (25%), 2-4pm (20%), 6-9pm (22%), spread else
        for _ in range(int(num_admissions * 0.25)):
            times.append(random.randint(8, 10))
        for _ in range(int(num_admissions * 0.20)):
            times.append(random.randint(14, 16))
        for _ in range(int(num_admissions * 0.22)):
            times.append(random.randint(18, 21))
        for _ in range(int(num_admissions * 0.33)):
            times.append(random.randint(0, 23))
    
    elif hospital_specialty == 'cancer':
        # Cancer: highly scheduled 8am-5pm (70%), emergency 12am-8am (30%)
        for _ in range(int(num_admissions * 0.70)):
            times.append(random.randint(8, 17))
        for _ in range(int(num_admissions * 0.30)):
            times.append(random.randint(0, 8))
    
    elif hospital_specialty == 'rehab':
        # Rehab: mostly scheduled morning (60%), afternoon (30%), sparse evening (10%)
        for _ in range(int(num_admissions * 0.60)):
            times.append(random.randint(7, 11))
        for _ in range(int(num_admissions * 0.30)):
            times.append(random.randint(13, 16))
        for _ in range(int(num_admissions * 0.10)):
            times.append(random.randint(0, 23))
    
    else:  # general or specialty
        # General: Morning peak 8am-12pm (35%), afternoon 12-6pm (40%), evening (25%)
        for _ in range(int(num_admissions * 0.35)):
            times.append(random.randint(8, 12))
        for _ in range(int(num_admissions * 0.40)):
            times.append(random.randint(12, 18))
        for _ in range(int(num_admissions * 0.25)):
            times.append(random.randint(18, 23))
    
    # Pad to exact count
    while len(times) < num_admissions:
        times.append(random.randint(0, 23))

    return times[:num_admissions]


# --- PAYER SELECTION HELPERS ---

def get_payer_for_patient(age, hospital_specialty):
    """Return a payer string sampled from market share adjusted for age and specialty."""
    from config import PAYER_MARKET_SHARE, SPECIALTY_PAYER_ADJUST

    base = PAYER_MARKET_SHARE.copy()

    # Adjust for age groups
    if age >= 65:
        # Medicare more likely
        base['Medicare'] = base.get('Medicare', 0.36) * 1.5
        base['Commercial'] = base.get('Commercial', 0.35) * 0.8
        base['Medicaid'] = base.get('Medicaid', 0.20) * 0.8
    elif age < 18:
        # Pediatrics: higher Medicaid share typically
        base['Medicaid'] = base.get('Medicaid', 0.20) * 1.3
        base['Commercial'] = base.get('Commercial', 0.35) * 0.9

    # Apply specialty multipliers
    adjust = SPECIALTY_PAYER_ADJUST.get(hospital_specialty, {})
    for k, v in adjust.items():
        base[k] = base.get(k, 0.0) * v

    # Normalize and sample
    total = sum(base.values())
    if total <= 0:
        # fallback
        choices = ['Commercial', 'Medicare', 'Medicaid', 'Uninsured', 'Other']
        return random.choice(choices)

    probs = {k: v / total for k, v in base.items()}
    # weighted random choice
    r = random.random()
    cum = 0.0
    for k, p in probs.items():
        cum += p
        if r <= cum:
            return k
    return k


# --- DIAGNOSIS/PROCEDURE/LAB/MED VARIATION HELPERS ---

def apply_diagnosis_seasonality(icd_code, month, hospital_specialty, weather_condition=None):
    """Return a multiplier for the given diagnosis based on month, specialty, and optional weather.
    This increases rates for flu in winter, asthma in pollen/seasonal months, cardiac in winter, etc.
    """
    m = 1.0
    # winter months (Dec-Feb)
    if icd_code.startswith('J11') or icd_code == 'J00':
        if month in [12, 1, 2]:
            m *= 2.0  # flu surge in winter
    # RSV/asthma (peds) higher in late fall/winter
    if icd_code == 'J45.9' and hospital_specialty == 'pediatric' and month in [11, 12, 1, 2]:
        m *= 1.8
    # Cardiac codes higher in winter
    if icd_code.startswith('I21') or icd_code.startswith('I50'):
        if month in [12, 1, 2]:
            m *= 1.25
    # Falls and accidents more common in winter and summer (different patterns)
    if icd_code.startswith('W') or icd_code.startswith('V'):
        if month in [12, 1, 2]:
            m *= 1.3
        if month in [6, 7, 8]:
            m *= 1.2

    # Weather-based increase
    if weather_condition == 'snow' and (icd_code.startswith('W') or icd_code.startswith('V')):
        m *= 1.8
    if weather_condition == 'rain' and icd_code.startswith('V'):
        m *= 1.3

    return m


def get_procedure_weights_by_specialty(hospital_specialty, date):
    """Return a dict of procedure weights adjusted by specialty and date-based seasonality."""
    from config import PROCEDURE_SEASONALITY
    month = pd.to_datetime(date).month
    adjusted = {}
    for proc, base in PROCEDURE_SEASONALITY.items():
        w = base
        # Cardiac hospitals more procedures like Cardiac Catheterization
        if hospital_specialty == 'cardiac' and proc == 'Cardiac Catheterization':
            w *= 1.6
        if hospital_specialty == 'rehab' and proc in ['Hip Replacement', 'Knee Arthroscopy']:
            w *= 1.2
        # Seasonal adjustments rely on existing proc seasonality
        # Example: appendectomy summer spike
        if proc == 'Appendectomy' and month in [6,7,8]:
            w *= 1.25
        adjusted[proc] = w
    # normalize
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v/total for k,v in adjusted.items()}
    return adjusted


def get_lab_for_diagnosis(icd_code):
    """Return likely labs for a diagnosis code (top 1-2 choices)."""
    from datetime import datetime
    mapping = {
        'I10': ['CMP', 'Lipid Panel'],
        'E11.9': ['Hemoglobin A1c', 'Glucose'],
        'I25.10': ['Troponin', 'EKG'],
        'E78.5': ['Lipid Panel'],
        'F41.9': ['TSH', 'Cortisol'],
        'J00': ['CBC'],
        'J11.00': ['Chest X-Ray', 'CBC'],
        'N39.0': ['Urinalysis'],
        'S72.1': ['X-Ray']
    }
    return mapping.get(icd_code, ['CBC'])


def get_medications_for_diagnosis(icd_code):
    mapping = {
        'I10': ['Lisinopril', 'Amlodipine', 'Hydrochlorothiazide'],
        'E11.9': ['Metformin', 'Insulin'],
        'J00': ['Albuterol', 'Fluticasone'],
        'N39.0': ['Ciprofloxacin'],
        'I21.9': ['Aspirin', 'Clopidogrel']
    }
    return mapping.get(icd_code, ['Acetaminophen'])


def sample_diagnosis_for_hospital(hospital_specialty, month, weather_condition=None):
    """Sample a diagnosis ICD code for a hospital specialty applying seasonality and specialty weights."""
    diags = get_specialty_diagnoses(hospital_specialty)
    # Apply seasonal multipliers per code
    weighted = {}
    for code, base_w in diags.items():
        # apply seasonality multiplier
        mult = apply_diagnosis_seasonality(code, month, hospital_specialty, weather_condition=weather_condition)
        weighted[code] = max(0.0, base_w * mult)
    # Normalize
    total = sum(weighted.values())
    if total <= 0:
        # fallback: choose from general ICD list
        return random.choice(list(diags.keys()))
    rnd = random.random() * total
    cum = 0.0
    for code, w in weighted.items():
        cum += w
        if rnd <= cum:
            return code
    return code

