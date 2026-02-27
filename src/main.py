import pandas as pd
from faker import Faker
from sqlalchemy import create_engine, text
from config import (
    CONNECTION_STRING,
    HOURLY_MULTIPLIERS,
    DAY_OF_WEEK_MULTIPLIERS,
    MONTHLY_MULTIPLIERS,
    PROCEDURE_SEASONALITY,
    PEDIATRIC_MONTHLY,
    CARDIAC_MONTHLY,
    CANCER_MONTHLY,
    GENERAL_MONTHLY,
    REHAB_MONTHLY,
    HOURLY_ED_OCCUPANCY,
    DAY_OF_WEEK_OCCUPANCY_MULT
)
from hospital_generation_helpers import (
    get_hospital_monthly_encounters,
    get_specialty_diagnoses,
    get_admission_rate,
    get_average_los,
    calculate_er_occupancy_at_hour,
    get_admission_times_by_specialty,
    get_payer_for_patient,
    sample_diagnosis_for_hospital,
    get_procedure_weights_by_specialty,
    get_lab_for_diagnosis,
    get_medications_for_diagnosis
)
import random
import argparse
from datetime import datetime, timedelta
import os
import requests
import json

# Initialize Faker
fake = Faker()

# Create database engine
engine = create_engine(f'mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}')

# Weather cache (date -> condition mapping) to avoid repeated API calls
WEATHER_CACHE = {}
WEATHER_CACHE_FILE = 'weather_cache.json'

def load_weather_cache():
    """Load weather cache from disk if it exists."""
    global WEATHER_CACHE
    if os.path.exists(WEATHER_CACHE_FILE):
        try:
            with open(WEATHER_CACHE_FILE, 'r') as f:
                WEATHER_CACHE = json.load(f)
        except Exception as e:
            print(f"Warning: could not load weather cache: {e}")

def save_weather_cache():
    """Save weather cache to disk for persistence across runs."""
    try:
        with open(WEATHER_CACHE_FILE, 'w') as f:
            json.dump(WEATHER_CACHE, f, indent=2)
    except Exception as e:
        print(f"Warning: could not save weather cache: {e}")

# Load cache on startup
load_weather_cache()

def get_next_id(table_name, id_col):
    """Return next id to use for inserts by querying the current max in the DB.
    If table doesn't exist or query fails, return 1.
    """
    try:
        q = f"SELECT MAX({id_col}) as max_id FROM {table_name}"
        df = pd.read_sql(q, engine)
        max_id = df.iloc[0]['max_id']
        if pd.isna(max_id) or max_id is None:
            return 1
        return int(max_id) + 1
    except Exception:
        return 1

# Contoso Health Systems Hospitals
HOSPITALS = [
    # Large general hospitals
    {'hospital_id': 1, 'name': 'Contoso Medical Center', 'bed_count': 750, 'specialty': 'general'},
    {'hospital_id': 2, 'name': 'Contoso University Hospital', 'bed_count': 650, 'specialty': 'general'},
    {'hospital_id': 3, 'name': 'Contoso General Hospital', 'bed_count': 550, 'specialty': 'general'},
    
    # Medium specialty hospitals
    {'hospital_id': 4, 'name': 'Contoso Regional Hospital', 'bed_count': 400, 'specialty': 'general'},
    {'hospital_id': 5, 'name': 'Contoso Community Hospital', 'bed_count': 350, 'specialty': 'general'},
    
    # Specialty hospitals
    {'hospital_id': 6, 'name': 'Contoso Heart Institute', 'bed_count': 280, 'specialty': 'cardiac'},
    {'hospital_id': 7, 'name': 'Contoso Children\'s Hospital', 'bed_count': 320, 'specialty': 'pediatric'},
    {'hospital_id': 8, 'name': 'Contoso Cancer Center', 'bed_count': 200, 'specialty': 'cancer'},
    {'hospital_id': 9, 'name': 'Contoso Rehab Center', 'bed_count': 180, 'specialty': 'rehab'},
    {'hospital_id': 10, 'name': 'Contoso Diagnostic Center', 'bed_count': 120, 'specialty': 'specialty'}
]

# Departments aligned to hospital specialties
# General hospitals have ED + multiple specialties; specialty hospitals have relevant depts only
DEPARTMENTS = [
    # Contoso Medical Center (large general, id=1)
    {'department_id': 1, 'name': 'Emergency', 'hospital_id': 1, 'specialty_type': 'Emergency'},
    {'department_id': 2, 'name': 'Internal Medicine', 'hospital_id': 1, 'specialty_type': 'Medical'},
    {'department_id': 3, 'name': 'Surgery', 'hospital_id': 1, 'specialty_type': 'Surgical'},
    {'department_id': 4, 'name': 'Cardiology', 'hospital_id': 1, 'specialty_type': 'Medical'},
    {'department_id': 5, 'name': 'Radiology', 'hospital_id': 1, 'specialty_type': 'Diagnostic'},
    
    # Contoso University Hospital (large general, id=2)
    {'department_id': 6, 'name': 'Emergency', 'hospital_id': 2, 'specialty_type': 'Emergency'},
    {'department_id': 7, 'name': 'Internal Medicine', 'hospital_id': 2, 'specialty_type': 'Medical'},
    {'department_id': 8, 'name': 'Trauma Surgery', 'hospital_id': 2, 'specialty_type': 'Surgical'},
    {'department_id': 9, 'name': 'Orthopedics', 'hospital_id': 2, 'specialty_type': 'Surgical'},
    {'department_id': 10, 'name': 'Neurology', 'hospital_id': 2, 'specialty_type': 'Medical'},
    
    # Contoso General Hospital (medium general, id=3)
    {'department_id': 11, 'name': 'Emergency', 'hospital_id': 3, 'specialty_type': 'Emergency'},
    {'department_id': 12, 'name': 'Internal Medicine', 'hospital_id': 3, 'specialty_type': 'Medical'},
    {'department_id': 13, 'name': 'Surgery', 'hospital_id': 3, 'specialty_type': 'Surgical'},
    {'department_id': 14, 'name': 'Radiology', 'hospital_id': 3, 'specialty_type': 'Diagnostic'},
    
    # Contoso Regional Hospital (medium general, id=4)
    {'department_id': 15, 'name': 'Emergency', 'hospital_id': 4, 'specialty_type': 'Emergency'},
    {'department_id': 16, 'name': 'Internal Medicine', 'hospital_id': 4, 'specialty_type': 'Medical'},
    {'department_id': 17, 'name': 'Surgery', 'hospital_id': 4, 'specialty_type': 'Surgical'},
    
    # Contoso Community Hospital (medium general, id=5)
    {'department_id': 18, 'name': 'Emergency', 'hospital_id': 5, 'specialty_type': 'Emergency'},
    {'department_id': 19, 'name': 'Internal Medicine', 'hospital_id': 5, 'specialty_type': 'Medical'},
    {'department_id': 20, 'name': 'Surgery', 'hospital_id': 5, 'specialty_type': 'Surgical'},
    
    # Contoso Heart Institute (cardiac specialty, id=6) - NO EMERGENCY DEPT
    {'department_id': 21, 'name': 'Cardiology', 'hospital_id': 6, 'specialty_type': 'Medical'},
    {'department_id': 22, 'name': 'Interventional Cardiology', 'hospital_id': 6, 'specialty_type': 'Surgical'},
    {'department_id': 23, 'name': 'Cardiac Surgery', 'hospital_id': 6, 'specialty_type': 'Surgical'},
    {'department_id': 24, 'name': 'Cardiac Rehabilitation', 'hospital_id': 6, 'specialty_type': 'Medical'},
    
    # Contoso Children's Hospital (pediatric specialty, id=7) - NO EMERGENCY DEPT
    {'department_id': 25, 'name': 'Pediatrics', 'hospital_id': 7, 'specialty_type': 'Medical'},
    {'department_id': 26, 'name': 'Pediatric Surgery', 'hospital_id': 7, 'specialty_type': 'Surgical'},
    {'department_id': 27, 'name': 'Pediatric ER/Urgent Care', 'hospital_id': 7, 'specialty_type': 'Emergency'},
    {'department_id': 28, 'name': 'Neonatology', 'hospital_id': 7, 'specialty_type': 'Medical'},
    
    # Contoso Cancer Center (oncology specialty, id=8) - NO EMERGENCY DEPT
    {'department_id': 29, 'name': 'Oncology', 'hospital_id': 8, 'specialty_type': 'Medical'},
    {'department_id': 30, 'name': 'Hematology', 'hospital_id': 8, 'specialty_type': 'Medical'},
    {'department_id': 31, 'name': 'Infusion Center', 'hospital_id': 8, 'specialty_type': 'Medical'},
    {'department_id': 32, 'name': 'Palliative Care', 'hospital_id': 8, 'specialty_type': 'Medical'},
    
    # Contoso Rehab Center (rehabilitation specialty, id=9) - NO EMERGENCY DEPT
    {'department_id': 33, 'name': 'Physical Rehabilitation', 'hospital_id': 9, 'specialty_type': 'Medical'},
    {'department_id': 34, 'name': 'Occupational Therapy', 'hospital_id': 9, 'specialty_type': 'Medical'},
    {'department_id': 35, 'name': 'Speech Therapy', 'hospital_id': 9, 'specialty_type': 'Medical'},
    
    # Contoso Diagnostic Center (specialty diagnostic, id=10) - BUSINESS HOURS ONLY
    {'department_id': 36, 'name': 'Radiology', 'hospital_id': 10, 'specialty_type': 'Diagnostic'},
    {'department_id': 37, 'name': 'Pathology', 'hospital_id': 10, 'specialty_type': 'Diagnostic'},
    {'department_id': 38, 'name': 'Laboratory', 'hospital_id': 10, 'specialty_type': 'Diagnostic'}
]

# Department demand multipliers (real-world based on patient volume)
DEPARTMENT_DEMAND_MULTIPLIERS = {
    'Emergency': 2.5,         # ER is busiest department
    'Internal Medicine': 1.8,  # High volume for routine care
    'Surgery': 1.2,            # Moderate surgical volume
    'Cardiology': 1.5,         # High demand specialty
    'Orthopedics': 1.4,        # Common injuries/procedures
    'Radiology': 1.9,          # High imaging demand
    'Oncology': 1.3,           # Cancer treatment volume
    'Pediatrics': 1.6,         # High child visit volume
    'Neurology': 1.1,          # Moderate specialty volume
    'Diagnostic': 1.7,         # High testing demand
    'Medical': 1.5,            # General medical services
    'Surgical': 1.0,           # Baseline surgical
    'Infusion Center': 0.9,    # Scheduled treatments
    'Palliative Care': 0.6,    # Lower volume specialty
    'Physical Rehabilitation': 0.8,
    'Occupational Therapy': 0.7,
    'Speech Therapy': 0.5,
    'Neonatology': 0.9,
    'Pathology': 1.2,
    'Laboratory': 1.8
}

