"""
Build script: assembles the Fabric Validation Notebook
(notebooks/healthcare_data_validation.ipynb) that runs a suite of SQL data
quality checks against the Healthcare ODS database.

Run this script whenever the validation logic needs to change:
    python scripts/build_validation_notebook.py

Then deploy it with:
    python scripts/deploy_notebook.py --notebook-path notebooks/healthcare_data_validation.ipynb --notebook-name Healthcare_Data_Validation

The notebook is self-contained (no src/ imports) and uses the same
non-interactive Fabric access-token connection pattern as the main generator
notebook, so it can be run headlessly via the Jobs API or on a schedule.
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
md(r"""# Healthcare Data Generator — Validation Notebook

Runs a suite of SQL data-quality checks against the Healthcare ODS database:

1. Table inventory & row counts
2. Encounter date-range & gap check (every calendar day should have data)
3. Daily volume sanity (last 10 days)
4. Referential integrity (orphan foreign-key checks)
5. Duplicate primary-key checks
6. NULL checks on key columns
7. Reference data presence (hospitals/departments/date_dim)
8. Patient-location tables & views
9. Diagnosis families (`icd_reference`) and simulated-stay length-of-stay checks
10. Overall PASS/FAIL summary

Safe to run any time (read-only). Can be scheduled to run after each
Healthcare_Data_Generator run, or on-demand via the Fabric Jobs API.
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 1: Configuration & Non-Interactive Connection
# ============================================================================

import importlib
import subprocess
import sys


def _ensure_package(pip_name, import_name=None):
    import_name = import_name or pip_name
    try:
        importlib.import_module(import_name)
    except ImportError:
        print(f'Installing missing package: {pip_name}...')
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', pip_name], check=False)


for _pip_name, _import_name in [('pyodbc', 'pyodbc'), ('sqlalchemy', 'sqlalchemy')]:
    _ensure_package(_pip_name, _import_name)

import os

FABRIC_SERVER = os.getenv(
    'FABRIC_SERVER',
    '5mx5ymqwo74ezmng6awpg76wx4-f2smxdwfuzzenbkp2vylj5c5ca.database.fabric.microsoft.com'
)
FABRIC_DB = os.getenv('FABRIC_DB', 'Healthcare ODS-63ba7f40-a784-49f0-ae76-387233bc2616')

try:
    import notebookutils  # noqa: F401
    RUNNING_IN_FABRIC = True
except ImportError:
    RUNNING_IN_FABRIC = False


def _get_fabric_access_token():
    # Non-interactive AAD token for the Fabric-provided notebook identity.
    # 'pbi' is the audience Fabric SQL endpoints/warehouses accept.
    for audience in ('pbi', 'https://database.windows.net/'):
        try:
            import notebookutils
            return notebookutils.credentials.getToken(audience)
        except Exception:
            pass
        try:
            import mssparkutils
            return mssparkutils.credentials.getToken(audience)
        except Exception:
            pass
    return None


import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.pool import SingletonThreadPool

print('Connecting to Healthcare ODS...')

if RUNNING_IN_FABRIC:
    token = _get_fabric_access_token()
    raw_odbc_str = (
        f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;'
        f'Database={FABRIC_DB};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
    )

    def _creator():
        import struct
        token_bytes = token.encode('utf-16-le')
        token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
        return pyodbc.connect(raw_odbc_str, attrs_before={1256: token_struct})

    ENGINE = create_engine('mssql+pyodbc://', creator=_creator, pool_pre_ping=True, poolclass=SingletonThreadPool)
else:
    CONNECTION_STRING = os.getenv('CONNECTION_STRING') or os.getenv('FABRIC_CONNECTION_STRING') or (
        f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;'
        f'Database={FABRIC_DB};Authentication=ActiveDirectoryInteractive;'
        f'Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
    )
    ENGINE = create_engine(f'mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}', pool_pre_ping=True, poolclass=SingletonThreadPool)

with ENGINE.connect() as conn:
    conn.execute(text('SELECT 1'))
print('\u2713 Connected.')

CHECK_RESULTS = []  # list of (check_name, passed: bool, detail: str)


def record(check_name, passed, detail=''):
    CHECK_RESULTS.append((check_name, passed, detail))
    icon = '\u2713' if passed else '\u2717'
    print(f'  {icon} {check_name}{": " + detail if detail else ""}')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 2: Table Inventory & Row Counts
# ============================================================================
import pandas as pd

print('\n[1/8] Table inventory & row counts')
print('-' * 60)

table_counts_df = pd.read_sql('''
    SELECT t.name AS table_name, p.rows AS row_count
    FROM sys.tables t
    JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0,1)
    ORDER BY t.name
''', ENGINE)

TABLE_COUNTS = dict(zip(table_counts_df['table_name'], table_counts_df['row_count']))
print(table_counts_df.to_string(index=False))

