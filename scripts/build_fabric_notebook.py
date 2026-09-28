"""
Build script: assembles the single-file Fabric notebook
(notebooks/healthcare_data_generator_fabric_inlined.ipynb) from the full-fidelity
generation logic that used to live across src/config.py, src/main.py,
src/hospital_generation_helpers.py and src/floor_management.py.

Run this script whenever the generation logic needs to change:
    python scripts/build_fabric_notebook.py

The output notebook is 100% self-contained (no imports from src/) and is the
artifact you upload/schedule in Microsoft Fabric.
"""
import nbformat as nbf
from pathlib import Path

nb = nbf.v4.new_notebook()
cells = []


def md(src):
    cells.append(nbf.v4.new_markdown_cell(src))


def code(src):
    cells.append(nbf.v4.new_code_cell(src))


# ---------------------------------------------------------------------------
md(r"""# Healthcare Data Generator — Microsoft Fabric (Complete, Single File)

**Single connection. Full clinical fidelity. Automatic daily catch-up.**

This notebook is the **only** artifact you need to deploy — it inlines the
entire generation engine (previously split across `src/main.py`,
`src/hospital_generation_helpers.py`, `src/floor_management.py`, and
`src/config.py`):

- 10 hospitals across 6 specialty types, with realistic departments, beds,
  floors, rooms and bed-level patient location tracking
- Hospital-specific seasonality, admission rates, length-of-stay and
  admission-time distributions
- Weather-driven diagnosis multipliers (flu, falls, accidents) using the
  Open-Meteo API with local caching
- Full ICD-10 clinical data — diagnoses, medications, labs, procedures,
  billing, insurance — with realistic diagnosis → medication/lab mappings
- **Catch-up on every run** — generates every missing day between the last
  loaded encounter date and today (run it daily, weekly, or after a long gap;
  it always fills the gap up to "now")
- **Single persistent connection** — one pooled SQLAlchemy engine for the
  whole run
- **Idempotent reference data** — hospitals/departments/floors/beds are only
  (re)initialized once; every subsequent run only appends new days

## Execution order
1. Config & environment
2. Dependency validation
3. Single database connection
4. Catch-up range detection (last loaded date → today)
5. Static reference data & constants
6. Hospital-specific helper functions (seasonality, admissions, payers, floors)
7. Weather functions (current + historical, cached)
8. Core data generators (patients, encounters, diagnoses, meds, labs, billing…)
9. Floor / room / bed / patient-location management
10. Orchestrator — generates every missing day and loads it
11. Patient-location refresh, view creation, run log
12. Validation & final report

## Configuration
```python
# Environment variable (recommended for Fabric)
CONNECTION_STRING = "Driver={ODBC Driver 18 for SQL Server};Server=..."

# or build from components
FABRIC_SERVER = "myworkspace.datawarehouse.pbidedicated.windows.net"
FABRIC_DB = "HealthcareODS"
```

### To regenerate this notebook
Edit the source of truth in `scripts/build_fabric_notebook.py` (or the
functions embedded below) and re-run the build script. The `src/` folder is
kept only as historical reference — this notebook is the production system.
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 1: Configuration & Environment Setup
# ============================================================================

import importlib
import subprocess
import sys


def _ensure_package(pip_name, import_name=None):
    # Auto-install packages that are commonly missing from the default Fabric
    # notebook runtime (faker/pyodbc/python-dotenv are not always pre-installed).
    import_name = import_name or pip_name
    try:
        importlib.import_module(import_name)
    except ImportError:
        print(f'Installing missing package: {pip_name}...')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', pip_name], check=False)


for _pip_name, _import_name in [
    ('faker', 'faker'),
    ('pyodbc', 'pyodbc'),
    ('python-dotenv', 'dotenv'),
    ('sqlalchemy', 'sqlalchemy'),
]:
    _ensure_package(_pip_name, _import_name)

import os
from pathlib import Path
from datetime import datetime, timedelta
import json

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / '.env')
except Exception:
    pass

# Target Fabric SQL endpoint (server/database). These defaults match the
# deployed Healthcare ODS SQL endpoint and can be overridden via env vars.
FABRIC_SERVER = os.getenv(
    'FABRIC_SERVER',
    '5mx5ymqwo74ezmng6awpg76wx4-f2smxdwfuzzenbkp2vylj5c5ca.database.fabric.microsoft.com'
)
FABRIC_DB = os.getenv('FABRIC_DB', 'Healthcare ODS-63ba7f40-a784-49f0-ae76-387233bc2616')

# Detect whether we're running inside a Fabric notebook session (Spark or
# pure-Python runtime both expose `notebookutils`). When running headless
# (e.g. triggered via the REST Jobs API with no human present), there is no
# way to complete an interactive browser login, so we authenticate with an
# AAD access token obtained from the Fabric-provided identity instead.
try:
    import notebookutils  # noqa: F401
    RUNNING_IN_FABRIC = True
except ImportError:
    RUNNING_IN_FABRIC = False


def _write_diagnostic(message):
    # Best-effort breadcrumb logger: writes a row directly via a throwaway
    # pyodbc connection (independent of SINGLE_ENGINE) so we can inspect
    # what happened during a headless run even if the main connection fails.
    # Never raises -- diagnostics must not affect the real notebook run.
    import struct as _struct
    token = None
    for _audience in ('pbi', 'https://database.windows.net/'):
        try:
            import notebookutils as _nu
            token = _nu.credentials.getToken(_audience)
            if token:
                break
        except Exception:
            pass
        try:
            import mssparkutils as _msu
            token = _msu.credentials.getToken(_audience)
            if token:
                break
        except Exception:
            pass
    try:
        import pyodbc as _pyodbc
        conn_str = (
            f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;'
            f'Database={FABRIC_DB};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
        )
        if token:
            token_bytes = token.encode('utf-16-le')
            token_struct = _struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
            conn = _pyodbc.connect(conn_str, attrs_before={1256: token_struct}, timeout=15)
        else:
            conn = _pyodbc.connect(
                conn_str.replace('Encrypt=yes', 'Authentication=ActiveDirectoryInteractive;Encrypt=yes'),
                timeout=15
            )
        cur = conn.cursor()
        cur.execute('''
            IF OBJECT_ID('notebook_diagnostics', 'U') IS NULL
            CREATE TABLE notebook_diagnostics (ts DATETIME2 DEFAULT SYSUTCDATETIME(), message NVARCHAR(4000))
        ''')
        cur.execute('INSERT INTO notebook_diagnostics (message) VALUES (?)', message[:4000])
        conn.commit()
        conn.close()
    except Exception:
        pass  # diagnostics are best-effort only


_write_diagnostic(f'[Cell1] RUNNING_IN_FABRIC={RUNNING_IN_FABRIC}')

# Connection string (priority: explicit env var -> built from Fabric components).
# When running in Fabric, auth is handled separately via an access token in
# Cell 3, so no Authentication= clause is needed here.
CONNECTION_STRING = os.getenv('CONNECTION_STRING') or os.getenv('FABRIC_CONNECTION_STRING')

if not CONNECTION_STRING:
    if RUNNING_IN_FABRIC:
        CONNECTION_STRING = (
            f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;'
            f'Database={FABRIC_DB};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
        )
    else:
        CONNECTION_STRING = (
            f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;'
            f'Database={FABRIC_DB};Authentication=ActiveDirectoryInteractive;'
            f'Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
        )

# Performance / volume tuning knobs
PATIENT_LOAD_MULTIPLIER = max(1.0, float(os.getenv('PATIENT_LOAD_MULTIPLIER', '4.0')))
HOSPITAL_BED_SCALE = min(1.0, max(0.1, float(os.getenv('HOSPITAL_BED_SCALE', '0.35'))))
MIN_HOSPITAL_BEDS = max(10, int(os.getenv('MIN_HOSPITAL_BEDS', '40')))
FABRIC_POOL_RECYCLE_SECONDS = max(3600, int(os.getenv('FABRIC_POOL_RECYCLE_SECONDS', '43200')))

# Optional: cap how many days a single run will backfill (protects against a
# multi-year empty database trying to generate everything in one go). Set to
# 0 / blank to disable the cap and always catch up fully to today.
MAX_CATCHUP_DAYS = int(os.getenv('MAX_CATCHUP_DAYS', '0') or '0')

# Default rebuild start date used only when the database is completely empty.
DEFAULT_HISTORY_START_DATE = os.getenv('DEFAULT_HISTORY_START_DATE', '2025-01-01')

# Weather location (default: New York City)
WEATHER_LATITUDE = float(os.getenv('WEATHER_LATITUDE', '40.7128'))
WEATHER_LONGITUDE = float(os.getenv('WEATHER_LONGITUDE', '-74.0060'))

NOTEBOOK_START_TIME = datetime.now()
SINGLE_ENGINE = None  # initialized in Cell 3

print('\n\U0001F3E5 Healthcare Data Generator \u2014 Fabric Edition (Single File)')
print(f'\u23F0 Start time: {NOTEBOOK_START_TIME.strftime("%Y-%m-%d %H:%M:%S")}')
print(f'\U0001F50C Connection configured: {"Yes" if CONNECTION_STRING else "No (will prompt/fail)"}')
print('\n[Cell 1/12] Configuration loaded. Proceed to Cell 2.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 2: Validate Dependencies & Environment
# ============================================================================

import importlib

required_packages = {
    'pandas': 'pandas',
    'numpy': 'numpy',
    'faker': 'faker',
    'sqlalchemy': 'sqlalchemy',
    'pyodbc': 'pyodbc',
    'requests': 'requests'
}

print('\n[Cell 2/12] Validating Environment')
print('\u2500' * 60)
print('\n[1/3] Checking Python packages...')
missing = []
for pkg, import_name in required_packages.items():
    try:
        importlib.import_module(import_name)
        print(f'  \u2713 {pkg}')
    except ImportError:
        print(f'  \u2717 {pkg} (MISSING)')
        missing.append(pkg)

if missing:
    print(f'\n\u26A0\ufe0f  Missing packages: {", ".join(missing)} \u2014 attempting install...')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', *missing], check=False)
    still_missing = []
    for pkg in missing:
        try:
            importlib.import_module(required_packages[pkg])
        except ImportError:
            still_missing.append(pkg)
    if still_missing:
        print(f'\n\u26A0\ufe0f  Still missing after install attempt: {", ".join(still_missing)}')
        print('Later cells that need these packages may fail \u2014 continuing anyway so the rest of the notebook can still run.')
    else:
        print('  \u2713 All missing packages installed successfully.')

print('\n[2/3] Checking ODBC drivers...')
try:
    import pyodbc
    drivers = pyodbc.drivers()
    sql_drivers = [d for d in drivers if 'SQL Server' in d or 'ODBC' in d]
    for driver in sql_drivers[:3]:
        print(f'  \u2713 {driver}')
    if not sql_drivers:
        print('  \u26A0\ufe0f  No SQL Server ODBC drivers found (may fail at connection time)')
except Exception as e:
    print(f'  \u26A0\ufe0f  Could not check ODBC drivers: {e}')

print('\n[3/3] Connection configuration...')
if CONNECTION_STRING:
    print('  \u2713 CONNECTION_STRING is set')
else:
    print('  \u26A0\ufe0f  CONNECTION_STRING not configured (set env var or edit Cell 1)')

print('\n\u2713 Dependencies validated. Proceed to Cell 3.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 3: Initialize Single Persistent Database Connection
# ============================================================================

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import SingletonThreadPool
import pyodbc
import pandas as pd

print('\n[Cell 3/12] Initializing Database Connection')
print('\u2500' * 60)


def _get_fabric_access_token():
    # Non-interactive AAD token for the Fabric-provided notebook identity.
    # Fabric SQL endpoints/warehouses accept tokens issued for the 'pbi'
    # audience (same backend resource as Power BI) -- the only officially
    # documented notebookutils.credentials audiences are: storage, pbi,
    # keyvault, kusto (arbitrary resource URLs like database.windows.net are
    # not supported), so 'pbi' is tried first.
    for audience in ('pbi', 'https://database.windows.net/'):
        try:
            import notebookutils
            token = notebookutils.credentials.getToken(audience)
            _write_diagnostic(f'[Cell3] notebookutils.getToken({audience}) succeeded, len={len(token) if token else 0}')
            return token
        except Exception as e:
            _write_diagnostic(f'[Cell3] notebookutils.getToken({audience}) failed: {e}')
        try:
            import mssparkutils
            token = mssparkutils.credentials.getToken(audience)
            _write_diagnostic(f'[Cell3] mssparkutils.getToken({audience}) succeeded, len={len(token) if token else 0}')
            return token
        except Exception as e:
            _write_diagnostic(f'[Cell3] mssparkutils.getToken({audience}) failed: {e}')
    _write_diagnostic('[Cell3] No token obtained from any audience')
    return None


def _pyodbc_creator_with_token(odbc_connect_str, token):
    import struct
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    token_bytes = token.encode('utf-16-le')
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

    def creator():
        return pyodbc.connect(odbc_connect_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})

    return creator


def init_connection():
    # Initialize a single persistent database connection for the entire notebook.
    global SINGLE_ENGINE

    if not CONNECTION_STRING:
        raise RuntimeError(
            'CONNECTION_STRING not configured.\n'
            'Set the CONNECTION_STRING environment variable or configure in Cell 1.'
        )

    fabric_token = _get_fabric_access_token() if RUNNING_IN_FABRIC else None

    if fabric_token:
        print('Initializing SQLAlchemy engine using a non-interactive Fabric access token...')
        raw_odbc_str = (
            f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;'
            f'Database={FABRIC_DB};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
        )
        SINGLE_ENGINE = create_engine(
            'mssql+pyodbc://',
            creator=_pyodbc_creator_with_token(raw_odbc_str, fabric_token),
            pool_pre_ping=True,
            pool_recycle=FABRIC_POOL_RECYCLE_SECONDS,
            poolclass=SingletonThreadPool
        )
    else:
        print('Initializing SQLAlchemy engine with a single pooled connection...')
        SINGLE_ENGINE = create_engine(
            f'mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}',
            pool_pre_ping=True,
            pool_recycle=FABRIC_POOL_RECYCLE_SECONDS,
            poolclass=SingletonThreadPool
        )

    with SINGLE_ENGINE.connect() as test_conn:
        test_conn.execute(text('SELECT 1'))
    print('  \u2713 Connected to database')
    _write_diagnostic(f'[Cell3] Connected successfully (token_auth={bool(fabric_token)})')

    inspector = inspect(SINGLE_ENGINE)
    tables = inspector.get_table_names()
    print(f'  \u2713 Found {len(tables)} existing tables')
    if tables:
        print(f'    Sample: {", ".join(tables[:5])}')

    return SINGLE_ENGINE


def query_db(sql, engine=None):
    # Execute a query using the single connection. Returns None on failure.
    engine = engine or SINGLE_ENGINE
    try:
        return pd.read_sql(sql, engine)
    except Exception as e:
        print(f'Query error: {e}')
        return None


def get_table_columns(table_name, engine=None):
    engine = engine or SINGLE_ENGINE
    try:
        df = pd.read_sql(f'SELECT TOP 0 * FROM {table_name}', engine)
        return list(df.columns)
    except Exception:
        return []


def align_df_to_table(df, table_name, engine=None):
    # Restrict a dataframe to columns that already exist in the target table.
    # If the table doesn't exist yet, return df unchanged so to_sql can create it.
    cols = get_table_columns(table_name, engine)
    if not cols:
        return df
    common = [c for c in df.columns if c in cols]
    return df[common] if common else df


def get_next_id(table_name, id_col, engine=None):
    # Return the next id to use for inserts by checking the current max in the DB.
    engine = engine or SINGLE_ENGINE
    try:
        result = pd.read_sql(f'SELECT MAX({id_col}) as max_id FROM {table_name}', engine)
        max_id = result.iloc[0]['max_id']
        if pd.isna(max_id) or max_id is None:
            return 1
        return int(max_id) + 1
    except Exception:
        return 1


try:
    init_connection()
    print('\n\u2713 Connection initialized. Proceed to Cell 4.')
except Exception as e:
    import traceback
    print(f'\n\u2717 Failed to initialize connection: {e}')
    traceback.print_exc()
    print('Please check your CONNECTION_STRING configuration.')
    _write_diagnostic(f'[Cell3] init_connection() raised: {e}')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 4: Determine Catch-Up Range (last loaded date -> today)
# ============================================================================

print('\n[Cell 4/12] Catch-Up Range Detection')
print('\u2500' * 60)


def get_last_loaded_date():
    # Most recent encounter_date already in the database, or None if empty/missing.
    result = query_db('SELECT MAX(encounter_date) as max_date FROM encounters')
    if result is not None and not result.empty:
        max_date = result.iloc[0]['max_date']
        if pd.notna(max_date):
            return pd.to_datetime(max_date).date()
    return None


def get_recent_encounter_counts():
    return query_db(
        '''
        SELECT CAST(encounter_date AS DATE) as date, COUNT(*) as count
        FROM encounters
        WHERE encounter_date >= DATEADD(day, -7, CAST(GETDATE() AS DATE))
        GROUP BY CAST(encounter_date AS DATE)
        ORDER BY date DESC
        '''
    )


TODAY = datetime.now().date()
LAST_LOADED_DATE = get_last_loaded_date()
IS_EMPTY_DATABASE = LAST_LOADED_DATE is None

if IS_EMPTY_DATABASE:
    START_DATE = pd.to_datetime(DEFAULT_HISTORY_START_DATE).date()
    END_DATE = TODAY
    print(f'\U0001F504 Database is empty \u2014 full history build: {START_DATE} \u2192 {END_DATE}')
else:
    START_DATE = LAST_LOADED_DATE + timedelta(days=1)
    END_DATE = TODAY
    days_behind = (END_DATE - START_DATE).days + 1
    if START_DATE > END_DATE:
        print(f'\u2713 Database is current (last loaded date: {LAST_LOADED_DATE})')
    else:
        print(f'\u26A0\ufe0f  Catching up {days_behind} day(s): {START_DATE} \u2192 {END_DATE}')

if MAX_CATCHUP_DAYS and START_DATE <= END_DATE:
    capped_end = min(END_DATE, START_DATE + timedelta(days=MAX_CATCHUP_DAYS - 1))
    if capped_end < END_DATE:
        print(f'\u2139\ufe0f  MAX_CATCHUP_DAYS={MAX_CATCHUP_DAYS} \u2014 capping this run to {START_DATE} \u2192 {capped_end}. '
              f'Re-run the notebook again to continue catching up to {END_DATE}.')
    END_DATE = capped_end

recent = get_recent_encounter_counts()
if recent is not None and not recent.empty:
    print('\n\U0001F4CA Last 7 days of encounter volumes:')
    print(recent.to_string(index=False))

NEEDS_GENERATION = START_DATE <= END_DATE
print(f'\nNEEDS_GENERATION = {NEEDS_GENERATION}')
print('\n\u2713 Catch-up range determined. Proceed to Cell 5.')
_write_diagnostic(
    f'[Cell4] SINGLE_ENGINE={"set" if SINGLE_ENGINE else "None"} LAST_LOADED_DATE={LAST_LOADED_DATE} '
    f'START_DATE={START_DATE} END_DATE={END_DATE} NEEDS_GENERATION={NEEDS_GENERATION}'
)
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 5: Static Reference Data & Constants
# (from src/config.py + src/main.py hospital/department/clinical constants)
# ============================================================================

import random
from faker import Faker
import requests
import warnings
warnings.filterwarnings('ignore')

fake = Faker()

# ----- Seasonality (CDC/NHS/AHA/NCI/APTA-informed, see src/config.py) -----
HOURLY_MULTIPLIERS = [
    0.65, 0.54, 0.49, 0.43, 0.43, 0.60, 0.87, 1.03, 1.14, 1.14,
    1.14, 1.14, 1.08, 1.08, 1.14, 1.19, 1.30, 1.41, 1.52, 1.46,
    1.30, 1.14, 0.98, 0.81
]

DAY_OF_WEEK_MULTIPLIERS = [1.06, 0.98, 0.96, 0.96, 1.00, 1.03, 1.02]  # Mon..Sun

MONTHLY_MULTIPLIERS = [
    1.12, 1.08, 1.02, 0.95, 0.93, 0.88,
    0.85, 0.88, 0.95, 0.98, 1.02, 1.12
]

HOSPITAL_SPECIALTY_MONTHLY = {
    'pediatric': [1.35, 1.28, 0.95, 0.82, 0.78, 0.75, 0.85, 0.88, 0.92, 0.98, 1.18, 1.26],
    'cardiac':   [1.38, 1.32, 1.08, 0.92, 0.85, 0.88, 0.87, 0.89, 0.95, 1.02, 1.18, 1.28],
    'cancer':    [1.05, 1.03, 1.02, 1.01, 0.98, 0.95, 0.94, 0.96, 1.00, 1.02, 1.04, 1.06],
    'general':   [1.12, 1.08, 0.98, 0.92, 0.88, 0.85, 0.90, 0.93, 0.95, 1.00, 1.08, 1.18],
    'rehab':     [1.04, 1.02, 1.08, 1.10, 1.01, 0.98, 0.92, 0.95, 1.05, 1.12, 1.06, 1.00],
    'specialty': [1.12, 1.08, 0.98, 0.92, 0.88, 0.85, 0.90, 0.93, 0.95, 1.00, 1.08, 1.18],
}

HOURLY_ED_OCCUPANCY = [
    45, 42, 40, 38, 40, 45, 50, 58, 68, 75, 82, 85,
    88, 87, 88, 89, 88, 85, 82, 80, 78, 75, 70, 62
]

DAY_OF_WEEK_OCCUPANCY_MULT = {
    'Monday': 1.02, 'Tuesday': 1.01, 'Wednesday': 1.00, 'Thursday': 1.02,
    'Friday': 1.04, 'Saturday': 0.97, 'Sunday': 0.96
}

PROCEDURE_SEASONALITY = {
    'Blood Test': 1.00, 'X-Ray': 1.05, 'MRI Scan': 1.00, 'CT Scan': 1.03,
    'Colonoscopy': 0.95, 'Endoscopy': 0.98, 'Cardiac Catheterization': 1.15,
    'Appendectomy': 1.10, 'Hip Replacement': 1.08, 'Knee Arthroscopy': 1.06,
    'Other': 1.00
}

PAYER_MARKET_SHARE = {
    'Medicare': 0.36, 'Medicaid': 0.20, 'Commercial': 0.35, 'Uninsured': 0.05, 'Other': 0.04
}

SPECIALTY_PAYER_ADJUST = {
    'pediatric': {'Medicaid': 1.35, 'Commercial': 0.85, 'Medicare': 0.2},
    'cardiac': {'Medicare': 1.10, 'Commercial': 1.05, 'Medicaid': 0.9},
    'cancer': {'Commercial': 1.10, 'Medicare': 1.05, 'Medicaid': 0.9},
    'rehab': {'Medicare': 1.20, 'Medicaid': 0.95, 'Commercial': 0.9},
    'general': {}, 'specialty': {}
}

# ----- Hospitals -----
BASE_HOSPITALS = [
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


def scale_hospital_beds(hospitals, bed_scale=HOSPITAL_BED_SCALE, min_beds=MIN_HOSPITAL_BEDS):
    return [{**h, 'bed_count': max(min_beds, int(round(h['bed_count'] * bed_scale)))} for h in hospitals]


HOSPITALS = scale_hospital_beds(BASE_HOSPITALS)

# ----- Departments -----
DEPARTMENTS = [
    {'department_id': 1, 'name': 'Emergency', 'hospital_id': 1, 'specialty_type': 'Emergency'},
    {'department_id': 2, 'name': 'Internal Medicine', 'hospital_id': 1, 'specialty_type': 'Medical'},
    {'department_id': 3, 'name': 'Surgery', 'hospital_id': 1, 'specialty_type': 'Surgical'},
    {'department_id': 4, 'name': 'Cardiology', 'hospital_id': 1, 'specialty_type': 'Medical'},
    {'department_id': 5, 'name': 'Radiology', 'hospital_id': 1, 'specialty_type': 'Diagnostic'},
    {'department_id': 6, 'name': 'Emergency', 'hospital_id': 2, 'specialty_type': 'Emergency'},
    {'department_id': 7, 'name': 'Internal Medicine', 'hospital_id': 2, 'specialty_type': 'Medical'},
    {'department_id': 8, 'name': 'Trauma Surgery', 'hospital_id': 2, 'specialty_type': 'Surgical'},
    {'department_id': 9, 'name': 'Orthopedics', 'hospital_id': 2, 'specialty_type': 'Surgical'},
    {'department_id': 10, 'name': 'Neurology', 'hospital_id': 2, 'specialty_type': 'Medical'},
    {'department_id': 11, 'name': 'Emergency', 'hospital_id': 3, 'specialty_type': 'Emergency'},
    {'department_id': 12, 'name': 'Internal Medicine', 'hospital_id': 3, 'specialty_type': 'Medical'},
    {'department_id': 13, 'name': 'Surgery', 'hospital_id': 3, 'specialty_type': 'Surgical'},
    {'department_id': 14, 'name': 'Radiology', 'hospital_id': 3, 'specialty_type': 'Diagnostic'},
    {'department_id': 15, 'name': 'Emergency', 'hospital_id': 4, 'specialty_type': 'Emergency'},
    {'department_id': 16, 'name': 'Internal Medicine', 'hospital_id': 4, 'specialty_type': 'Medical'},
    {'department_id': 17, 'name': 'Surgery', 'hospital_id': 4, 'specialty_type': 'Surgical'},
    {'department_id': 18, 'name': 'Emergency', 'hospital_id': 5, 'specialty_type': 'Emergency'},
    {'department_id': 19, 'name': 'Internal Medicine', 'hospital_id': 5, 'specialty_type': 'Medical'},
    {'department_id': 20, 'name': 'Surgery', 'hospital_id': 5, 'specialty_type': 'Surgical'},
    {'department_id': 21, 'name': 'Cardiology', 'hospital_id': 6, 'specialty_type': 'Medical'},
    {'department_id': 22, 'name': 'Interventional Cardiology', 'hospital_id': 6, 'specialty_type': 'Surgical'},
    {'department_id': 23, 'name': 'Cardiac Surgery', 'hospital_id': 6, 'specialty_type': 'Surgical'},
    {'department_id': 24, 'name': 'Cardiac Rehabilitation', 'hospital_id': 6, 'specialty_type': 'Medical'},
    {'department_id': 25, 'name': 'Pediatrics', 'hospital_id': 7, 'specialty_type': 'Medical'},
    {'department_id': 26, 'name': 'Pediatric Surgery', 'hospital_id': 7, 'specialty_type': 'Surgical'},
    {'department_id': 27, 'name': 'Pediatric ER/Urgent Care', 'hospital_id': 7, 'specialty_type': 'Emergency'},
    {'department_id': 28, 'name': 'Neonatology', 'hospital_id': 7, 'specialty_type': 'Medical'},
    {'department_id': 29, 'name': 'Oncology', 'hospital_id': 8, 'specialty_type': 'Medical'},
    {'department_id': 30, 'name': 'Hematology', 'hospital_id': 8, 'specialty_type': 'Medical'},
    {'department_id': 31, 'name': 'Infusion Center', 'hospital_id': 8, 'specialty_type': 'Medical'},
    {'department_id': 32, 'name': 'Palliative Care', 'hospital_id': 8, 'specialty_type': 'Medical'},
    {'department_id': 33, 'name': 'Physical Rehabilitation', 'hospital_id': 9, 'specialty_type': 'Medical'},
    {'department_id': 34, 'name': 'Occupational Therapy', 'hospital_id': 9, 'specialty_type': 'Medical'},
    {'department_id': 35, 'name': 'Speech Therapy', 'hospital_id': 9, 'specialty_type': 'Medical'},
    {'department_id': 36, 'name': 'Radiology', 'hospital_id': 10, 'specialty_type': 'Diagnostic'},
    {'department_id': 37, 'name': 'Pathology', 'hospital_id': 10, 'specialty_type': 'Diagnostic'},
    {'department_id': 38, 'name': 'Laboratory', 'hospital_id': 10, 'specialty_type': 'Diagnostic'}
]

DEPARTMENT_DEMAND_MULTIPLIERS = {
    'Emergency': 2.5, 'Internal Medicine': 1.8, 'Surgery': 1.2, 'Cardiology': 1.5,
    'Orthopedics': 1.4, 'Radiology': 1.9, 'Oncology': 1.3, 'Pediatrics': 1.6,
    'Neurology': 1.1, 'Diagnostic': 1.7, 'Medical': 1.5, 'Surgical': 1.0,
    'Infusion Center': 0.9, 'Palliative Care': 0.6, 'Physical Rehabilitation': 0.8,
    'Occupational Therapy': 0.7, 'Speech Therapy': 0.5, 'Neonatology': 0.9,
    'Pathology': 1.2, 'Laboratory': 1.8
}

DEPARTMENT_BED_ALLOCATION = {
    'Emergency': 0.06, 'Internal Medicine': 0.35, 'Surgery': 0.25, 'Trauma Surgery': 0.20,
    'Cardiology': 0.15, 'Orthopedics': 0.12, 'Neurology': 0.10, 'Radiology': 0.03,
    'Interventional Cardiology': 0.30, 'Cardiac Surgery': 0.40, 'Cardiac Rehabilitation': 0.25,
    'Pediatrics': 0.50, 'Pediatric Surgery': 0.30, 'Pediatric ER/Urgent Care': 0.05, 'Neonatology': 0.15,
    'Oncology': 0.50, 'Hematology': 0.30, 'Infusion Center': 0.15, 'Palliative Care': 0.05,
    'Physical Rehabilitation': 0.60, 'Occupational Therapy': 0.25, 'Speech Therapy': 0.15,
    'Pathology': 0.05, 'Laboratory': 0.05, 'default': 0.10
}

# ----- Procedures -----
PROCEDURE_WEIGHTS = {
    'Blood Test': 0.25, 'X-Ray': 0.20, 'MRI Scan': 0.10, 'CT Scan': 0.08,
    'Colonoscopy': 0.07, 'Endoscopy': 0.06, 'Cardiac Catheterization': 0.05,
    'Appendectomy': 0.04, 'Hip Replacement': 0.03, 'Knee Arthroscopy': 0.02, 'Other': 0.10
}


def apply_seasonality_to_procedure_weights(date):
    month = pd.to_datetime(date).month - 1
    month_mult = MONTHLY_MULTIPLIERS[month] if month < len(MONTHLY_MULTIPLIERS) else 1.0
    adjusted = {}
    for proc, base_weight in PROCEDURE_WEIGHTS.items():
        proc_seasonal = PROCEDURE_SEASONALITY.get(proc, 1.0)
        adjusted[proc] = base_weight * proc_seasonal * month_mult
    total = sum(adjusted.values())
    return {k: v / total for k, v in adjusted.items()} if total > 0 else adjusted


# ----- Codes -----
ICD_CODES = [
    'I10', 'E11.9', 'Z00.00', 'M54.5', 'J00', 'R05', 'F41.9', 'N28.1', 'Z01.419', 'Z51.11',
    'I25.10', 'E78.5', 'Z95.1', 'M79.3', 'R10.9', 'F32.9', 'N39.0', 'Z12.31', 'Z79.899', 'I48.91',
    'G43.909', 'K21.9', 'Z98.891', 'M17.9', 'R51', 'F33.9', 'N18.9', 'Z23', 'Z87.440', 'I50.9'
]

CPT_CODES = [
    '99213', '99214', '99215', '85025', '71020', '74176', '45378', '43235', '99201', '99202',
    '99203', '99204', '99205', '80053', '83036', '84443', '85027', '85610', '84153', '84439',
    '82306', '84132', '82565', '84520', '82947', '83540', '82247', '83001', '86038', '86334'
]

MEDICATIONS = [
    'Lisinopril', 'Metformin', 'Amlodipine', 'Omeprazole', 'Simvastatin', 'Losartan', 'Albuterol', 'Gabapentin',
    'Sertraline', 'Furosemide', 'Fluticasone', 'Prednisone', 'Warfarin', 'Levothyroxine', 'Hydrochlorothiazide',
    'Aspirin', 'Atorvastatin', 'Clopidogrel', 'Montelukast', 'Trazodone', 'Citalopram', 'Duloxetine', 'Escitalopram',
    'Bupropion', 'Venlafaxine', 'Quetiapine', 'Risperidone', 'Olanzapine', 'Lamotrigine', 'Topiramate',
    'Ceftriaxone', 'Vancomycin', 'Piperacillin-Tazobactam', 'Norepinephrine'
]

LAB_TESTS = [
    'CBC', 'CMP', 'Lipid Panel', 'TSH', 'Hemoglobin A1c', 'Urinalysis', 'Chest X-Ray', 'EKG', 'PT/INR',
    'Vitamin D', 'B12', 'Folate', 'Ferritin', 'Iron', 'TIBC', 'Liver Function', 'Kidney Function', 'Electrolytes',
    'Glucose', 'Cortisol', 'T3/T4', 'PSA', 'CA-125', 'CEA', 'AFP', 'Beta-HCG', 'Troponin', 'CK-MB', 'BNP', 'D-Dimer',
    'Lactic Acid', 'Blood Culture', 'ABG', 'CT Head'
]

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
}

FLU_ICD_CODE = 'J11.00'
FALL_ICD_CODE = 'W19.XXXA'
ACCIDENT_ICD_CODE = 'V89.2'
DIAGNOSIS_DETAILS['J11.00'] = {'description': 'Influenza with pneumonia, unspecified type', 'complaints': ['Fever', 'Cough', 'Body aches', 'Respiratory symptoms']}
DIAGNOSIS_DETAILS['W19.XXXA'] = {'description': 'Unspecified fall', 'complaints': ['Fall', 'Trauma', 'Injury', 'Fracture']}
DIAGNOSIS_DETAILS['V89.2'] = {'description': 'Unspecified motor vehicle accident', 'complaints': ['Accident', 'Trauma', 'Injury']}

# ---------------------------------------------------------------------------
# ICD-10 reference dimension.
#
# Single source of truth for code -> description, clinical family and official
# ICD-10-CM chapter. Every code reachable from get_specialty_diagnoses(), from
# DIAGNOSIS_DETAILS and from the hospital-operations simulator appears here, so
# a generated diagnosis can never fall back to an unusable placeholder
# description. Clinical families intentionally match the condition families in
# docs/LENGTH_OF_STAY_BENCHMARKS.md so length-of-stay work and analytics share
# one grouping.
#
# Chapter ranges are the real ICD-10-CM ranges, which is why the chapter cannot
# be derived from the leading letter alone: neoplasms span C00-D49, blood and
# immune disorders resume at D50-D89, and injury spans S00-T88.
# Layout: code -> (description, clinical_family, chapter, chapter_range)
# ---------------------------------------------------------------------------
ICD_REFERENCE = {
    'A08.39':  ('Other viral enteritis', 'Infectious Disease', 'Certain infectious and parasitic diseases', 'A00-B99'),
    'C34.9':   ('Malignant neoplasm of unspecified part of bronchus or lung', 'Oncology', 'Neoplasms', 'C00-D49'),
    'C50.9':   ('Malignant neoplasm of breast, unspecified site', 'Oncology', 'Neoplasms', 'C00-D49'),
    'C80.1':   ('Malignant (primary) neoplasm, unspecified', 'Oncology', 'Neoplasms', 'C00-D49'),
    'C82.9':   ('Follicular lymphoma, unspecified', 'Oncology', 'Neoplasms', 'C00-D49'),
    'C85.9':   ('Non-Hodgkin lymphoma, unspecified', 'Oncology', 'Neoplasms', 'C00-D49'),
    'C91.0':   ('Acute lymphoblastic leukemia', 'Oncology', 'Neoplasms', 'C00-D49'),
    'C92.0':   ('Acute myeloblastic leukemia', 'Oncology', 'Neoplasms', 'C00-D49'),
    'D70.9':   ('Neutropenia, unspecified', 'Hematology', 'Diseases of the blood and blood-forming organs', 'D50-D89'),
    'E11.9':   ('Type 2 diabetes mellitus without complications', 'Endocrine & Metabolic', 'Endocrine, nutritional and metabolic diseases', 'E00-E89'),
    'E78.5':   ('Hyperlipidemia, unspecified', 'Endocrine & Metabolic', 'Endocrine, nutritional and metabolic diseases', 'E00-E89'),
    'F32.9':   ('Major depressive disorder, single episode, unspecified', 'Behavioral Health', 'Mental, behavioral and neurodevelopmental disorders', 'F01-F99'),
    'F33.9':   ('Major depressive disorder, recurrent, unspecified', 'Behavioral Health', 'Mental, behavioral and neurodevelopmental disorders', 'F01-F99'),
    'F41.9':   ('Anxiety disorder, unspecified', 'Behavioral Health', 'Mental, behavioral and neurodevelopmental disorders', 'F01-F99'),
    'G40.9':   ('Epilepsy, unspecified', 'Neurology', 'Diseases of the nervous system', 'G00-G99'),
    'G43.909': ('Migraine, unspecified, not intractable, without status migrainosus', 'Neurology', 'Diseases of the nervous system', 'G00-G99'),
    'G81.9':   ('Hemiplegia, unspecified affecting unspecified side', 'Neurology', 'Diseases of the nervous system', 'G00-G99'),
    'H66.001': ('Acute suppurative otitis media without spontaneous rupture of ear drum, right ear', 'Ear, Nose & Throat', 'Diseases of the ear and mastoid process', 'H60-H95'),
    'I10':     ('Essential (primary) hypertension', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I20.0':   ('Unstable angina', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I21.0':   ('ST elevation myocardial infarction of anterior wall', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I21.9':   ('Acute myocardial infarction, unspecified', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I25.10':  ('Atherosclerotic heart disease of native coronary artery without angina pectoris', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I26.9':   ('Pulmonary embolism without acute cor pulmonale', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I47.9':   ('Paroxysmal tachycardia, unspecified', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I48.91':  ('Unspecified atrial fibrillation', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I50.9':   ('Heart failure, unspecified', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'I63.9':   ('Cerebral infarction, unspecified', 'Neurology', 'Diseases of the circulatory system', 'I00-I99'),
    'I69.3':   ('Sequelae of cerebral infarction', 'Neurology', 'Diseases of the circulatory system', 'I00-I99'),
    'I71.0':   ('Dissection of aorta', 'Cardiology', 'Diseases of the circulatory system', 'I00-I99'),
    'J00':     ('Acute nasopharyngitis (common cold)', 'Respiratory', 'Diseases of the respiratory system', 'J00-J99'),
    'J11.00':  ('Influenza with pneumonia, unspecified type', 'Respiratory', 'Diseases of the respiratory system', 'J00-J99'),
    'J18.9':   ('Pneumonia, unspecified organism', 'Respiratory', 'Diseases of the respiratory system', 'J00-J99'),
    'J44.9':   ('Chronic obstructive pulmonary disease, unspecified', 'Respiratory', 'Diseases of the respiratory system', 'J00-J99'),
    'J45.9':   ('Other and unspecified asthma', 'Respiratory', 'Diseases of the respiratory system', 'J00-J99'),
    'J45.901': ('Unspecified asthma with (acute) exacerbation', 'Respiratory', 'Diseases of the respiratory system', 'J00-J99'),
    'K21.9':   ('Gastro-esophageal reflux disease without esophagitis', 'Gastroenterology', 'Diseases of the digestive system', 'K00-K95'),
    'K37':     ('Unspecified appendicitis', 'Gastroenterology', 'Diseases of the digestive system', 'K00-K95'),
    'L03.90':  ('Cellulitis, unspecified', 'Infectious Disease', 'Diseases of the skin and subcutaneous tissue', 'L00-L99'),
    'M16.1':   ('Unilateral primary osteoarthritis, unspecified hip', 'Musculoskeletal', 'Diseases of the musculoskeletal system and connective tissue', 'M00-M99'),
    'M17.9':   ('Osteoarthritis of knee, unspecified', 'Musculoskeletal', 'Diseases of the musculoskeletal system and connective tissue', 'M00-M99'),
    'M17.11':  ('Unilateral primary osteoarthritis, right knee', 'Musculoskeletal', 'Diseases of the musculoskeletal system and connective tissue', 'M00-M99'),
    'M54.5':   ('Low back pain', 'Musculoskeletal', 'Diseases of the musculoskeletal system and connective tissue', 'M00-M99'),
    'M62.81':  ('Muscle weakness (generalized)', 'Musculoskeletal', 'Diseases of the musculoskeletal system and connective tissue', 'M00-M99'),
    'M79.3':   ('Panniculitis, unspecified', 'Musculoskeletal', 'Diseases of the musculoskeletal system and connective tissue', 'M00-M99'),
    'N18.9':   ('Chronic kidney disease, unspecified', 'Renal & Genitourinary', 'Diseases of the genitourinary system', 'N00-N99'),
    'N28.1':   ('Cyst of kidney, acquired', 'Renal & Genitourinary', 'Diseases of the genitourinary system', 'N00-N99'),
    'N39.0':   ('Urinary tract infection, site not specified', 'Renal & Genitourinary', 'Diseases of the genitourinary system', 'N00-N99'),
    'R05':     ('Cough', 'Signs & Symptoms', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'R10.9':   ('Unspecified abdominal pain', 'Signs & Symptoms', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'R26':     ('Abnormalities of gait and mobility', 'Signs & Symptoms', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'R50.82':  ('Postprocedural fever', 'Signs & Symptoms', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'R50.9':   ('Fever, unspecified', 'Signs & Symptoms', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'R51':     ('Headache', 'Signs & Symptoms', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'R55':     ('Syncope and collapse', 'Signs & Symptoms', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'R65.21':  ('Severe sepsis with septic shock', 'Infectious Disease', 'Symptoms, signs and abnormal clinical and laboratory findings', 'R00-R99'),
    'A41.9':   ('Sepsis, unspecified organism', 'Infectious Disease', 'Certain infectious and parasitic diseases', 'A00-B99'),
    'S72.1':   ('Pertrochanteric fracture of femur', 'Injury & Trauma', 'Injury, poisoning and certain other consequences of external causes', 'S00-T88'),
    'S72.9':   ('Unspecified fracture of femur', 'Injury & Trauma', 'Injury, poisoning and certain other consequences of external causes', 'S00-T88'),
    'W19.XXXA': ('Unspecified fall, initial encounter', 'Injury & Trauma', 'External causes of morbidity', 'V00-Y99'),
    'V89.2':   ('Person injured in unspecified motor-vehicle accident, traffic', 'Injury & Trauma', 'External causes of morbidity', 'V00-Y99'),
    'Z00.00':  ('Encounter for general adult medical examination without abnormal findings', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z01.419': ('Encounter for gynecological examination without abnormal findings', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z12.31':  ('Encounter for screening mammogram for malignant neoplasm of breast', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z23':     ('Encounter for immunization', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z50.0':   ('Encounter for cardiac rehabilitation', 'Rehabilitation & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z50.1':   ('Other physical therapy', 'Rehabilitation & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z51.0':   ('Encounter for antineoplastic radiation therapy', 'Oncology', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z51.11':  ('Encounter for antineoplastic chemotherapy', 'Oncology', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z54':     ('Convalescence', 'Rehabilitation & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z79.899': ('Other long term (current) drug therapy', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z87.440': ('Personal history of other diseases of respiratory system', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z95.1':   ('Presence of aortocoronary bypass graft', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
    'Z98.891': ('History of bariatric surgery', 'Preventive & Aftercare', 'Factors influencing health status and contact with health services', 'Z00-Z99'),
}


def describe_icd_code(icd_code):
    # Authoritative description for a code, preferring the reference dimension.
    # Returns None when a code is genuinely unknown so callers can fail loudly
    # rather than silently writing an unusable placeholder into the ODS.
    if icd_code in ICD_REFERENCE:
        return ICD_REFERENCE[icd_code][0]
    detail = DIAGNOSIS_DETAILS.get(icd_code)
    if detail and detail.get('description'):
        return detail['description']
    return None


def build_icd_reference_frame():
    # Reference dimension rows, one per ICD-10 code used by the generator.
    return pd.DataFrame(
        [{'icd_code': code, 'description': desc, 'clinical_family': family,
          'icd_chapter': chapter, 'chapter_code_range': code_range}
         for code, (desc, family, chapter, code_range) in sorted(ICD_REFERENCE.items())]
    )

WEATHER_IMPACT = {
    'rain': {'flu_multiplier': 1.5, 'fall_multiplier': 1.8, 'accident_multiplier': 1.3},
    'snow': {'flu_multiplier': 2.0, 'fall_multiplier': 2.5, 'accident_multiplier': 2.0},
    'sleet': {'flu_multiplier': 1.8, 'fall_multiplier': 2.2, 'accident_multiplier': 1.8},
    'thunderstorm': {'flu_multiplier': 1.6, 'fall_multiplier': 1.4, 'accident_multiplier': 1.7},
    'fog': {'flu_multiplier': 1.3, 'fall_multiplier': 1.1, 'accident_multiplier': 2.2},
    'clear': {'flu_multiplier': 1.0, 'fall_multiplier': 1.0, 'accident_multiplier': 1.0},
    'cloudy': {'flu_multiplier': 1.1, 'fall_multiplier': 1.05, 'accident_multiplier': 1.05}
}

DIAGNOSIS_TO_MEDS = {
    'I10': ['Lisinopril', 'Amlodipine', 'Hydrochlorothiazide'],
    'E11.9': ['Metformin', 'Insulin'],
    'I25.10': ['Atorvastatin', 'Aspirin'],
    'E78.5': ['Atorvastatin', 'Simvastatin'],
    'F41.9': ['Sertraline', 'Escitalopram'],
    'F32.9': ['Sertraline', 'Citalopram'],
    'M54.5': ['Gabapentin', 'Ibuprofen'],
    'J00': ['Albuterol', 'Fluticasone'],
    'R05': ['Dextromethorphan'],
    'N39.0': ['Ciprofloxacin'],
    'J18.9': ['Azithromycin', 'Ceftriaxone', 'Levofloxacin'],
    'A41.9': ['Piperacillin-Tazobactam', 'Vancomycin', 'Cefepime'],
    'J44.9': ['Albuterol', 'Tiotropium', 'Prednisone'],
    'L03.90': ['Cephalexin', 'Dicloxacillin', 'Clindamycin'],
    'I63.9': ['Aspirin', 'Atorvastatin'],
    'R55': ['Observation', 'IV fluids']
}

DIAGNOSIS_TO_LABS = {
    'I10': ['CMP', 'Lipid Panel'],
    'E11.9': ['Hemoglobin A1c', 'Glucose'],
    'I25.10': ['Troponin', 'EKG'],
    'E78.5': ['Lipid Panel'],
    'F41.9': ['TSH', 'Cortisol'],
    'F32.9': ['TSH'],
    'M54.5': ['X-Ray'],
    'J00': ['CBC'],
    'R05': ['Chest X-Ray'],
    'N39.0': ['Urinalysis'],
    'J18.9': ['CBC', 'Chest X-Ray', 'Blood Culture'],
    'A41.9': ['CBC', 'Lactic Acid', 'Blood Culture'],
    'J44.9': ['ABG', 'Chest X-Ray', 'CBC'],
    'L03.90': ['CBC', 'CRP'],
    'I63.9': ['CT Head', 'Glucose', 'CBC']
}

print('\n[Cell 5/12] \u2713 Static reference data & constants loaded.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 6: Hospital-Specific Helper Functions
# (from src/hospital_generation_helpers.py)
# ============================================================================


def get_hospital_monthly_encounters(hospital_specialty, month, base_encounters=300):
    multiplier = HOSPITAL_SPECIALTY_MONTHLY.get(hospital_specialty, HOSPITAL_SPECIALTY_MONTHLY['general'])[month - 1]
    return int(base_encounters * multiplier)


def get_specialty_diagnoses(hospital_specialty):
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
    rates = {'pediatric': 0.12, 'cardiac': 0.72, 'cancer': 0.96, 'rehab': 0.85, 'general': 0.20, 'specialty': 0.15}
    return rates.get(hospital_specialty, 0.20)


def get_average_los(hospital_specialty):
    los = {'pediatric': 1.2, 'cardiac': 3.5, 'cancer': 7.4, 'rehab': 21.0, 'general': 3.8, 'specialty': 2.0}
    return los.get(hospital_specialty, 3.0)


def calculate_er_occupancy_at_hour(hospital_id, hour_of_day, day_of_week):
    base_occupancy = HOURLY_ED_OCCUPANCY[hour_of_day]
    day_mult = DAY_OF_WEEK_OCCUPANCY_MULT.get(day_of_week, 1.00)
    noise = random.uniform(-0.05, 0.05)
    final_occupancy = base_occupancy * day_mult * (1 + noise)
    return min(100, max(0, final_occupancy))


def get_admission_times_by_specialty(hospital_specialty, num_admissions):
    times = []
    if hospital_specialty == 'cardiac':
        for _ in range(int(num_admissions * 0.35)):
            times.append(random.randint(6, 9))
        for _ in range(int(num_admissions * 0.28)):
            times.append(random.randint(14, 17))
        for _ in range(int(num_admissions * 0.37)):
            times.append(random.randint(0, 23))
    elif hospital_specialty == 'pediatric':
        for _ in range(int(num_admissions * 0.25)):
            times.append(random.randint(8, 10))
        for _ in range(int(num_admissions * 0.20)):
            times.append(random.randint(14, 16))
        for _ in range(int(num_admissions * 0.22)):
            times.append(random.randint(18, 21))
        for _ in range(int(num_admissions * 0.33)):
            times.append(random.randint(0, 23))
    elif hospital_specialty == 'cancer':
        for _ in range(int(num_admissions * 0.70)):
            times.append(random.randint(8, 17))
        for _ in range(int(num_admissions * 0.30)):
            times.append(random.randint(0, 8))
    elif hospital_specialty == 'rehab':
        for _ in range(int(num_admissions * 0.60)):
            times.append(random.randint(7, 11))
        for _ in range(int(num_admissions * 0.30)):
            times.append(random.randint(13, 16))
        for _ in range(int(num_admissions * 0.10)):
            times.append(random.randint(0, 23))
    else:
        for _ in range(int(num_admissions * 0.35)):
            times.append(random.randint(8, 12))
        for _ in range(int(num_admissions * 0.40)):
            times.append(random.randint(12, 18))
        for _ in range(int(num_admissions * 0.25)):
            times.append(random.randint(18, 23))
    while len(times) < num_admissions:
        times.append(random.randint(0, 23))
    return times[:num_admissions]


def get_payer_for_patient(age, hospital_specialty):
    base = PAYER_MARKET_SHARE.copy()
    if age >= 65:
        base['Medicare'] = base.get('Medicare', 0.36) * 1.5
        base['Commercial'] = base.get('Commercial', 0.35) * 0.8
        base['Medicaid'] = base.get('Medicaid', 0.20) * 0.8
    elif age < 18:
        base['Medicaid'] = base.get('Medicaid', 0.20) * 1.3
        base['Commercial'] = base.get('Commercial', 0.35) * 0.9

    adjust = SPECIALTY_PAYER_ADJUST.get(hospital_specialty, {})
    for k, v in adjust.items():
        base[k] = base.get(k, 0.0) * v

    total = sum(base.values())
    if total <= 0:
        return random.choice(['Commercial', 'Medicare', 'Medicaid', 'Uninsured', 'Other'])

    probs = {k: v / total for k, v in base.items()}
    r = random.random()
    cum = 0.0
    k = 'Other'
    for k, p in probs.items():
        cum += p
        if r <= cum:
            return k
    return k


def apply_diagnosis_seasonality(icd_code, month, hospital_specialty, weather_condition=None):
    m = 1.0
    if icd_code.startswith('J11') or icd_code == 'J00':
        if month in [12, 1, 2]:
            m *= 2.0
    if icd_code == 'J45.9' and hospital_specialty == 'pediatric' and month in [11, 12, 1, 2]:
        m *= 1.8
    if icd_code.startswith('I21') or icd_code.startswith('I50'):
        if month in [12, 1, 2]:
            m *= 1.25
    if icd_code.startswith('W') or icd_code.startswith('V'):
        if month in [12, 1, 2]:
            m *= 1.3
        if month in [6, 7, 8]:
            m *= 1.2
    if weather_condition == 'snow' and (icd_code.startswith('W') or icd_code.startswith('V')):
        m *= 1.8
    if weather_condition == 'rain' and icd_code.startswith('V'):
        m *= 1.3
    return m


def sample_diagnosis_for_hospital(hospital_specialty, month, weather_condition=None):
    diags = get_specialty_diagnoses(hospital_specialty)
    weighted = {code: max(0.0, w * apply_diagnosis_seasonality(code, month, hospital_specialty, weather_condition))
                for code, w in diags.items()}
    total = sum(weighted.values())
    if total <= 0:
        return random.choice(list(diags.keys()))
    rnd = random.random() * total
    cum = 0.0
    code = list(diags.keys())[0]
    for code, w in weighted.items():
        cum += w
        if rnd <= cum:
            return code
    return code


def get_procedure_weights_by_specialty(hospital_specialty, date):
    month = pd.to_datetime(date).month
    adjusted = {}
    for proc, base in PROCEDURE_SEASONALITY.items():
        w = base
        if hospital_specialty == 'cardiac' and proc == 'Cardiac Catheterization':
            w *= 1.6
        if hospital_specialty == 'rehab' and proc in ['Hip Replacement', 'Knee Arthroscopy']:
            w *= 1.2
        if proc == 'Appendectomy' and month in [6, 7, 8]:
            w *= 1.25
        adjusted[proc] = w
    total = sum(adjusted.values())
    return {k: v / total for k, v in adjusted.items()} if total > 0 else adjusted


def get_lab_for_diagnosis(icd_code):
    mapping = {
        'I10': ['CMP', 'Lipid Panel'], 'E11.9': ['Hemoglobin A1c', 'Glucose'], 'I25.10': ['Troponin', 'EKG'],
        'E78.5': ['Lipid Panel'], 'F41.9': ['TSH', 'Cortisol'], 'J00': ['CBC'], 'J11.00': ['Chest X-Ray', 'CBC'],
        'N39.0': ['Urinalysis'], 'S72.1': ['X-Ray']
    }
    return random.choice(mapping.get(icd_code, ['CBC', 'CMP']))


def get_medications_for_diagnosis(icd_code):
    mapping = {
        'I10': ['Lisinopril', 'Amlodipine', 'Hydrochlorothiazide'], 'E11.9': ['Metformin', 'Insulin'],
        'J00': ['Albuterol', 'Fluticasone'], 'N39.0': ['Ciprofloxacin'], 'I21.9': ['Aspirin', 'Clopidogrel']
    }
    return mapping.get(icd_code, ['Acetaminophen'])


def get_patient_clinical_status(diagnosis_code, los_days, hospital_specialty):
    critical_codes = ['I21.0', 'I21.9', 'R65.21', 'I63.9', 'C92.0', 'C91.0', 'R50.82']
    postop_codes = ['Z24', 'Z54']

    if diagnosis_code in critical_codes:
        if los_days <= 2:
            return 'Critical'
        elif los_days <= 5:
            return 'Unstable'
        return 'Improving'

    if diagnosis_code in postop_codes or (diagnosis_code and 'Z' in diagnosis_code):
        if los_days <= 1:
            return 'Post-Op'
        elif los_days <= 3:
            return 'Recovering'
        return 'Improving'

    if hospital_specialty == 'cardiac' and diagnosis_code and diagnosis_code.startswith('I'):
        return 'Unstable' if los_days <= 3 else 'Improving'

    if hospital_specialty == 'cancer' and diagnosis_code and diagnosis_code.startswith('C'):
        if los_days <= 2:
            return 'Unstable'
        elif los_days <= 7:
            return 'Improving'
        return 'Stable'

    if hospital_specialty == 'pediatric':
        if los_days <= 1:
            return 'Unstable'
        elif los_days <= 3:
            return 'Improving'
        return 'Stable'

    if los_days <= 1:
        return 'Unstable'
    elif los_days <= 3:
        return 'Improving'
    return 'Stable'


def get_floors_for_hospital(hospital_id, hospital_specialty, bed_count):
    # Create floor configuration for a hospital based on specialty and bed count.
    floors = []
    floor_num = 1

    if hospital_specialty == 'general':
        ed_capacity = max(20, int(bed_count * 0.06))
        floors.append({'floor_number': floor_num, 'department': 'Emergency Department', 'capacity': ed_capacity, 'bed_type': 'Emergency'})
        floor_num += 1
        icu_capacity = max(15, int(bed_count * 0.08))
        floors.append({'floor_number': floor_num, 'department': 'Intensive Care Unit', 'capacity': icu_capacity, 'bed_type': 'Critical Care'})
        floor_num += 1
        medsurg_capacity = int(bed_count * 0.40)
        num_medsurg_floors = max(2, medsurg_capacity // 50)
        per_floor = medsurg_capacity // num_medsurg_floors
        for i in range(num_medsurg_floors):
            floors.append({'floor_number': floor_num, 'department': f'Medical/Surgical Unit {i+1}', 'capacity': per_floor, 'bed_type': 'Medical/Surgical'})
            floor_num += 1
        remaining = bed_count - sum(f['capacity'] for f in floors)
        if remaining > 0:
            floors.append({'floor_number': floor_num, 'department': 'Specialty Services', 'capacity': remaining, 'bed_type': 'Specialty'})

    elif hospital_specialty == 'cardiac':
        cicu_capacity = int(bed_count * 0.25)
        floors.append({'floor_number': floor_num, 'department': 'Cardiac ICU', 'capacity': cicu_capacity, 'bed_type': 'Critical Care'})
        floor_num += 1
        cardio_capacity = int(bed_count * 0.60)
        num_cardio_floors = max(1, cardio_capacity // 50)
        per_floor = cardio_capacity // num_cardio_floors
        for i in range(num_cardio_floors):
            floors.append({'floor_number': floor_num, 'department': f'Cardiology Unit {i+1}', 'capacity': per_floor, 'bed_type': 'Medical'})
            floor_num += 1
        remaining = bed_count - sum(f['capacity'] for f in floors)
        if remaining > 0:
            floors.append({'floor_number': floor_num, 'department': 'Cath Lab Recovery', 'capacity': remaining, 'bed_type': 'Recovery'})

    elif hospital_specialty == 'pediatric':
        ped_ed = int(bed_count * 0.08)
        floors.append({'floor_number': floor_num, 'department': 'Pediatric Emergency', 'capacity': ped_ed, 'bed_type': 'Emergency'})
        floor_num += 1
        picu_capacity = int(bed_count * 0.12)
        floors.append({'floor_number': floor_num, 'department': 'Pediatric Intensive Care', 'capacity': picu_capacity, 'bed_type': 'Critical Care'})
        floor_num += 1
        remaining = bed_count - sum(f['capacity'] for f in floors)
        num_ped_floors = max(1, remaining // 50)
        per_floor = remaining // num_ped_floors
        for i in range(num_ped_floors):
            floors.append({'floor_number': floor_num, 'department': f'Pediatric Ward {i+1}', 'capacity': per_floor, 'bed_type': 'Medical'})
            floor_num += 1

    elif hospital_specialty == 'cancer':
        onc_icu = int(bed_count * 0.20)
        floors.append({'floor_number': floor_num, 'department': 'Oncology ICU', 'capacity': onc_icu, 'bed_type': 'Critical Care'})
        floor_num += 1
        chemo_capacity = int(bed_count * 0.70)
        num_chemo_floors = max(1, chemo_capacity // 40)
        per_floor = chemo_capacity // num_chemo_floors
        for i in range(num_chemo_floors):
            floors.append({'floor_number': floor_num, 'department': f'Oncology Unit {i+1}', 'capacity': per_floor, 'bed_type': 'Medical'})
            floor_num += 1
        remaining = bed_count - sum(f['capacity'] for f in floors)
        if remaining > 0:
            floors.append({'floor_number': floor_num, 'department': 'Bone Marrow Transplant', 'capacity': remaining, 'bed_type': 'Medical'})

    elif hospital_specialty == 'rehab':
        intensive = int(bed_count * 0.40)
        floors.append({'floor_number': floor_num, 'department': 'Intensive Rehabilitation', 'capacity': intensive, 'bed_type': 'Rehabilitation'})
        floor_num += 1
        postsurg = int(bed_count * 0.30)
        floors.append({'floor_number': floor_num, 'department': 'Post-Surgical Rehabilitation', 'capacity': postsurg, 'bed_type': 'Rehabilitation'})
        floor_num += 1
        remaining = bed_count - sum(f['capacity'] for f in floors)
        if remaining > 0:
            floors.append({'floor_number': floor_num, 'department': 'Specialty Rehabilitation', 'capacity': remaining, 'bed_type': 'Rehabilitation'})

    elif hospital_specialty == 'specialty':
        floors.append({'floor_number': floor_num, 'department': 'Observation & Recovery', 'capacity': bed_count, 'bed_type': 'Observation'})

    return floors


print('\n[Cell 6/12] \u2713 Hospital-specific helper functions loaded.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 7: Weather Functions (current + historical, cached)
# (from src/main.py + src/hospital_generation_helpers.py)
# ============================================================================

WEATHER_CACHE_FILE = 'weather_cache.json'
WEATHER_CACHE = {}


def load_weather_cache():
    global WEATHER_CACHE
    if os.path.exists(WEATHER_CACHE_FILE):
        try:
            with open(WEATHER_CACHE_FILE, 'r') as f:
                WEATHER_CACHE = json.load(f)
        except Exception as e:
            print(f'Warning: could not load weather cache: {e}')


def save_weather_cache():
    try:
        with open(WEATHER_CACHE_FILE, 'w') as f:
            json.dump(WEATHER_CACHE, f, indent=2)
    except Exception as e:
        print(f'Warning: could not save weather cache: {e}')


load_weather_cache()


def _map_weather_code(weather_code):
    if weather_code == 0:
        return 'clear'
    if weather_code in [1, 2, 3]:
        return 'cloudy'
    if weather_code in [45, 48]:
        return 'fog'
    if weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return 'rain'
    if weather_code in [71, 73, 75, 77, 85, 86]:
        return 'snow'
    if weather_code in [95, 96, 99]:
        return 'thunderstorm'
    return 'cloudy'


def get_current_weather(latitude=None, longitude=None):
    latitude = latitude if latitude is not None else WEATHER_LATITUDE
    longitude = longitude if longitude is not None else WEATHER_LONGITUDE
    try:
        url = (f'https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}'
               f'&current=weather_code,temperature,precipitation')
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            weather_code = data['current']['weather_code']
            condition = _map_weather_code(weather_code)
            return condition, WEATHER_IMPACT.get(condition, WEATHER_IMPACT['clear'])
    except Exception as e:
        print(f'Warning: Could not fetch weather data: {e}. Using default (clear) weather.')
    return 'clear', WEATHER_IMPACT['clear']


def get_weather_for_date(date, latitude=None, longitude=None):
    latitude = latitude if latitude is not None else WEATHER_LATITUDE
    longitude = longitude if longitude is not None else WEATHER_LONGITUDE
    d = pd.to_datetime(date).date()
    date_str = d.isoformat()

    if date_str in WEATHER_CACHE:
        condition = WEATHER_CACHE[date_str]
        return condition, WEATHER_IMPACT.get(condition, WEATHER_IMPACT['clear'])

    try:
        url = (f'https://archive-api.open-meteo.com/v1/archive?latitude={latitude}&longitude={longitude}'
               f'&start_date={date_str}&end_date={date_str}&daily=weathercode,precipitation_sum&timezone=UTC')
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            weather_codes = data.get('daily', {}).get('weathercode')
            weather_code = weather_codes[0] if weather_codes else None
            condition = _map_weather_code(weather_code) if weather_code is not None else 'clear'
            WEATHER_CACHE[date_str] = condition
            return condition, WEATHER_IMPACT.get(condition, WEATHER_IMPACT['clear'])
    except Exception as e:
        print(f'Warning: could not fetch historical weather for {date}: {e}. Using default clear.')

    WEATHER_CACHE[date_str] = 'clear'
    return 'clear', WEATHER_IMPACT['clear']


print('\n[Cell 7/12] \u2713 Weather functions loaded.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 8: Core Data Generators
# (from src/main.py - patients, doctors, encounters, diagnoses, procedures,
#  medications, labs, insurance, billing, date dimension, admissions)
# ============================================================================

encounter_types = ['Office Visit', 'Emergency', 'Inpatient', 'Telehealth', 'Surgery']
ENCOUNTER_MIX_BY_SPECIALTY = {
    'general': [0.18, 0.34, 0.30, 0.05, 0.13],
    'cardiac': [0.08, 0.22, 0.50, 0.03, 0.17],
    'pediatric': [0.20, 0.35, 0.25, 0.08, 0.12],
    'cancer': [0.12, 0.08, 0.58, 0.07, 0.15],
    'rehab': [0.10, 0.05, 0.72, 0.02, 0.11],
    'specialty': [0.20, 0.10, 0.45, 0.10, 0.15]
}


def generate_patients(n, as_of_date=None):
    as_of = pd.to_datetime(as_of_date).date() if as_of_date is not None else datetime.now().date()
    rows = []
    for _ in range(n):
        hospital = random.choice(HOSPITALS)
        dob = fake.date_of_birth(minimum_age=0, maximum_age=100)
        age = as_of.year - pd.to_datetime(dob).year - ((as_of.month, as_of.day) < (pd.to_datetime(dob).month, pd.to_datetime(dob).day))
        payer = get_payer_for_patient(age, hospital.get('specialty', 'general'))
        gender = fake.random_element(['M', 'F'])
        rows.append({
            'hospital_id': hospital['hospital_id'],
            'first_name': fake.first_name_male() if gender == 'M' else fake.first_name_female(),
            'last_name': fake.last_name(),
            'date_of_birth': dob,
            'age': age,
            'gender': gender,
            'address': fake.address().replace('\n', ', '),
            'phone': fake.phone_number(),
            'email': fake.email(),
            'primary_payer': payer
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'patient_id', range(1, len(df) + 1))
    return df


def generate_doctors(n):
    specialties = ['Cardiology', 'Dermatology', 'Neurology', 'Pediatrics', 'Orthopedics', 'Radiology', 'Surgery', 'Internal Medicine']
    rows = []
    for _ in range(n):
        hospital = random.choice(HOSPITALS)
        rows.append({
            'hospital_id': hospital['hospital_id'],
            'first_name': fake.first_name(),
            'last_name': fake.last_name(),
            'specialty': fake.random_element(specialties),
            'license_number': fake.unique.random_number(digits=10),
            'phone': fake.phone_number(),
            'email': fake.email()
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'provider_id', range(1, len(df) + 1))
    return df


def generate_encounters(n, min_date, end_date, patient_start, patient_count, provider_start, provider_count, hospital_id=None):
    rows = []
    for _ in range(n):
        hospital = next((h for h in HOSPITALS if h['hospital_id'] == hospital_id), None) if hospital_id else random.choice(HOSPITALS)
        if not hospital:
            hospital = random.choice(HOSPITALS)

        month = pd.to_datetime(min_date).month if min_date else pd.Timestamp.now().month
        try:
            icd_code = sample_diagnosis_for_hospital(hospital.get('specialty', 'general'), month)
            details = DIAGNOSIS_DETAILS.get(icd_code, {'description': fake.sentence(), 'complaints': [fake.sentence()]})
        except Exception:
            icd_code = random.choice(list(DIAGNOSIS_DETAILS.keys()))
            details = DIAGNOSIS_DETAILS[icd_code]
        chief_complaint = random.choice(details['complaints'])

        hosp_depts = [d for d in DEPARTMENTS if d['hospital_id'] == hospital['hospital_id']]
        if hosp_depts:
            dept_weights = [DEPARTMENT_DEMAND_MULTIPLIERS.get(d['name'], DEPARTMENT_DEMAND_MULTIPLIERS.get(d['specialty_type'], 1.0)) for d in hosp_depts]
            department = random.choices(hosp_depts, weights=dept_weights)[0]
        else:
            department = {'department_id': 1, 'name': 'General', 'specialty_type': 'Medical'}

        specialty = hospital.get('specialty', 'general')
        payer_type = get_payer_for_patient(age=random.randint(0, 90), hospital_specialty=specialty)
        encounter_weights = ENCOUNTER_MIX_BY_SPECIALTY.get(specialty, ENCOUNTER_MIX_BY_SPECIALTY['general'])

        patient_id = random.randint(patient_start, max(patient_start, patient_start + max(0, patient_count - 1)))
        provider_id = random.randint(provider_start, max(provider_start, provider_start + max(0, provider_count - 1)))
        rows.append({
            'hospital_id': hospital['hospital_id'],
            'department_id': department['department_id'],
            'patient_id': patient_id,
            'provider_id': provider_id,
            'encounter_type': random.choices(encounter_types, weights=encounter_weights, k=1)[0],
            'encounter_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'start_time': fake.time(),
            'end_time': fake.time(),
            'payer_type': payer_type,
            'chief_complaint': chief_complaint,
            'notes': f"Patient presented with {chief_complaint.lower()}. Assessment: {details['description']}. Plan: Monitor and treat accordingly. {fake.text(max_nb_chars=100)}"
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'encounter_id', range(1, len(df) + 1))
    return df


def generate_procedures(n, min_date=None, end_date=None, encounters_df=None):
    rows = []
    date = end_date or min_date or datetime.now().date()
    for _ in range(n):
        if encounters_df is not None and len(encounters_df) > 0:
            enc = encounters_df.sample(1).iloc[0]
            encounter_id = int(enc['encounter_id'])
            hospital_id = int(enc['hospital_id'])
            hosp = next((h for h in HOSPITALS if h['hospital_id'] == hospital_id), None)
            specialty = hosp.get('specialty', 'general') if hosp else 'general'
            proc_weights = get_procedure_weights_by_specialty(specialty, date)
            proc_names = list(proc_weights.keys())
            weights = [proc_weights.get(p, 0.01) for p in proc_names]
            proc_name = random.choices(proc_names, weights=weights)[0]
        else:
            encounter_id = random.randint(1, 300)
            hospital = random.choice(HOSPITALS)
            hospital_id = hospital['hospital_id']
            seasonal_weights = apply_seasonality_to_procedure_weights(date)
            procedure_names = list(PROCEDURE_WEIGHTS.keys())
            weights = [seasonal_weights.get(name, PROCEDURE_WEIGHTS.get(name, 0.01)) for name in procedure_names]
            proc_name = random.choices(procedure_names, weights=weights)[0]

        rows.append({
            'hospital_id': hospital_id,
            'encounter_id': encounter_id,
            'procedure_name': proc_name,
            'procedure_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'cost': round(random.uniform(100, 10000), 2),
            'duration_minutes': random.randint(15, 240)
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'procedure_id', range(1, len(df) + 1))
    return df


def generate_diagnoses_weather_aware(n, min_date=None, end_date=None, weather_condition='clear', weather_impacts=None):
    if weather_impacts is None:
        weather_impacts = WEATHER_IMPACT.get(weather_condition, WEATHER_IMPACT['clear'])
    rows = []
    general_dist = get_specialty_diagnoses('general')
    flu_target = int(n * 0.05 * weather_impacts.get('flu_multiplier', 1.0))
    fall_target = int(n * 0.08 * weather_impacts.get('fall_multiplier', 1.0))
    flu_count = fall_count = 0
    month = pd.to_datetime(min_date).month if min_date else pd.Timestamp.now().month

    for _ in range(n):
        if flu_count < flu_target and random.random() < 0.20:
            icd_code = FLU_ICD_CODE
            flu_count += 1
        elif fall_count < fall_target and random.random() < 0.22:
            icd_code = FALL_ICD_CODE
            fall_count += 1
        else:
            weighted = {code: w * apply_diagnosis_seasonality(code, month, 'general', weather_condition) for code, w in general_dist.items()}
            total = sum(weighted.values())
            if total <= 0:
                icd_code = random.choice(ICD_CODES)
            else:
                r = random.random() * total
                cum = 0.0
                icd_code = list(weighted.keys())[0]
                for code, val in weighted.items():
                    cum += val
                    if r <= cum:
                        icd_code = code
                        break

        details = DIAGNOSIS_DETAILS.get(icd_code, {'description': fake.sentence(), 'complaints': [fake.sentence()]})
        rows.append({
            'encounter_id': 0,
            'patient_id': 0,
            'icd_code': icd_code,
            'description': details['description'],
            'onset_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'status': random.choice(['Active', 'Resolved', 'Chronic'])
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'diagnosis_id', range(1, len(df) + 1))
    return df


def generate_medications(n, min_date=None, end_date=None, encounters_df=None, diagnoses_df=None):
    rows = []
    for _ in range(n):
        if encounters_df is not None and len(encounters_df) > 0:
            enc = encounters_df.sample(1).iloc[0]
            encounter_id = int(enc['encounter_id'])
            patient_id = int(enc['patient_id'])
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

        rows.append({
            'encounter_id': encounter_id,
            'patient_id': patient_id,
            'drug_name': random.choice(med_choices),
            'dosage': f'{random.randint(1, 100)}mg',
            'frequency': random.choice(['Once daily', 'Twice daily', 'As needed']),
            'start_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'end_date': (fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date and random.random() > 0.5 else None),
            'prescribing_provider_id': random.randint(1, 20),
            'status': random.choice(['Active', 'Discontinued'])
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'medication_id', range(1, len(df) + 1))
    return df


def generate_labs(n, min_date=None, end_date=None, encounters_df=None, diagnoses_df=None):
    rows = []
    for _ in range(n):
        if encounters_df is not None and len(encounters_df) > 0:
            enc = encounters_df.sample(1).iloc[0]
            encounter_id = int(enc['encounter_id'])
            patient_id = int(enc['patient_id'])
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

        rows.append({
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
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'lab_id', range(1, len(df) + 1))
    return df


def generate_insurance_for_patients(patients_df, min_date=None, end_date=None):
    rows = []
    for _, p in patients_df.iterrows():
        payer = p.get('primary_payer') or random.choice(['Blue Cross', 'Aetna', 'UnitedHealthcare', 'Cigna', 'Medicare', 'Medicaid'])
        rows.append({
            'patient_id': int(p['patient_id']),
            'payer_name': payer,
            'policy_number': fake.random_number(digits=10),
            'group_number': fake.random_number(digits=8),
            'effective_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year(),
            'expiration_date': fake.date_between(start_date=min_date, end_date=end_date or 'today') if min_date else fake.date_this_year()
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'insurance_id', range(1, len(df) + 1))
    return df


def generate_billing(n, min_date=None, end_date=None):
    rows = []
    for _ in range(n):
        rows.append({
            'encounter_id': random.randint(1, 300),
            'patient_id': random.randint(1, 100),
            'total_charges': round(random.uniform(100, 50000), 2),
            'paid_amount': round(random.uniform(0, 50000), 2),
            'balance': round(random.uniform(0, 50000), 2),
            'claim_status': random.choice(['Submitted', 'Paid', 'Denied', 'Pending']),
            'cpt_codes': random.choice(CPT_CODES),
            'modifiers': random.choice(['26', 'TC', '50', ''])
        })
    df = pd.DataFrame(rows)
    df.insert(0, 'billing_id', range(1, len(df) + 1))
    return df


def generate_date_dimension(start_date, end_date):
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    dates = pd.date_range(start=start, end=end, freq='D')
    rows = []
    for d in dates:
        iso = d.isocalendar()
        rows.append({
            'date': d.date(), 'date_key': int(d.strftime('%Y%m%d')), 'yyyy': d.year, 'mm': d.month,
            'mm_name': d.strftime('%B'), 'mm_short': d.strftime('%b'), 'dd': d.day,
            'day_of_week': d.weekday(), 'day_of_week_name': d.strftime('%A'),
            'is_weekend': 1 if d.weekday() >= 5 else 0, 'quarter': (d.month - 1) // 3 + 1,
            'iso_year': iso.year, 'iso_week': int(iso.week), 'day_of_year': int(d.strftime('%j')),
            'week_of_year': int(d.strftime('%U')), 'fiscal_year': d.year, 'fiscal_month': d.month,
            'mm_dd_yyyy': d.strftime('%m-%d-%Y'), 'dd_mm_yyyy': d.strftime('%d-%m-%Y'), 'yyyy_mm_dd': d.strftime('%Y-%m-%d')
        })
    return pd.DataFrame(rows)


def generate_hospital_department_beds(hospitals_df, departments_df, effective_date):
    rows = []
    for _, h in hospitals_df.iterrows():
        hid = int(h['hospital_id'])
        total_beds = int(h['bed_count'])
        deps = departments_df[departments_df['hospital_id'] == hid]
        if deps.empty:
            rows.append({'hospital_id': hid, 'department_id': None, 'date': effective_date, 'beds_allocated': total_beds})
            continue

        allocations = []
        for _, dep in deps.iterrows():
            allocation_pct = DEPARTMENT_BED_ALLOCATION.get(dep['name'], DEPARTMENT_BED_ALLOCATION['default'])
            allocations.append({'dept': dep, 'beds': int(total_beds * allocation_pct)})

        allocated_sum = sum(a['beds'] for a in allocations)
        if allocated_sum > 0:
            ratio = total_beds / allocated_sum
            adjusted = [{'dept': a['dept'], 'beds': int(a['beds'] * ratio)} for a in allocations]
            remainder = total_beds - sum(a['beds'] for a in adjusted)
            sorted_adjusted = sorted(adjusted, key=lambda x: x['beds'], reverse=True)
            for i in range(abs(remainder)):
                if remainder > 0:
                    sorted_adjusted[i % len(sorted_adjusted)]['beds'] += 1
                else:
                    sorted_adjusted[i % len(sorted_adjusted)]['beds'] -= 1
            for a in sorted_adjusted:
                rows.append({'hospital_id': hid, 'department_id': int(a['dept']['department_id']), 'date': effective_date, 'beds_allocated': int(a['beds'])})
        else:
            beds_per_dept = total_beds // len(deps)
            remainder = total_beds % len(deps)
            for i, (_, dep) in enumerate(deps.iterrows()):
                beds = beds_per_dept + (1 if i < remainder else 0)
                rows.append({'hospital_id': hid, 'department_id': int(dep['department_id']), 'date': effective_date, 'beds_allocated': int(beds)})
    return pd.DataFrame(rows)


def generate_admissions_for_day_specialty_aware(hospitals_df, encounters_df, patients_df, departments_df, date, start_admission_id=1):
    rows = []
    if encounters_df is None or encounters_df.empty:
        return pd.DataFrame()

    encounter_admission_factor = {'Inpatient': 3.0, 'Emergency': 1.8, 'Surgery': 2.2, 'Office Visit': 0.20, 'Telehealth': 0.05}
    aid = start_admission_id
    hospital_lookup = {h['hospital_id']: h for h in HOSPITALS}

    for _, enc in encounters_df.iterrows():
        hid = int(enc.get('hospital_id', random.choice(hospitals_df['hospital_id'].tolist())))
        hospital = hospital_lookup.get(hid, {'specialty': 'general'})
        specialty = hospital.get('specialty', 'general')
        admission_prob = get_admission_rate(specialty)
        encounter_type = enc.get('encounter_type', 'Office Visit')
        type_factor = encounter_admission_factor.get(encounter_type, 0.25)
        adjusted_admission_prob = min(0.98, admission_prob * type_factor)

        if random.random() > adjusted_admission_prob:
            continue

        pid = int(enc.get('patient_id', random.randint(1, max(1, len(patients_df)))))
        dept_id = enc.get('department_id')
        ed = departments_df[(departments_df['hospital_id'] == hid) & (departments_df['name'].str.lower().str.contains('emergency', na=False))]
        if not ed.empty:
            dept_id = int(ed.iloc[0]['department_id'])

        admit_hours = get_admission_times_by_specialty(specialty, num_admissions=1)
        admit_hour = admit_hours[0] if admit_hours else random.randint(0, 23)
        admit_dt = pd.to_datetime(date) + pd.Timedelta(hours=admit_hour, minutes=random.randint(0, 59))
        avg_los = get_average_los(specialty)

        if random.random() < 0.45:
            los_days = max(1, int(avg_los + random.gauss(0, avg_los * 0.35)))
            discharge_dt = admit_dt + pd.Timedelta(days=los_days, hours=random.randint(7, 17))
        else:
            discharge_dt = None

        rows.append({
            'admission_id': aid, 'patient_id': pid, 'hospital_id': hid,
            'department_id': int(dept_id) if dept_id is not None else None,
            'encounter_id': int(enc.get('encounter_id', -1)),
            'admit_datetime': admit_dt, 'discharge_datetime': discharge_dt
        })
        aid += 1

    return pd.DataFrame(rows)


print('\n[Cell 8/12] \u2713 Core data generators loaded.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 9: Floor / Room / Bed / Patient-Location Management
# (from src/floor_management.py)
# ============================================================================


def create_floors_for_hospitals(engine, hospitals):
    floors_data = []
    hospital_floors = {}
    for hospital in hospitals:
        h_id = hospital['hospital_id']
        floor_configs = get_floors_for_hospital(h_id, hospital['specialty'], hospital['bed_count'])
        for fc in floor_configs:
            floors_data.append({'hospital_id': h_id, 'floor_number': fc['floor_number'], 'department': fc['department'],
                                 'bed_type': fc['bed_type'], 'capacity': fc['capacity']})
        hospital_floors[h_id] = floor_configs
    if floors_data:
        pd.DataFrame(floors_data).to_sql('floors', engine, if_exists='replace', index=False)
    return hospital_floors


def create_rooms_and_beds(engine, hospital_floors):
    rooms_data = []
    beds_data = []
    room_id = 1
    bed_id = 1
    for hospital_id, floor_configs in hospital_floors.items():
        for floor_config in floor_configs:
            floor_num = floor_config['floor_number']
            bed_type = floor_config['bed_type']
            capacity = floor_config['capacity']
            if bed_type in ['Critical Care', 'Emergency']:
                single = int(capacity * 0.9)
                room_configs = ([{'bed_count': 1, 'room_type': 'Single'}] * single) + ([{'bed_count': 2, 'room_type': 'Double'}] * max(0, capacity - single))
            elif bed_type in ['Rehabilitation', 'Recovery']:
                single = int(capacity * 0.6)
                room_configs = ([{'bed_count': 1, 'room_type': 'Single'}] * single) + ([{'bed_count': 2, 'room_type': 'Double'}] * max(0, capacity - single))
            else:
                single = int(capacity * 0.3)
                rem = max(0, capacity - single)
                dbl = int(rem * 0.6)
                quad = max(0, rem - dbl)
                room_configs = (([{'bed_count': 1, 'room_type': 'Single'}] * single)
                                + ([{'bed_count': 2, 'room_type': 'Double'}] * dbl)
                                + ([{'bed_count': 4, 'room_type': 'Quad'}] * quad))

            floor_room_num = 1
            for room_config in room_configs:
                rooms_data.append({'room_id': room_id, 'hospital_id': hospital_id, 'floor_number': floor_num,
                                    'room_number': floor_room_num, 'bed_count': room_config['bed_count'], 'room_type': room_config['room_type']})
                for bed_pos in range(1, room_config['bed_count'] + 1):
                    beds_data.append({'bed_id': bed_id, 'room_id': room_id, 'hospital_id': hospital_id, 'floor_number': floor_num,
                                       'room_number': floor_room_num, 'bed_position': bed_pos, 'bed_type': bed_type, 'status': 'Available'})
                    bed_id += 1
                room_id += 1
                floor_room_num += 1

    if rooms_data:
        pd.DataFrame(rooms_data).to_sql('rooms', engine, if_exists='replace', index=False)
    if beds_data:
        pd.DataFrame(beds_data).to_sql('beds', engine, if_exists='replace', index=False)
    return pd.DataFrame(beds_data)


def create_patient_bed_assignments_table(engine):
    empty = pd.DataFrame(columns=['assignment_id', 'admission_id', 'patient_id', 'hospital_id', 'bed_id',
                                   'floor_number', 'room_number', 'bed_position', 'assigned_datetime',
                                   'discharged_datetime', 'patient_status', 'diagnosis_code', 'los_days'])
    empty.to_sql('patient_bed_assignments', engine, if_exists='replace', index=False)


def rebuild_patient_bed_assignments(engine, hospitals):
    try:
        admissions = pd.read_sql(
            "SELECT admission_id, patient_id, hospital_id, encounter_id, admit_datetime, discharge_datetime "
            "FROM admissions WHERE admit_datetime IS NOT NULL", engine)
    except Exception:
        create_patient_bed_assignments_table(engine)
        return
    if admissions.empty:
        create_patient_bed_assignments_table(engine)
        return

    diagnoses = pd.read_sql('SELECT encounter_id, icd_code FROM diagnoses', engine)
    patients = pd.read_sql('SELECT patient_id, age FROM patients', engine)
    bed_cols = set(pd.read_sql('SELECT TOP 0 * FROM beds', engine).columns)
    bed_select_cols = ['bed_id', 'hospital_id', 'floor_number', 'room_number', 'bed_position', 'bed_type']
    if 'room_id' in bed_cols:
        bed_select_cols.insert(1, 'room_id')
    beds = pd.read_sql(f"SELECT {', '.join(bed_select_cols)} FROM beds", engine)

    diag_map = diagnoses.groupby('encounter_id').first()['icd_code'].to_dict() if not diagnoses.empty else {}
    age_map = patients.set_index('patient_id')['age'].to_dict() if not patients.empty else {}
    specialty_by_hospital = {h['hospital_id']: h.get('specialty', 'general') for h in hospitals}

    admissions['admit_datetime'] = pd.to_datetime(admissions['admit_datetime'])
    admissions['discharge_datetime'] = pd.to_datetime(admissions['discharge_datetime'])

    now = pd.Timestamp(datetime.now())
    assignments = []
    occupied_now = set()
    assignment_id = 1

    for hospital_id in sorted(admissions['hospital_id'].unique()):
        hosp_beds = beds[beds['hospital_id'] == hospital_id].copy()
        if hosp_beds.empty:
            continue
        active = []
        free_beds = hosp_beds.to_dict('records')
        hosp_adm = admissions[admissions['hospital_id'] == hospital_id].sort_values('admit_datetime')
        for _, adm in hosp_adm.iterrows():
            admit_dt = adm['admit_datetime']
            discharge_dt = adm['discharge_datetime']
            still_active = []
            for free_at, bed in active:
                if pd.notna(free_at) and free_at <= admit_dt:
                    free_beds.append(bed)
                else:
                    still_active.append((free_at, bed))
            active = still_active
            if not free_beds:
                continue

            encounter_id = int(adm['encounter_id']) if pd.notna(adm['encounter_id']) else None
            diagnosis_code = diag_map.get(encounter_id, None)
            age = int(age_map.get(int(adm['patient_id']), 50))
            los_days = int(max(0, ((discharge_dt if pd.notna(discharge_dt) else now) - admit_dt).days))
            specialty = specialty_by_hospital.get(hospital_id, 'general')
            patient_status = get_patient_clinical_status(str(diagnosis_code) if diagnosis_code else 'I10', los_days, specialty)

            preferred = (['Critical Care', 'Emergency'] if patient_status in ['Critical', 'Unstable']
                         else ['Medical', 'Medical/Surgical', 'Recovery', 'Rehabilitation', 'Observation', 'Specialty'])
            bed_idx = next((i for i, b in enumerate(free_beds) if b['bed_type'] in preferred), 0)
            bed = free_beds.pop(bed_idx)

            assignments.append({
                'assignment_id': assignment_id, 'admission_id': int(adm['admission_id']), 'patient_id': int(adm['patient_id']),
                'hospital_id': int(hospital_id), 'bed_id': int(bed['bed_id']), 'floor_number': int(bed['floor_number']),
                'room_number': int(bed['room_number']), 'bed_position': int(bed['bed_position']), 'assigned_datetime': admit_dt,
                'discharged_datetime': discharge_dt if pd.notna(discharge_dt) else None, 'patient_status': patient_status,
                'diagnosis_code': diagnosis_code, 'los_days': los_days
            })
            assignment_id += 1

            if pd.isna(discharge_dt) or discharge_dt > now:
                occupied_now.add(int(bed['bed_id']))
                active.append((pd.Timestamp.max, bed))
            else:
                active.append((discharge_dt, bed))

    assign_df = pd.DataFrame(assignments)
    if assign_df.empty:
        create_patient_bed_assignments_table(engine)
    else:
        assign_df.to_sql('patient_bed_assignments', engine, if_exists='replace', index=False)

    beds['status'] = beds['bed_id'].apply(lambda b: 'Occupied' if int(b) in occupied_now else 'Available')
    beds.to_sql('beds', engine, if_exists='replace', index=False)


def create_current_er_beds_view(engine):
    sql = '''
    CREATE OR ALTER VIEW vw_current_er_beds AS
    SELECT h.hospital_id, h.name AS hospital_name, ISNULL(b.beds_allocated, 0) AS er_beds
    FROM hospitals h
    LEFT JOIN (
      SELECT hb.hospital_id, hb.beds_allocated
      FROM hospital_department_beds hb
      JOIN departments d ON hb.department_id = d.department_id
      WHERE d.name = 'Emergency' AND hb.date = (SELECT MAX(date) FROM hospital_department_beds)
    ) b ON h.hospital_id = b.hospital_id;
    '''
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as e:
        print('Note: could not create vw_current_er_beds:', e)


def create_current_patient_beds_view(engine):
    sql = '''
    CREATE OR ALTER VIEW vw_current_patient_beds AS
    SELECT h.hospital_id, h.name AS hospital_name, ISNULL(a.total_beds, 0) AS allocated_beds,
        ISNULL(o.occupied_beds, 0) AS occupied_beds,
        CASE WHEN ISNULL(a.total_beds, 0) - ISNULL(o.occupied_beds, 0) < 0 THEN 0
             ELSE ISNULL(a.total_beds, 0) - ISNULL(o.occupied_beds, 0) END AS available_beds
    FROM hospitals h
    LEFT JOIN (SELECT hospital_id, COUNT(*) AS total_beds FROM beds GROUP BY hospital_id) a ON h.hospital_id = a.hospital_id
    LEFT JOIN (
        SELECT pba.hospital_id, COUNT(DISTINCT pba.bed_id) AS occupied_beds
        FROM patient_bed_assignments pba
        LEFT JOIN admissions adm ON pba.admission_id = adm.admission_id
        WHERE pba.assigned_datetime <= GETDATE()
          AND (pba.discharged_datetime IS NULL OR pba.discharged_datetime > GETDATE())
          AND (adm.discharge_datetime IS NULL OR adm.discharge_datetime > GETDATE())
        GROUP BY pba.hospital_id
    ) o ON h.hospital_id = o.hospital_id;
    '''
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as e:
        print('Note: could not create vw_current_patient_beds:', e)


def create_floor_views(engine):
    def table_cols(table_name):
        try:
            return set(pd.read_sql(f'SELECT TOP 0 * FROM {table_name}', engine).columns)
        except Exception:
            return set()

    hospital_cols = table_cols('hospitals')
    patient_cols = table_cols('patients')
    doctor_cols = table_cols('doctors')
    insurance_cols = table_cols('insurance')

    hospital_name_expr = 'h.name' if 'name' in hospital_cols else ("h.hospital_name" if 'hospital_name' in hospital_cols else "'Unknown Hospital'")
    patient_name_expr = ("p.first_name + ' ' + p.last_name" if {'first_name', 'last_name'}.issubset(patient_cols)
                          else 'CAST(p.patient_id AS VARCHAR(50))')
    doctor_name_expr = ("doc.first_name + ' ' + doc.last_name" if {'first_name', 'last_name'}.issubset(doctor_cols)
                         else 'CAST(doc.provider_id AS VARCHAR(50))')
    payer_name_expr = ('ins.payer_name' if 'payer_name' in insurance_cols else ('ins.company_name' if 'company_name' in insurance_cols else 'NULL'))
    room_join_expr = 'r.hospital_id = b.hospital_id AND r.floor_number = b.floor_number AND r.room_number = b.room_number'

    vw_floor_plan = f'''
    CREATE OR ALTER VIEW vw_floor_plan AS
    SELECT h.hospital_id, {hospital_name_expr} AS hospital_name, f.floor_number, f.department, f.bed_type,
        r.room_id, r.room_number, b.bed_id, b.bed_position, b.status AS bed_status,
        CASE WHEN b.status = 'Occupied' THEN 'Occupied' ELSE 'Available' END AS occupancy_status,
        pba.patient_id, {patient_name_expr} AS patient_name, pba.patient_status AS clinical_status,
        pba.diagnosis_code, pba.los_days, pba.assigned_datetime, f.capacity AS floor_capacity
    FROM hospitals h
    LEFT JOIN floors f ON h.hospital_id = f.hospital_id
    LEFT JOIN rooms r ON f.hospital_id = r.hospital_id AND f.floor_number = r.floor_number
    LEFT JOIN beds b ON {room_join_expr}
    LEFT JOIN patient_bed_assignments pba ON b.bed_id = pba.bed_id AND pba.discharged_datetime IS NULL
    LEFT JOIN patients p ON pba.patient_id = p.patient_id
    '''

    vw_patient_location = f'''
    CREATE OR ALTER VIEW vw_patient_location AS
    SELECT p.patient_id, {patient_name_expr} AS patient_name, p.date_of_birth, p.age, a.admission_id,
        h.hospital_id, {hospital_name_expr} AS hospital_name, f.floor_number, f.department,
        pba.room_number, pba.bed_position, pba.patient_status AS clinical_status, pba.diagnosis_code,
        diag.description AS diagnosis_name, e.chief_complaint, pba.los_days, a.admit_datetime, a.discharge_datetime,
        {doctor_name_expr} AS doctor_name, doc.specialty AS doctor_specialty, e.payer_type, {payer_name_expr} AS payer_name
    FROM patient_bed_assignments pba
    LEFT JOIN admissions a ON pba.admission_id = a.admission_id
    LEFT JOIN patients p ON pba.patient_id = p.patient_id
    LEFT JOIN hospitals h ON pba.hospital_id = h.hospital_id
    LEFT JOIN floors f ON pba.floor_number = f.floor_number AND pba.hospital_id = f.hospital_id
    LEFT JOIN encounters e ON a.encounter_id = e.encounter_id
    OUTER APPLY (SELECT TOP 1 d1.* FROM diagnoses d1 WHERE d1.encounter_id = e.encounter_id) diag
    LEFT JOIN doctors doc ON e.provider_id = doc.provider_id
    OUTER APPLY (SELECT TOP 1 ins1.* FROM insurance ins1 WHERE ins1.patient_id = p.patient_id) ins
    WHERE pba.discharged_datetime IS NULL AND (a.discharge_datetime IS NULL OR a.discharge_datetime > GETDATE())
    '''

    vw_floor_occupancy = f'''
    CREATE OR ALTER VIEW vw_floor_occupancy AS
    SELECT h.hospital_id, {hospital_name_expr} AS hospital_name, f.floor_number, f.department, f.bed_type,
        bed_counts.floor_beds AS capacity, COALESCE(pba_counts.occupied_beds, 0) AS occupied_beds,
        COALESCE(bed_counts.floor_beds, 0) - COALESCE(pba_counts.occupied_beds, 0) AS available_beds
    FROM hospitals h
    LEFT JOIN floors f ON h.hospital_id = f.hospital_id
    LEFT JOIN (SELECT hospital_id, floor_number, COUNT(*) AS floor_beds FROM beds GROUP BY hospital_id, floor_number) bed_counts
        ON h.hospital_id = bed_counts.hospital_id AND f.floor_number = bed_counts.floor_number
    LEFT JOIN (
        SELECT hospital_id, floor_number, COUNT(DISTINCT bed_id) AS occupied_beds
        FROM patient_bed_assignments WHERE discharged_datetime IS NULL GROUP BY hospital_id, floor_number
    ) pba_counts ON h.hospital_id = pba_counts.hospital_id AND f.floor_number = pba_counts.floor_number
    WHERE f.floor_number IS NOT NULL
    '''

    vw_hospital_status = f'''
    CREATE OR ALTER VIEW vw_hospital_status AS
    SELECT h.hospital_id, {hospital_name_expr} AS hospital_name, bed_counts.total_beds AS bed_count,
        COALESCE(pba_counts.total_occupied, 0) AS total_occupied,
        COALESCE(bed_counts.total_beds, 0) - COALESCE(pba_counts.total_occupied, 0) AS total_available
    FROM hospitals h
    LEFT JOIN (SELECT hospital_id, COUNT(*) AS total_beds FROM beds GROUP BY hospital_id) bed_counts ON h.hospital_id = bed_counts.hospital_id
    LEFT JOIN (
        SELECT hospital_id, COUNT(DISTINCT bed_id) AS total_occupied
        FROM patient_bed_assignments WHERE discharged_datetime IS NULL GROUP BY hospital_id
    ) pba_counts ON h.hospital_id = pba_counts.hospital_id
    '''

    for view_name, sql in [('vw_floor_plan', vw_floor_plan), ('vw_patient_location', vw_patient_location),
                            ('vw_floor_occupancy', vw_floor_occupancy), ('vw_hospital_status', vw_hospital_status)]:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception as e:
            print(f'Note: Could not create {view_name}: {e}')


def refresh_patient_location_system(engine, hospitals, rebuild=False):
    if rebuild:
        hospital_floors = create_floors_for_hospitals(engine, hospitals)
        create_rooms_and_beds(engine, hospital_floors)
    else:
        try:
            existing = pd.read_sql('SELECT TOP 1 bed_id FROM beds', engine)
            if existing.empty:
                hospital_floors = create_floors_for_hospitals(engine, hospitals)
                create_rooms_and_beds(engine, hospital_floors)
        except Exception:
            hospital_floors = create_floors_for_hospitals(engine, hospitals)
            create_rooms_and_beds(engine, hospital_floors)

    rebuild_patient_bed_assignments(engine, hospitals)
    create_floor_views(engine)


print('\n[Cell 9/12] \u2713 Floor / room / bed / patient-location management loaded.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 10: Orchestrator - Generate & Load Every Missing Day (START_DATE..END_DATE)
# ============================================================================

print('\n[Cell 10/12] Running Data Generator')
print('\u2500' * 60)

if not SINGLE_ENGINE:
    print('\u274c Database engine not initialized. Please run Cell 3 first.')
elif not NEEDS_GENERATION:
    print('\u2713 Database is already current \u2014 nothing to generate.')
else:
    hospitals_df = pd.DataFrame(HOSPITALS)
    departments_df = pd.DataFrame(DEPARTMENTS)

    # Reference data is only (re)written the first time the database is populated.
    if IS_EMPTY_DATABASE:
        hospitals_df.to_sql('hospitals', SINGLE_ENGINE, if_exists='replace', index=False)
        departments_df.to_sql('departments', SINGLE_ENGINE, if_exists='replace', index=False)
        print(f'  \u2713 Initialized {len(hospitals_df)} hospitals, {len(departments_df)} departments')

    # Seed running id counters from the database so ids never collide, even
    # when a previous run was interrupted mid-way.
    next_ids = {
        'patient': get_next_id('patients', 'patient_id'),
        'provider': get_next_id('doctors', 'provider_id'),
        'encounter': get_next_id('encounters', 'encounter_id'),
        'procedure': get_next_id('procedures', 'procedure_id'),
        'diagnosis': get_next_id('diagnoses', 'diagnosis_id'),
        'medication': get_next_id('medications', 'medication_id'),
        'lab': get_next_id('labs', 'lab_id'),
        'insurance': get_next_id('insurance', 'insurance_id'),
        'billing': get_next_id('billing', 'billing_id'),
        'admission': get_next_id('admissions', 'admission_id'),
    }

    # Daily generation volumes (mirrors src/main.py 'daily' frequency).
    PATIENT_COUNT_PER_DAY = 50
    DOCTOR_COUNT_PER_DAY = 5
    PROCEDURE_COUNT_PER_DAY = 100
    BASE_ENCOUNTER_COUNT_PER_DAY = 150
    DIAGNOSIS_COUNT_PER_DAY = 200
    MEDICATION_COUNT_PER_DAY = 125
    LAB_COUNT_PER_DAY = 175
    BILLING_COUNT_PER_DAY = 150

    date_range = pd.date_range(start=START_DATE, end=END_DATE, freq='D')
    total_days = len(date_range)
    total_encounters = 0
    total_admissions = 0

    for day_idx, current_ts in enumerate(date_range, start=1):
        day = current_ts.date()

        patients_df = generate_patients(PATIENT_COUNT_PER_DAY, as_of_date=day)
        patients_df['patient_id'] = range(next_ids['patient'], next_ids['patient'] + len(patients_df))

        doctors_df = generate_doctors(DOCTOR_COUNT_PER_DAY)
        doctors_df['provider_id'] = range(next_ids['provider'], next_ids['provider'] + len(doctors_df))

        weather_condition, weather_impacts = get_weather_for_date(day)

        # Generate encounters per hospital using specialty + bed-size scaling.
        encounters_df = pd.DataFrame()
        total_beds = sum(h['bed_count'] for h in HOSPITALS)
        for hospital in HOSPITALS:
            hospital_id = hospital['hospital_id']
            specialty = hospital.get('specialty', 'general')
            hosp_base_count = get_hospital_monthly_encounters(specialty, day.month, base_encounters=BASE_ENCOUNTER_COUNT_PER_DAY)
            bed_ratio = hospital['bed_count'] / total_beds
            variation = random.uniform(0.85, 1.30)
            hosp_encounter_count = max(1, int(hosp_base_count * bed_ratio * 10 * variation * PATIENT_LOAD_MULTIPLIER))

            hosp_encounters = generate_encounters(
                hosp_encounter_count, min_date=day, end_date=day,
                patient_start=next_ids['patient'], patient_count=PATIENT_COUNT_PER_DAY,
                provider_start=next_ids['provider'], provider_count=DOCTOR_COUNT_PER_DAY,
                hospital_id=hospital_id
            )
            hosp_encounters['encounter_id'] = range(next_ids['encounter'], next_ids['encounter'] + len(hosp_encounters))
            next_ids['encounter'] += len(hosp_encounters)
            encounters_df = pd.concat([encounters_df, hosp_encounters], ignore_index=True)

        # Specialty + weather + seasonality-aware diagnoses tied to real encounters.
        diagnoses_rows = []
        for hospital in HOSPITALS:
            hospital_id = hospital['hospital_id']
            specialty = hospital.get('specialty', 'general')
            hosp_encounters = encounters_df[encounters_df['hospital_id'] == hospital_id]
            if hosp_encounters.empty:
                continue
            hosp_diagnosis_count = max(1, int(DIAGNOSIS_COUNT_PER_DAY * (len(hosp_encounters) / max(1, len(encounters_df)))))
            for _ in range(hosp_diagnosis_count):
                icd_code = sample_diagnosis_for_hospital(specialty, day.month, weather_condition=weather_condition)
                description = describe_icd_code(icd_code)
                if description is None:
                    raise KeyError(
                        f'ICD code {icd_code} is missing from ICD_REFERENCE. Add it there '
                        f'rather than writing a placeholder description into the ODS.'
                    )
                diagnoses_rows.append({
                    'encounter_id': int(random.choice(hosp_encounters['encounter_id'].tolist())),
                    'patient_id': random.randint(next_ids['patient'], next_ids['patient'] + PATIENT_COUNT_PER_DAY - 1),
                    'icd_code': icd_code, 'description': description, 'onset_date': day,
                    'status': random.choice(['Active', 'Resolved', 'Chronic'])
                })
        diagnoses_df = pd.DataFrame(diagnoses_rows)
        if not diagnoses_df.empty:
            diagnoses_df.insert(0, 'diagnosis_id', range(next_ids['diagnosis'], next_ids['diagnosis'] + len(diagnoses_df)))
            next_ids['diagnosis'] += len(diagnoses_df)

        procedures_df = generate_procedures(PROCEDURE_COUNT_PER_DAY, min_date=day, end_date=day, encounters_df=encounters_df)
        procedures_df['procedure_id'] = range(next_ids['procedure'], next_ids['procedure'] + len(procedures_df))
        next_ids['procedure'] += len(procedures_df)

        medications_df = generate_medications(MEDICATION_COUNT_PER_DAY, min_date=day, end_date=day, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
        medications_df['medication_id'] = range(next_ids['medication'], next_ids['medication'] + len(medications_df))
        next_ids['medication'] += len(medications_df)
        if 'prescribing_provider_id' in medications_df.columns:
            medications_df['prescribing_provider_id'] = medications_df['prescribing_provider_id'] + (next_ids['provider'] - DOCTOR_COUNT_PER_DAY - 1)

        labs_df = generate_labs(LAB_COUNT_PER_DAY, min_date=day, end_date=day, encounters_df=encounters_df, diagnoses_df=diagnoses_df)
        labs_df['lab_id'] = range(next_ids['lab'], next_ids['lab'] + len(labs_df))
        next_ids['lab'] += len(labs_df)

        insurance_df = generate_insurance_for_patients(patients_df, min_date=day)
        insurance_df['insurance_id'] = range(next_ids['insurance'], next_ids['insurance'] + len(insurance_df))
        next_ids['insurance'] += len(insurance_df)

        billing_df = generate_billing(BILLING_COUNT_PER_DAY, min_date=day)
        billing_df['billing_id'] = range(next_ids['billing'], next_ids['billing'] + len(billing_df))
        next_ids['billing'] += len(billing_df)
        if 'encounter_id' in billing_df.columns and len(encounters_df) > 0:
            billing_df['encounter_id'] = random.choices(encounters_df['encounter_id'].tolist(), k=len(billing_df))
        if 'patient_id' in billing_df.columns and len(patients_df) > 0:
            billing_df['patient_id'] = random.choices(patients_df['patient_id'].tolist(), k=len(billing_df))

        admissions_df = generate_admissions_for_day_specialty_aware(
            hospitals_df, encounters_df, patients_df, departments_df, day, start_admission_id=next_ids['admission']
        )
        next_ids['admission'] += len(admissions_df)

        dept_beds_df = generate_hospital_department_beds(hospitals_df, departments_df, day)

        # Always append: pandas to_sql(if_exists='append') creates the table
        # automatically the first time, so this is safe for both an empty and
        # an already-populated database.
        patients_df.to_sql('patients', SINGLE_ENGINE, if_exists='append', index=False)
        doctors_df.to_sql('doctors', SINGLE_ENGINE, if_exists='append', index=False)
        encounters_df.to_sql('encounters', SINGLE_ENGINE, if_exists='append', index=False)
        if not diagnoses_df.empty:
            diagnoses_df.to_sql('diagnoses', SINGLE_ENGINE, if_exists='append', index=False)
        if not procedures_df.empty:
            procedures_df.to_sql('procedures', SINGLE_ENGINE, if_exists='append', index=False)
        if not medications_df.empty:
            medications_df.to_sql('medications', SINGLE_ENGINE, if_exists='append', index=False)
        if not labs_df.empty:
            labs_df.to_sql('labs', SINGLE_ENGINE, if_exists='append', index=False)
        if not insurance_df.empty:
            insurance_df.to_sql('insurance', SINGLE_ENGINE, if_exists='append', index=False)
        if not billing_df.empty:
            billing_df.to_sql('billing', SINGLE_ENGINE, if_exists='append', index=False)
        if not admissions_df.empty:
            admissions_df.to_sql('admissions', SINGLE_ENGINE, if_exists='append', index=False)
        dept_beds_df.to_sql('hospital_department_beds', SINGLE_ENGINE, if_exists='append', index=False)

        next_ids['patient'] += len(patients_df)
        next_ids['provider'] += len(doctors_df)

        total_encounters += len(encounters_df)
        total_admissions += len(admissions_df)

        if day_idx == 1 or day_idx == total_days or day_idx % 7 == 0:
            print(f'  [{day_idx}/{total_days}] {day}: {len(encounters_df):,} encounters, {len(admissions_df):,} admissions ({weather_condition})')

    # Keep date dimension covering the full encounter range.
    db_range = query_db('SELECT MIN(CAST(encounter_date AS DATE)) as min_d, MAX(CAST(encounter_date AS DATE)) as max_d FROM encounters')
    if db_range is not None and not db_range.empty and pd.notna(db_range.iloc[0]['min_d']):
        dim_min = pd.to_datetime(db_range.iloc[0]['min_d']).date()
        dim_max = pd.to_datetime(db_range.iloc[0]['max_d']).date()
        generate_date_dimension(dim_min, dim_max).to_sql('date_dim', SINGLE_ENGINE, if_exists='replace', index=False)

    print(f'\n\u2713 Generated {total_encounters:,} encounters and {total_admissions:,} admissions across {total_days} day(s).')
    print('  Proceed to Cell 11 to refresh patient-location assignments and views.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 11: Refresh Patient-Location System, Views & Run Log
# ============================================================================

print('\n[Cell 11/12] Patient-Location Refresh & Views')
print('\u2500' * 60)

if not SINGLE_ENGINE:
    print('\u274c Database engine not available.')
else:
    # Reference dimension + description repair run on every pass, independent of
    # whether new days were generated, so an existing database gains the
    # dimension and has legacy placeholder descriptions corrected in place.
    icd_reference_df = build_icd_reference_frame()
    icd_reference_df.to_sql('icd_reference', SINGLE_ENGINE, if_exists='replace', index=False)
    print(f'  \u2713 icd_reference refreshed: {len(icd_reference_df)} codes, '
          f'{icd_reference_df["clinical_family"].nunique()} clinical families')

    try:
        with SINGLE_ENGINE.begin() as conn:
            repaired = conn.execute(text(
                'UPDATE d SET description = r.description '
                'FROM dbo.diagnoses d JOIN dbo.icd_reference r ON r.icd_code = d.icd_code '
                # icd_reference is the authority for code titles, so this also
                # corrects rows written by other producers (e.g. the ops
                # simulator) whose wording drifted from the reference.
                'WHERE d.description IS NULL OR d.description <> r.description'
            )).rowcount
        if repaired:
            print(f'  \u2713 Repaired {repaired:,} diagnosis rows whose description was missing or disagreed with icd_reference')
        else:
            print('  \u2713 Every diagnosis description matches icd_reference')
        orphans = query_db(
            'SELECT COUNT(*) AS n FROM dbo.diagnoses d '
            'LEFT JOIN dbo.icd_reference r ON r.icd_code = d.icd_code WHERE r.icd_code IS NULL'
        )
        if orphans is not None and int(orphans.iloc[0]['n']) > 0:
            print(f'  \u26A0\ufe0f  {int(orphans.iloc[0]["n"]):,} diagnosis rows use a code missing '
                  f'from ICD_REFERENCE \u2014 add it so the family dimension stays complete')
    except Exception as e:
        print(f'  \u26A0\ufe0f  Could not repair diagnosis descriptions: {e}')

if not SINGLE_ENGINE:
    pass
elif not NEEDS_GENERATION:
    print('\u2713 No generation occurred this run \u2014 skipping refresh.')
else:
    refresh_patient_location_system(SINGLE_ENGINE, HOSPITALS, rebuild=IS_EMPTY_DATABASE)
    create_current_er_beds_view(SINGLE_ENGINE)
    create_current_patient_beds_view(SINGLE_ENGINE)
    print('  \u2713 Floors/rooms/beds ensured, patient_bed_assignments recomputed, views refreshed')

    save_weather_cache()

    # run_logs predates the day-range catch-up model and older databases still
    # carry only the per-entity count columns. Add the columns this notebook
    # writes, idempotently, so logging self-heals in place instead of failing
    # silently into the exception handler below.
    run_log_columns = [
        ('start_date', 'DATE'),
        ('end_date', 'DATE'),
        ('days_generated', 'INT'),
        ('admissions_generated', 'BIGINT'),
    ]
    try:
        with SINGLE_ENGINE.begin() as conn:
            for column_name, column_type in run_log_columns:
                conn.execute(text(
                    f"IF COL_LENGTH('dbo.run_logs', '{column_name}') IS NULL "
                    f'ALTER TABLE dbo.run_logs ADD {column_name} {column_type} NULL'
                ))
    except Exception as e:
        print(f'  \u26A0\ufe0f  Could not upgrade run_logs schema: {e}')

    run_log = pd.DataFrame([{
        'run_timestamp': datetime.now(),
        'frequency': 'catchup',
        'start_date': START_DATE,
        'end_date': END_DATE,
        'days_generated': (END_DATE - START_DATE).days + 1,
        'encounters_generated': int(total_encounters),
        'admissions_generated': int(total_admissions),
    }])
    try:
        run_log.to_sql('run_logs', SINGLE_ENGINE, if_exists='append', index=False)
        print(f'  \u2713 run_logs updated: {int(total_encounters):,} encounters, '
              f'{int(total_admissions):,} admissions across '
              f'{(END_DATE - START_DATE).days + 1} day(s)')
    except Exception as e:
        print(f'  \u26A0\ufe0f  Could not write run_logs: {e}')

    print('\n\u2713 Refresh complete. Proceed to Cell 12 for validation.')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 12: Validation & Final Report
# ============================================================================

print('\n[Cell 12/12] Validation & Final Report')
print('\u2500' * 60)

if not SINGLE_ENGINE:
    print('\u274c Database engine not available')
else:
    print('\n\U0001F4CA Row Counts by Table:')
    tables_to_check = [
        'hospitals', 'departments', 'patients', 'doctors', 'encounters', 'procedures',
        'diagnoses', 'medications', 'labs', 'insurance', 'billing', 'admissions',
        'date_dim', 'floors', 'rooms', 'beds', 'patient_bed_assignments',
        'hospital_department_beds', 'icd_reference', 'run_logs'
    ]
    total_rows = 0
    for table in tables_to_check:
        result = query_db(f'SELECT COUNT(*) as cnt FROM {table}')
        if result is not None:
            count = int(result.iloc[0]['cnt'])
            total_rows += count
            print(f'  {table:24s} : {count:>10,}')
        else:
            print(f'  {table:24s} : [table not found]')
    print(f'\n  {"TOTAL":24s} : {total_rows:>10,}')

    print('\n\U0001F4C5 Encounter Date Range:')
    date_range = query_db('SELECT MIN(CAST(encounter_date AS DATE)) as min_date, MAX(CAST(encounter_date AS DATE)) as max_date FROM encounters')
    if date_range is not None and not date_range.empty:
        print(f"  Min: {date_range.iloc[0]['min_date']}")
        print(f"  Max: {date_range.iloc[0]['max_date']}")

    print('\n\u23F0 Execution Summary:')
    elapsed = (datetime.now() - NOTEBOOK_START_TIME).total_seconds()
    print(f'  Start time: {NOTEBOOK_START_TIME.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  End time:   {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  Duration:   {int(elapsed)} seconds')
    print('  Status:     \u2713 Complete')

    print('\n\U0001F517 Connection Status:')
    print('  Single connection pool: Active (pool_size=1, recycle every 12h)')
    print('  This connection will be re-created fresh on the next scheduled run.')

    print('\n\u2705 Healthcare Data Generator - Complete')
    print('\nNext steps:')
    print('  1. Review the row counts and date range above')
    print('  2. Schedule this notebook to run daily in Fabric \u2014 it will always')
    print('     catch up every day between the last loaded date and today')
    print('  3. If you fall behind (e.g. schedule paused for a week), just run it')
    print('     again \u2014 it will backfill every missing day automatically')
    print('  4. To force a full history rebuild, drop the "encounters" table (or all')
    print('     tables) before running \u2014 the notebook will detect an empty database')
    print('     and regenerate from DEFAULT_HISTORY_START_DATE')
""")

nb['cells'] = cells
nb['metadata'] = {
    'kernelspec': {
        'name': 'synapse_pyspark',
        'display_name': 'Synapse PySpark',
        'language': 'Python'
    },
    'language_info': {
        'name': 'python'
    }
}

out_path = Path(__file__).resolve().parents[1] / 'notebooks' / 'healthcare_data_generator_fabric_inlined.ipynb'
nbf.write(nb, str(out_path))
print(f'Wrote {len(cells)} cells to {out_path}')