# Realistic department bed allocation percentages (% of total hospital beds)
# Based on real-world hospital resource distribution
DEPARTMENT_BED_ALLOCATION = {
    # General hospital departments
    'Emergency': 0.06,              # 6% - ER beds (just treatment bays, not volume)
    'Internal Medicine': 0.35,      # 35% - largest inpatient service
    'Surgery': 0.25,                # 25% - surgical floors
    'Trauma Surgery': 0.20,         # 20% - trauma surgical service
    'Cardiology': 0.15,             # 15% - cardiac care
    'Orthopedics': 0.12,            # 12% - orthopedic surgery
    'Neurology': 0.10,              # 10% - neuro service
    'Radiology': 0.03,              # 3% - imaging (mostly outpatient)
    
    # Specialty hospital departments
    'Interventional Cardiology': 0.30,  # 30% in cardiac hospital
    'Cardiac Surgery': 0.40,            # 40% in cardiac hospital
    'Cardiac Rehabilitation': 0.25,     # 25% in cardiac hospital
    
    'Pediatrics': 0.50,                 # 50% in children's hospital
    'Pediatric Surgery': 0.30,          # 30% in children's hospital
    'Pediatric ER/Urgent Care': 0.05,   # 5% - small pediatric ER
    'Neonatology': 0.15,                # 15% - NICU
    
    'Oncology': 0.50,                   # 50% in cancer center
    'Hematology': 0.30,                 # 30% in cancer center
    'Infusion Center': 0.15,            # 15% - outpatient infusion
    'Palliative Care': 0.05,            # 5% - end-of-life care
    
    'Physical Rehabilitation': 0.60,    # 60% in rehab center
    'Occupational Therapy': 0.25,       # 25% in rehab center
    'Speech Therapy': 0.15,             # 15% in rehab center
    
    'Pathology': 0.05,                  # 5% - mostly outpatient
    'Laboratory': 0.05,                 # 5% - mostly outpatient
    
    # Default for unlisted departments
    'default': 0.10
}

# Common procedures with skew
PROCEDURE_WEIGHTS = {
    'Blood Test': 0.25,
    'X-Ray': 0.20,
    'MRI Scan': 0.10,
    'CT Scan': 0.08,
    'Colonoscopy': 0.07,
    'Endoscopy': 0.06,
    'Cardiac Catheterization': 0.05,
    'Appendectomy': 0.04,
    'Hip Replacement': 0.03,
    'Knee Arthroscopy': 0.02,
    'Other': 0.10
}

def apply_seasonality_to_procedure_weights(date):
    """Apply seasonal multipliers to procedure weights for a given date.
    Returns adjusted weights dict normalized to sum to 1.0.
    """
    month = pd.to_datetime(date).month - 1  # 0-indexed
    month_mult = MONTHLY_MULTIPLIERS[month] if month < len(MONTHLY_MULTIPLIERS) else 1.0
    
    adjusted = {}
    for proc, base_weight in PROCEDURE_WEIGHTS.items():
        proc_seasonal = PROCEDURE_SEASONALITY.get(proc, 1.0)
        adjusted[proc] = base_weight * proc_seasonal * month_mult
    
    # Normalize so weights sum to 1.0
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted

# Sample ICD-10 codes (top 30 common)
ICD_CODES = [
    'I10', 'E11.9', 'Z00.00', 'M54.5', 'J00', 'R05', 'F41.9', 'N28.1', 'Z01.419', 'Z51.11',
    'I25.10', 'E78.5', 'Z95.1', 'M79.3', 'R10.9', 'F32.9', 'N39.0', 'Z12.31', 'Z79.899', 'I48.91',
    'G43.909', 'K21.9', 'Z98.891', 'M17.9', 'R51', 'F33.9', 'N18.9', 'Z23', 'Z87.440', 'I50.9'
]

# Sample CPT codes (top 30 common)
CPT_CODES = [
    '99213', '99214', '99215', '85025', '71020', '74176', '45378', '43235', '99201', '99202',
    '99203', '99204', '99205', '80053', '83036', '84443', '85027', '85610', '84153', '84439',
    '82306', '84132', '82565', '84520', '82947', '83540', '82247', '83001', '86038', '86334'
]

# Sample medications (top 30 common)
MEDICATIONS = [
    'Lisinopril', 'Metformin', 'Amlodipine', 'Omeprazole', 'Simvastatin', 'Losartan', 'Albuterol', 'Gabapentin',
    'Sertraline', 'Furosemide', 'Fluticasone', 'Prednisone', 'Warfarin', 'Levothyroxine', 'Hydrochlorothiazide',
    'Aspirin', 'Atorvastatin', 'Clopidogrel', 'Montelukast', 'Trazodone', 'Citalopram', 'Duloxetine', 'Escitalopram',
    'Bupropion', 'Venlafaxine', 'Quetiapine', 'Risperidone', 'Olanzapine', 'Lamotrigine', 'Topiramate',
    # Antibiotics & critical care meds (added for realism)
    'Ceftriaxone', 'Vancomycin', 'Piperacillin-Tazobactam', 'Norepinephrine'
]

# Sample lab tests (top 30 common)
LAB_TESTS = [
    'CBC', 'CMP', 'Lipid Panel', 'TSH', 'Hemoglobin A1c', 'Urinalysis', 'Chest X-Ray', 'EKG', 'PT/INR',
    'Vitamin D', 'B12', 'Folate', 'Ferritin', 'Iron', 'TIBC', 'Liver Function', 'Kidney Function', 'Electrolytes',
    'Glucose', 'Cortisol', 'T3/T4', 'PSA', 'CA-125', 'CEA', 'AFP', 'Beta-HCG', 'Troponin', 'CK-MB', 'BNP', 'D-Dimer',
    'Lactic Acid', 'Blood Culture', 'ABG', 'CT Head'
]

# Realistic descriptions and complaints for diagnoses (expanded to cover all ICD_CODES)
DIAGNOSIS_DETAILS = {
    'I10': {'description': 'Essential (primary) hypertension', 'complaints': ['Headache', 'Dizziness', 'High blood pressure reading']},
    'E11.9': {'description': 'Type 2 diabetes mellitus without complications', 'complaints': ['Frequent urination', 'Increased thirst', 'Fatigue']},
    'Z00.00': {'description': 'Encounter for general adult medical examination without abnormal findings', 'complaints': ['Routine check-up', 'Annual physical']},
    'M54.5': {'description': 'Low back pain', 'complaints': ['Back pain', 'Difficulty moving', 'Muscle spasm']},
    'J00': {'description': 'Acute nasopharyngitis (common cold)', 'complaints': ['Sore throat', 'Runny nose', 'Cough']},
    'R05': {'description': 'Cough', 'complaints': ['Persistent cough', 'Chest discomfort']},
    'F41.9': {'description': 'Anxiety disorder, unspecified', 'complaints': ['Anxiety', 'Panic attacks', 'Restlessness']},
    'N28.1': {'description': 'Cyst of kidney, acquired', 'complaints': ['Flank pain', 'Blood in urine']},
    'Z01.419': {'description': 'Encounter for gynecological examination (general) (routine) without abnormal findings', 'complaints': ['Routine gynecological exam']},
    'Z51.11': {'description': 'Encounter for antineoplastic chemotherapy', 'complaints': ['Chemotherapy session', 'Cancer treatment']},
    'I25.10': {'description': 'Atherosclerotic heart disease of native coronary artery without angina pectoris', 'complaints': ['Chest pain', 'Shortness of breath']},
    'E78.5': {'description': 'Hyperlipidemia, unspecified', 'complaints': ['High cholesterol', 'Fatigue']},
    'Z95.1': {'description': 'Presence of aortocoronary bypass graft', 'complaints': ['Post-surgery check', 'Cardiac monitoring']},
    'M79.3': {'description': 'Pain in limb', 'complaints': ['Limb pain', 'Swelling']},
    'R10.9': {'description': 'Unspecified abdominal pain', 'complaints': ['Abdominal pain', 'Nausea']},
    'F32.9': {'description': 'Major depressive disorder, single episode, unspecified', 'complaints': ['Depression', 'Loss of interest']},
    'N39.0': {'description': 'Urinary tract infection, site not specified', 'complaints': ['Painful urination', 'Frequent urination']},
    'Z12.31': {'description': 'Encounter for screening mammogram for malignant neoplasm of breast', 'complaints': ['Mammogram screening']},
    'Z79.899': {'description': 'Other long term (current) drug therapy', 'complaints': ['Medication management']},
    'I48.91': {'description': 'Unspecified atrial fibrillation', 'complaints': ['Irregular heartbeat', 'Palpitations']},
    'G43.909': {'description': 'Migraine, unspecified, not intractable, without status migrainosus', 'complaints': ['Migraine headache', 'Nausea']},
    'K21.9': {'description': 'Gastro-esophageal reflux disease without esophagitis', 'complaints': ['Heartburn', 'Acid reflux']},
    'Z98.891': {'description': 'History of bariatric surgery', 'complaints': ['Weight management follow-up']},
    'M17.9': {'description': 'Osteoarthritis of knee, unspecified', 'complaints': ['Knee pain', 'Stiffness']},
    'R51': {'description': 'Headache', 'complaints': ['Headache', 'Migraine']},
    'F33.9': {'description': 'Major depressive disorder, recurrent, unspecified', 'complaints': ['Recurrent depression']},
    'N18.9': {'description': 'Chronic kidney disease, unspecified', 'complaints': ['Fatigue', 'Swelling']},
    'Z23': {'description': 'Encounter for immunization', 'complaints': ['Vaccination']},
    'Z87.440': {'description': 'Personal history of other diseases of respiratory system', 'complaints': ['Respiratory history review']},
    'I50.9': {'description': 'Heart failure, unspecified', 'complaints': ['Shortness of breath', 'Fatigue']},
    'J18.9': {'description': 'Pneumonia, unspecified organism', 'complaints': ['Fever', 'Cough', 'Shortness of breath', 'Chest pain']},
    'A41.9': {'description': 'Sepsis, unspecified organism', 'complaints': ['Fever', 'Hypotension', 'Altered mental status', 'Rapid heart rate']},
    'J44.9': {'description': 'Chronic obstructive pulmonary disease, unspecified', 'complaints': ['Shortness of breath', 'Wheezing', 'Chronic cough']},
    'L03.90': {'description': 'Cellulitis, unspecified', 'complaints': ['Localized redness', 'Warmth', 'Pain', 'Swelling']},
    'I63.9': {'description': 'Cerebral infarction, unspecified (Ischemic stroke)', 'complaints': ['Sudden weakness', 'Slurred speech', 'Facial droop', 'Neurologic deficits']},
    'R55': {'description': 'Syncope and collapse', 'complaints': ['Fainting', 'Loss of consciousness', 'Dizziness']},
    # Fallback for any missing
} 

