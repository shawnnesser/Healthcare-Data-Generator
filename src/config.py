# Database configuration
# Replace with your Fabric SQL Database details

SERVER = 'your-server.database.windows.net'
DATABASE = 'your-database'
USERNAME = 'your-username'
PASSWORD = 'your-password'
DRIVER = '{ODBC Driver 18 for SQL Server}'

# Connection string
# The connection string must not be committed to source control. Provide it via environment variable
# or by creating a local non-tracked file `src/config_local.py` containing CONNECTION_STRING.
import os
# Optional local override file (create `src/config_local.py`, add to .gitignore)
# Try relative import (package context), fall back to absolute import when running scripts directly
LOCAL_CONNECTION_STRING = None
try:
    from .config_local import CONNECTION_STRING as LOCAL_CONNECTION_STRING
except Exception:
    try:
        from config_local import CONNECTION_STRING as LOCAL_CONNECTION_STRING
    except Exception:
        LOCAL_CONNECTION_STRING = None

# Environment variable takes precedence
CONNECTION_STRING = os.getenv('CONNECTION_STRING') or LOCAL_CONNECTION_STRING or None

# If CONNECTION_STRING is None, the runtime will need to provide it; do NOT hardcode secrets here.

# Seasonality multipliers for realistic hospital patterns
# Based on CDC/NHS data on ED visit patterns and procedure seasonality
# All are normalized to mean ~1.0 so they scale encounter/procedure rates

# Hourly encounter multiplier (0–23, midnight to 23:00)
# Peak: afternoon/evening (16:00–20:00); trough: 03:00–05:00
HOURLY_MULTIPLIERS = [
    0.65, 0.54, 0.49, 0.43, 0.43, 0.60, 0.87, 1.03, 1.14, 1.14,
    1.14, 1.14, 1.08, 1.08, 1.14, 1.19, 1.30, 1.41, 1.52, 1.46,
    1.30, 1.14, 0.98, 0.81
]  # Sources: NHS A&E, NHAMCS (CDC)

# Day-of-week multiplier (Mon=0 → Sun=6)
# Higher Monday (primary-care backlog), elevated weekends (injuries)
DAY_OF_WEEK_MULTIPLIERS = [
    1.06,  # Monday
    0.98,  # Tuesday
    0.96,  # Wednesday
    0.96,  # Thursday
    1.00,  # Friday
    1.03,  # Saturday
    1.02   # Sunday
]  # Source: NHS/NHAMCS ED time-series

# Monthly multiplier (Jan=0 → Dec=11)
# Winter surge (flu/respiratory/cardiac), summer trough
MONTHLY_MULTIPLIERS = [
    1.12, 1.08, 1.02, 0.95, 0.93, 0.88,  # Jan-Jun
    0.85, 0.88, 0.95, 0.98, 1.02, 1.12   # Jul-Dec
]  # Source: CDC influenza season, NHS A&E monthly

# Hospital-type-specific monthly multipliers (Jan-Dec)
# Based on CDC/NHAMCS and specialty hospital patterns
# Pediatric hospitals: winter flu/RSV peaks
PEDIATRIC_MONTHLY = [
    1.35, 1.28, 0.95, 0.82, 0.78, 0.75, 0.85, 0.88, 0.92, 0.98, 1.18, 1.26
]  # Sources: CDC NHAMCS pediatric, NIH respiratory illness, AAP ED utilization

# Cardiac specialty centers: winter ACS peaks, summer dips
CARDIAC_MONTHLY = [
    1.38, 1.32, 1.08, 0.92, 0.85, 0.88, 0.87, 0.89, 0.95, 1.02, 1.18, 1.28
]  # Sources: AHA Cardiovascular Disease Statistics, seasonal ACS studies

# Cancer centers: stable year-round with summer vacation dip
CANCER_MONTHLY = [
    1.05, 1.03, 1.02, 1.01, 0.98, 0.95, 0.94, 0.96, 1.00, 1.02, 1.04, 1.06
]  # Sources: NCI SEER database, ASCO oncology admission patterns