expected_tables = [
    'patients', 'doctors', 'encounters', 'diagnoses', 'procedures', 'medications',
    'labs', 'insurance', 'billing', 'admissions', 'hospitals', 'departments',
    'date_dim', 'hospital_department_beds', 'floors', 'rooms', 'beds',
    'patient_bed_assignments'
]
missing_tables = [t for t in expected_tables if t not in TABLE_COUNTS]
record('All expected tables present', len(missing_tables) == 0, f'missing: {missing_tables}' if missing_tables else f'{len(expected_tables)} tables found')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 3: Encounter Date-Range & Gap Check
# ============================================================================

print('\n[2/8] Encounter date-range & gap check')
print('-' * 60)

date_range_df = pd.read_sql('''
    SELECT MIN(encounter_date) AS min_d, MAX(encounter_date) AS max_d,
           COUNT(DISTINCT CAST(encounter_date AS DATE)) AS distinct_days
    FROM encounters
''', ENGINE)
min_d, max_d, distinct_days = date_range_df.iloc[0]
print(f'Min date: {min_d}   Max date: {max_d}   Distinct days: {distinct_days}')

calendar_df = pd.read_sql('''
    WITH days AS (
        SELECT CAST(encounter_date AS DATE) AS d FROM encounters GROUP BY CAST(encounter_date AS DATE)
    )
    SELECT DATEDIFF(day, MIN(d), MAX(d)) + 1 AS calendar_days, COUNT(*) AS days_with_data FROM days
''', ENGINE)
calendar_days, days_with_data = calendar_df.iloc[0]
missing_days = int(calendar_days) - int(days_with_data)
print(f'Calendar days in range: {calendar_days}   Days with data: {days_with_data}   Missing: {missing_days}')

record('Zero missing calendar days', missing_days == 0, f'{missing_days} missing day(s)')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 4: Daily Volume Sanity (last 10 days)
# ============================================================================

print('\n[3/8] Daily volume sanity (last 10 days)')
print('-' * 60)

recent_df = pd.read_sql('''
    SELECT TOP 10 CAST(encounter_date AS DATE) AS d, COUNT(*) AS encounters
    FROM encounters GROUP BY CAST(encounter_date AS DATE) ORDER BY d DESC
''', ENGINE)
print(recent_df.to_string(index=False))

low_volume_days = recent_df[recent_df['encounters'] < 100]
record('Recent days have healthy volume (>=100/day)', len(low_volume_days) == 0,
       f'{len(low_volume_days)} day(s) below 100 encounters' if len(low_volume_days) else '')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 5: Referential Integrity (Orphan Checks)
# ============================================================================

print('\n[4/8] Referential integrity (orphan checks)')
print('-' * 60)

orphan_checks = [
    ('diagnoses -> encounters', 'SELECT COUNT(*) FROM diagnoses d LEFT JOIN encounters e ON d.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL'),
    ('procedures -> encounters', 'SELECT COUNT(*) FROM procedures p LEFT JOIN encounters e ON p.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL'),
    ('medications -> encounters', 'SELECT COUNT(*) FROM medications m LEFT JOIN encounters e ON m.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL'),
    ('labs -> encounters', 'SELECT COUNT(*) FROM labs l LEFT JOIN encounters e ON l.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL'),
    ('encounters -> patients', 'SELECT COUNT(*) FROM encounters e LEFT JOIN patients p ON e.patient_id = p.patient_id WHERE p.patient_id IS NULL'),
    ('billing -> encounters', 'SELECT COUNT(*) FROM billing b LEFT JOIN encounters e ON b.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL'),
    ('billing -> patients', 'SELECT COUNT(*) FROM billing b LEFT JOIN patients p ON b.patient_id = p.patient_id WHERE p.patient_id IS NULL'),
    ('insurance -> patients', 'SELECT COUNT(*) FROM insurance i LEFT JOIN patients p ON i.patient_id = p.patient_id WHERE p.patient_id IS NULL'),
    ('admissions -> encounters', 'SELECT COUNT(*) FROM admissions a LEFT JOIN encounters e ON a.encounter_id = e.encounter_id WHERE e.encounter_id IS NULL'),
]

for label, sql in orphan_checks:
    try:
        orphans = pd.read_sql(sql, ENGINE).iloc[0, 0]
        record(f'{label} (no orphans)', orphans == 0, f'{orphans} orphan(s)' if orphans else '')
    except Exception as e:
        print(f'  \u26A0\ufe0f  {label} skipped: {e}')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 6: Duplicate Primary Key Checks
# ============================================================================

print('\n[5/8] Duplicate primary key checks')
print('-' * 60)

pk_checks = [
    ('patients', 'patient_id'), ('doctors', 'provider_id'), ('encounters', 'encounter_id'),
    ('diagnoses', 'diagnosis_id'), ('procedures', 'procedure_id'), ('medications', 'medication_id'),
    ('labs', 'lab_id'), ('billing', 'billing_id'), ('insurance', 'insurance_id'), ('admissions', 'admission_id'),
]