# Realistic relations: Diagnosis to Medications and Labs
DIAGNOSIS_TO_MEDS = {
    'I10': ['Lisinopril', 'Amlodipine', 'Hydrochlorothiazide'],  # Hypertension
    'E11.9': ['Metformin', 'Insulin'],  # Diabetes
    'I25.10': ['Atorvastatin', 'Aspirin'],  # Atherosclerotic heart disease
    'E78.5': ['Atorvastatin', 'Simvastatin'],  # Hyperlipidemia
    'F41.9': ['Sertraline', 'Escitalopram'],  # Anxiety
    'F32.9': ['Sertraline', 'Citalopram'],  # Depression
    'M54.5': ['Gabapentin', 'Ibuprofen'],  # Back pain
    'J00': ['Albuterol', 'Fluticasone'],  # Cold
    'R05': ['Dextromethorphan'],  # Cough
    'N39.0': ['Ciprofloxacin'],  # UTI
    'J18.9': ['Azithromycin', 'Ceftriaxone', 'Levofloxacin'],  # Pneumonia - common empiric antibiotics
    'A41.9': ['Piperacillin-Tazobactam', 'Vancomycin', 'Cefepime'],  # Sepsis - broad-spectrum
    'J44.9': ['Albuterol', 'Tiotropium', 'Prednisone'],  # COPD exacerbation meds
    'L03.90': ['Cephalexin', 'Dicloxacillin', 'Clindamycin'],  # Cellulitis antibiotics
    'I63.9': ['Aspirin', 'Atorvastatin'],  # Stroke secondary prevention (initial inpatient meds vary)
    'R55': ['Observation', 'IV fluids']
} 

DIAGNOSIS_TO_LABS = {
    'I10': ['CMP', 'Lipid Panel'],  # Hypertension
    'E11.9': ['Hemoglobin A1c', 'Glucose'],  # Diabetes
    'I25.10': ['Troponin', 'EKG'],  # Heart disease
    'E78.5': ['Lipid Panel'],  # Hyperlipidemia
    'F41.9': ['TSH', 'Cortisol'],  # Anxiety
    'F32.9': ['TSH'],  # Depression
    'M54.5': ['X-Ray'],  # Back pain
    'J00': ['CBC'],  # Cold
    'R05': ['Chest X-Ray'],  # Cough
    'N39.0': ['Urinalysis'],  # UTI
    'J18.9': ['CBC', 'Chest X-Ray', 'Blood Culture'],  # Pneumonia
    'A41.9': ['CBC', 'Lactic Acid', 'Blood Culture'],  # Sepsis workup
    'J44.9': ['ABG', 'Chest X-Ray', 'CBC'],  # COPD exacerbation
    'L03.90': ['CBC', 'CRP'],  # Cellulitis inflammatory markers
    'I63.9': ['CT Head', 'Glucose', 'CBC']  # Stroke imaging & labs
} 

# ICD-10 codes for weather-related conditions
FLU_ICD_CODE = 'J11.00'  # Influenza A
FALL_ICD_CODE = 'W19.XXXA'  # Fall, unspecified
ACCIDENT_ICD_CODE = 'V89.2'  # Unspecified motor vehicle accident

# Add flu and fall to diagnosis details
DIAGNOSIS_DETAILS['J11.00'] = {'description': 'Influenza with pneumonia, unspecified type', 'complaints': ['Fever', 'Cough', 'Body aches', 'Respiratory symptoms']}
DIAGNOSIS_DETAILS['W19.XXXA'] = {'description': 'Unspecified fall', 'complaints': ['Fall', 'Trauma', 'Injury', 'Fracture']}
DIAGNOSIS_DETAILS['V89.2'] = {'description': 'Unspecified motor vehicle accident', 'complaints': ['Accident', 'Trauma', 'Injury']}

# Weather conditions and their impact multipliers
WEATHER_IMPACT = {
    'rain': {'flu_multiplier': 1.5, 'fall_multiplier': 1.8, 'accident_multiplier': 1.3},
    'snow': {'flu_multiplier': 2.0, 'fall_multiplier': 2.5, 'accident_multiplier': 2.0},
    'sleet': {'flu_multiplier': 1.8, 'fall_multiplier': 2.2, 'accident_multiplier': 1.8},
    'thunderstorm': {'flu_multiplier': 1.6, 'fall_multiplier': 1.4, 'accident_multiplier': 1.7},
    'fog': {'flu_multiplier': 1.3, 'fall_multiplier': 1.1, 'accident_multiplier': 2.2},
    'clear': {'flu_multiplier': 1.0, 'fall_multiplier': 1.0, 'accident_multiplier': 1.0},
    'cloudy': {'flu_multiplier': 1.1, 'fall_multiplier': 1.05, 'accident_multiplier': 1.05}
}

def get_current_weather(latitude=40.7128, longitude=-74.0060):
    """
    Fetch current weather conditions.
    Default coordinates are for New York City.
    Returns weather condition and impact multipliers.
    """
    try:
        # Using Open-Meteo free API (no API key required)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=weather_code,temperature,precipitation,weather_description"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            weather_code = data['current']['weather_code']
            weather_desc = data['current'].get('weather_description', 'Unknown')
            
            # Map weather codes to conditions
            # WMO Weather interpretation codes
            if weather_code == 0:
                condition = 'clear'
            elif weather_code in [1, 2]:
                condition = 'cloudy'
            elif weather_code == 3:
                condition = 'cloudy'
            elif weather_code in [45, 48]:
                condition = 'fog'
            elif weather_code in [51, 53, 55, 61, 63, 65]:
                condition = 'rain'
            elif weather_code in [71, 73, 75, 77]:
                condition = 'snow'
            elif weather_code in [80, 81, 82]:
                condition = 'rain'
            elif weather_code in [85, 86]:
                condition = 'snow'
            elif weather_code in [95, 96, 99]:
                condition = 'thunderstorm'
            else:
                condition = 'cloudy'
                
            return condition, WEATHER_IMPACT.get(condition, WEATHER_IMPACT['clear'])
    except Exception as e:
        print(f"Warning: Could not fetch weather data: {e}. Using default (clear) weather.")
    
    return 'clear', WEATHER_IMPACT['clear']


def get_weather_for_date(date, latitude=40.7128, longitude=-74.0060):
    """Fetch weather for a specific date (YYYY-MM-DD or date/datetime).
    Uses in-memory cache first, then Open-Meteo archive endpoint; falls back to 'clear' on error.
    Returns (condition, impact_dict)
    """
    d = pd.to_datetime(date).date()
    date_str = d.isoformat()
    
    # Check cache first
    if date_str in WEATHER_CACHE:
        condition = WEATHER_CACHE[date_str]
        return condition, WEATHER_IMPACT.get(condition, WEATHER_IMPACT['clear'])
    
    try:
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?latitude={latitude}&longitude={longitude}"
            f"&start_date={date_str}&end_date={date_str}&daily=weathercode,precipitation_sum&timezone=UTC"
        )
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            # daily.weathercode is a list; pick first
            weather_codes = data.get('daily', {}).get('weathercode')
            if weather_codes and len(weather_codes) > 0:
                weather_code = weather_codes[0]
            else:
                weather_code = None

            # Map as in get_current_weather
            if weather_code == 0:
                condition = 'clear'
            elif weather_code in [1, 2, 3]:
                condition = 'cloudy'
            elif weather_code in [45, 48]:
                condition = 'fog'
            elif weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
                condition = 'rain'
            elif weather_code in [71, 73, 75, 77, 85, 86]:
                condition = 'snow'
            elif weather_code in [95, 96, 99]:
                condition = 'thunderstorm'
            else:
                condition = 'cloudy'

            # Store in cache
            WEATHER_CACHE[date_str] = condition
            return condition, WEATHER_IMPACT.get(condition, WEATHER_IMPACT['clear'])
    except Exception as e:
        # fallback
        print(f"Warning: could not fetch historical weather for {date}: {e}. Using default clear.")
    
    # Cache the fallback
    condition = 'clear'
    WEATHER_CACHE[date_str] = condition
    return condition, WEATHER_IMPACT['clear']

def generate_patients(n=100, as_of_date=None):
    """Generate `n` patients and include age and a sampled primary payer.
    as_of_date: date used to compute age and favor payer selection (default today)
    """
    from hospital_generation_helpers import get_payer_for_patient
    patients = []
    as_of = pd.to_datetime(as_of_date).date() if as_of_date is not None else pd.to_datetime('today').date()
    for _ in range(n):
        hospital = random.choice(HOSPITALS)
        dob = fake.date_of_birth(minimum_age=0, maximum_age=100)
        age = as_of.year - pd.to_datetime(dob).year - ((as_of.month, as_of.day) < (pd.to_datetime(dob).month, pd.to_datetime(dob).day))
        payer = get_payer_for_patient(age, hospital.get('specialty', 'general'))
        patient = {
            # patient_id will be assigned by caller via start_id offset if needed
            'hospital_id': hospital['hospital_id'],
            'first_name': fake.first_name(),
            'last_name': fake.last_name(),
            'date_of_birth': dob,
            'age': age,
            'gender': fake.random_element(['M', 'F']),
            'address': fake.address().replace('\n', ', '),
            'phone': fake.phone_number(),
            'email': fake.email(),
            'primary_payer': payer
        }
        patients.append(patient)
    df = pd.DataFrame(patients)
    # add patient_id sequentially starting at 1 (caller may offset before insert)
    df.insert(0, 'patient_id', range(1, len(df) + 1))
    return df