# General hospitals: blended pattern
GENERAL_MONTHLY = [
    1.12, 1.08, 0.98, 0.92, 0.88, 0.85, 0.90, 0.93, 0.95, 1.00, 1.08, 1.18
]  # Sources: CDC NHAMCS, AHRQ ED utilization reports

# Rehabilitation centers: spring/fall peaks (post-surgical recovery)
REHAB_MONTHLY = [
    1.04, 1.02, 1.08, 1.10, 1.01, 0.98, 0.92, 0.95, 1.05, 1.12, 1.06, 1.00
]  # Sources: APTA rehabilitation statistics, Medicare utilization data

# Hourly ED bed occupancy (% of licensed beds occupied, 0-23 hours)
# General hospital ED context: peak 2-7pm (87-89%), trough 4-5am (38%)
HOURLY_ED_OCCUPANCY = [
    45, 42, 40, 38, 40, 45, 50, 58, 68, 75, 82, 85,  # Hours 0-11 (midnight-11am)
    88, 87, 88, 89, 88, 85, 82, 80, 78, 75, 70, 62   # Hours 12-23 (noon-11pm)
]  # Sources: ACEP ED operations, NHAMCS ED wait time data

# Day-of-week occupancy variance (multiplier on HOURLY_ED_OCCUPANCY)
# Friday peaks at 93% (1.04x stress), Sunday lowest at 82% (0.96x)
DAY_OF_WEEK_OCCUPANCY_MULT = {
    'Monday': 1.02,     # Start of week stress
    'Tuesday': 1.01,    # Sustained
    'Wednesday': 1.00,  # Mid-week
    'Thursday': 1.02,   # Pre-weekend
    'Friday': 1.04,     # PEAK - weekend prep, highest overall stress
    'Saturday': 0.97,   # Weekend lower (electives closed)
    'Sunday': 0.96      # Lowest occupancy
}

# Procedure weight seasonal adjustments (relative to baseline 1.0)
# Procedures not listed default to 1.0
PROCEDURE_SEASONALITY = {
    'Blood Test': 1.00,
    'X-Ray': 1.05,
    'MRI Scan': 1.00,
    'CT Scan': 1.03,
    'Colonoscopy': 0.95,
    'Endoscopy': 0.98,
    'Cardiac Catheterization': 1.15,  # Winter cardiac events
    'Appendectomy': 1.10,             # Summer peak
    'Hip Replacement': 1.08,          # Elective spring/summer
    'Knee Arthroscopy': 1.06,         # Elective orthopedics
    'Other': 1.00
}
# Sources: PMC studies on procedural seasonality, NHS diagnostics

# Payer market share (approximate US mix). These are used to sample patient payers and insurance distributions.
# Based on public payer mix data (Medicare, Medicaid, Commercial/Private, Uninsured, Other)
PAYER_MARKET_SHARE = {
    'Medicare': 0.36,
    'Medicaid': 0.20,
    'Commercial': 0.35,
    'Uninsured': 0.05,
    'Other': 0.04
}

# Specialty-specific payer adjustments (multipliers applied to base market share to reflect typical caseloads)
# e.g., Pediatrics tends to have higher Medicaid share; Cancer centers see higher Commercial/Medicare mix
SPECIALTY_PAYER_ADJUST = {
    'pediatric': {'Medicaid': 1.35, 'Commercial': 0.85, 'Medicare': 0.2},
    'cardiac': {'Medicare': 1.10, 'Commercial': 1.05, 'Medicaid': 0.9},
    'cancer': {'Commercial': 1.10, 'Medicare': 1.05, 'Medicaid': 0.9},
    'rehab': {'Medicare': 1.20, 'Medicaid': 0.95, 'Commercial': 0.9},
    'general': {},
    'specialty': {}
}