for table, pk in pk_checks:
    if table not in TABLE_COUNTS:
        continue
    try:
        dupes = pd.read_sql(f'SELECT COUNT(*) - COUNT(DISTINCT {pk}) FROM {table}', ENGINE).iloc[0, 0]
        record(f'{table}.{pk} unique', dupes == 0, f'{dupes} duplicate(s)' if dupes else '')
    except Exception as e:
        print(f'  \u26A0\ufe0f  {table}.{pk} skipped: {e}')
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 7: NULL Checks & Reference Data
# ============================================================================

print('\n[6/8] NULL checks on key columns')
print('-' * 60)

null_checks = [
    ('patients', 'patient_id'), ('encounters', 'patient_id'),
    ('encounters', 'encounter_date'), ('encounters', 'hospital_id'),
]
for table, col in null_checks:
    if table not in TABLE_COUNTS:
        continue
    try:
        nulls = pd.read_sql(f'SELECT COUNT(*) FROM {table} WHERE {col} IS NULL', ENGINE).iloc[0, 0]
        record(f'{table}.{col} has no NULLs', nulls == 0, f'{nulls} NULL(s)' if nulls else '')
    except Exception as e:
        print(f'  \u26A0\ufe0f  {table}.{col} skipped: {e}')

print('\n[7/8] Reference data presence')
print('-' * 60)
for t in ('hospitals', 'departments', 'date_dim'):
    cnt = TABLE_COUNTS.get(t, 0)
    record(f'{t} populated', cnt > 0, f'{cnt} row(s)')
""")

# ---------------------------------------------------------------------------
# Embedded verbatim so the Fabric notebook stays self-contained while sharing
# one definition of these checks with scripts/validate_fabric_data.py.
_QUALITY_CHECKS_SOURCE = (Path(__file__).resolve().parent / 'ods_quality_checks.py').read_text(encoding='utf-8')
code(_QUALITY_CHECKS_SOURCE + r"""

# ============================================================================
# Diagnosis families & simulated stays
# ============================================================================
print('\nDiagnosis families & simulated stays')
print('-' * 60)

SKIPPED_CHECKS = []


def _fetch_rows(sql):
    return list(pd.read_sql(sql, ENGINE).itertuples(index=False, name=None))


def _fetch_table(sql):
    frame = pd.read_sql(sql, ENGINE)
    return list(frame.columns), list(frame.itertuples(index=False, name=None))


for _name, _status, _detail in run_quality_checks(_fetch_rows, set(TABLE_COUNTS)):
    if _status == 'SKIP':
        # Not deployed is reported, never counted as a pass.
        SKIPPED_CHECKS.append((_name, _detail))
        print(f'  \u2013 {_name}: SKIPPED ({_detail})')
    else:
        record(_name, _status == 'PASS', _detail)

for _name, _columns, _rows in run_quality_summaries(_fetch_table, set(TABLE_COUNTS)):
    print(f'\n  {_name}')
    print(f'    ({_rows})' if _columns is None else format_table(_columns, _rows))
""")

# ---------------------------------------------------------------------------
code(r"""# ============================================================================
# CELL 8: Views Check & Overall Summary
# ============================================================================

print('\n[8/8] Views check')
print('-' * 60)

views = ['vw_current_er_beds', 'vw_current_patient_beds', 'vw_floor_plan',
         'vw_patient_location', 'vw_floor_occupancy', 'vw_hospital_status']
for view in views:
    try:
        cnt = pd.read_sql(f'SELECT COUNT(*) FROM {view}', ENGINE).iloc[0, 0]
        record(f'VIEW {view} queryable', True, f'{cnt} row(s)')
    except Exception as e:
        record(f'VIEW {view} queryable', False, str(e))

print('\n' + '=' * 60)
print('SUMMARY')
print('=' * 60)

passed = [c for c in CHECK_RESULTS if c[1]]
failed = [c for c in CHECK_RESULTS if not c[1]]

print(f'Checks passed: {len(passed)}/{len(CHECK_RESULTS)}')
if SKIPPED_CHECKS:
    print(f'Checks skipped (not deployed, not counted as passing): {len(SKIPPED_CHECKS)}')
    for name, detail in SKIPPED_CHECKS:
        print(f'  \u2013 {name}: {detail}')
if failed:
    print('\nFAILED CHECKS:')
    for name, _, detail in failed:
        print(f'  \u2717 {name}: {detail}')
    print('\n\u274c VALIDATION FAILED')
else:
    print('\n\u2705 ALL VALIDATION CHECKS PASSED')
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

out_path = Path(__file__).resolve().parents[1] / 'notebooks' / 'healthcare_data_validation.ipynb'
nbf.write(nb, str(out_path))
print(f'Wrote {len(cells)} cells to {out_path}')