def generate_doctors(n=20):
    doctors = []
    specialties = ['Cardiology', 'Dermatology', 'Neurology', 'Pediatrics', 'Orthopedics', 'Radiology', 'Surgery', 'Internal Medicine']
    for _ in range(n):
        hospital = random.choice(HOSPITALS)
        doctor = {
            'hospital_id': hospital['hospital_id'],
            'first_name': fake.first_name(),
            'last_name': fake.last_name(),
            'specialty': fake.random_element(specialties),
            'license_number': fake.unique.random_number(digits=10),
            'phone': fake.phone_number(),
            'email': fake.email()
        }
        doctors.append(doctor)
    df = pd.DataFrame(doctors)
    # provider_id is used elsewhere as provider reference
    df.insert(0, 'provider_id', range(1, len(df) + 1))
    return df

def generate_diagnoses_weather_aware(n=400, min_date=None, end_date=None, weather_condition='clear', weather_impacts=None, encounter_start=1, encounter_count=300, patient_start=1, patient_count=100):
    """
    Generate diagnoses with weather-based adjustments for flu and fall-related injuries.
    """
    if weather_impacts is None:
        weather_impacts = WEATHER_IMPACT.get(weather_condition, WEATHER_IMPACT['clear'])
    
    diagnoses = []
    flu_count = 0
    fall_count = 0
    normal_count = 0

    # Use general specialty distribution as baseline
    general_dist = get_specialty_diagnoses('general')
    total_base = sum(general_dist.values())

    # Calculate how many flu and fall diagnoses to generate based on weather
    flu_target = int(n * 0.05 * weather_impacts.get('flu_multiplier', 1.0))  # Base 5% of diagnoses
    fall_target = int(n * 0.08 * weather_impacts.get('fall_multiplier', 1.0))  # Base 8% for injuries

    for i in range(n):
        # bias towards weather-driven diagnoses first
        if flu_count < flu_target and random.random() < 0.20:
            icd_code = FLU_ICD_CODE
            flu_count += 1
        elif fall_count < fall_target and random.random() < 0.22:
            icd_code = FALL_ICD_CODE
            fall_count += 1
        else:
            # Sample from general distribution applying month seasonality
            month = pd.to_datetime(min_date).month if min_date else pd.Timestamp.now().month
            # Build weighted list
            weighted = {}
            for code, w in general_dist.items():
                # apply seasonal multiplier for codes that are seasonal (via helper function)
                try:
                    mult = apply_diagnosis_seasonality(code, month, 'general', weather_condition=weather_condition)
                except Exception:
                    mult = 1.0
                weighted[code] = w * mult
            # normalize
            total = sum(weighted.values())
            if total <= 0:
                icd_code = random.choice(ICD_CODES)
            else:
                r = random.random() * total
                cum = 0.0
                for code, val in weighted.items():
                    cum += val
                    if r <= cum:
                        icd_code = code
                        break
        normal_count += 1

        details = DIAGNOSIS_DETAILS.get(icd_code, {'description': fake.sentence(), 'complaints': [fake.sentence()]})
        diagnosis = {
            'encounter_id': random.randint(encounter_start, max(encounter_start, encounter_start + max(0, encounter_count-1))),
            'patient_id': random.randint(patient_start, max(patient_start, patient_start + max(0, patient_count-1))),
            'icd_code': icd_code,
            'description': details['description'],
            'onset_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'status': random.choice(['Active', 'Resolved', 'Chronic'])
        }
        diagnoses.append(diagnosis)

    print(f"Weather condition: {weather_condition} | Flu diagnoses: {flu_count} | Fall diagnoses: {fall_count} | Normal: {normal_count}")
    df = pd.DataFrame(diagnoses)
    df.insert(0, 'diagnosis_id', range(1, len(df) + 1))
    return df

def generate_procedures(n=200, min_date=None, end_date=None, encounter_start=1, encounter_count=300, encounters_df=None):
    procedures = []

    date = end_date or min_date or datetime.now().date()

    for _ in range(n):
        # If encounters_df provided, pick a real encounter to attach procedure to
        if encounters_df is not None and len(encounters_df) > 0:
            enc = encounters_df.sample(1).iloc[0]
            encounter_id = int(enc['encounter_id'])
            hospital_id = int(enc['hospital_id'])
            # find hospital specialty
            hosp = next((h for h in HOSPITALS if h['hospital_id'] == hospital_id), None)
            specialty = hosp.get('specialty', 'general') if hosp else 'general'
            # get specialty-weighted procedure weights
            proc_weights = get_procedure_weights_by_specialty(specialty, date)
            proc_names = list(proc_weights.keys())
            weights = [proc_weights.get(p, 0.01) for p in proc_names]
            proc_name = random.choices(proc_names, weights=weights)[0]
        else:
            encounter_id = random.randint(encounter_start, max(encounter_start, encounter_start + max(0, encounter_count-1)))
            hospital = random.choice(HOSPITALS)
            hospital_id = hospital['hospital_id']
            seasonal_weights = apply_seasonality_to_procedure_weights(date)
            procedure_names = list(PROCEDURE_WEIGHTS.keys())
            weights = [seasonal_weights.get(name, PROCEDURE_WEIGHTS.get(name, 0.01)) for name in procedure_names]
            proc_name = random.choices(procedure_names, weights=weights)[0]

        procedure = {
            'hospital_id': hospital_id,
            'encounter_id': encounter_id,
            'procedure_name': proc_name,
            'procedure_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'cost': round(random.uniform(100, 10000), 2),
            'duration_minutes': random.randint(15, 240)
        }
        procedures.append(procedure)
    df = pd.DataFrame(procedures)
    df.insert(0, 'procedure_id', range(1, len(df) + 1))
    return df

def generate_encounters(n=300, min_date=None, end_date=None, patient_start=1, patient_count=100, provider_start=1, provider_count=20, hospital_id=None):
    encounters = []
    encounter_types = ['Office Visit', 'Emergency', 'Inpatient', 'Telehealth', 'Surgery']
    for i in range(n):
        hospital = next((h for h in HOSPITALS if h['hospital_id'] == hospital_id), None) if hospital_id else random.choice(HOSPITALS)
        if not hospital:
            hospital = random.choice(HOSPITALS)
        
        # Pick a diagnosis representative of the hospital specialty and date
        try:
            month = pd.to_datetime(min_date).month if min_date else pd.Timestamp.now().month
        except Exception:
            month = pd.Timestamp.now().month
        try:
            icd_code = sample_diagnosis_for_hospital(hospital.get('specialty', 'general'), month)
            details = DIAGNOSIS_DETAILS.get(icd_code, {'description': fake.sentence(), 'complaints': [fake.sentence()]})
        except Exception:
            icd_code = random.choice(list(DIAGNOSIS_DETAILS.keys()))
            details = DIAGNOSIS_DETAILS[icd_code]
        chief_complaint = random.choice(details['complaints'])
        
        # Assign department based on specialty type with realistic demand distribution
        hosp_depts = [d for d in DEPARTMENTS if d['hospital_id'] == hospital['hospital_id']]
        if hosp_depts:
            # Weight departments by demand multiplier
            dept_weights = [DEPARTMENT_DEMAND_MULTIPLIERS.get(d['name'], DEPARTMENT_DEMAND_MULTIPLIERS.get(d['specialty_type'], 1.0)) for d in hosp_depts]
            department = random.choices(hosp_depts, weights=dept_weights)[0]
        else:
            department = {'department_id': 1, 'name': 'General', 'specialty_type': 'Medical'}
        
        # Assign payer based on hospital specialty (realistic market share)
        specialty = hospital.get('specialty', 'general')
        payer_type = get_payer_for_patient(age=random.randint(0, 90), hospital_specialty=specialty)
        
        # pick patient and provider from provided ranges
        patient_id = random.randint(patient_start, max(patient_start, patient_start + max(0, patient_count-1)))
        provider_id = random.randint(provider_start, max(provider_start, provider_start + max(0, provider_count-1)))
        encounter = {
            'hospital_id': hospital['hospital_id'],
            'department_id': department['department_id'],
            'patient_id': patient_id,
            'provider_id': provider_id,
            'encounter_type': random.choice(encounter_types),
            'encounter_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'start_time': fake.time(),
            'end_time': fake.time(),
            'payer_type': payer_type,
            'chief_complaint': chief_complaint,
            'notes': f"Patient presented with {chief_complaint.lower()}. Assessment: {details['description']}. Plan: Monitor and treat accordingly. {fake.text(max_nb_chars=100)}"
        }
        encounters.append(encounter)
    df = pd.DataFrame(encounters)
    df.insert(0, 'encounter_id', range(1, len(df) + 1))
    return df

def generate_diagnoses(n=400, min_date=None, end_date=None, encounter_start=1, encounter_count=300, patient_start=1, patient_count=100):
    diagnoses = []
    for _ in range(n):
        icd_code = random.choice(ICD_CODES)
        details = DIAGNOSIS_DETAILS.get(icd_code, {'description': fake.sentence(), 'complaints': [fake.sentence()]})
        diagnosis = {
            'encounter_id': random.randint(encounter_start, max(encounter_start, encounter_start + max(0, encounter_count-1))),
            'patient_id': random.randint(patient_start, max(patient_start, patient_start + max(0, patient_count-1))),
            'icd_code': icd_code,
            'description': details['description'],
            'onset_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'status': random.choice(['Active', 'Resolved', 'Chronic'])
        }
        diagnoses.append(diagnosis)
    df = pd.DataFrame(diagnoses)
    df.insert(0, 'diagnosis_id', range(1, len(df) + 1))
    return df

def generate_medications(n=250, min_date=None, end_date=None, encounters_df=None, diagnoses_df=None):
    medications = []
    for _ in range(n):
        if encounters_df is not None and len(encounters_df) > 0:
            enc = encounters_df.sample(1).iloc[0]
            encounter_id = int(enc['encounter_id'])
            patient_id = int(enc['patient_id'])
            # try to choose meds based on diagnosis for this encounter
            med_choices = MEDICATIONS
            if diagnoses_df is not None and 'encounter_id' in diagnoses_df.columns:
                diags = diagnoses_df[diagnoses_df['encounter_id'] == encounter_id]
                if not diags.empty:
                    icd = diags.sample(1).iloc[0]['icd_code']
                    med_choices = DIAGNOSIS_TO_MEDS.get(icd, MEDICATIONS)
        else:
            encounter_id = random.randint(1, 300)
            patient_id = random.randint(1, 100)
            med_choices = MEDICATIONS

        medication = {
            'encounter_id': encounter_id,
            'patient_id': patient_id,
            'drug_name': random.choice(med_choices),
            'dosage': f'{random.randint(1,100)}mg',
            'frequency': random.choice(['Once daily', 'Twice daily', 'As needed']),
            'start_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'end_date': (fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date and random.random() > 0.5 else (fake.date_this_year() if random.random() > 0.5 else None)),
            'prescribing_provider_id': random.randint(1, 20),
            'status': random.choice(['Active', 'Discontinued'])
        }
        medications.append(medication)
    df = pd.DataFrame(medications)
    df.insert(0, 'medication_id', range(1, len(df) + 1))
    return df


def generate_labs(n=350, min_date=None, end_date=None, encounters_df=None, diagnoses_df=None):
    labs = []
    for _ in range(n):
        if encounters_df is not None and len(encounters_df) > 0:
            enc = encounters_df.sample(1).iloc[0]
            encounter_id = int(enc['encounter_id'])
            patient_id = int(enc['patient_id'])
            # try to find a diagnosis for this encounter
            test_choices = LAB_TESTS
            if diagnoses_df is not None and 'encounter_id' in diagnoses_df.columns:
                diags = diagnoses_df[diagnoses_df['encounter_id'] == encounter_id]
                if not diags.empty:
                    icd = diags.sample(1).iloc[0]['icd_code']
                    test_choices = DIAGNOSIS_TO_LABS.get(icd, LAB_TESTS)
        else:
            encounter_id = random.randint(1, 300)
            patient_id = random.randint(1, 100)
            test_choices = LAB_TESTS

        lab = {
            'encounter_id': encounter_id,
            'patient_id': patient_id,
            'test_name': random.choice(test_choices),
            'test_code': random.choice(CPT_CODES),
            'order_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'result_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'value': str(round(random.uniform(1, 200), 2)),
            'units': random.choice(['mg/dL', 'g/dL', '%', 'IU/mL']),
            'reference_range': 'Normal',
            'status': random.choice(['Completed', 'Pending'])
        }
        labs.append(lab)
    df = pd.DataFrame(labs)
    df.insert(0, 'lab_id', range(1, len(df) + 1))
    return df

def generate_insurance_for_patients(patients_df, min_date=None, end_date=None):
    """Generate one insurance record per patient reflecting their primary payer."""
    insurance = []
    for _, p in patients_df.iterrows():
        payer = p.get('primary_payer') or random.choice(['Blue Cross', 'Aetna', 'UnitedHealthcare', 'Cigna', 'Medicare', 'Medicaid'])
        ins = {
            'patient_id': int(p['patient_id']),
            'payer_name': payer,
            'policy_number': fake.random_number(digits=10),
            'group_number': fake.random_number(digits=8),
            'effective_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'expiration_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year()
        }
        insurance.append(ins)
    df = pd.DataFrame(insurance)
    df.insert(0, 'insurance_id', range(1, len(df) + 1))
    return df

def generate_billing(n=300, min_date=None, end_date=None):
    billing = []
    for _ in range(n):
        bill = {
            'encounter_id': random.randint(1, 300),
            'patient_id': random.randint(1, 100),
            'total_charges': round(random.uniform(100, 50000), 2),
            'paid_amount': round(random.uniform(0, 50000), 2),
            'balance': round(random.uniform(0, 50000), 2),
            'claim_status': random.choice(['Submitted', 'Paid', 'Denied', 'Pending']),
            'cpt_codes': random.choice(CPT_CODES),
            'modifiers': random.choice(['26', 'TC', '50', ''])
        }
        billing.append(bill)
    df = pd.DataFrame(billing)
    df.insert(0, 'billing_id', range(1, len(df) + 1))
    return df

def export_to_parquet(dataframes, output_dir='data'):
    os.makedirs(output_dir, exist_ok=True)
    for name, df in dataframes.items():
        file_path = os.path.join(output_dir, f'{name}.parquet')
        df.to_parquet(file_path, index=False)
        print(f"Exported {name} to {file_path}")


def get_table_columns(table_name):
    try:
        df = pd.read_sql(f"SELECT TOP 0 * FROM {table_name}", engine)
        return [c for c in df.columns]
    except Exception:
        return []


def get_encounter_date_range():
    """Return (min_date, max_date) from encounters table as date objects, or (None, None)."""
    try:
        df = pd.read_sql("SELECT MIN(encounter_date) as min_d, MAX(encounter_date) as max_d FROM encounters", engine)
        min_d = df.iloc[0]['min_d']
        max_d = df.iloc[0]['max_d']
        if pd.isna(min_d) or pd.isna(max_d):
            return None, None
        return pd.to_datetime(min_d).date(), pd.to_datetime(max_d).date()
    except Exception:
        return None, None


def generate_date_dimension(start_date, end_date):
    """Generate a comprehensive date dimension between two dates (inclusive).

    Columns included (common standards):
      - date: date
      - date_key: YYYYMMDD integer
      - year, month, month_name, month_short
      - day, day_of_week (0=Mon), day_of_week_name
      - is_weekend
      - quarter
      - iso_year, iso_week
      - day_of_year
      - week_of_year
      - fiscal_year, fiscal_month (fiscal start month = 1 by default)
      - formatted variants: mm_dd_yyyy, dd_mm_yyyy, yyyy_mm_dd
    """
    # normalize inputs to pandas Timestamp
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    dates = pd.date_range(start=start, end=end, freq='D')
    rows = []
    for d in dates:
        iso = d.isocalendar()
        fiscal_start_month = 1
        fiscal_year = d.year if d.month >= fiscal_start_month else d.year - 1
        rows.append({
            'date': d.date(),
            'date_key': int(d.strftime('%Y%m%d')),
            'yyyy': d.year,
            'mm': d.month,
            'mm_name': d.strftime('%B'),
            'mm_short': d.strftime('%b'),
            'dd': d.day,
            'day_of_week': d.weekday(),
            'day_of_week_name': d.strftime('%A'),
            'is_weekend': 1 if d.weekday() >= 5 else 0,
            'quarter': (d.month - 1) // 3 + 1,
            'iso_year': iso.year,
            'iso_week': int(iso.week),
            'day_of_year': int(d.strftime('%j')),
            'week_of_year': int(d.strftime('%U')),
            'fiscal_year': fiscal_year,
            'fiscal_month': ((d.month - fiscal_start_month) % 12) + 1,
            'mm_dd_yyyy': d.strftime('%m-%d-%Y'),
            'dd_mm_yyyy': d.strftime('%d-%m-%Y'),
            'yyyy_mm_dd': d.strftime('%Y-%m-%d')
        })
    df = pd.DataFrame(rows)
    return df


def generate_hospital_department_beds(hospitals_df, departments_df, effective_date):
    """Allocate beds to each department for each hospital using realistic percentages.
    
    Uses DEPARTMENT_BED_ALLOCATION to assign beds based on real-world hospital bed distribution.
    ER gets 5-8% of beds, Internal Medicine gets 30-40%, etc.
    
    Returns DataFrame with columns: hospital_id, department_id, date, beds_allocated
    """
    rows = []
    
    for _, h in hospitals_df.iterrows():
        hid = int(h['hospital_id'])
        total_beds = int(h['bed_count'])
        
        # Get departments for this hospital
        deps = departments_df[departments_df['hospital_id'] == hid]
        if deps.empty:
            # No departments: create catch-all 'General' bucket
            rows.append({'hospital_id': hid, 'department_id': None, 'date': effective_date, 'beds_allocated': total_beds})
            continue
        
        # Calculate bed allocation using realistic percentages
        allocations = []
        for _, dep in deps.iterrows():
            dept_name = dep['name']
            # Get allocation percentage from lookup, or use default
            allocation_pct = DEPARTMENT_BED_ALLOCATION.get(dept_name, DEPARTMENT_BED_ALLOCATION['default'])
            beds = int(total_beds * allocation_pct)
            allocations.append({'dept': dep, 'beds': beds})
        
        # Normalize allocations to match total_beds exactly
        allocated_sum = sum(a['beds'] for a in allocations)
        
        if allocated_sum > 0:
            # Proportionally adjust to match total
            ratio = total_beds / allocated_sum
            adjusted = []
            for a in allocations:
                adjusted_beds = int(a['beds'] * ratio)
                adjusted.append({'dept': a['dept'], 'beds': adjusted_beds})
            
            # Handle rounding remainder
            remainder = total_beds - sum(a['beds'] for a in adjusted)
            # Distribute remainder to largest departments first
            sorted_adjusted = sorted(adjusted, key=lambda x: x['beds'], reverse=True)
            for i in range(abs(remainder)):
                if remainder > 0:
                    sorted_adjusted[i % len(sorted_adjusted)]['beds'] += 1
                else:
                    sorted_adjusted[i % len(sorted_adjusted)]['beds'] -= 1
            
            # Build final rows
            for a in sorted_adjusted:
                rows.append({
                    'hospital_id': hid,
                    'department_id': int(a['dept']['department_id']),
                    'date': effective_date,
                    'beds_allocated': int(a['beds'])
                })
        else:
            # Fallback: equal distribution
            beds_per_dept = total_beds // len(deps)
            remainder = total_beds % len(deps)
            for i, (_, dep) in enumerate(deps.iterrows()):
                beds = beds_per_dept + (1 if i < remainder else 0)
                rows.append({
                    'hospital_id': hid,
                    'department_id': int(dep['department_id']),
                    'date': effective_date,
                    'beds_allocated': int(beds)
                })
    
    return pd.DataFrame(rows)


def generate_admissions_for_day(hospitals_df, encounters_df, patients_df, departments_df, date, start_admission_id=1):
    """Generate admissions for inpatient encounters on the given date.

    Produces columns: admission_id, patient_id, hospital_id, department_id, encounter_id, admit_datetime, discharge_datetime
    discharge_datetime may be NULL to represent ongoing admissions.
    """
    rows = []
    # select inpatient encounters for that date
    if 'encounter_type' in encounters_df.columns:
        inpatients = encounters_df[encounters_df['encounter_type'] == 'Inpatient']
    else:
        inpatients = pd.DataFrame()

    aid = start_admission_id
    for _, enc in inpatients.iterrows():
        pid = int(enc.get('patient_id', random.randint(1, max(1, len(patients_df)))))
        hid = int(enc.get('hospital_id', random.choice(hospitals_df['hospital_id'].tolist())))
        dept_id = enc.get('provider_id')  # fallback; we'll try to map a department
        # map to an emergency department if encounter is emergency-like
        # find Emergency dept for hospital if exists
        ed = departments_df[(departments_df['hospital_id'] == hid) & (departments_df['name'].str.lower() == 'emergency')]
        if not ed.empty:
            dept_id = int(ed.iloc[0]['department_id'])
        # admit time within the day
        admit_dt = pd.to_datetime(date) + pd.Timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
        # discharge: 50% chance discharged within 0-7 days, otherwise open
        if random.random() < 0.5:
            discharge_dt = admit_dt + pd.Timedelta(days=random.randint(0, 7), hours=random.randint(0,23))
        else:
            discharge_dt = None

        row = {
            'admission_id': aid,
            'patient_id': pid,
            'hospital_id': hid,
            'department_id': int(dept_id) if dept_id is not None else None,
            'encounter_id': int(enc.get('encounter_id', -1)),
            'admit_datetime': admit_dt,
            'discharge_datetime': discharge_dt
        }
        rows.append(row)
        aid += 1

    df = pd.DataFrame(rows)
    return df


def generate_admissions_for_day_specialty_aware(hospitals_df, encounters_df, patients_df, departments_df, date, start_admission_id=1):
    """Generate admissions for inpatient encounters on the given date, using hospital-specific admission rates and timing.
    
    Uses get_admission_rate() for hospital specialty admission rates.
    Uses get_admission_times_by_specialty() for specialty-specific hour distributions.
    """
    rows = []
    
    # select inpatient encounters for that date
    if 'encounter_type' in encounters_df.columns:
        inpatients = encounters_df[encounters_df['encounter_type'] == 'Inpatient']
    else:
        inpatients = pd.DataFrame()
    
    aid = start_admission_id
    
    # Group encounters by hospital to apply specialty-specific admission rates
    hospital_lookup = {h['hospital_id']: h for h in HOSPITALS}
    
    for _, enc in inpatients.iterrows():
        hid = int(enc.get('hospital_id', random.choice(hospitals_df['hospital_id'].tolist())))
        
        # Get hospital specialty for admission rate and timing lookup
        hospital = hospital_lookup.get(hid, {'specialty': 'general'})
        specialty = hospital.get('specialty', 'general')
        
        # Get specialty-specific admission rate
        admission_prob = get_admission_rate(specialty)
        
        # Randomly decide if this encounter becomes an admission
        if random.random() > admission_prob:
            # Skip this encounter - not admitted
            continue
        
        pid = int(enc.get('patient_id', random.randint(1, max(1, len(patients_df)))))
        dept_id = enc.get('provider_id')
        
        # map to an emergency department if encounter is emergency-like
        ed = departments_df[(departments_df['hospital_id'] == hid) & (departments_df['name'].str.lower().str.contains('emergency', na=False))]
        if not ed.empty:
            dept_id = int(ed.iloc[0]['department_id'])
        
        # Get specialty-specific admission time distribution
        admit_hours = get_admission_times_by_specialty(specialty, num_admissions=1)
        admit_hour = admit_hours[0] if admit_hours else random.randint(0, 23)
        
        # admit time within the day at the specialty-appropriate hour
        admit_dt = pd.to_datetime(date) + pd.Timedelta(hours=admit_hour, minutes=random.randint(0, 59))
        
        # Get specialty-specific average LOS for discharge prediction
        avg_los = get_average_los(specialty)
        
        # discharge: 60% chance discharged within LOS range, 40% still inpatient
        if random.random() < 0.60:
            # Generate discharge with variance around avg LOS
            los_days = max(0, int(avg_los + random.gauss(0, avg_los * 0.3)))  # ±30% variance
            discharge_dt = admit_dt + pd.Timedelta(days=los_days, hours=random.randint(7, 17))  # Discharge 7am-5pm
        else:
            discharge_dt = None  # Still inpatient
        
        row = {
            'admission_id': aid,
            'patient_id': pid,
            'hospital_id': hid,
            'department_id': int(dept_id) if dept_id is not None else None,
            'encounter_id': int(enc.get('encounter_id', -1)),
            'admit_datetime': admit_dt,
            'discharge_datetime': discharge_dt
        }
        rows.append(row)
        aid += 1
    
    df = pd.DataFrame(rows)
    return df


def create_current_er_beds_view():
    """Create or replace a SQL view showing current ER bedcount per hospital."""
    # Use CREATE OR ALTER VIEW for SQL Server compatibility
    sql = """
    CREATE OR ALTER VIEW vw_current_er_beds AS
    SELECT
      h.hospital_id,
      h.name AS hospital_name,
      ISNULL(b.beds_allocated, 0) AS er_beds
    FROM hospitals h
    LEFT JOIN (
      SELECT hb.hospital_id, hb.beds_allocated
      FROM hospital_department_beds hb
      JOIN departments d ON hb.department_id = d.department_id
      WHERE d.name = 'Emergency'
        AND hb.date = (SELECT MAX(date) FROM hospital_department_beds)
    ) b ON h.hospital_id = b.hospital_id;
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as e:
        print('Warning: could not create vw_current_er_beds view:', e)


def create_current_patient_beds_view():
        """Create or replace a SQL view showing current patient bed counts per hospital.

        This view uses the latest date available in `hospital_department_beds` for allocated beds
        and the latest date available in `encounters` to count current inpatient encounters.
        If you need more accurate occupancy (admissions/discharges, bed-level assignments),
        add an `admissions` table with `admit_date` and `discharge_date` or add `admitted`/`discharged` fields.
        """
        # Use admissions table for accurate occupancy: count admissions where
        # admit_date <= latest_date AND (discharge_date IS NULL OR discharge_date > latest_date)
        sql = """
        CREATE OR ALTER VIEW vw_current_patient_beds AS
        SELECT
            h.hospital_id,
            h.name AS hospital_name,
            ISNULL(a.total_beds, 0) AS allocated_beds,
            ISNULL(o.occupied_beds, 0) AS occupied_beds,
            ISNULL(a.total_beds, 0) - ISNULL(o.occupied_beds, 0) AS available_beds
        FROM hospitals h
        LEFT JOIN (
            SELECT hospital_id, SUM(beds_allocated) AS total_beds
            FROM hospital_department_beds
            WHERE date = (SELECT MAX(date) FROM hospital_department_beds)
            GROUP BY hospital_id
        ) a ON h.hospital_id = a.hospital_id
        LEFT JOIN (
            SELECT hospital_id, COUNT(*) AS occupied_beds
            FROM admissions
            WHERE CAST(admit_datetime AS DATE) <= (SELECT MAX(date) FROM hospital_department_beds)
                AND (discharge_datetime IS NULL OR CAST(discharge_datetime AS DATE) > (SELECT MAX(date) FROM hospital_department_beds))
            GROUP BY hospital_id
        ) o ON h.hospital_id = o.hospital_id;
        """
        try:
                with engine.begin() as conn:
                        conn.execute(text(sql))
        except Exception as e:
                print('Warning: could not create vw_current_patient_beds view:', e)


def align_df_to_table(df, table_name):
    """Return a dataframe containing only columns that exist in target table.
    If the table does not exist or has no columns, return original df so to_sql can create it.
    """
    cols = get_table_columns(table_name)
    if not cols:
        return df
    common = [c for c in df.columns if c in cols]
    if not common:
        # No overlapping columns; return df to allow table creation by to_sql
        return df
    return df[common]

def main(frequency='once', export_parquet=False, rebuild_start=None):
    if export_parquet and frequency != 'once':
        print("Error: --export-parquet is only supported for full load (frequency='once').")
        return
    
    # If rebuild_start provided, perform full rebuild from that date to today
    if rebuild_start:
        try:
            start_date = datetime.strptime(rebuild_start, "%Y-%m-%d").date()
        except Exception as e:
            print(f"Invalid rebuild start date: {rebuild_start}. Use YYYY-MM-DD.")
            return
        end_date = datetime.now().date()
        days = (end_date - start_date).days + 1
        print(f"[REBUILD] Full rebuild requested: {start_date} -> {end_date} ({days} days). Truncating and repopulating tables.")
        # Generate & write date dimension once for full rebuild range
        date_dim_df = generate_date_dimension(start_date, end_date)
        date_dim_df.to_sql('date_dim', engine, if_exists='replace', index=False)

        # daily counts
        patient_count = 50
        doctor_count = 5
        procedure_count = 100
        encounter_count = 150
        diagnosis_count = 200
        medication_count = 125
        lab_count = 175
        insurance_count = 50
        billing_count = 150

        # add admissions to next id counters

        # initialize running id counters
        next_ids = {
            'patient': 1,
            'provider': 1,
            'encounter': 1,
            'procedure': 1,
            'diagnosis': 1,
            'medication': 1,
            'lab': 1,
            'insurance': 1,
            'billing': 1,
            'admission': 1
        }

        first = True
        # iterate each day and append (or replace on first iteration)
        for day_offset in range(days):
            day = start_date + timedelta(days=day_offset)
            print(f"Generating data for {day}...")

            hospitals_df = pd.DataFrame(HOSPITALS)
            departments_df = pd.DataFrame(DEPARTMENTS)

            # generate patients/providers for the day and assign global ids
            patients_df = generate_patients(patient_count)
            patients_df['patient_id'] = range(next_ids['patient'], next_ids['patient'] + len(patients_df))

            doctors_df = generate_doctors(doctor_count)
            doctors_df['provider_id'] = range(next_ids['provider'], next_ids['provider'] + len(doctors_df))

            # ===== HOSPITAL-SPECIFIC GENERATION =====
            # Instead of global encounter_count, generate per-hospital with specialty multipliers
            encounters_df = pd.DataFrame()
            diagnoses_df = pd.DataFrame()
            procedures_df = pd.DataFrame()
            
            # Get the month for specialty multiplier lookup
            month = day.month
            
            # Generate encounters per hospital with specialty-adjusted counts
            for hospital in HOSPITALS:
                hospital_id = hospital['hospital_id']
                specialty = hospital.get('specialty', 'general')
                
                # Get specialty-adjusted encounter count for this hospital
                hosp_encounter_count = get_hospital_monthly_encounters(specialty, month, base_encounters=150)
                
                # Scale by hospital size (bed_count) with realistic variation (5-30%)
                total_beds = sum(h['bed_count'] for h in HOSPITALS)
                bed_ratio = hospital['bed_count'] / total_beds
                
                # Apply bed-based distribution with random variation (5-30%)
                variation = random.uniform(0.85, 1.30)  # +/- 15% to 30% variation
                hosp_encounter_count = max(1, int(hosp_encounter_count * bed_ratio * 10 * variation))
                
                # Generate encounters for this hospital on this day
                hosp_encounters = generate_encounters(
                    hosp_encounter_count,
                    min_date=day,
                    end_date=day,
                    patient_start=next_ids['patient'],
                    patient_count=patient_count,
                    provider_start=next_ids['provider'],
                    provider_count=doctor_count,
                    hospital_id=hospital_id
                )
                
                # Assign encounter IDs
                hosp_encounters['encounter_id'] = range(next_ids['encounter'], next_ids['encounter'] + len(hosp_encounters))
                next_ids['encounter'] += len(hosp_encounters)
                
                # Append to master encounters dataframe
                encounters_df = pd.concat([encounters_df, hosp_encounters], ignore_index=True)
                
                # Generate specialty-specific diagnoses for these encounters
                # Fetch weather for the specific day
                w_cond, w_imp = get_weather_for_date(day)
                
                # Get specialty-specific diagnosis distribution
                specialty_diags = get_specialty_diagnoses(specialty)
                
                # Generate diagnoses for this hospital's encounters
                hosp_diagnosis_count = int(diagnosis_count * (hosp_encounter_count / encounter_count)) if encounter_count > 0 else 0
                hosp_diagnoses = []
                for _ in range(hosp_diagnosis_count):
                    # Pick from specialty-specific diagnosis distribution with seasonality & weather
                    icd_code = sample_diagnosis_for_hospital(specialty, day.month, weather_condition=w_cond)
                    details = DIAGNOSIS_DETAILS.get(icd_code, {'description': 'Unknown diagnosis', 'complaints': ['Unknown complaint']})
                    diag = {
                        'encounter_id': random.choice(hosp_encounters['encounter_id'].tolist()) if len(hosp_encounters) > 0 else 1,
                        'patient_id': random.randint(next_ids['patient'], max(next_ids['patient'], next_ids['patient'] + patient_count - 1)),
                        'icd_code': icd_code,
                        'description': details['description'],
                        'onset_date': day,
                        'status': random.choice(['Active', 'Resolved', 'Chronic'])
                    }
                    hosp_diagnoses.append(diag)
                
                hosp_diag_df = pd.DataFrame(hosp_diagnoses)
                if not hosp_diag_df.empty:
                    hosp_diag_df['diagnosis_id'] = range(next_ids['diagnosis'], next_ids['diagnosis'] + len(hosp_diag_df))
                    next_ids['diagnosis'] += len(hosp_diag_df)
                    diagnoses_df = pd.concat([diagnoses_df, hosp_diag_df], ignore_index=True)
            
            # Procedures - attach to real encounters with specialty-aware sampling
            procedures_df = generate_procedures(procedure_count, min_date=day, end_date=day, encounters_df=encounters_df)
            if not procedures_df.empty:
                procedures_df['procedure_id'] = range(next_ids['procedure'], next_ids['procedure'] + len(procedures_df))
                next_ids['procedure'] += len(procedures_df)

            # Diagnoses already generated per-hospital above, so skip duplicate generation

            medications_df = generate_medications(medication_count, min_date=day, end_date=day, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
            medications_df['medication_id'] = range(next_ids['medication'], next_ids['medication'] + len(medications_df))
            # medications already reference real encounters and patients when generated from encounters_df
            if 'prescribing_provider_id' in medications_df.columns:
                medications_df['prescribing_provider_id'] = medications_df['prescribing_provider_id'] + (next_ids['provider'] - 1)

            labs_df = generate_labs(lab_count, min_date=day, end_date=day, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
            labs_df['lab_id'] = range(next_ids['lab'], next_ids['lab'] + len(labs_df))
            # labs already reference real encounters and patients when generated from encounters_df

            insurance_df = generate_insurance_for_patients(patients_df, min_date=day)
            insurance_df['insurance_id'] = range(next_ids['insurance'], next_ids['insurance'] + len(insurance_df))
            # patient ids already aligned to today's generated patients; no offset needed here

            billing_df = generate_billing(billing_count, min_date=day)
            billing_df['billing_id'] = range(next_ids['billing'], next_ids['billing'] + len(billing_df))
            if 'encounter_id' in billing_df.columns:
                billing_df['encounter_id'] = billing_df['encounter_id'] + (next_ids['encounter'] - 1)
            if 'patient_id' in billing_df.columns:
                billing_df['patient_id'] = billing_df['patient_id'] + (next_ids['patient'] - 1)

            # generate admissions for inpatient encounters for this day
            # Use hospital-specific admission rates and timing
            admissions_df = generate_admissions_for_day_specialty_aware(hospitals_df, encounters_df, patients_df, departments_df, day, start_admission_id=next_ids['admission'])

            # Insert into DB (replace on first day to recreate schema, append afterwards)
            if first:
                hospitals_df.to_sql('hospitals', engine, if_exists='replace', index=False)
                departments_df.to_sql('departments', engine, if_exists='replace', index=False)
                patients_df.to_sql('patients', engine, if_exists='replace', index=False)
                doctors_df.to_sql('doctors', engine, if_exists='replace', index=False)
                procedures_df.to_sql('procedures', engine, if_exists='replace', index=False)
                encounters_df.to_sql('encounters', engine, if_exists='replace', index=False)
                diagnoses_df.to_sql('diagnoses', engine, if_exists='replace', index=False)
                medications_df.to_sql('medications', engine, if_exists='replace', index=False)
                labs_df.to_sql('labs', engine, if_exists='replace', index=False)
                insurance_df.to_sql('insurance', engine, if_exists='replace', index=False)
                billing_df.to_sql('billing', engine, if_exists='replace', index=False)
                admissions_df.to_sql('admissions', engine, if_exists='replace', index=False)
                # generate department bed allocations for this day and write
                dept_beds_df = generate_hospital_department_beds(hospitals_df, departments_df, day)
                dept_beds_df.to_sql('hospital_department_beds', engine, if_exists='replace', index=False)
                # create or update ER beds view
                create_current_er_beds_view()
                # create or update patient beds view
                create_current_patient_beds_view()
                first = False
            else:
                patients_df.to_sql('patients', engine, if_exists='append', index=False)
                doctors_df.to_sql('doctors', engine, if_exists='append', index=False)
                procedures_df.to_sql('procedures', engine, if_exists='append', index=False)
                encounters_df.to_sql('encounters', engine, if_exists='append', index=False)
                diagnoses_df.to_sql('diagnoses', engine, if_exists='append', index=False)
                medications_df.to_sql('medications', engine, if_exists='append', index=False)
                labs_df.to_sql('labs', engine, if_exists='append', index=False)
                insurance_df.to_sql('insurance', engine, if_exists='append', index=False)
                billing_df.to_sql('billing', engine, if_exists='append', index=False)
                if not admissions_df.empty:
                    admissions_df.to_sql('admissions', engine, if_exists='append', index=False)
                # append department bed allocations for this day
                dept_beds_df = generate_hospital_department_beds(hospitals_df, departments_df, day)
                dept_beds_df.to_sql('hospital_department_beds', engine, if_exists='append', index=False)
                create_current_er_beds_view()
                create_current_patient_beds_view()

            # advance counters
            next_ids['patient'] += len(patients_df)
            next_ids['provider'] += len(doctors_df)
            next_ids['encounter'] += len(encounters_df)
            next_ids['procedure'] += len(procedures_df)
            next_ids['diagnosis'] += len(diagnoses_df)
            next_ids['medication'] += len(medications_df)
            next_ids['lab'] += len(labs_df)
            next_ids['insurance'] += len(insurance_df)
            next_ids['billing'] += len(billing_df)
            next_ids['admission'] += len(admissions_df)

        print("Full rebuild complete.")
        save_weather_cache()
        return

    # Get the last run timestamp to generate dates since then
    try:
        last_run_df = pd.read_sql("SELECT MAX(run_timestamp) as last_run FROM run_logs", engine)
        last_run = last_run_df.iloc[0]['last_run']
        if pd.isna(last_run):
            last_run = datetime(2026, 1, 1)  # Default to start of year if no logs
        else:
            last_run = pd.to_datetime(last_run)
    except:
        last_run = datetime(2026, 1, 1)  # Fallback
    
    # Check if catch-up is needed (app hasn't run in more than 24 hours)
    time_since_last_run = datetime.now() - last_run
    needs_catchup = time_since_last_run > timedelta(hours=24)
    
    if needs_catchup:
        print(f"⚠️  Catch-up needed! Last run was {time_since_last_run.days} days and {time_since_last_run.seconds // 3600} hours ago.")
        print(f"📊 Generating catch-up data from {last_run.date()} to today...")
        
        # Generate multiple rounds of daily data to catch up
        days_behind = time_since_last_run.days
        if days_behind > 7:
            print(f"📈 Generating {days_behind} days of backfilled data...")
            frequency = 'daily'
        else:
            frequency = 'daily'
    else:
        print(f"✓ Data is current (last run: {last_run})")
    
    # Get current weather conditions
    print("🌤️  Checking weather conditions...")
    weather_condition, weather_impacts = get_current_weather()
    print(f"Current weather: {weather_condition.upper()}")
    if weather_condition != 'clear':
        print(f"  → Flu hospitalizations will increase by {weather_impacts['flu_multiplier']:.1f}x")
        print(f"  → Fall-related injuries will increase by {weather_impacts['fall_multiplier']:.1f}x")

    # Determine number of records based on frequency
    if frequency == 'hourly':
        patient_count = 10
        doctor_count = 2
        procedure_count = 20
        encounter_count = 30
        diagnosis_count = 40
        medication_count = 25
        lab_count = 35
        insurance_count = 10
        billing_count = 30
    elif frequency == 'daily':
        patient_count = 50
        doctor_count = 5
        procedure_count = 100
        encounter_count = 150
        diagnosis_count = 200
        medication_count = 125
        lab_count = 175
        insurance_count = 50
        billing_count = 150
    else:  # once or default
        patient_count = 100
        doctor_count = 20
        procedure_count = 200
        encounter_count = 300
        diagnosis_count = 400
        medication_count = 250
        lab_count = 350
        insurance_count = 100
        billing_count = 300

    if export_parquet:
        # For export, generate full load data without date constraints
        hospitals_df = pd.DataFrame(HOSPITALS)
        departments_df = pd.DataFrame(DEPARTMENTS)
        patients_df = generate_patients(patient_count)
        doctors_df = generate_doctors(doctor_count)
        encounters_df = generate_encounters(encounter_count)
        # tie procedures/meds/labs to encounters/diagnoses for realism
        procedures_df = generate_procedures(procedure_count, encounters_df=encounters_df)
        diagnoses_df = generate_diagnoses_weather_aware(diagnosis_count, weather_condition=weather_condition, weather_impacts=weather_impacts)
        medications_df = generate_medications(medication_count, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
        labs_df = generate_labs(lab_count, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
        insurance_df = generate_insurance_for_patients(patients_df)
        billing_df = generate_billing(billing_count)
    else:
        # Generate data with date constraints for incremental loads
        hospitals_df = pd.DataFrame(HOSPITALS)
        departments_df = pd.DataFrame(DEPARTMENTS)

        # Generate base tables first (they include local sequential ids starting at 1)
        patients_df = generate_patients(patient_count)
        doctors_df = generate_doctors(doctor_count)

        # Determine next id offsets in target DB to avoid collisions
        patient_start = get_next_id('patients', 'patient_id')
        provider_start = get_next_id('doctors', 'provider_id')
        encounter_start = get_next_id('encounters', 'encounter_id')
        procedure_start = get_next_id('procedures', 'procedure_id')
        diagnosis_start = get_next_id('diagnoses', 'diagnosis_id')
        medication_start = get_next_id('medications', 'medication_id')
        lab_start = get_next_id('labs', 'lab_id')
        insurance_start = get_next_id('insurance', 'insurance_id')
        billing_start = get_next_id('billing', 'billing_id')

        # Offset primary keys in generated base tables before inserting
        patients_df['patient_id'] = patients_df['patient_id'] + (patient_start - 1)
        doctors_df['provider_id'] = doctors_df['provider_id'] + (provider_start - 1)

        # Admissions generation moved to after encounters_df creation (see later)

        # Now generate dependent records using local id ranges (1..count) then offset them
        encounters_df = generate_encounters(encounter_count, last_run, patient_start=1, patient_count=patient_count, provider_start=1, provider_count=doctor_count)
        # generate admissions for today's incremental load (based on encounters) - specialty-aware
        admissions_df = generate_admissions_for_day_specialty_aware(hospitals_df, encounters_df, patients_df, departments_df, pd.to_datetime(datetime.now()).date(), start_admission_id=get_next_id('admissions', 'admission_id'))
        # Procedures and other clinical artifacts can be tied to generated encounters/diagnoses for realism
        procedures_df = generate_procedures(procedure_count, last_run, encounters_df=encounters_df)
        diagnoses_df = generate_diagnoses_weather_aware(diagnosis_count, last_run, weather_condition=weather_condition, weather_impacts=weather_impacts)
        medications_df = generate_medications(medication_count, last_run, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
        labs_df = generate_labs(lab_count, last_run, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
        insurance_df = generate_insurance_for_patients(patients_df, min_date=last_run)
        billing_df = generate_billing(billing_count)

        # Offset dependent IDs so they point to the real rows in DB
        # Encounters reference patients and providers
        encounters_df['encounter_id'] = encounters_df['encounter_id'] + (encounter_start - 1)
        encounters_df['patient_id'] = encounters_df['patient_id'] + (patient_start - 1)
        encounters_df['provider_id'] = encounters_df['provider_id'] + (provider_start - 1)

        # Procedures, diagnoses, medications, labs, billing reference encounter_ids -> offset them
        if 'procedure_id' in procedures_df.columns:
            procedures_df['procedure_id'] = procedures_df['procedure_id'] + (procedure_start - 1)
        if 'encounter_id' in procedures_df.columns:
            procedures_df['encounter_id'] = procedures_df['encounter_id'] + (encounter_start - 1)

        if 'diagnosis_id' in diagnoses_df.columns:
            diagnoses_df['diagnosis_id'] = diagnoses_df['diagnosis_id'] + (diagnosis_start - 1)
        if 'encounter_id' in diagnoses_df.columns:
            diagnoses_df['encounter_id'] = diagnoses_df['encounter_id'] + (encounter_start - 1)
        if 'patient_id' in diagnoses_df.columns:
            diagnoses_df['patient_id'] = diagnoses_df['patient_id'] + (patient_start - 1)

        if 'medication_id' in medications_df.columns:
            medications_df['medication_id'] = medications_df['medication_id'] + (medication_start - 1)
        if 'encounter_id' in medications_df.columns:
            medications_df['encounter_id'] = medications_df['encounter_id'] + (encounter_start - 1)
        if 'patient_id' in medications_df.columns:
            medications_df['patient_id'] = medications_df['patient_id'] + (patient_start - 1)
        if 'prescribing_provider_id' in medications_df.columns:
            medications_df['prescribing_provider_id'] = medications_df['prescribing_provider_id'] + (provider_start - 1)

        if 'lab_id' in labs_df.columns:
            labs_df['lab_id'] = labs_df['lab_id'] + (lab_start - 1)
        if 'encounter_id' in labs_df.columns:
            labs_df['encounter_id'] = labs_df['encounter_id'] + (encounter_start - 1)
        if 'patient_id' in labs_df.columns:
            labs_df['patient_id'] = labs_df['patient_id'] + (patient_start - 1)

        if 'insurance_id' in insurance_df.columns:
            insurance_df['insurance_id'] = insurance_df['insurance_id'] + (insurance_start - 1)
        if 'patient_id' in insurance_df.columns:
            insurance_df['patient_id'] = insurance_df['patient_id'] + (patient_start - 1)

        if 'billing_id' in billing_df.columns:
            billing_df['billing_id'] = billing_df['billing_id'] + (billing_start - 1)
        if 'encounter_id' in billing_df.columns:
            billing_df['encounter_id'] = billing_df['encounter_id'] + (encounter_start - 1)
        if 'patient_id' in billing_df.columns:
            billing_df['patient_id'] = billing_df['patient_id'] + (patient_start - 1)

    if export_parquet:
        # Export to Parquet files
        dataframes = {
            'hospitals': hospitals_df,
            'departments': departments_df,
            'patients': patients_df,
            'doctors': doctors_df,
            'procedures': procedures_df,
            'encounters': encounters_df,
            'diagnoses': diagnoses_df,
            'medications': medications_df,
            'labs': labs_df,
            'insurance': insurance_df,
            'billing': billing_df
        }
        export_to_parquet(dataframes)
        print("Data exported to Parquet files successfully.")
    else:
        # Insert into database
        # Ensure date dimension covers existing DB encounters and newly generated encounters
        db_min, db_max = get_encounter_date_range()
        try:
            if 'encounter_date' in encounters_df.columns and len(encounters_df) > 0:
                gen_min = pd.to_datetime(encounters_df['encounter_date']).min().date()
                gen_max = pd.to_datetime(encounters_df['encounter_date']).max().date()
            else:
                gen_min, gen_max = None, None
        except Exception:
            gen_min, gen_max = None, None

        # Determine combined range
        combined_min = None
        combined_max = None
        if db_min and gen_min:
            combined_min = min(db_min, gen_min)
        elif db_min:
            combined_min = db_min
        elif gen_min:
            combined_min = gen_min

        if db_max and gen_max:
            combined_max = max(db_max, gen_max)
        elif db_max:
            combined_max = db_max
        elif gen_max:
            combined_max = gen_max

        if combined_min and combined_max:
            date_dim_df = generate_date_dimension(combined_min, combined_max)
            # Replace date_dim to ensure it covers full required range
            date_dim_df.to_sql('date_dim', engine, if_exists='replace', index=False)

        print("💾 Inserting data into database...")
        hospitals_df.to_sql('hospitals', engine, if_exists='replace', index=False)
        departments_df.to_sql('departments', engine, if_exists='replace', index=False)
        # generate department bed allocations for today's incremental load
        today = pd.to_datetime(datetime.now()).date()
        dept_beds_df = generate_hospital_department_beds(hospitals_df, departments_df, today)
        # upsert strategy: append row for today; if table missing, to_sql will create it
        dept_beds_df.to_sql('hospital_department_beds', engine, if_exists='append', index=False)
        # write admissions for today
        if not admissions_df.empty:
            admissions_df.to_sql('admissions', engine, if_exists='append', index=False)
        create_current_er_beds_view()
        create_current_patient_beds_view()
        # Align DataFrames with existing DB schema to avoid inserting unknown columns
        align_df_to_table(patients_df, 'patients').to_sql('patients', engine, if_exists='append', index=False)
        align_df_to_table(doctors_df, 'doctors').to_sql('doctors', engine, if_exists='append', index=False)
        align_df_to_table(procedures_df, 'procedures').to_sql('procedures', engine, if_exists='append', index=False)
        align_df_to_table(encounters_df, 'encounters').to_sql('encounters', engine, if_exists='append', index=False)
        align_df_to_table(diagnoses_df, 'diagnoses').to_sql('diagnoses', engine, if_exists='append', index=False)
        align_df_to_table(medications_df, 'medications').to_sql('medications', engine, if_exists='append', index=False)
        align_df_to_table(labs_df, 'labs').to_sql('labs', engine, if_exists='append', index=False)
        align_df_to_table(insurance_df, 'insurance').to_sql('insurance', engine, if_exists='append', index=False)
        align_df_to_table(billing_df, 'billing').to_sql('billing', engine, if_exists='append', index=False)

        # Log the run
        run_log = {
            'run_timestamp': datetime.now(),
            'frequency': frequency,
            'patients_generated': len(patients_df),
            'doctors_generated': len(doctors_df),
            'procedures_generated': len(procedures_df),
            'encounters_generated': len(encounters_df),
            'diagnoses_generated': len(diagnoses_df),
            'medications_generated': len(medications_df),
            'labs_generated': len(labs_df),
            'insurance_generated': len(insurance_df),
            'billing_generated': len(billing_df)
        }
        run_log_df = pd.DataFrame([run_log])
        run_log_df.to_sql('run_logs', engine, if_exists='append', index=False)

        print(f"\n✅ Data generation complete!")
        print(f"   Frequency: {frequency}")
        print(f"   Weather: {weather_condition}")
        print(f"   Total records generated: {len(diagnoses_df) + len(medications_df) + len(labs_df)}")
        save_weather_cache()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Healthcare Data Generator')
    parser.add_argument('--frequency', choices=['once', 'hourly', 'daily'], default='once',
                        help='Frequency of data infusion')
    parser.add_argument('--export-parquet', action='store_true',
                        help='Export data to Parquet files instead of database (full load only)')
    parser.add_argument('--rebuild-start', type=str, default=None,
                        help='Perform full rebuild from YYYY-MM-DD (inclusive) to today')
    parser.add_argument('--clear-weather-cache', action='store_true',
                        help='Clear the weather cache before running')
    args = parser.parse_args()
    
    if args.clear_weather_cache:
        WEATHER_CACHE.clear()
        if os.path.exists(WEATHER_CACHE_FILE):
            os.remove(WEATHER_CACHE_FILE)
        print("Weather cache cleared.")
    
    main(args.frequency, args.export_parquet, args.rebuild_start)