"""
Build script: assembles the two self-contained Hospital Operations Fabric
notebooks (notebooks/Hospital_Operations_Setup.ipynb and
notebooks/Hospital_Operations_Realtime_Simulator.ipynb) the same way
scripts/build_fabric_notebook.py assembles the main generator notebook.

WHY inlined instead of `import hospital_operations`: a notebook triggered
headlessly inside Fabric (Jobs API / schedule) has no access to this git
repo's filesystem, so it cannot `import src.hospital_operations`. Both
notebooks below are 100% self-contained -- including the operations-schema
DDL, which is embedded as string constants (read from sql/hospital_operations/
at BUILD time only, not at notebook-run time).

The `src/hospital_operations/` package is kept as the readable, testable,
version-controlled source of truth for this logic (and is exercised by
tests/hospital_operations/). Edit the package + the SQL files under
sql/hospital_operations/, then re-run this script to regenerate both
notebooks:

    python scripts/build_hospital_operations_notebooks.py

Never hand-edit the generated .ipynb files.
"""
import nbformat as nbf
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = REPO_ROOT / "sql" / "hospital_operations"
NOTEBOOKS_DIR = REPO_ROOT / "notebooks"

# Same defaults used by scripts/build_fabric_notebook.py -- the operations
# tables live in the SAME Fabric SQL database as the clinical tables.
FABRIC_SERVER_DEFAULT = "5mx5ymqwo74ezmng6awpg76wx4-f2smxdwfuzzenbkp2vylj5c5ca.database.fabric.microsoft.com"
FABRIC_DB_DEFAULT = "Healthcare ODS-63ba7f40-a784-49f0-ae76-387233bc2616"


def read_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


# ============================================================================
# Shared cell bodies (identical in both notebooks)
# ============================================================================

def cell_config_and_environment(simulator_name: str) -> str:
    return r"""# ============================================================================
# CELL: Configuration & Environment Setup
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


for _pip_name, _import_name in [
    ('faker', 'faker'),
    ('pyodbc', 'pyodbc'),
    ('python-dotenv', 'dotenv'),
    ('sqlalchemy', 'sqlalchemy'),
]:
    _ensure_package(_pip_name, _import_name)

import os
import json
import random
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / '.env')
except Exception:
    pass

try:
    import notebookutils  # noqa: F401
    RUNNING_IN_FABRIC = True
except ImportError:
    RUNNING_IN_FABRIC = False

FABRIC_SERVER = os.getenv('FABRIC_SERVER', 'FABRIC_SERVER_DEFAULT_PLACEHOLDER')
FABRIC_DB = os.getenv('FABRIC_DB', 'FABRIC_DB_DEFAULT_PLACEHOLDER')

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

FABRIC_POOL_RECYCLE_SECONDS = max(3600, int(os.getenv('FABRIC_POOL_RECYCLE_SECONDS', '43200')))

# ---------------------------------------------------------------------------
# Hospital Operations parameters -- override via env vars (HOSPITAL_OPS_*) or
# by editing this cell directly. Zero for MAX_RUNTIME_MINUTES/MAX_ITERATIONS
# means unlimited (subject to STOP via ops_simulation_control or a manual
# interrupt of this cell).
# ---------------------------------------------------------------------------
SIMULATOR_NAME = 'SIMULATOR_NAME_PLACEHOLDER'
SCENARIO_NAME = os.getenv('HOSPITAL_OPS_SCENARIO', 'NORMAL_OPERATIONS')
UPDATE_INTERVAL_SECONDS = int(os.getenv('HOSPITAL_OPS_UPDATE_INTERVAL_SECONDS', '10'))
SPEED_MULTIPLIER = float(os.getenv('HOSPITAL_OPS_SPEED_MULTIPLIER', '60'))
RANDOM_SEED = int(os.getenv('HOSPITAL_OPS_RANDOM_SEED', '42'))
MAX_RUNTIME_MINUTES = int(os.getenv('HOSPITAL_OPS_MAX_RUNTIME_MINUTES', '0'))
MAX_ITERATIONS = int(os.getenv('HOSPITAL_OPS_MAX_ITERATIONS', '0'))
BATCH_SIZE = int(os.getenv('HOSPITAL_OPS_BATCH_SIZE', '10'))
SELECTED_HOSPITAL_ID = int(os.getenv('HOSPITAL_OPS_SELECTED_HOSPITAL_ID')) if os.getenv('HOSPITAL_OPS_SELECTED_HOSPITAL_ID') else None
RESET_CURRENT_STATE = os.getenv('HOSPITAL_OPS_RESET_CURRENT_STATE', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
RESUME_FROM_CHECKPOINT = os.getenv('HOSPITAL_OPS_RESUME_FROM_CHECKPOINT', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
ENABLE_PATIENT_FLOW = os.getenv('HOSPITAL_OPS_ENABLE_PATIENT_FLOW', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
ENABLE_STAFFING_EVENTS = os.getenv('HOSPITAL_OPS_ENABLE_STAFFING_EVENTS', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
ENABLE_EQUIPMENT_EVENTS = os.getenv('HOSPITAL_OPS_ENABLE_EQUIPMENT_EVENTS', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
ENABLE_ALERTS = os.getenv('HOSPITAL_OPS_ENABLE_ALERTS', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
ENABLE_SNAPSHOT_REFRESH = os.getenv('HOSPITAL_OPS_ENABLE_SNAPSHOT_REFRESH', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
LOG_LEVEL = os.getenv('HOSPITAL_OPS_LOG_LEVEL', 'INFO')
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv('HOSPITAL_OPS_HEARTBEAT_INTERVAL_SECONDS', '10'))
CHECKPOINT_INTERVAL_ITERATIONS = int(os.getenv('HOSPITAL_OPS_CHECKPOINT_INTERVAL', '10'))
MAX_CONSECUTIVE_ERRORS = int(os.getenv('HOSPITAL_OPS_MAX_CONSECUTIVE_ERRORS', '5'))

NOTEBOOK_START_TIME = datetime.now()
SINGLE_ENGINE = None  # initialized in the "Initialize Database Connection" cell

print('SYNTHETIC DEMONSTRATION DATA ONLY -- not derived from or usable for real clinical decision-making.')
print(f'Start time: {NOTEBOOK_START_TIME.strftime("%Y-%m-%d %H:%M:%S")}')
print(f'Running in Fabric: {RUNNING_IN_FABRIC}')
print(f'Scenario: {SCENARIO_NAME} | seed={RANDOM_SEED} | speed_multiplier={SPEED_MULTIPLIER}x')
""".replace("FABRIC_SERVER_DEFAULT_PLACEHOLDER", FABRIC_SERVER_DEFAULT) \
   .replace("FABRIC_DB_DEFAULT_PLACEHOLDER", FABRIC_DB_DEFAULT) \
   .replace("SIMULATOR_NAME_PLACEHOLDER", simulator_name)


CELL_CONNECTION = r"""# ============================================================================
# CELL: Initialize Database Connection + Generic SQL Helpers
# ============================================================================
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import SingletonThreadPool
import pyodbc
import contextlib


def _get_fabric_access_token():
    for audience in ('pbi', 'https://database.windows.net/'):
        try:
            import notebookutils as _nu
            token = _nu.credentials.getToken(audience)
            if token:
                return token
        except Exception:
            pass
        try:
            import mssparkutils as _msu
            token = _msu.credentials.getToken(audience)
            if token:
                return token
        except Exception:
            pass
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
    global SINGLE_ENGINE
    if not CONNECTION_STRING:
        raise RuntimeError('CONNECTION_STRING not configured. Set the env var or edit the config cell.')

    fabric_token = _get_fabric_access_token() if RUNNING_IN_FABRIC else None
    if fabric_token:
        print('Initializing SQLAlchemy engine using a non-interactive Fabric access token...')
        raw_odbc_str = (
            f'Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;'
            f'Database={FABRIC_DB};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;'
        )
        SINGLE_ENGINE = create_engine(
            'mssql+pyodbc://', creator=_pyodbc_creator_with_token(raw_odbc_str, fabric_token),
            pool_pre_ping=True, pool_recycle=FABRIC_POOL_RECYCLE_SECONDS, poolclass=SingletonThreadPool,
        )
    else:
        print('Initializing SQLAlchemy engine with a single pooled connection...')
        SINGLE_ENGINE = create_engine(
            f'mssql+pyodbc:///?odbc_connect={CONNECTION_STRING}',
            pool_pre_ping=True, pool_recycle=FABRIC_POOL_RECYCLE_SECONDS, poolclass=SingletonThreadPool,
        )

    with SINGLE_ENGINE.connect() as test_conn:
        test_conn.execute(text('SELECT 1'))
    print('  \u2713 Connected to database')

    inspector = inspect(SINGLE_ENGINE)
    tables = inspector.get_table_names()
    print(f'  \u2713 Found {len(tables)} existing tables ({sum(1 for t in tables if t.startswith("ops_"))} already ops_*)')
    return SINGLE_ENGINE


def query_db(sql, engine=None, params=None):
    '''Read-only query helper; returns an empty DataFrame (not an exception) on failure.'''
    engine = engine or SINGLE_ENGINE
    try:
        return pd.read_sql(text(sql), engine, params=params or {})
    except Exception as e:
        print(f'[query_db] error: {e}')
        return pd.DataFrame()


def execute(sql, engine=None, params=None):
    engine = engine or SINGLE_ENGINE
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def table_exists(table, engine=None):
    engine = engine or SINGLE_ENGINE
    df = query_db("SELECT 1 AS present FROM sys.tables WHERE name = :t AND schema_id = SCHEMA_ID('dbo')", engine, {'t': table})
    return not df.empty


def get_next_id(table, id_col, engine=None):
    engine = engine or SINGLE_ENGINE
    df = query_db(f'SELECT MAX({id_col}) AS max_id FROM dbo.{table}', engine)
    if df.empty or pd.isna(df.iloc[0]['max_id']):
        return 1
    return int(df.iloc[0]['max_id']) + 1


@contextlib.contextmanager
def transaction(engine=None):
    engine = engine or SINGLE_ENGINE
    with engine.begin() as conn:
        yield conn


def upsert_row(conn, table, key_cols, row):
    '''Upsert a single row into a current-state table via T-SQL MERGE.'''
    all_cols = list(row.keys())
    update_cols = [c for c in all_cols if c not in key_cols]
    src_select = ', '.join(f':{c} AS {c}' for c in all_cols)
    on_clause = ' AND '.join(f'tgt.{c} = src.{c}' for c in key_cols)
    update_clause = ', '.join(f'{c} = src.{c}' for c in update_cols) if update_cols else None
    insert_cols = ', '.join(all_cols)
    insert_vals = ', '.join(f'src.{c}' for c in all_cols)
    match_clause = ('WHEN MATCHED THEN UPDATE SET ' + update_clause) if update_clause else ''
    merge_sql = f'''
    MERGE INTO dbo.{table} AS tgt
    USING (SELECT {src_select}) AS src
    ON {on_clause}
    {match_clause}
    WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals});
    '''
    conn.execute(text(merge_sql), row)


def insert_rows(conn, table, rows):
    count = 0
    for row in rows:
        cols = ', '.join(row.keys())
        vals = ', '.join(f':{c}' for c in row.keys())
        conn.execute(text(f'INSERT INTO dbo.{table} ({cols}) VALUES ({vals})'), row)
        count += 1
    return count


init_connection()
"""

CELL_MODELS = r"""# ============================================================================
# CELL: Shared constants (staffing roles, equipment plan, state machines, scenarios)
# ============================================================================
from dataclasses import dataclass, field
from typing import Optional

STAFF_ROLES = [
    ('CN', 'Charge Nurse'), ('RN', 'Registered Nurse'), ('PCT', 'Patient Care Technician'),
    ('NP', 'Nurse Practitioner'), ('RT', 'Respiratory Therapist'), ('HOSP', 'Hospitalist'),
    ('ATT', 'Attending Physician'), ('CM', 'Case Manager'), ('TRANS', 'Transporter'),
    ('EVS', 'Environmental Services'), ('BME', 'Biomedical Engineer'),
]
PHYSICIAN_ROLE_CODES = {'HOSP', 'ATT'}

SHIFT_SEED = [
    ('DAY', 'Day', '07:00:00', '15:00:00', False),
    ('EVE', 'Evening', '15:00:00', '23:00:00', False),
    ('NOC', 'Night', '23:00:00', '07:00:00', True),
]

EQUIPMENT_TYPES = [
    'Ventilator', 'Infusion Pump', 'Patient Monitor', 'Portable X-Ray', 'Ultrasound',
    'Dialysis Machine', 'MRI', 'CT Scanner', 'Defibrillator', 'ECMO',
]
CRITICAL_EQUIPMENT_TYPES = {'Ventilator', 'ECMO', 'Defibrillator', 'Dialysis Machine'}

EQUIPMENT_BY_UNIT_TYPE = {
    'Critical Care': [
        ('Ventilator', ('per_bed', 0.6)), ('Patient Monitor', ('per_bed', 1.0)),
        ('Infusion Pump', ('per_bed', 2.0)), ('Defibrillator', 2), ('ECMO', 1),
        ('Dialysis Machine', 1),
    ],
    'Emergency': [
        ('Patient Monitor', ('per_bed', 0.75)), ('Defibrillator', 3),
        ('Portable X-Ray', 2), ('Ultrasound', 1),
    ],
    'Medical/Surgical': [('Patient Monitor', ('per_bed', 0.4)), ('Infusion Pump', ('per_bed', 1.0))],
    'Specialty': [('Infusion Pump', ('per_bed', 0.8)), ('Patient Monitor', ('per_bed', 0.3))],
    'Recovery': [('Patient Monitor', ('per_bed', 0.8)), ('Infusion Pump', ('per_bed', 0.6))],
    'Rehabilitation': [('Patient Monitor', ('per_bed', 0.2))],
    'Observation': [('Patient Monitor', ('per_bed', 0.5)), ('Infusion Pump', ('per_bed', 0.5))],
    'Diagnostic': [('MRI', 1), ('CT Scanner', 1), ('Ultrasound', 2), ('Portable X-Ray', 1)],
    'Medical': [('Infusion Pump', ('per_bed', 0.8)), ('Patient Monitor', ('per_bed', 0.3))],
    'default': [('Patient Monitor', ('per_bed', 0.3))],
}

ROOM_OPERATIONAL_STATUSES = ['Available', 'Occupied', 'Reserved', 'Cleaning', 'Maintenance', 'Closed', 'Isolation']
BED_OPERATIONAL_STATUSES = ['Available', 'Reserved', 'Occupied', 'Discharge Pending', 'Cleaning', 'Maintenance', 'Blocked']
MOVEMENT_TYPES = [
    'Admission', 'Internal Transfer', 'ICU Transfer', 'Step-Down Transfer',
    'Procedure Transfer', 'Discharge', 'Environmental Relocation', 'Maintenance Relocation',
]
ALERT_CATEGORIES = ['Capacity', 'Staffing', 'Patient Flow', 'Equipment', 'Environmental', 'Safety', 'Clinical Operations']
ALERT_SEVERITIES = ['Info', 'Warning', 'Critical']
SCENARIOS = [
    'NORMAL_OPERATIONS', 'FRIDAY_ED_SURGE', 'WINTER_RESPIRATORY_SURGE',
    'ICU_CAPACITY_CRISIS', 'STAFFING_SHORTAGE', 'EQUIPMENT_FAILURE', 'DISCHARGE_BOTTLENECK',
]


@dataclass
class ScenarioProfile:
    name: str
    admission_rate_multiplier: float = 1.0
    ed_boarding_multiplier: float = 1.0
    icu_pressure_multiplier: float = 1.0
    equipment_failure_rate: float = 0.01
    staffing_absence_rate: float = 0.05
    discharge_delay_multiplier: float = 1.0
    icu_occupancy_alert_threshold: float = 0.90
    ed_occupancy_alert_threshold: float = 0.90
    rn_coverage_alert_threshold: float = 0.85


SCENARIO_PROFILES = {
    'NORMAL_OPERATIONS': ScenarioProfile('NORMAL_OPERATIONS'),
    'FRIDAY_ED_SURGE': ScenarioProfile('FRIDAY_ED_SURGE', admission_rate_multiplier=1.4, ed_boarding_multiplier=2.0, ed_occupancy_alert_threshold=0.85),
    'WINTER_RESPIRATORY_SURGE': ScenarioProfile('WINTER_RESPIRATORY_SURGE', admission_rate_multiplier=1.3, icu_pressure_multiplier=1.5, equipment_failure_rate=0.02),
    'ICU_CAPACITY_CRISIS': ScenarioProfile('ICU_CAPACITY_CRISIS', icu_pressure_multiplier=2.2, icu_occupancy_alert_threshold=0.80, discharge_delay_multiplier=1.5),
    'STAFFING_SHORTAGE': ScenarioProfile('STAFFING_SHORTAGE', staffing_absence_rate=0.25, rn_coverage_alert_threshold=0.95),
    'EQUIPMENT_FAILURE': ScenarioProfile('EQUIPMENT_FAILURE', equipment_failure_rate=0.15),
    'DISCHARGE_BOTTLENECK': ScenarioProfile('DISCHARGE_BOTTLENECK', discharge_delay_multiplier=2.5, ed_boarding_multiplier=1.5),
}


def get_scenario_profile(name):
    return SCENARIO_PROFILES.get((name or 'NORMAL_OPERATIONS').upper(), SCENARIO_PROFILES['NORMAL_OPERATIONS'])


def heartbeat_line(**kwargs):
    parts = [f'{k}={v}' for k, v in kwargs.items()]
    return 'HEARTBEAT | ' + ' | '.join(parts)
"""


def cell_schema_deployment() -> str:
    sql_texts = {
        "SQL_001": read_sql("001_create_operations_schema.sql"),
        "SQL_002": read_sql("002_create_reference_tables.sql"),
        "SQL_003": read_sql("003_create_current_state_tables.sql"),
        "SQL_004": read_sql("004_create_event_tables.sql"),
        "SQL_005": read_sql("005_create_indexes.sql"),
        "SQL_006": read_sql("006_create_snapshot_views.sql"),
        "SQL_008_DROP": read_sql("008_drop_operations_objects.sql"),
    }
    assignments = "\n".join(f"{name} = {sql!r}\n" for name, sql in sql_texts.items())
    body = r"""
# ============================================================================
# CELL: Operations Schema DDL + Idempotent Deployment
# The DDL below is embedded verbatim from sql/hospital_operations/*.sql at
# build time (see scripts/build_hospital_operations_notebooks.py) so this
# notebook needs no repo filesystem access to deploy/upgrade the schema.
# Every statement is idempotent (IF NOT EXISTS / CREATE OR ALTER).
# ============================================================================
import re


def _split_batches(sql_text):
    batches = re.split(r'^\s*GO\s*$', sql_text, flags=re.IGNORECASE | re.MULTILINE)
    return [b.strip() for b in batches if b.strip()]


def _run_sql_script(sql_text, engine=None, verbose=True):
    engine = engine or SINGLE_ENGINE
    batches = _split_batches(sql_text)
    with engine.begin() as conn:
        for batch in batches:
            conn.execute(text(batch))
    if verbose:
        print(f'  \u2713 {len(batches)} batch(es) executed')
    return len(batches)


def deploy_schema(engine=None, verbose=True):
    engine = engine or SINGLE_ENGINE
    results = {}
    for name, sql_text in [('001', SQL_001), ('002', SQL_002), ('003', SQL_003), ('004', SQL_004), ('005', SQL_005), ('006', SQL_006)]:
        if verbose:
            print(f'Deploying {name}...')
        results[name] = _run_sql_script(sql_text, engine, verbose)
    return results


def drop_schema(engine=None, verbose=True):
    return _run_sql_script(SQL_008_DROP, engine or SINGLE_ENGINE, verbose)


def list_ops_tables(engine=None):
    df = query_db("SELECT name FROM sys.tables WHERE name LIKE 'ops[_]%' ORDER BY name", engine or SINGLE_ENGINE)
    return df['name'].tolist() if not df.empty else []


def list_ops_views(engine=None):
    df = query_db("SELECT name FROM sys.views WHERE name LIKE 'vw[_]ops[_]%' ORDER BY name", engine or SINGLE_ENGINE)
    return df['name'].tolist() if not df.empty else []
"""
    return assignments + body


CELL_HIERARCHY = r"""# ============================================================================
# CELL: Hierarchy Generation (building -> unit -> room attribute extension)
# NEW entities: ops_building, ops_unit. `rooms`/`beds` are REUSED, never duplicated.
# ============================================================================
BUILDING_NAME = 'Main Campus'
BUILDING_TYPE = 'Acute Care'
_LAT_RANGE = (30.0, 45.0)
_LON_RANGE = (-115.0, -75.0)


def generate_buildings(engine=None, seed=None):
    engine = engine or SINGLE_ENGINE
    hospitals = query_db('SELECT hospital_id, name FROM dbo.hospitals', engine)
    existing = query_db('SELECT hospital_id FROM dbo.ops_building', engine)
    existing_ids = set(existing['hospital_id'].tolist()) if not existing.empty else set()
    missing = hospitals[~hospitals['hospital_id'].isin(existing_ids)]
    if not missing.empty:
        next_id = get_next_id('ops_building', 'building_id', engine)
        rng = random.Random(seed)
        with transaction(engine) as conn:
            for _, h in missing.iterrows():
                lat = round(rng.uniform(*_LAT_RANGE), 6)
                lon = round(rng.uniform(*_LON_RANGE), 6)
                upsert_row(conn, 'ops_building', ['building_id'], {
                    'building_id': next_id, 'hospital_id': int(h['hospital_id']),
                    'building_code': f"H{h['hospital_id']}-B1", 'building_name': BUILDING_NAME,
                    'building_type': BUILDING_TYPE, 'campus_label': f"{h['name']} Main Campus",
                    'latitude': lat, 'longitude': lon, 'floor_count': 0, 'active_flag': True,
                    'created_datetime': pd.Timestamp.utcnow().tz_localize(None),
                    'updated_datetime': pd.Timestamp.utcnow().tz_localize(None),
                })
                next_id += 1
    return query_db('SELECT * FROM dbo.ops_building', engine)


def _match_department_id(departments, hospital_id, floor_department):
    if departments.empty or not floor_department:
        return None
    hosp_deps = departments[departments['hospital_id'] == hospital_id]
    if hosp_deps.empty:
        return None
    floor_dep_lower = str(floor_department).lower()
    for _, dep in hosp_deps.iterrows():
        if str(dep['name']).lower() in floor_dep_lower or floor_dep_lower in str(dep['name']).lower():
            return int(dep['department_id'])
    return None


def generate_units(engine=None):
    engine = engine or SINGLE_ENGINE
    floors = query_db('SELECT hospital_id, floor_number, department, bed_type, capacity FROM dbo.floors', engine)
    if floors.empty:
        raise RuntimeError('No rows found in `floors` -- run the Healthcare Data Generator notebook first.')
    departments = query_db('SELECT department_id, hospital_id, name FROM dbo.departments', engine)
    buildings = query_db('SELECT building_id, hospital_id FROM dbo.ops_building', engine)
    existing_units = query_db('SELECT hospital_id, source_floor_number FROM dbo.ops_unit', engine)
    existing_keys = set(zip(existing_units['hospital_id'], existing_units['source_floor_number'])) if not existing_units.empty else set()
    building_by_hospital = dict(zip(buildings['hospital_id'], buildings['building_id'])) if not buildings.empty else {}

    to_create = [f for _, f in floors.iterrows() if (int(f['hospital_id']), int(f['floor_number'])) not in existing_keys]
    if to_create:
        next_id = get_next_id('ops_unit', 'unit_id', engine)
        with transaction(engine) as conn:
            for f in to_create:
                hospital_id = int(f['hospital_id'])
                floor_number = int(f['floor_number'])
                dept_id = _match_department_id(departments, hospital_id, f['department'])
                capacity = int(f['capacity']) if pd.notna(f['capacity']) else 0
                unit_type = str(f['bed_type']) if pd.notna(f['bed_type']) else 'Medical/Surgical'
                upsert_row(conn, 'ops_unit', ['unit_id'], {
                    'unit_id': next_id, 'hospital_id': hospital_id, 'building_id': building_by_hospital.get(hospital_id, 0),
                    'source_floor_number': floor_number,
                    'source_department': str(f['department']) if pd.notna(f['department']) else None,
                    'department_id': dept_id, 'unit_code': f'H{hospital_id}-F{floor_number}',
                    'unit_name': str(f['department']) if pd.notna(f['department']) else f'Floor {floor_number}',
                    'unit_type': unit_type, 'clinical_specialty': str(f['department']) if pd.notna(f['department']) else None,
                    'licensed_bed_count': capacity, 'staffed_bed_count': capacity,
                    'nurse_ratio_target': 2.0 if unit_type == 'Critical Care' else (3.0 if unit_type == 'Emergency' else 4.0),
                    'active_flag': True, 'created_datetime': pd.Timestamp.utcnow().tz_localize(None),
                    'updated_datetime': pd.Timestamp.utcnow().tz_localize(None),
                })
                next_id += 1

    with transaction(engine) as conn:
        counts = query_db('SELECT hospital_id, COUNT(DISTINCT source_floor_number) AS n FROM dbo.ops_unit GROUP BY hospital_id', conn)
        for _, row in counts.iterrows():
            conn.execute(text('UPDATE dbo.ops_building SET floor_count = :n, updated_datetime = SYSUTCDATETIME() WHERE hospital_id = :h'),
                         {'n': int(row['n']), 'h': int(row['hospital_id'])})
    return query_db('SELECT * FROM dbo.ops_unit', engine)


_ISOLATION_PRONE_TYPES = {'Critical Care', 'Emergency'}


def generate_room_attributes(engine=None, seed=None):
    engine = engine or SINGLE_ENGINE
    rooms = query_db('SELECT room_id, hospital_id, floor_number, room_number, bed_count, room_type FROM dbo.rooms', engine)
    if rooms.empty:
        raise RuntimeError('No rows found in `rooms` -- run the Healthcare Data Generator notebook first.')
    units = query_db('SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit', engine)
    existing = query_db('SELECT room_id FROM dbo.ops_room_attribute', engine)
    existing_ids = set(existing['room_id'].tolist()) if not existing.empty else set()
    unit_lookup = {(int(u['hospital_id']), int(u['source_floor_number'])): (int(u['unit_id']), u['unit_type']) for _, u in units.iterrows()}

    to_create = rooms[~rooms['room_id'].isin(existing_ids)]
    if not to_create.empty:
        rng = random.Random(seed)
        cols_per_row = 8
        cell_size = 4.0
        with transaction(engine) as conn:
            for _, r in to_create.iterrows():
                key = (int(r['hospital_id']), int(r['floor_number']))
                unit_id, unit_type = unit_lookup.get(key, (0, 'Medical/Surgical'))
                room_number = int(r['room_number'])
                floor_x = ((room_number - 1) % cols_per_row) * cell_size
                floor_y = ((room_number - 1) // cols_per_row) * cell_size
                isolation_prob = 0.30 if unit_type in _ISOLATION_PRONE_TYPES else 0.05
                isolation = rng.random() < isolation_prob
                neg_pressure = isolation and rng.random() < 0.5
                telemetry = unit_type in {'Critical Care', 'Medical/Surgical', 'Emergency'} and rng.random() < 0.7
                upsert_row(conn, 'ops_room_attribute', ['room_id'], {
                    'room_id': int(r['room_id']), 'unit_id': unit_id, 'room_name': f'Room {room_number}',
                    'isolation_capable_flag': isolation, 'negative_pressure_flag': neg_pressure,
                    'telemetry_capable_flag': telemetry, 'private_room_flag': str(r['room_type']) == 'Single',
                    'floor_x': floor_x, 'floor_y': floor_y, 'width': cell_size - 0.5, 'height': cell_size - 0.5,
                    'active_flag': True, 'created_datetime': pd.Timestamp.utcnow().tz_localize(None),
                    'updated_datetime': pd.Timestamp.utcnow().tz_localize(None),
                })
    return query_db('SELECT * FROM dbo.ops_room_attribute', engine)


def generate_hierarchy(engine=None, seed=None):
    buildings = generate_buildings(engine, seed=seed)
    units = generate_units(engine)
    rooms = generate_room_attributes(engine, seed=seed)
    return {'buildings': len(buildings), 'units': len(units), 'room_attributes': len(rooms)}
"""

CELL_STAFFING = r"""# ============================================================================
# CELL: Staffing Generation + Staffing-State Computation
# Physician roles (Hospitalist/Attending) reuse a real doctors.provider_id;
# all other roles are fully synthetic (Faker).
# ============================================================================
from faker import Faker

_NON_PHYSICIAN_ROLE_RATIOS = [('RN', 0.25), ('PCT', 0.15)]


def generate_shifts(engine=None):
    engine = engine or SINGLE_ENGINE
    existing = query_db('SELECT shift_code FROM dbo.ops_shift', engine)
    existing_codes = set(existing['shift_code'].tolist()) if not existing.empty else set()
    to_create = [s for s in SHIFT_SEED if s[0] not in existing_codes]
    if to_create:
        next_id = get_next_id('ops_shift', 'shift_id', engine)
        with transaction(engine) as conn:
            for code, name, start, end, crosses in to_create:
                upsert_row(conn, 'ops_shift', ['shift_id'], {
                    'shift_id': next_id, 'shift_code': code, 'shift_name': name,
                    'start_time': start, 'end_time': end, 'crosses_midnight_flag': crosses,
                })
                next_id += 1
    return query_db('SELECT * FROM dbo.ops_shift', engine)


def _insert_staff(conn, next_id, hospital_id, unit_id, role_code, fake, existing_provider_id=None, display_name=None):
    role_name = dict(STAFF_ROLES)[role_code]
    upsert_row(conn, 'ops_staff', ['staff_id'], {
        'staff_id': next_id, 'existing_provider_id': existing_provider_id,
        'synthetic_staff_number': f'STF-{next_id:06d}', 'display_name': display_name or fake.name(),
        'role_code': role_code, 'role_name': role_name,
        'credential': 'MD' if role_code in PHYSICIAN_ROLE_CODES else ('RN' if role_code in ('CN', 'RN') else None),
        'primary_hospital_id': hospital_id, 'primary_unit_id': unit_id, 'active_flag': True,
        'created_datetime': pd.Timestamp.utcnow().tz_localize(None), 'updated_datetime': pd.Timestamp.utcnow().tz_localize(None),
    })
    return next_id + 1


def generate_staff(engine=None, seed=None):
    engine = engine or SINGLE_ENGINE
    units = query_db('SELECT unit_id, hospital_id, unit_type, staffed_bed_count FROM dbo.ops_unit', engine)
    if units.empty:
        raise RuntimeError('No ops_unit rows found -- run generate_hierarchy() first.')
    doctors = query_db('SELECT provider_id, hospital_id, first_name, last_name FROM dbo.doctors', engine)
    existing = query_db('SELECT DISTINCT primary_unit_id FROM dbo.ops_staff WHERE primary_unit_id IS NOT NULL', engine)
    staffed_unit_ids = set(existing['primary_unit_id'].tolist()) if not existing.empty else set()

    fake = Faker()
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    to_staff = units[~units['unit_id'].isin(staffed_unit_ids)]
    if not to_staff.empty:
        next_id = get_next_id('ops_staff', 'staff_id', engine)
        with transaction(engine) as conn:
            for _, u in to_staff.iterrows():
                unit_id = int(u['unit_id'])
                hospital_id = int(u['hospital_id'])
                bed_count = max(1, int(u['staffed_bed_count']) or 1)
                next_id = _insert_staff(conn, next_id, hospital_id, unit_id, 'CN', fake, existing_provider_id=None)
                for role_code, ratio in _NON_PHYSICIAN_ROLE_RATIOS:
                    n = max(1, round(bed_count * ratio))
                    for _ in range(n):
                        next_id = _insert_staff(conn, next_id, hospital_id, unit_id, role_code, fake, existing_provider_id=None)
                hosp_docs = doctors[doctors['hospital_id'] == hospital_id]
                if not hosp_docs.empty:
                    sample = hosp_docs.sample(n=min(2, len(hosp_docs)), random_state=seed)
                    for i, (_, doc) in enumerate(sample.iterrows()):
                        role_code = 'HOSP' if i == 0 else 'ATT'
                        next_id = _insert_staff(conn, next_id, hospital_id, unit_id, role_code, fake,
                                                 existing_provider_id=int(doc['provider_id']),
                                                 display_name=f"{doc['first_name']} {doc['last_name']}")
    return query_db('SELECT * FROM dbo.ops_staff', engine)


def _current_shift(shifts, as_of):
    if shifts.empty:
        return None
    hour = as_of.hour
    for _, s in shifts.iterrows():
        start_h = int(str(s['start_time']).split(':')[0])
        end_h = int(str(s['end_time']).split(':')[0])
        in_shift = (hour >= start_h or hour < end_h) if s['crosses_midnight_flag'] else (start_h <= hour < end_h)
        if in_shift:
            shift_start = as_of.normalize() + pd.Timedelta(hours=start_h)
            if s['crosses_midnight_flag'] and hour < end_h:
                shift_start -= pd.Timedelta(days=1)
            return int(s['shift_id']), shift_start, None
    first = shifts.iloc[0]
    return int(first['shift_id']), as_of.normalize(), None


def generate_staff_assignments(engine=None, as_of=None, run_id=None):
    engine = engine or SINGLE_ENGINE
    as_of = as_of or pd.Timestamp.utcnow().tz_localize(None)
    staff = query_db("SELECT staff_id, primary_hospital_id, primary_unit_id, role_name FROM dbo.ops_staff WHERE active_flag = 1", engine)
    shifts = query_db('SELECT shift_id, start_time, end_time, crosses_midnight_flag FROM dbo.ops_shift', engine)
    open_assignments = query_db(
        "SELECT DISTINCT staff_id FROM dbo.ops_staff_assignment WHERE status = 'Active' AND assignment_end_datetime IS NULL", engine)
    already_assigned = set(open_assignments['staff_id'].tolist()) if not open_assignments.empty else set()
    current_shift = _current_shift(shifts, as_of)
    to_assign = staff[~staff['staff_id'].isin(already_assigned)]
    if not to_assign.empty and current_shift is not None:
        next_id = get_next_id('ops_staff_assignment', 'staff_assignment_id', engine)
        shift_id, shift_start, shift_end = current_shift
        with transaction(engine) as conn:
            for _, s in to_assign.iterrows():
                upsert_row(conn, 'ops_staff_assignment', ['staff_assignment_id'], {
                    'staff_assignment_id': next_id, 'staff_id': int(s['staff_id']), 'hospital_id': int(s['primary_hospital_id']),
                    'unit_id': int(s['primary_unit_id']) if pd.notna(s['primary_unit_id']) else 0,
                    'room_id': None, 'bed_id': None, 'encounter_id': None, 'shift_id': shift_id,
                    'assignment_start_datetime': shift_start, 'assignment_end_datetime': None,
                    'assignment_role': s['role_name'], 'patient_load': 0, 'status': 'Active', 'source_run_id': run_id,
                    'created_datetime': pd.Timestamp.utcnow().tz_localize(None), 'updated_datetime': pd.Timestamp.utcnow().tz_localize(None),
                })
                next_id += 1
    return query_db('SELECT * FROM dbo.ops_staff_assignment', engine)


def compute_staffing_state(engine=None, run_id=None, staffing_absence_rate=0.0):
    engine = engine or SINGLE_ENGINE
    units = query_db('SELECT unit_id, nurse_ratio_target FROM dbo.ops_unit', engine)
    if units.empty:
        return pd.DataFrame()
    now = pd.Timestamp.utcnow().tz_localize(None)
    rng = random.Random()
    with transaction(engine) as conn:
        for _, u in units.iterrows():
            unit_id = int(u['unit_id'])
            occupied = query_db(
                "SELECT COUNT(*) AS n FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
                "JOIN dbo.ops_unit uu ON uu.hospital_id = b.hospital_id AND uu.source_floor_number = b.floor_number "
                f"WHERE uu.unit_id = {unit_id} AND bs.occupancy_status = 'Occupied'", conn)
            occupied_beds = int(occupied.iloc[0]['n']) if not occupied.empty else 0
            required_rn = max(1, round(occupied_beds / max(u['nurse_ratio_target'], 0.5)))
            scheduled = query_db(
                "SELECT s.role_code, COUNT(*) AS n FROM dbo.ops_staff_assignment sa JOIN dbo.ops_staff s ON sa.staff_id = s.staff_id "
                f"WHERE sa.unit_id = {unit_id} AND sa.status = 'Active' GROUP BY s.role_code", conn)
            scheduled_rn = int(scheduled.loc[scheduled['role_code'].isin(['RN', 'CN']), 'n'].sum()) if not scheduled.empty else 0
            scheduled_pct = int(scheduled.loc[scheduled['role_code'] == 'PCT', 'n'].sum()) if not scheduled.empty else 0
            present_rn = scheduled_rn
            if staffing_absence_rate > 0:
                absences = sum(1 for _ in range(scheduled_rn) if rng.random() < staffing_absence_rate)
                present_rn = max(0, scheduled_rn - absences)
            present_pct = scheduled_pct
            charge = query_db(
                "SELECT TOP 1 sa.staff_id FROM dbo.ops_staff_assignment sa JOIN dbo.ops_staff s ON sa.staff_id = s.staff_id "
                f"WHERE sa.unit_id = {unit_id} AND sa.status = 'Active' AND s.role_code = 'CN'", conn)
            charge_id = int(charge.iloc[0]['staff_id']) if not charge.empty else None
            open_shift = max(0, required_rn - present_rn)
            coverage_pct = round(100.0 * present_rn / required_rn, 1) if required_rn > 0 else 100.0
            status = 'Critical' if coverage_pct < 70 else ('Watch' if coverage_pct < 90 else 'Normal')
            upsert_row(conn, 'ops_staffing_state', ['unit_id'], {
                'unit_id': unit_id, 'snapshot_datetime': now, 'scheduled_rn_count': scheduled_rn,
                'present_rn_count': present_rn, 'required_rn_count': required_rn, 'scheduled_pct_count': scheduled_pct,
                'present_pct_count': present_pct, 'open_shift_count': open_shift, 'charge_nurse_staff_id': charge_id,
                'staffing_coverage_pct': coverage_pct, 'staffing_status': status, 'simulation_run_id': run_id,
            })
    return query_db('SELECT * FROM dbo.ops_staffing_state', engine)
"""

CELL_EQUIPMENT_GENERATOR = r"""# ============================================================================
# CELL: Equipment Inventory Generation + Initial Equipment State
# ============================================================================
_MANUFACTURERS = ['Contoso Med', 'Fabrikam Health', 'Northwind Devices', 'AdventureWorks Medical']


def _resolve_count(count_expr, licensed_beds):
    if isinstance(count_expr, tuple) and count_expr[0] == 'per_bed':
        return max(1, int(-(-licensed_beds * count_expr[1] // 1)))
    return int(count_expr)


def generate_equipment(engine=None, seed=None):
    engine = engine or SINGLE_ENGINE
    units = query_db('SELECT unit_id, hospital_id, building_id, source_floor_number, unit_type, licensed_bed_count FROM dbo.ops_unit', engine)
    if units.empty:
        raise RuntimeError('No ops_unit rows found -- run generate_hierarchy() first.')
    existing = query_db('SELECT DISTINCT unit_id FROM dbo.ops_equipment', engine)
    equipped_units = set(existing['unit_id'].tolist()) if not existing.empty else set()
    fake = Faker()
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    rng = random.Random(seed)

    to_equip = units[~units['unit_id'].isin(equipped_units)]
    if not to_equip.empty:
        next_id = get_next_id('ops_equipment', 'equipment_id', engine)
        with transaction(engine) as conn:
            for _, u in to_equip.iterrows():
                unit_type = u['unit_type'] if pd.notna(u['unit_type']) else 'default'
                plan = EQUIPMENT_BY_UNIT_TYPE.get(unit_type, EQUIPMENT_BY_UNIT_TYPE['default'])
                for equipment_type, count_expr in plan:
                    count = _resolve_count(count_expr, int(u['licensed_bed_count']) or 1)
                    for _ in range(count):
                        criticality = 'Critical' if equipment_type in CRITICAL_EQUIPMENT_TYPES else 'Standard'
                        upsert_row(conn, 'ops_equipment', ['equipment_id'], {
                            'equipment_id': next_id, 'hospital_id': int(u['hospital_id']), 'building_id': int(u['building_id']),
                            'floor_number': int(u['source_floor_number']), 'unit_id': int(u['unit_id']), 'room_id': None,
                            'equipment_type': equipment_type, 'manufacturer': rng.choice(_MANUFACTURERS),
                            'model': f"{equipment_type.split()[0][:3].upper()}-{rng.randint(100, 999)}",
                            'synthetic_serial_number': f'SN-{next_id:07d}', 'criticality': criticality,
                            'installation_date': (pd.Timestamp.utcnow() - pd.Timedelta(days=rng.randint(30, 2000))).date(),
                            'maintenance_interval_days': 90 if criticality == 'Critical' else 180, 'active_flag': True,
                            'created_datetime': pd.Timestamp.utcnow().tz_localize(None), 'updated_datetime': pd.Timestamp.utcnow().tz_localize(None),
                        })
                        next_id += 1
    return query_db('SELECT * FROM dbo.ops_equipment', engine)


def initialize_equipment_state(engine=None, run_id=None):
    engine = engine or SINGLE_ENGINE
    equipment = query_db('SELECT equipment_id, maintenance_interval_days FROM dbo.ops_equipment', engine)
    existing = query_db('SELECT equipment_id FROM dbo.ops_equipment_state', engine)
    existing_ids = set(existing['equipment_id'].tolist()) if not existing.empty else set()
    to_init = equipment[~equipment['equipment_id'].isin(existing_ids)]
    now = pd.Timestamp.utcnow().tz_localize(None)
    if not to_init.empty:
        with transaction(engine) as conn:
            for _, eq in to_init.iterrows():
                upsert_row(conn, 'ops_equipment_state', ['equipment_id'], {
                    'equipment_id': int(eq['equipment_id']), 'status': 'Available', 'availability_status': 'Available',
                    'utilization_status': 'Idle', 'battery_pct': 100.0, 'temperature': None, 'pressure': None, 'error_code': None,
                    'maintenance_due_date': (now + pd.Timedelta(days=int(eq['maintenance_interval_days']))).date(),
                    'last_seen_datetime': now, 'updated_datetime': now, 'simulation_run_id': run_id,
                })
    return query_db('SELECT * FROM dbo.ops_equipment_state', engine)
"""

CELL_ROOM_BED_STATE = r"""# ============================================================================
# CELL: Room/Bed Operational-State Initialization + Iteration Helpers
# Current-state tables (ops_room_state, ops_bed_state) are upserted, never
# truncated. Initial state is derived from `patient_bed_assignments`.
# ============================================================================

def initialize_bed_state(engine=None, run_id=None):
    engine = engine or SINGLE_ENGINE
    beds = query_db('SELECT bed_id, hospital_id FROM dbo.beds', engine)
    existing = query_db('SELECT bed_id FROM dbo.ops_bed_state', engine)
    existing_ids = set(existing['bed_id'].tolist()) if not existing.empty else set()
    open_assignments = query_db(
        'SELECT bed_id, admission_id, patient_id, assigned_datetime FROM dbo.patient_bed_assignments WHERE discharged_datetime IS NULL', engine)
    open_by_bed = {int(r['bed_id']): r for _, r in open_assignments.iterrows()} if not open_assignments.empty else {}
    admissions = query_db('SELECT admission_id, encounter_id FROM dbo.admissions', engine)
    encounter_by_admission = dict(zip(admissions['admission_id'], admissions['encounter_id'])) if not admissions.empty else {}

    to_init = beds[~beds['bed_id'].isin(existing_ids)]
    now = pd.Timestamp.utcnow().tz_localize(None)
    if not to_init.empty:
        with transaction(engine) as conn:
            for _, b in to_init.iterrows():
                bed_id = int(b['bed_id'])
                occ = open_by_bed.get(bed_id)
                if occ is not None:
                    admission_id = int(occ['admission_id']) if pd.notna(occ['admission_id']) else None
                    upsert_row(conn, 'ops_bed_state', ['bed_id'], {
                        'bed_id': bed_id, 'operational_status': 'Occupied', 'occupancy_status': 'Occupied',
                        'encounter_id': encounter_by_admission.get(admission_id), 'patient_id': int(occ['patient_id']),
                        'admission_id': admission_id, 'assigned_datetime': occ['assigned_datetime'],
                        'expected_release_datetime': None, 'cleaning_required_flag': False,
                        'updated_datetime': now, 'simulation_run_id': run_id,
                    })
                else:
                    upsert_row(conn, 'ops_bed_state', ['bed_id'], {
                        'bed_id': bed_id, 'operational_status': 'Available', 'occupancy_status': 'Available',
                        'encounter_id': None, 'patient_id': None, 'admission_id': None, 'assigned_datetime': None,
                        'expected_release_datetime': None, 'cleaning_required_flag': False,
                        'updated_datetime': now, 'simulation_run_id': run_id,
                    })
    return query_db('SELECT * FROM dbo.ops_bed_state', engine)


def initialize_room_state(engine=None, run_id=None):
    engine = engine or SINGLE_ENGINE
    rooms = query_db('SELECT room_id, bed_count FROM dbo.rooms', engine)
    existing = query_db('SELECT room_id FROM dbo.ops_room_state', engine)
    existing_ids = set(existing['room_id'].tolist()) if not existing.empty else set()
    to_init = rooms[~rooms['room_id'].isin(existing_ids)]
    now = pd.Timestamp.utcnow().tz_localize(None)
    if not to_init.empty:
        with transaction(engine) as conn:
            for _, r in to_init.iterrows():
                room_id = int(r['room_id'])
                occ = query_db(f"SELECT COUNT(*) AS n FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
                               f"WHERE b.room_id = {room_id} AND bs.occupancy_status = 'Occupied'", conn)
                occupied = int(occ.iloc[0]['n']) if not occ.empty else 0
                available = max(0, int(r['bed_count']) - occupied)
                upsert_row(conn, 'ops_room_state', ['room_id'], {
                    'room_id': room_id, 'operational_status': 'Occupied' if occupied > 0 else 'Available',
                    'isolation_status': 'None', 'cleaning_status': 'Clean', 'maintenance_status': 'None',
                    'current_patient_count': occupied, 'available_bed_count': available,
                    'last_cleaned_datetime': now, 'next_expected_available_datetime': None,
                    'updated_datetime': now, 'simulation_run_id': run_id,
                })
    return query_db('SELECT * FROM dbo.ops_room_state', engine)


def refresh_room_aggregates(engine=None, run_id=None):
    engine = engine or SINGLE_ENGINE
    rooms = query_db('SELECT room_id, bed_count FROM dbo.rooms', engine)
    now = pd.Timestamp.utcnow().tz_localize(None)
    with transaction(engine) as conn:
        for _, r in rooms.iterrows():
            room_id = int(r['room_id'])
            occ = query_db(f"SELECT COUNT(*) AS n FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
                           f"WHERE b.room_id = {room_id} AND bs.occupancy_status = 'Occupied'", conn)
            occupied = int(occ.iloc[0]['n']) if not occ.empty else 0
            available = max(0, int(r['bed_count']) - occupied)
            upsert_row(conn, 'ops_room_state', ['room_id'], {
                'room_id': room_id, 'operational_status': 'Occupied' if occupied > 0 else 'Available',
                'isolation_status': 'None', 'cleaning_status': 'Clean', 'maintenance_status': 'None',
                'current_patient_count': occupied, 'available_bed_count': available,
                'last_cleaned_datetime': now, 'next_expected_available_datetime': None,
                'updated_datetime': now, 'simulation_run_id': run_id,
            })


def simulate_room_cleaning_iteration(engine=None, run_id=None, rng=None):
    engine = engine or SINGLE_ENGINE
    rng = rng or random.Random()
    cleaning_rooms = query_db(
        "SELECT DISTINCT r.room_id FROM dbo.rooms r JOIN dbo.beds b ON r.room_id = b.room_id "
        "JOIN dbo.ops_bed_state bs ON b.bed_id = bs.bed_id WHERE bs.occupancy_status = 'Cleaning'", engine)
    changed = 0
    if not cleaning_rooms.empty:
        now = pd.Timestamp.utcnow().tz_localize(None)
        with transaction(engine) as conn:
            for _, r in cleaning_rooms.iterrows():
                if rng.random() < 0.4:
                    conn.execute(text(
                        "UPDATE dbo.ops_bed_state SET occupancy_status = 'Available', operational_status = 'Available', "
                        "cleaning_required_flag = 0, updated_datetime = :now, simulation_run_id = :rid "
                        "WHERE bed_id IN (SELECT bed_id FROM dbo.beds WHERE room_id = :room_id) AND occupancy_status = 'Cleaning'"
                    ), {'now': now, 'rid': run_id, 'room_id': int(r['room_id'])})
                    changed += 1
    if changed:
        refresh_room_aggregates(engine, run_id)
    return changed
"""

CELL_PATIENT_FLOW = r"""# ============================================================================
# CELL: Patient-Flow Simulation
# Never writes to clinical admissions/encounters -- "discharge" here only
# releases the OPERATIONAL bed (ops_bed_state -> Cleaning -> Available).
# ============================================================================
_MIN_DWELL_HOURS = 2.0


def _pick_target_unit(units, hospital_id, encounter_type, rng):
    hosp_units = units[units['hospital_id'] == hospital_id]
    if hosp_units.empty:
        return None
    if encounter_type == 'Emergency':
        preferred = hosp_units[hosp_units['unit_type'] == 'Emergency']
        if not preferred.empty:
            return preferred.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]
    non_critical = hosp_units[hosp_units['unit_type'] != 'Critical Care']
    pool = non_critical if not non_critical.empty else hosp_units
    return pool.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]


def _find_available_bed(engine, hospital_id, floor_number):
    df = query_db(
        "SELECT TOP 1 bs.bed_id FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
        "WHERE b.hospital_id = :h AND b.floor_number = :f AND bs.occupancy_status = 'Available' ORDER BY bs.bed_id",
        engine, {'h': hospital_id, 'f': floor_number})
    return int(df.iloc[0]['bed_id']) if not df.empty else None


def admit_patients(engine, simulated_now, run_id, batch_size, scenario, rng):
    candidates = query_db(
        "SELECT TOP (:lim) a.admission_id, a.encounter_id, a.patient_id, a.hospital_id, e.encounter_type "
        "FROM dbo.admissions a JOIN dbo.encounters e ON a.encounter_id = e.encounter_id "
        "WHERE a.discharge_datetime IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM dbo.ops_bed_state bs WHERE bs.admission_id = a.admission_id) "
        "ORDER BY a.admit_datetime DESC", engine, {'lim': batch_size})
    if candidates.empty:
        return 0
    units = query_db('SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit', engine)
    processed = 0
    bed_event_id = get_next_id('ops_bed_state_event', 'bed_state_event_id', engine)
    movement_id = get_next_id('ops_patient_movement', 'movement_id', engine)
    with transaction(engine) as conn:
        for _, cand in candidates.iterrows():
            unit = _pick_target_unit(units, int(cand['hospital_id']), cand['encounter_type'], rng)
            if unit is None:
                continue
            bed_id = _find_available_bed(conn, int(cand['hospital_id']), int(unit['source_floor_number']))
            if bed_id is None:
                continue
            upsert_row(conn, 'ops_bed_state', ['bed_id'], {
                'bed_id': bed_id, 'operational_status': 'Occupied', 'occupancy_status': 'Occupied',
                'encounter_id': int(cand['encounter_id']), 'patient_id': int(cand['patient_id']),
                'admission_id': int(cand['admission_id']), 'assigned_datetime': simulated_now,
                'expected_release_datetime': None, 'cleaning_required_flag': False,
                'updated_datetime': simulated_now, 'simulation_run_id': run_id,
            })
            insert_rows(conn, 'ops_bed_state_event', [{
                'bed_state_event_id': bed_event_id, 'bed_id': bed_id, 'event_datetime': simulated_now,
                'event_type': 'Admission', 'status_before': 'Available', 'status_after': 'Occupied',
                'encounter_id': int(cand['encounter_id']), 'patient_id': int(cand['patient_id']),
                'reason': 'Simulated admission bed assignment', 'simulation_run_id': run_id,
            }])
            insert_rows(conn, 'ops_patient_movement', [{
                'movement_id': movement_id, 'encounter_id': int(cand['encounter_id']), 'patient_id': int(cand['patient_id']),
                'hospital_id': int(cand['hospital_id']), 'from_unit_id': None, 'from_room_id': None, 'from_bed_id': None,
                'to_unit_id': int(unit['unit_id']), 'to_room_id': None, 'to_bed_id': bed_id,
                'requested_datetime': simulated_now, 'accepted_datetime': simulated_now, 'started_datetime': simulated_now,
                'completed_datetime': simulated_now, 'movement_type': 'Admission', 'movement_status': 'Completed',
                'priority': 'Routine', 'delay_reason': None, 'simulation_run_id': run_id,
            }])
            upsert_row(conn, 'ops_discharge_readiness', ['encounter_id'], {
                'encounter_id': int(cand['encounter_id']), 'patient_id': int(cand['patient_id']),
                'expected_discharge_datetime': None, 'readiness_status': 'Not Ready',
                'clinical_ready_flag': False, 'medication_ready_flag': False, 'transport_ready_flag': False,
                'destination_ready_flag': False, 'education_complete_flag': False, 'outstanding_barrier_count': 1,
                'primary_barrier': 'Simulated: awaiting clinical progress', 'updated_datetime': simulated_now,
                'simulation_run_id': run_id,
            })
            bed_event_id += 1
            movement_id += 1
            processed += 1
    return processed


def advance_discharge_readiness(engine, simulated_now, run_id, batch_size, discharge_delay_multiplier, rng):
    occupied = query_db(
        "SELECT TOP (:lim) dr.encounter_id, dr.outstanding_barrier_count FROM dbo.ops_discharge_readiness dr "
        "WHERE dr.readiness_status <> 'Ready' ORDER BY dr.updated_datetime ASC", engine, {'lim': batch_size})
    if occupied.empty:
        return 0
    progressed = 0
    progress_chance = max(0.02, 0.20 / max(discharge_delay_multiplier, 0.1))
    with transaction(engine) as conn:
        for _, row in occupied.iterrows():
            if rng.random() > progress_chance:
                continue
            barriers = max(0, int(row['outstanding_barrier_count']) - 1)
            status = 'Ready' if barriers == 0 else ('Pending' if barriers <= 1 else 'Not Ready')
            conn.execute(text(
                "UPDATE dbo.ops_discharge_readiness SET outstanding_barrier_count = :b, readiness_status = :s, "
                "clinical_ready_flag = CASE WHEN :b = 0 THEN 1 ELSE clinical_ready_flag END, "
                "primary_barrier = CASE WHEN :b = 0 THEN NULL ELSE primary_barrier END, "
                "expected_discharge_datetime = CASE WHEN :b = 0 THEN :now ELSE expected_discharge_datetime END, "
                "updated_datetime = :now, simulation_run_id = :rid WHERE encounter_id = :eid"
            ), {'b': barriers, 's': status, 'now': simulated_now, 'rid': run_id, 'eid': int(row['encounter_id'])})
            progressed += 1
    return progressed


def discharge_ready_patients(engine, simulated_now, run_id, batch_size, rng):
    ready = query_db(
        "SELECT TOP (:lim) bs.bed_id, bs.encounter_id, bs.patient_id, b.hospital_id FROM dbo.ops_bed_state bs "
        "JOIN dbo.beds b ON bs.bed_id = b.bed_id "
        "JOIN dbo.ops_discharge_readiness dr ON bs.encounter_id = dr.encounter_id "
        "WHERE bs.occupancy_status = 'Occupied' AND dr.readiness_status = 'Ready'", engine, {'lim': batch_size})
    if ready.empty:
        return 0
    bed_event_id = get_next_id('ops_bed_state_event', 'bed_state_event_id', engine)
    movement_id = get_next_id('ops_patient_movement', 'movement_id', engine)
    released = 0
    with transaction(engine) as conn:
        for _, row in ready.iterrows():
            bed_id = int(row['bed_id'])
            upsert_row(conn, 'ops_bed_state', ['bed_id'], {
                'bed_id': bed_id, 'operational_status': 'Cleaning', 'occupancy_status': 'Cleaning',
                'encounter_id': None, 'patient_id': None, 'admission_id': None, 'assigned_datetime': None,
                'expected_release_datetime': None, 'cleaning_required_flag': True,
                'updated_datetime': simulated_now, 'simulation_run_id': run_id,
            })
            insert_rows(conn, 'ops_bed_state_event', [{
                'bed_state_event_id': bed_event_id, 'bed_id': bed_id, 'event_datetime': simulated_now,
                'event_type': 'Discharge', 'status_before': 'Occupied', 'status_after': 'Cleaning',
                'encounter_id': int(row['encounter_id']), 'patient_id': int(row['patient_id']),
                'reason': 'Simulated operational discharge (bed released for cleaning)', 'simulation_run_id': run_id,
            }])
            insert_rows(conn, 'ops_patient_movement', [{
                'movement_id': movement_id, 'encounter_id': int(row['encounter_id']), 'patient_id': int(row['patient_id']),
                'hospital_id': int(row['hospital_id']), 'from_unit_id': None, 'from_room_id': None, 'from_bed_id': bed_id,
                'to_unit_id': None, 'to_room_id': None, 'to_bed_id': None, 'requested_datetime': simulated_now,
                'accepted_datetime': simulated_now, 'started_datetime': simulated_now, 'completed_datetime': simulated_now,
                'movement_type': 'Discharge', 'movement_status': 'Completed', 'priority': 'Routine',
                'delay_reason': None, 'simulation_run_id': run_id,
            }])
            bed_event_id += 1
            movement_id += 1
            released += 1
    return released


def transfer_patients(engine, simulated_now, run_id, batch_size, icu_pressure_multiplier, rng):
    if rng.random() > min(0.5, 0.05 * icu_pressure_multiplier):
        return 0
    occupied = query_db(
        "SELECT TOP (:lim) bs.bed_id, bs.encounter_id, bs.patient_id, b.hospital_id, b.floor_number "
        "FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id WHERE bs.occupancy_status = 'Occupied' "
        "ORDER BY NEWID()", engine, {'lim': batch_size})
    if occupied.empty:
        return 0
    units = query_db('SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit', engine)
    movement_id = get_next_id('ops_patient_movement', 'movement_id', engine)
    bed_event_id = get_next_id('ops_bed_state_event', 'bed_state_event_id', engine)
    moved = 0
    with transaction(engine) as conn:
        for _, row in occupied.iterrows():
            hosp_units = units[(units['hospital_id'] == row['hospital_id']) & (units['source_floor_number'] != row['floor_number'])]
            if hosp_units.empty:
                continue
            target_unit = hosp_units.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]
            new_bed_id = _find_available_bed(conn, int(row['hospital_id']), int(target_unit['source_floor_number']))
            if new_bed_id is None:
                continue
            old_bed_id = int(row['bed_id'])
            upsert_row(conn, 'ops_bed_state', ['bed_id'], {
                'bed_id': new_bed_id, 'operational_status': 'Occupied', 'occupancy_status': 'Occupied',
                'encounter_id': int(row['encounter_id']), 'patient_id': int(row['patient_id']), 'admission_id': None,
                'assigned_datetime': simulated_now, 'expected_release_datetime': None, 'cleaning_required_flag': False,
                'updated_datetime': simulated_now, 'simulation_run_id': run_id,
            })
            upsert_row(conn, 'ops_bed_state', ['bed_id'], {
                'bed_id': old_bed_id, 'operational_status': 'Cleaning', 'occupancy_status': 'Cleaning',
                'encounter_id': None, 'patient_id': None, 'admission_id': None, 'assigned_datetime': None,
                'expected_release_datetime': None, 'cleaning_required_flag': True,
                'updated_datetime': simulated_now, 'simulation_run_id': run_id,
            })
            insert_rows(conn, 'ops_bed_state_event', [{
                'bed_state_event_id': bed_event_id, 'bed_id': old_bed_id, 'event_datetime': simulated_now,
                'event_type': 'Internal Transfer', 'status_before': 'Occupied', 'status_after': 'Cleaning',
                'encounter_id': int(row['encounter_id']), 'patient_id': int(row['patient_id']),
                'reason': 'Simulated internal transfer', 'simulation_run_id': run_id,
            }])
            insert_rows(conn, 'ops_patient_movement', [{
                'movement_id': movement_id, 'encounter_id': int(row['encounter_id']), 'patient_id': int(row['patient_id']),
                'hospital_id': int(row['hospital_id']), 'from_unit_id': None, 'from_room_id': None, 'from_bed_id': old_bed_id,
                'to_unit_id': int(target_unit['unit_id']), 'to_room_id': None, 'to_bed_id': new_bed_id,
                'requested_datetime': simulated_now, 'accepted_datetime': simulated_now, 'started_datetime': simulated_now,
                'completed_datetime': simulated_now,
                'movement_type': 'Internal Transfer' if target_unit['unit_type'] != 'Critical Care' else 'ICU Transfer',
                'movement_status': 'Completed', 'priority': 'Urgent' if target_unit['unit_type'] == 'Critical Care' else 'Routine',
                'delay_reason': None, 'simulation_run_id': run_id,
            }])
            bed_event_id += 1
            movement_id += 1
            moved += 1
    return moved


def seed_discharge_readiness_for_occupied(engine=None, run_id=None):
    '''Setup-only helper: seed ops_discharge_readiness for beds that started
    Occupied (from existing patient_bed_assignments) and don't have one yet.'''
    engine = engine or SINGLE_ENGINE
    missing = query_db(
        "SELECT bs.encounter_id, bs.patient_id FROM dbo.ops_bed_state bs "
        "LEFT JOIN dbo.ops_discharge_readiness dr ON bs.encounter_id = dr.encounter_id "
        "WHERE bs.occupancy_status = 'Occupied' AND bs.encounter_id IS NOT NULL AND dr.encounter_id IS NULL", engine)
    if missing.empty:
        return 0
    now = pd.Timestamp.utcnow().tz_localize(None)
    with transaction(engine) as conn:
        for _, row in missing.iterrows():
            upsert_row(conn, 'ops_discharge_readiness', ['encounter_id'], {
                'encounter_id': int(row['encounter_id']), 'patient_id': int(row['patient_id']),
                'expected_discharge_datetime': None, 'readiness_status': 'Not Ready',
                'clinical_ready_flag': False, 'medication_ready_flag': False, 'transport_ready_flag': False,
                'destination_ready_flag': False, 'education_complete_flag': False, 'outstanding_barrier_count': 1,
                'primary_barrier': 'Simulated: awaiting clinical progress', 'updated_datetime': now,
                'simulation_run_id': run_id,
            })
    return len(missing)


def simulate_patient_flow_iteration(engine, simulated_now, run_id, scenario, batch_size, rng):
    admitted = admit_patients(engine, simulated_now, run_id, max(1, batch_size // 3), scenario, rng)
    progressed = advance_discharge_readiness(engine, simulated_now, run_id, batch_size, scenario.discharge_delay_multiplier, rng)
    discharged = discharge_ready_patients(engine, simulated_now, run_id, max(1, batch_size // 3), rng)
    transferred = transfer_patients(engine, simulated_now, run_id, max(1, batch_size // 4), scenario.icu_pressure_multiplier, rng)
    return {'admitted': admitted, 'discharge_progressed': progressed, 'discharged': discharged, 'transferred': transferred}
"""

CELL_EQUIPMENT_SIMULATOR = r"""# ============================================================================
# CELL: Per-Iteration Equipment State Transitions
# ============================================================================
_EQUIPMENT_TRANSITIONS = {
    'Available': [('InUse', 0.15)],
    'InUse': [('Available', 0.20)],
    'Warning': [('Unavailable', 0.30), ('Available', 0.40)],
    'Unavailable': [('Maintenance', 0.50)],
    'Maintenance': [('Available', 0.60)],
}


def simulate_equipment_iteration(engine, simulated_now, run_id, equipment_failure_rate, batch_size, rng):
    states = query_db(
        "SELECT es.equipment_id, es.status, eq.equipment_type, eq.criticality FROM dbo.ops_equipment_state es "
        "JOIN dbo.ops_equipment eq ON es.equipment_id = eq.equipment_id ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT (:lim) ROWS ONLY",
        engine, {'lim': batch_size})
    if states.empty:
        return {'events': 0, 'failures': 0, 'recoveries': 0}
    event_id = get_next_id('ops_equipment_event', 'equipment_event_id', engine)
    events = failures = recoveries = 0
    with transaction(engine) as conn:
        for _, row in states.iterrows():
            equipment_id = int(row['equipment_id'])
            current = row['status']
            if current == 'Available' and rng.random() < equipment_failure_rate:
                new_status, severity, event_type = 'Unavailable', 'Critical', 'Failure'
                failures += 1
            else:
                options = _EQUIPMENT_TRANSITIONS.get(current, [])
                new_status = current
                for candidate, prob in options:
                    if rng.random() < prob:
                        new_status = candidate
                        break
                if new_status == current:
                    continue
                severity = 'Warning' if new_status in ('Warning', 'Unavailable') else 'Info'
                event_type = 'Status Change'
                if current in ('Unavailable', 'Maintenance') and new_status == 'Available':
                    recoveries += 1
            availability = 'Available' if new_status in ('Available', 'InUse') else 'Unavailable'
            utilization = 'InUse' if new_status == 'InUse' else 'Idle'
            upsert_row(conn, 'ops_equipment_state', ['equipment_id'], {
                'equipment_id': equipment_id, 'status': new_status, 'availability_status': availability,
                'utilization_status': utilization, 'battery_pct': None, 'temperature': None, 'pressure': None,
                'error_code': 'ERR-001' if new_status == 'Unavailable' else None, 'maintenance_due_date': None,
                'last_seen_datetime': simulated_now, 'updated_datetime': simulated_now, 'simulation_run_id': run_id,
            })
            insert_rows(conn, 'ops_equipment_event', [{
                'equipment_event_id': event_id, 'equipment_id': equipment_id, 'event_datetime': simulated_now,
                'event_type': event_type, 'severity': severity, 'metric_name': None, 'metric_value': None, 'metric_unit': None,
                'status_before': current, 'status_after': new_status,
                'description': f"Simulated {event_type.lower()} for {row['equipment_type']}", 'simulation_run_id': run_id,
            }])
            event_id += 1
            events += 1
    return {'events': events, 'failures': failures, 'recoveries': recoveries}
"""

CELL_ALERT_ENGINE = r"""# ============================================================================
# CELL: Alert Engine (opens / escalates / resolves ops_operational_alert)
# ============================================================================

def _get_open_alert(conn, alert_key):
    df = query_db("SELECT * FROM dbo.ops_operational_alert WHERE alert_key = :k AND status <> 'Resolved'", conn, {'k': alert_key})
    return df.iloc[0] if not df.empty else None


def _severity_rank(sev):
    return {'Info': 0, 'Warning': 1, 'Critical': 2}.get(sev, 0)


def _open_or_escalate(conn, alert_id_holder, alert_key, hospital_id, category, alert_type, severity, title,
                       description, source_metric, source_value, threshold_value, simulated_now, run_id, dims):
    existing = _get_open_alert(conn, alert_key)
    if existing is None:
        alert_id = alert_id_holder[0]
        alert_id_holder[0] += 1
        conn.execute(text(
            "INSERT INTO dbo.ops_operational_alert (alert_id, alert_key, hospital_id, building_id, floor_number, "
            "unit_id, room_id, bed_id, equipment_id, encounter_id, alert_category, alert_type, severity, title, "
            "description, status, opened_datetime, source_metric, source_value, threshold_value, simulation_run_id, "
            "created_datetime, updated_datetime) VALUES (:alert_id, :alert_key, :hospital_id, :building_id, "
            ":floor_number, :unit_id, :room_id, :bed_id, :equipment_id, :encounter_id, :category, :alert_type, "
            ":severity, :title, :description, 'Open', :opened, :source_metric, :source_value, :threshold_value, "
            ":run_id, :now, :now)"
        ), {
            'alert_id': alert_id, 'alert_key': alert_key, 'hospital_id': hospital_id, 'building_id': dims.get('building_id'),
            'floor_number': dims.get('floor_number'), 'unit_id': dims.get('unit_id'), 'room_id': dims.get('room_id'),
            'bed_id': dims.get('bed_id'), 'equipment_id': dims.get('equipment_id'), 'encounter_id': dims.get('encounter_id'),
            'category': category, 'alert_type': alert_type, 'severity': severity, 'title': title, 'description': description,
            'opened': simulated_now, 'source_metric': source_metric, 'source_value': source_value,
            'threshold_value': threshold_value, 'run_id': run_id, 'now': simulated_now,
        })
        event_id = get_next_id('ops_alert_event', 'alert_event_id', conn)
        insert_rows(conn, 'ops_alert_event', [{
            'alert_event_id': event_id, 'alert_id': alert_id, 'event_datetime': simulated_now, 'event_type': 'Opened',
            'status_before': None, 'status_after': 'Open', 'description': description, 'simulation_run_id': run_id,
        }])
        return 'opened'
    if existing['severity'] != severity and _severity_rank(severity) > _severity_rank(existing['severity']):
        conn.execute(text(
            "UPDATE dbo.ops_operational_alert SET severity = :sev, source_value = :sv, updated_datetime = :now WHERE alert_id = :aid"
        ), {'sev': severity, 'sv': source_value, 'now': simulated_now, 'aid': int(existing['alert_id'])})
        event_id = get_next_id('ops_alert_event', 'alert_event_id', conn)
        insert_rows(conn, 'ops_alert_event', [{
            'alert_event_id': event_id, 'alert_id': int(existing['alert_id']), 'event_datetime': simulated_now,
            'event_type': 'Escalated', 'status_before': existing['severity'], 'status_after': severity,
            'description': f'Escalated to {severity}', 'simulation_run_id': run_id,
        }])
        return 'escalated'
    return 'unchanged'


def _resolve_if_open(conn, alert_key, simulated_now, run_id):
    existing = _get_open_alert(conn, alert_key)
    if existing is None:
        return False
    conn.execute(text(
        "UPDATE dbo.ops_operational_alert SET status = 'Resolved', resolved_datetime = :now, updated_datetime = :now WHERE alert_id = :aid"
    ), {'now': simulated_now, 'aid': int(existing['alert_id'])})
    event_id = get_next_id('ops_alert_event', 'alert_event_id', conn)
    insert_rows(conn, 'ops_alert_event', [{
        'alert_event_id': event_id, 'alert_id': int(existing['alert_id']), 'event_datetime': simulated_now,
        'event_type': 'Resolved', 'status_before': existing['status'], 'status_after': 'Resolved',
        'description': 'Condition cleared', 'simulation_run_id': run_id,
    }])
    return True


def evaluate_alerts(engine, simulated_now, run_id, scenario):
    opened = escalated = resolved = 0
    alert_id_holder = [get_next_id('ops_operational_alert', 'alert_id', engine)]
    hospitals = query_db('SELECT hospital_id, name FROM dbo.hospitals', engine)
    with transaction(engine) as conn:
        for _, h in hospitals.iterrows():
            hid = int(h['hospital_id'])
            for unit_type, label, threshold_attr in (
                ('Critical Care', 'ICU', 'icu_occupancy_alert_threshold'),
                ('Emergency', 'ED', 'ed_occupancy_alert_threshold'),
            ):
                occ_df = query_db(
                    "SELECT COUNT(*) AS total, SUM(CASE WHEN bs.occupancy_status = 'Occupied' THEN 1 ELSE 0 END) AS occ "
                    "FROM dbo.beds b JOIN dbo.ops_unit u ON u.hospital_id = b.hospital_id AND u.source_floor_number = b.floor_number "
                    "LEFT JOIN dbo.ops_bed_state bs ON b.bed_id = bs.bed_id "
                    "WHERE b.hospital_id = :h AND u.unit_type = :ut", conn, {'h': hid, 'ut': unit_type})
                total = int(occ_df.iloc[0]['total'] or 0) if not occ_df.empty else 0
                occ = int(occ_df.iloc[0]['occ'] or 0) if not occ_df.empty else 0
                pct = (occ / total) if total > 0 else 0.0
                threshold = getattr(scenario, threshold_attr)
                key = f'CAPACITY:{label}_OCCUPANCY:hospital={hid}'
                if total > 0 and pct >= threshold:
                    sev = 'Critical' if pct >= 0.97 else 'Warning'
                    result = _open_or_escalate(conn, alert_id_holder, key, hid, 'Capacity', f'{label} Occupancy High', sev,
                                                f'{label} occupancy above threshold at {h["name"]}',
                                                f'{label} occupancy is {pct:.0%} (threshold {threshold:.0%}).', 'occupancy_pct',
                                                round(pct * 100, 1), round(threshold * 100, 1), simulated_now, run_id, {'unit_id': None})
                    opened += result == 'opened'; escalated += result == 'escalated'
                    if total > 0 and occ >= total:
                        no_bed_key = f'CAPACITY:NO_AVAILABLE_{label}_BEDS:hospital={hid}'
                        result2 = _open_or_escalate(conn, alert_id_holder, no_bed_key, hid, 'Capacity', f'No Available {label} Beds',
                                                     'Critical', f'No available {label} beds at {h["name"]}',
                                                     f'All {total} {label} beds are occupied.', 'available_beds', 0, 0,
                                                     simulated_now, run_id, {})
                        opened += result2 == 'opened'
                    else:
                        resolved += _resolve_if_open(conn, f'CAPACITY:NO_AVAILABLE_{label}_BEDS:hospital={hid}', simulated_now, run_id)
                else:
                    resolved += _resolve_if_open(conn, key, simulated_now, run_id)
                    resolved += _resolve_if_open(conn, f'CAPACITY:NO_AVAILABLE_{label}_BEDS:hospital={hid}', simulated_now, run_id)

            staffing = query_db(
                "SELECT ss.unit_id, ss.staffing_coverage_pct, ss.charge_nurse_staff_id FROM dbo.ops_staffing_state ss "
                "JOIN dbo.ops_unit u ON ss.unit_id = u.unit_id WHERE u.hospital_id = :h", conn, {'h': hid})
            for _, s in staffing.iterrows():
                unit_id = int(s['unit_id'])
                cov = float(s['staffing_coverage_pct'] or 100.0) / 100.0
                key = f'STAFFING:RN_COVERAGE_LOW:unit={unit_id}'
                if cov < scenario.rn_coverage_alert_threshold:
                    sev = 'Critical' if cov < 0.6 else 'Warning'
                    result = _open_or_escalate(conn, alert_id_holder, key, hid, 'Staffing', 'RN Coverage Below Target', sev,
                                                f'RN coverage below target on unit {unit_id}', f'Coverage is {cov:.0%}.',
                                                'staffing_coverage_pct', round(cov * 100, 1),
                                                round(scenario.rn_coverage_alert_threshold * 100, 1), simulated_now, run_id, {'unit_id': unit_id})
                    opened += result == 'opened'; escalated += result == 'escalated'
                else:
                    resolved += _resolve_if_open(conn, key, simulated_now, run_id)
                cn_key = f'STAFFING:OPEN_CHARGE_NURSE:unit={unit_id}'
                if pd.isna(s['charge_nurse_staff_id']):
                    result = _open_or_escalate(conn, alert_id_holder, cn_key, hid, 'Staffing', 'Open Charge Nurse Assignment',
                                                'Warning', f'No charge nurse assigned on unit {unit_id}',
                                                'Charge nurse slot is open for the current shift.', None, None, None,
                                                simulated_now, run_id, {'unit_id': unit_id})
                    opened += result == 'opened'
                else:
                    resolved += _resolve_if_open(conn, cn_key, simulated_now, run_id)

            delayed = query_db(
                "SELECT COUNT(*) AS n FROM dbo.ops_discharge_readiness dr JOIN dbo.admissions a ON dr.encounter_id = a.encounter_id "
                "WHERE a.hospital_id = :h AND dr.readiness_status = 'Not Ready' AND dr.outstanding_barrier_count >= 2",
                conn, {'h': hid})
            delay_n = int(delayed.iloc[0]['n']) if not delayed.empty else 0
            key = f'PATIENT_FLOW:DISCHARGE_DELAYS:hospital={hid}'
            if delay_n >= 5:
                result = _open_or_escalate(conn, alert_id_holder, key, hid, 'Patient Flow', 'Excessive Discharge Delays',
                                            'Critical' if delay_n >= 15 else 'Warning', f'Excessive discharge delays at {h["name"]}',
                                            f'{delay_n} encounters have >=2 outstanding discharge barriers.', 'delayed_discharge_count',
                                            delay_n, 5, simulated_now, run_id, {})
                opened += result == 'opened'; escalated += result == 'escalated'
            else:
                resolved += _resolve_if_open(conn, key, simulated_now, run_id)

            for equip_type, label in (('Ventilator', 'Ventilator'), ('MRI', 'Imaging'), ('CT Scanner', 'Imaging'), ('Portable X-Ray', 'Imaging')):
                unavailable = query_db(
                    "SELECT eq.equipment_id FROM dbo.ops_equipment eq JOIN dbo.ops_equipment_state es ON eq.equipment_id = es.equipment_id "
                    "WHERE eq.hospital_id = :h AND eq.equipment_type = :t AND es.availability_status = 'Unavailable'",
                    conn, {'h': hid, 't': equip_type})
                for _, eq_row in unavailable.iterrows():
                    key = f'EQUIPMENT:{label.upper()}_UNAVAILABLE:equipment={int(eq_row["equipment_id"])}'
                    result = _open_or_escalate(conn, alert_id_holder, key, hid, 'Equipment', f'{equip_type} Unavailable',
                                                'Critical' if equip_type == 'Ventilator' else 'Warning',
                                                f'{equip_type} unavailable at {h["name"]}',
                                                f'{equip_type} (id {int(eq_row["equipment_id"])}) is currently unavailable.', None, None, None,
                                                simulated_now, run_id, {'equipment_id': int(eq_row['equipment_id'])})
                    opened += result == 'opened'; escalated += result == 'escalated'

            blocked = query_db(
                "SELECT rs.room_id FROM dbo.ops_room_state rs JOIN dbo.rooms r ON rs.room_id = r.room_id "
                "WHERE r.hospital_id = :h AND rs.operational_status IN ('Maintenance', 'Closed')", conn, {'h': hid})
            for _, r_row in blocked.iterrows():
                key = f'ENVIRONMENTAL:ROOM_BLOCKED:room={int(r_row["room_id"])}'
                result = _open_or_escalate(conn, alert_id_holder, key, hid, 'Environmental', 'Room Blocked For Maintenance',
                                            'Warning', f'Room {int(r_row["room_id"])} blocked for maintenance',
                                            'Room is out of service.', None, None, None, simulated_now, run_id,
                                            {'room_id': int(r_row['room_id'])})
                opened += result == 'opened'
    return {'opened': opened, 'escalated': escalated, 'resolved': resolved}
"""

CELL_CHECKPOINT = r"""# ============================================================================
# CELL: Simulation Control / Run / Checkpoint bookkeeping
# ============================================================================
STALE_HEARTBEAT_MINUTES = 5


def ensure_control_row(engine, simulator_name, scenario_name, update_interval_seconds, speed_multiplier, random_seed, selected_hospital_id):
    existing = query_db('SELECT * FROM dbo.ops_simulation_control WHERE simulator_name = :n', engine, {'n': simulator_name})
    if existing.empty:
        control_id = get_next_id('ops_simulation_control', 'control_id', engine)
        with transaction(engine) as conn:
            upsert_row(conn, 'ops_simulation_control', ['control_id'], {
                'control_id': control_id, 'simulator_name': simulator_name, 'requested_state': 'RUN',
                'update_interval_seconds': update_interval_seconds, 'speed_multiplier': speed_multiplier,
                'random_seed': random_seed, 'scenario_name': scenario_name, 'selected_hospital_id': selected_hospital_id,
                'last_updated_datetime': pd.Timestamp.utcnow().tz_localize(None), 'updated_by': 'setup',
            })
        existing = query_db('SELECT * FROM dbo.ops_simulation_control WHERE simulator_name = :n', engine, {'n': simulator_name})
    return existing.iloc[0].to_dict()


def get_control_state(engine, simulator_name):
    df = query_db('SELECT * FROM dbo.ops_simulation_control WHERE simulator_name = :n', engine, {'n': simulator_name})
    return df.iloc[0].to_dict() if not df.empty else None


def set_requested_state(engine, simulator_name, requested_state, updated_by='notebook'):
    assert requested_state in ('RUN', 'PAUSE', 'STOP')
    with transaction(engine) as conn:
        conn.execute(text(
            "UPDATE dbo.ops_simulation_control SET requested_state = :s, last_updated_datetime = SYSUTCDATETIME(), "
            "updated_by = :u WHERE simulator_name = :n"
        ), {'s': requested_state, 'u': updated_by, 'n': simulator_name})


def find_resumable_run(engine, simulator_name, stale_minutes=STALE_HEARTBEAT_MINUTES):
    df = query_db(
        "SELECT TOP 1 * FROM dbo.ops_simulation_run WHERE simulator_name = :n AND current_status = 'RUNNING' "
        "ORDER BY simulation_run_id DESC", engine, {'n': simulator_name})
    if df.empty:
        return None
    row = df.iloc[0]
    last_hb = row['last_successful_iteration_datetime'] or row['started_datetime']
    age_minutes = (pd.Timestamp.utcnow().tz_localize(None) - pd.Timestamp(last_hb)).total_seconds() / 60.0
    return row.to_dict() if age_minutes >= stale_minutes else None


def start_run(engine, simulator_name, scenario_name, random_seed, config):
    run_id = get_next_id('ops_simulation_run', 'simulation_run_id', engine)
    now = pd.Timestamp.utcnow().tz_localize(None)
    with transaction(engine) as conn:
        upsert_row(conn, 'ops_simulation_run', ['simulation_run_id'], {
            'simulation_run_id': run_id, 'simulator_name': simulator_name, 'scenario_name': scenario_name,
            'random_seed': random_seed, 'started_datetime': now, 'ended_datetime': None, 'current_status': 'RUNNING',
            'iteration_count': 0, 'last_successful_iteration_datetime': now, 'error_count': 0,
            'hostname': socket.gethostname(), 'configuration_json': json.dumps(config, default=str),
        })
    return run_id


def update_heartbeat(engine, run_id, iteration_count, error_count=0):
    with transaction(engine) as conn:
        conn.execute(text(
            "UPDATE dbo.ops_simulation_run SET iteration_count = :it, error_count = :err, "
            "last_successful_iteration_datetime = SYSUTCDATETIME() WHERE simulation_run_id = :rid"
        ), {'it': iteration_count, 'err': error_count, 'rid': run_id})


def complete_run(engine, run_id, status):
    with transaction(engine) as conn:
        conn.execute(text(
            "UPDATE dbo.ops_simulation_run SET current_status = :s, ended_datetime = SYSUTCDATETIME() WHERE simulation_run_id = :rid"
        ), {'s': status, 'rid': run_id})


def save_checkpoint(engine, simulator_name, run_id, iteration, simulated_datetime, random_state_json=None, extra=None):
    with transaction(engine) as conn:
        upsert_row(conn, 'ops_simulation_checkpoint', ['simulator_name', 'simulation_run_id'], {
            'simulator_name': simulator_name, 'simulation_run_id': run_id, 'last_completed_iteration': iteration,
            'simulated_datetime': simulated_datetime, 'random_state': random_state_json,
            'checkpoint_datetime': pd.Timestamp.utcnow().tz_localize(None), 'checkpoint_json': json.dumps(extra or {}, default=str),
        })


def load_latest_checkpoint(engine, simulator_name, run_id):
    df = query_db('SELECT * FROM dbo.ops_simulation_checkpoint WHERE simulator_name = :n AND simulation_run_id = :rid',
                   engine, {'n': simulator_name, 'rid': run_id})
    return df.iloc[0].to_dict() if not df.empty else None


def log_event(engine, run_id, iteration_number, category, action, status='OK', message=None, entity_type=None, entity_id=None):
    event_id = get_next_id('ops_simulation_event_log', 'simulation_event_log_id', engine)
    if message is not None and len(message) > 1000:
        message = message[:997] + '...'
    with transaction(engine) as conn:
        conn.execute(text(
            "INSERT INTO dbo.ops_simulation_event_log (simulation_event_log_id, simulation_run_id, iteration_number, "
            "event_datetime, event_category, entity_type, entity_id, action, status, message) VALUES "
            "(:id, :rid, :it, SYSUTCDATETIME(), :cat, :etype, :eid, :action, :status, :msg)"
        ), {'id': event_id, 'rid': run_id, 'it': iteration_number, 'cat': category, 'etype': entity_type,
            'eid': entity_id, 'action': action, 'status': status, 'msg': message})
"""

CELL_VALIDATION = r"""# ============================================================================
# CELL: PASS/WARN/FAIL Validation Checks
# ============================================================================

def _rowcount_check(engine, name, sql, warn_only=False):
    df = query_db(sql, engine)
    n = len(df)
    if n == 0:
        return {'check': name, 'status': 'PASS', 'detail': '0 violations'}
    return {'check': name, 'status': 'WARN' if warn_only else 'FAIL', 'detail': f'{n} row(s) violate this check'}


def run_all_checks(engine=None):
    engine = engine or SINGLE_ENGINE
    checks = [
        _rowcount_check(engine, 'Every ops_building references a valid hospital', '''
            SELECT b.building_id FROM dbo.ops_building b
            LEFT JOIN dbo.hospitals h ON b.hospital_id = h.hospital_id WHERE h.hospital_id IS NULL'''),
        _rowcount_check(engine, 'Every ops_unit references a valid building/hospital/floors row', '''
            SELECT u.unit_id FROM dbo.ops_unit u
            LEFT JOIN dbo.ops_building b ON u.building_id = b.building_id
            LEFT JOIN dbo.hospitals h ON u.hospital_id = h.hospital_id
            LEFT JOIN dbo.floors f ON f.hospital_id = u.hospital_id AND f.floor_number = u.source_floor_number
            WHERE b.building_id IS NULL OR h.hospital_id IS NULL OR f.floor_number IS NULL'''),
        _rowcount_check(engine, 'Every ops_room_attribute references a valid room and unit', '''
            SELECT ra.room_id FROM dbo.ops_room_attribute ra
            LEFT JOIN dbo.rooms r ON ra.room_id = r.room_id
            LEFT JOIN dbo.ops_unit u ON ra.unit_id = u.unit_id
            WHERE r.room_id IS NULL OR u.unit_id IS NULL'''),
        _rowcount_check(engine, 'Every ops_bed_state references a valid bed', '''
            SELECT bs.bed_id FROM dbo.ops_bed_state bs
            LEFT JOIN dbo.beds b ON bs.bed_id = b.bed_id WHERE b.bed_id IS NULL'''),
        _rowcount_check(engine, 'ops_unit.staffed_bed_count matches actual bed count on that floor', '''
            SELECT u.unit_id FROM dbo.ops_unit u
            WHERE u.staffed_bed_count <> (
                SELECT COUNT(*) FROM dbo.beds b WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number)'''),
        _rowcount_check(engine, 'No bed has more than one active (Occupied) encounter', '''
            SELECT bed_id FROM dbo.ops_bed_state WHERE occupancy_status = 'Occupied' GROUP BY bed_id HAVING COUNT(*) > 1'''),
        _rowcount_check(engine, 'No encounter occupies more than one bed at a time', '''
            SELECT encounter_id FROM dbo.ops_bed_state WHERE occupancy_status = 'Occupied' AND encounter_id IS NOT NULL
            GROUP BY encounter_id HAVING COUNT(DISTINCT bed_id) > 1'''),
        _rowcount_check(engine, 'Occupied beds have patient+encounter; available/cleaning beds do not', '''
            SELECT bed_id FROM dbo.ops_bed_state
            WHERE (occupancy_status = 'Occupied' AND (encounter_id IS NULL OR patient_id IS NULL))
               OR (occupancy_status IN ('Available', 'Cleaning') AND encounter_id IS NOT NULL)'''),
        _rowcount_check(engine, 'Charge nurses reference valid ops_staff rows', '''
            SELECT ss.unit_id FROM dbo.ops_staffing_state ss
            LEFT JOIN dbo.ops_staff s ON ss.charge_nurse_staff_id = s.staff_id
            WHERE ss.charge_nurse_staff_id IS NOT NULL AND s.staff_id IS NULL'''),
        _rowcount_check(engine, 'Equipment locations are valid (unit hospital matches equipment hospital)', '''
            SELECT eq.equipment_id FROM dbo.ops_equipment eq
            LEFT JOIN dbo.ops_unit u ON eq.unit_id = u.unit_id
            WHERE u.unit_id IS NULL OR u.hospital_id <> eq.hospital_id'''),
        _rowcount_check(engine, 'Active alerts reference a valid hospital', '''
            SELECT alert_id FROM dbo.ops_operational_alert oa
            LEFT JOIN dbo.hospitals h ON oa.hospital_id = h.hospital_id
            WHERE oa.status <> 'Resolved' AND h.hospital_id IS NULL'''),
        _rowcount_check(engine, 'Hospital snapshot occupancy_pct matches occupied/staffed beds', '''
            SELECT hospital_id FROM dbo.vw_ops_hospital_snapshot
            WHERE ABS(occupancy_pct - CASE WHEN staffed_beds > 0 THEN ROUND(100.0 * occupied_beds / staffed_beds, 1) ELSE 0 END) > 0.1'''),
        _rowcount_check(
            engine, 'ops_unit staffed-bed sum vs latest hospital_department_beds.beds_allocated sum (informational)', '''
            SELECT h.hospital_id FROM dbo.hospitals h
            WHERE ISNULL((SELECT SUM(staffed_bed_count) FROM dbo.ops_unit WHERE hospital_id = h.hospital_id), 0) <>
                  ISNULL((SELECT SUM(hdb.beds_allocated) FROM dbo.hospital_department_beds hdb
                          WHERE hdb.hospital_id = h.hospital_id AND hdb.date = (SELECT MAX(date) FROM dbo.hospital_department_beds)), 0)''',
            warn_only=True),
    ]
    return pd.DataFrame(checks)


def print_validation_summary(results):
    fail = int((results['status'] == 'FAIL').sum())
    warn = int((results['status'] == 'WARN').sum())
    passed = int((results['status'] == 'PASS').sum())
    overall = 'FAIL' if fail else ('WARN' if warn else 'PASS')
    print(f'Validation summary: {passed} PASS, {warn} WARN, {fail} FAIL -> overall {overall}')
    for _, row in results.iterrows():
        marker = {'PASS': '\u2713', 'WARN': '\u26a0', 'FAIL': '\u2717'}[row['status']]
        print(f"  {marker} [{row['status']}] {row['check']} -- {row['detail']}")
    return overall
"""

CELL_SNAPSHOT_BUILDER = r"""# ============================================================================
# CELL: Application Snapshot Refresh
# All vw_ops_* objects are plain SQL VIEWs computed live from current-state
# tables -- "refreshing" only means keeping room aggregates up to date.
# ============================================================================

def refresh_snapshots(engine=None, run_id=None):
    refresh_room_aggregates(engine or SINGLE_ENGINE, run_id)


def get_health_system_summary(engine=None):
    df = query_db('SELECT * FROM dbo.vw_ops_health_system_snapshot', engine or SINGLE_ENGINE)
    return df.iloc[0].to_dict() if not df.empty else {}


def get_hospital_summary(engine=None, hospital_id=None):
    engine = engine or SINGLE_ENGINE
    if hospital_id:
        return query_db('SELECT * FROM dbo.vw_ops_hospital_snapshot WHERE hospital_id = :h', engine, {'h': hospital_id})
    return query_db('SELECT * FROM dbo.vw_ops_hospital_snapshot', engine)
"""


def add_shared_cells(md, code, simulator_name: str):
    code(cell_config_and_environment(simulator_name))
    code(CELL_CONNECTION)
    code(CELL_MODELS)
    code(cell_schema_deployment())
    code(CELL_HIERARCHY)
    code(CELL_STAFFING)
    code(CELL_EQUIPMENT_GENERATOR)
    code(CELL_ROOM_BED_STATE)
    code(CELL_PATIENT_FLOW)
    code(CELL_EQUIPMENT_SIMULATOR)
    code(CELL_ALERT_ENGINE)
    code(CELL_CHECKPOINT)
    code(CELL_VALIDATION)
    code(CELL_SNAPSHOT_BUILDER)


# ============================================================================
# Notebook 1: Hospital_Operations_Setup.ipynb
# ============================================================================

def build_setup_notebook():
    nb = nbf.v4.new_notebook()
    cells = []
    md = lambda src: cells.append(nbf.v4.new_markdown_cell(src))
    code = lambda src: cells.append(nbf.v4.new_code_cell(src))

    md(r"""# Hospital Operations -- Setup (Microsoft Fabric)

**SYNTHETIC DEMONSTRATION DATA ONLY.** This notebook builds a synthetic
hospital-operations layer (buildings, units, staffing, equipment, initial
bed/room state, alerts) on top of the existing Healthcare Data Generator's
clinical tables. Nothing here is derived from, or suitable for, real clinical
decision-making.

## What this notebook does
This is a companion to the main `Healthcare_Data_Generator` notebook. It never
duplicates clinical data (hospitals, patients, encounters, admissions,
diagnoses, floors, rooms, beds) -- it only **extends** that data with a new,
clearly-separated `ops_*` layer:

1. Configuration & environment
2. Database connection
3. Source validation (fails clearly if the generator hasn't been run yet)
4. Idempotent schema deployment (`ops_*` tables + `vw_ops_*` views)
5. Hierarchy generation (building -> unit -> room-attribute extension)
6. Initial bed/room operational state (derived from existing patient placements)
7. Staffing generation (shifts, staff, current-shift assignments, coverage)
8. Equipment generation (inventory + initial state)
9. Initial discharge-readiness seeding + initial alert evaluation
10. Simulation-control row seeding (so the Real-Time Simulator notebook has
    sane defaults to start from)
11. Validation queries (PASS/WARN/FAIL summary)

Run this notebook **once** after the Healthcare Data Generator has produced
data, and any time you want to pick up new hospitals/floors/rooms it created.
Every step is idempotent -- safe to re-run.

## Prerequisites
Run `Healthcare_Data_Generator` at least once first (this notebook reads
`hospitals`, `departments`, `floors`, `rooms`, `beds`, `admissions`,
`encounters`, `patient_bed_assignments`).

## Next notebook
After this completes with an overall **PASS** (or acceptable **WARN**),
open and run `Hospital_Operations_Realtime_Simulator.ipynb`.
""")

    add_shared_cells(md, code, simulator_name="Hospital_Operations_Realtime_Simulator")

    code(r"""# ============================================================================
# CELL: Source Validation -- fail clearly if upstream data is missing
# ============================================================================
required_tables = ['hospitals', 'departments', 'floors', 'rooms', 'beds', 'admissions', 'encounters', 'patient_bed_assignments']
print('Checking required upstream tables from the Healthcare Data Generator...')
missing_or_empty = []
for t in required_tables:
    if not table_exists(t):
        missing_or_empty.append(f'{t} (table does not exist)')
        continue
    count_df = query_db(f'SELECT COUNT(*) AS n FROM dbo.{t}')
    n = int(count_df.iloc[0]['n']) if not count_df.empty else 0
    status = '\u2713' if n > 0 else '\u2717 EMPTY'
    print(f'  {status} {t}: {n:,} row(s)')
    if n == 0:
        missing_or_empty.append(f'{t} (0 rows)')

if missing_or_empty:
    raise RuntimeError(
        'Hospital Operations Setup cannot proceed -- missing/empty upstream tables: '
        + ', '.join(missing_or_empty)
        + '. Run the Healthcare_Data_Generator notebook first.'
    )
print('\n\u2713 All required upstream tables are present and populated.')
""")

    code(r"""# ============================================================================
# CELL: Idempotent Schema Deployment (ops_* tables + vw_ops_* views)
# ============================================================================
print('Deploying Hospital Operations schema (idempotent)...')
deploy_schema(SINGLE_ENGINE)
print(f'\n\u2713 ops_* tables: {len(list_ops_tables(SINGLE_ENGINE))}')
print(f'\u2713 vw_ops_* views: {len(list_ops_views(SINGLE_ENGINE))}')
""")

    code(r"""# ============================================================================
# CELL: Hierarchy Generation (building -> unit -> room-attribute extension)
# ============================================================================
print('Generating operational hierarchy...')
hierarchy_counts = generate_hierarchy(SINGLE_ENGINE, seed=RANDOM_SEED)
print(f"  \u2713 buildings: {hierarchy_counts['buildings']}, units: {hierarchy_counts['units']}, room attributes: {hierarchy_counts['room_attributes']}")
""")

    code(r"""# ============================================================================
# CELL: Initial Bed/Room Operational State (from existing patient placements)
# ============================================================================
print('Initializing bed/room operational state from patient_bed_assignments...')
bed_state = initialize_bed_state(SINGLE_ENGINE)
room_state = initialize_room_state(SINGLE_ENGINE)
occupied_now = int((bed_state['occupancy_status'] == 'Occupied').sum()) if not bed_state.empty else 0
print(f'  \u2713 ops_bed_state rows: {len(bed_state)} ({occupied_now} Occupied)')
print(f'  \u2713 ops_room_state rows: {len(room_state)}')
""")

    code(r"""# ============================================================================
# CELL: Staffing Generation (shifts, staff, current-shift assignments, coverage)
# ============================================================================
print('Generating staffing...')
shifts = generate_shifts(SINGLE_ENGINE)
staff = generate_staff(SINGLE_ENGINE, seed=RANDOM_SEED)
assignments = generate_staff_assignments(SINGLE_ENGINE)
staffing_state = compute_staffing_state(SINGLE_ENGINE)
print(f'  \u2713 shifts: {len(shifts)}, staff: {len(staff)}, active assignments: {len(assignments)}, units staffed: {len(staffing_state)}')
""")

    code(r"""# ============================================================================
# CELL: Equipment Generation (inventory + initial state)
# ============================================================================
print('Generating equipment...')
equipment = generate_equipment(SINGLE_ENGINE, seed=RANDOM_SEED)
equipment_state = initialize_equipment_state(SINGLE_ENGINE)
print(f'  \u2713 equipment: {len(equipment)}, equipment_state rows: {len(equipment_state)}')
""")

    code(r"""# ============================================================================
# CELL: Initial Discharge-Readiness Seeding + Initial Alert Evaluation
# ============================================================================
print('Seeding discharge-readiness for already-occupied beds...')
seeded = seed_discharge_readiness_for_occupied(SINGLE_ENGINE)
print(f'  \u2713 discharge-readiness rows seeded: {seeded}')

print('Running initial alert evaluation (NORMAL_OPERATIONS baseline)...')
initial_scenario = get_scenario_profile('NORMAL_OPERATIONS')
alert_result = evaluate_alerts(SINGLE_ENGINE, pd.Timestamp.utcnow().tz_localize(None), None, initial_scenario)
print(f"  \u2713 alerts opened: {alert_result['opened']}, escalated: {alert_result['escalated']}, resolved: {alert_result['resolved']}")
""")

    code(r"""# ============================================================================
# CELL: Simulation-Control Row Seeding (defaults for the Realtime Simulator)
# ============================================================================
control = ensure_control_row(
    SINGLE_ENGINE, SIMULATOR_NAME, SCENARIO_NAME, UPDATE_INTERVAL_SECONDS, SPEED_MULTIPLIER, RANDOM_SEED, SELECTED_HOSPITAL_ID
)
print(f"  \u2713 ops_simulation_control ready for '{SIMULATOR_NAME}': requested_state={control['requested_state']}, scenario={control['scenario_name']}")
""")

    code(r"""# ============================================================================
# CELL: Validation Queries (PASS/WARN/FAIL summary)
# ============================================================================
results = run_all_checks(SINGLE_ENGINE)
overall = print_validation_summary(results)
""")

    md(r"""## Summary & next steps

If the overall validation status above is **PASS** (or an acceptable **WARN**
for the informational bed-count reconciliation check), the operations schema
is ready.

**Next step:** open `Hospital_Operations_Realtime_Simulator.ipynb` and run it
to start producing continuous, believable operational events (admissions,
transfers, discharges, staffing/equipment changes, alerts) written to the
`ops_*` tables and readable through the `vw_ops_*` snapshot views.

To reset and start over (drops ONLY `ops_*`/`vw_ops_*` objects -- never
touches clinical tables): `drop_schema(SINGLE_ENGINE)`, then re-run this
notebook from the top.
""")

    nb['cells'] = cells
    nb['metadata'] = {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                       'language_info': {'name': 'python'}}
    return nb


# ============================================================================
# Notebook 2: Hospital_Operations_Realtime_Simulator.ipynb
# ============================================================================

CELL_REALTIME_ENGINE = r"""# ============================================================================
# CELL: Real-Time Simulation Loop
# Reads ops_simulation_control every iteration (RUN/PAUSE/STOP). Simulated
# time = simulated_start + (wall_elapsed * SPEED_MULTIPLIER). A
# KeyboardInterrupt (stopping this cell) triggers a graceful shutdown:
# final checkpoint + run marked STOPPED_BY_USER.
# ============================================================================

def _simulated_now(sim_time_base, wall_start, speed_multiplier):
    wall_elapsed_seconds = time.monotonic() - wall_start
    return sim_time_base + pd.Timedelta(seconds=wall_elapsed_seconds * speed_multiplier)


def reset_current_state(engine=None):
    '''Optional demo helper (RESET_CURRENT_STATE=True): clears current-state
    tables only (never the append-only event tables or reference/hierarchy
    tables), then re-seeds bed/room state from patient_bed_assignments.'''
    engine = engine or SINGLE_ENGINE
    print('RESET_CURRENT_STATE=True -- clearing current-state tables...')
    with transaction(engine) as conn:
        for t in ('ops_operational_alert', 'ops_discharge_readiness', 'ops_staffing_state',
                  'ops_equipment_state', 'ops_room_state', 'ops_bed_state'):
            conn.execute(text(f'DELETE FROM dbo.{t}'))
    initialize_bed_state(engine)
    initialize_room_state(engine)
    initialize_equipment_state(engine)
    print('  \u2713 current-state tables reset and re-seeded.')


def run_one_iteration(engine, run_id, iteration_number, simulated_now, scenario, rng):
    metrics = {'admitted': 0, 'discharge_progressed': 0, 'discharged': 0, 'transferred': 0,
               'rooms_cleaned': 0, 'equipment_events': 0, 'equipment_failures': 0, 'equipment_recoveries': 0,
               'alerts_opened': 0, 'alerts_escalated': 0, 'alerts_resolved': 0}

    if ENABLE_PATIENT_FLOW:
        metrics.update(simulate_patient_flow_iteration(engine, simulated_now, run_id, scenario, BATCH_SIZE, rng))
        metrics['rooms_cleaned'] = simulate_room_cleaning_iteration(engine, run_id, rng)

    if ENABLE_STAFFING_EVENTS:
        compute_staffing_state(engine, run_id, staffing_absence_rate=scenario.staffing_absence_rate)

    if ENABLE_EQUIPMENT_EVENTS:
        eq_metrics = simulate_equipment_iteration(engine, simulated_now, run_id, scenario.equipment_failure_rate, BATCH_SIZE, rng)
        metrics['equipment_events'] = eq_metrics['events']
        metrics['equipment_failures'] = eq_metrics['failures']
        metrics['equipment_recoveries'] = eq_metrics['recoveries']

    if ENABLE_ALERTS:
        alert_metrics = evaluate_alerts(engine, simulated_now, run_id, scenario)
        metrics['alerts_opened'] = alert_metrics['opened']
        metrics['alerts_escalated'] = alert_metrics['escalated']
        metrics['alerts_resolved'] = alert_metrics['resolved']

    if ENABLE_SNAPSHOT_REFRESH:
        refresh_snapshots(engine, run_id)

    return metrics


def run_loop(engine=None):
    engine = engine or SINGLE_ENGINE
    ensure_control_row(engine, SIMULATOR_NAME, SCENARIO_NAME, UPDATE_INTERVAL_SECONDS, SPEED_MULTIPLIER, RANDOM_SEED, SELECTED_HOSPITAL_ID)
    # Starting this cell always means "run" -- force past any stale PAUSE/STOP left over
    # from a previous session (e.g. someone stopped an earlier run and never reset it).
    set_requested_state(engine, SIMULATOR_NAME, 'RUN', updated_by='run_loop_start')

    if RESET_CURRENT_STATE:
        reset_current_state(engine)

    resumable = find_resumable_run(engine, SIMULATOR_NAME) if RESUME_FROM_CHECKPOINT else None
    if resumable is not None:
        run_id = int(resumable['simulation_run_id'])
        cp = load_latest_checkpoint(engine, SIMULATOR_NAME, run_id)
        start_iteration = int(cp['last_completed_iteration']) + 1 if cp else 1
        sim_time_base = pd.Timestamp(cp['simulated_datetime']) if cp and cp.get('simulated_datetime') is not None else pd.Timestamp.utcnow().tz_localize(None)
        print(f'Resuming run {run_id} from iteration {start_iteration} (simulated time {sim_time_base}).')
    else:
        run_id = start_run(engine, SIMULATOR_NAME, SCENARIO_NAME, RANDOM_SEED, {
            'update_interval_seconds': UPDATE_INTERVAL_SECONDS, 'speed_multiplier': SPEED_MULTIPLIER,
            'batch_size': BATCH_SIZE, 'selected_hospital_id': SELECTED_HOSPITAL_ID,
        })
        start_iteration = 1
        sim_time_base = pd.Timestamp.utcnow().tz_localize(None)
        print(f'Started new run {run_id} (scenario={SCENARIO_NAME}).')

    scenario = get_scenario_profile(SCENARIO_NAME)
    rng = random.Random(RANDOM_SEED)
    wall_start = time.monotonic()
    loop_start = time.monotonic()
    iteration = start_iteration
    consecutive_errors = 0
    totals = {k: 0 for k in ['admitted', 'discharged', 'transferred', 'alerts_opened', 'alerts_resolved']}
    final_status = 'COMPLETED'

    try:
        while True:
            control = get_control_state(engine, SIMULATOR_NAME) or {}
            requested_state = control.get('requested_state', 'RUN')

            if requested_state == 'STOP':
                print('STOP requested via ops_simulation_control -- exiting cleanly.')
                final_status = 'STOPPED_BY_USER'
                break
            if requested_state == 'PAUSE':
                update_heartbeat(engine, run_id, iteration - 1, consecutive_errors)
                print(heartbeat_line(run_id=run_id, state='PAUSED', iteration=iteration))
                time.sleep(UPDATE_INTERVAL_SECONDS)
                continue

            if MAX_ITERATIONS and iteration > MAX_ITERATIONS:
                print(f'Reached MAX_ITERATIONS={MAX_ITERATIONS} -- stopping.')
                break
            if MAX_RUNTIME_MINUTES and (time.monotonic() - loop_start) / 60.0 >= MAX_RUNTIME_MINUTES:
                print(f'Reached MAX_RUNTIME_MINUTES={MAX_RUNTIME_MINUTES} -- stopping.')
                break

            simulated_now = _simulated_now(sim_time_base, wall_start, SPEED_MULTIPLIER)
            iter_start = time.monotonic()
            try:
                metrics = run_one_iteration(engine, run_id, iteration, simulated_now, scenario, rng)
                consecutive_errors = 0
            except Exception as exc:
                consecutive_errors += 1
                print(f'Iteration {iteration} failed ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {exc}')
                try:
                    log_event(engine, run_id, iteration, 'Error', 'iteration_failed', status='ERROR', message=str(exc))
                except Exception as log_exc:
                    print(f'  (also failed to write the error to ops_simulation_event_log: {log_exc})')
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print('Max consecutive errors reached -- stopping.')
                    final_status = 'ERROR'
                    break
                time.sleep(min(30, 2 ** consecutive_errors))
                continue

            for k in totals:
                totals[k] += metrics.get(k, 0)

            write_ms = round((time.monotonic() - iter_start) * 1000, 1)
            update_heartbeat(engine, run_id, iteration, consecutive_errors)
            if iteration % CHECKPOINT_INTERVAL_ITERATIONS == 0:
                save_checkpoint(engine, SIMULATOR_NAME, run_id, iteration, simulated_now)

            print(heartbeat_line(
                run_id=run_id, scenario=SCENARIO_NAME, state='RUN', iteration=iteration,
                sim_time=simulated_now.isoformat(sep=' ', timespec='seconds'),
                admitted=metrics['admitted'], discharged=metrics['discharged'], transferred=metrics['transferred'],
                beds_changed=metrics['rooms_cleaned'], equip_events=metrics['equipment_events'],
                alerts_opened=metrics['alerts_opened'], alerts_resolved=metrics['alerts_resolved'],
                write_ms=write_ms, errors=consecutive_errors,
                next_checkpoint_in=CHECKPOINT_INTERVAL_ITERATIONS - (iteration % CHECKPOINT_INTERVAL_ITERATIONS),
            ))

            iteration += 1
            time.sleep(UPDATE_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print('KeyboardInterrupt -- shutting down gracefully.')
        final_status = 'STOPPED_BY_USER'

    save_checkpoint(engine, SIMULATOR_NAME, run_id, iteration - 1, _simulated_now(sim_time_base, wall_start, SPEED_MULTIPLIER))
    complete_run(engine, run_id, final_status)
    summary = {'run_id': run_id, 'final_status': final_status, 'iterations_completed': iteration - 1, **totals}
    print(f'\nRun {run_id} finished with status {final_status} after {iteration - 1} iteration(s).')
    return summary
"""


def build_realtime_notebook():
    nb = nbf.v4.new_notebook()
    cells = []
    md = lambda src: cells.append(nbf.v4.new_markdown_cell(src))
    code = lambda src: cells.append(nbf.v4.new_code_cell(src))

    md(r"""# Hospital Operations -- Real-Time Simulator (Microsoft Fabric)

**SYNTHETIC DEMONSTRATION DATA ONLY -- not derived from or usable for real
clinical decision-making.** Acuity, risk, discharge-readiness and alert
outputs in this notebook are simulated operational signals for demo purposes.

This notebook runs a continuous loop that produces small, believable
operational changes (admissions, transfers, discharges, staffing/equipment
status changes, alerts) and writes them to the `ops_*` tables created by
`Hospital_Operations_Setup.ipynb`. It never modifies clinical tables owned by
the Healthcare Data Generator.

## Prerequisites
Run `Hospital_Operations_Setup.ipynb` at least once first.

## Controlling a running simulator
This loop reads `ops_simulation_control.requested_state` every iteration:
- `RUN` (default) -- keep going
- `PAUSE` -- heartbeat and wait, without ending the run
- `STOP` -- exit cleanly, mark the run `STOPPED_BY_USER`

From another notebook cell (or a separate notebook connected to the same
database), call:
```python
set_requested_state(SINGLE_ENGINE, 'Hospital_Operations_Realtime_Simulator', 'PAUSE')  # or 'RUN' / 'STOP'
```
Interrupting this cell (Fabric "Cancel" / Jupyter "Interrupt Kernel") also
triggers a graceful shutdown -- a final checkpoint is saved and the run is
marked `STOPPED_BY_USER` instead of being left `RUNNING` forever.

## Scenarios
`NORMAL_OPERATIONS`, `FRIDAY_ED_SURGE`, `WINTER_RESPIRATORY_SURGE`,
`ICU_CAPACITY_CRISIS`, `STAFFING_SHORTAGE`, `EQUIPMENT_FAILURE`,
`DISCHARGE_BOTTLENECK` -- set via `SCENARIO_NAME` (config cell) or the
`HOSPITAL_OPS_SCENARIO` env var. Scenarios are configuration profiles (tunable
probabilities/thresholds), not separate code paths.
""")

    add_shared_cells(md, code, simulator_name="Hospital_Operations_Realtime_Simulator")

    code(CELL_REALTIME_ENGINE)

    code(r"""# ============================================================================
# CELL: Preflight -- confirm the operations schema exists before looping
# ============================================================================
existing_ops_tables = list_ops_tables(SINGLE_ENGINE)
if not existing_ops_tables:
    raise RuntimeError('No ops_* tables found -- run Hospital_Operations_Setup.ipynb first.')
print(f'\u2713 Found {len(existing_ops_tables)} ops_* tables. Ready to start the real-time loop.')
print(f'Parameters: scenario={SCENARIO_NAME}, update_interval={UPDATE_INTERVAL_SECONDS}s, speed_multiplier={SPEED_MULTIPLIER}x, '
      f'max_iterations={MAX_ITERATIONS or "unlimited"}, max_runtime_minutes={MAX_RUNTIME_MINUTES or "unlimited"}')
""")

    code(r"""# ============================================================================
# CELL: Main Loop -- runs until STOP / MAX_ITERATIONS / MAX_RUNTIME_MINUTES /
# manual interrupt. Safe to interrupt this cell at any time.
# ============================================================================
run_summary = run_loop(SINGLE_ENGINE)
run_summary
""")

    md(r"""## Run summary & diagnostics

The cell above prints a compact heartbeat every iteration and returns a final
summary dict (`run_id`, `final_status`, `iterations_completed`, totals for
admitted/discharged/transferred/alerts).

Useful follow-up queries:
```python
query_db("SELECT * FROM dbo.ops_simulation_run ORDER BY simulation_run_id DESC")
query_db("SELECT TOP 50 * FROM dbo.ops_simulation_event_log WHERE simulation_run_id = :rid ORDER BY simulation_event_log_id DESC", SINGLE_ENGINE, {'rid': run_summary['run_id']})
query_db("SELECT * FROM dbo.vw_ops_active_alerts")
query_db("SELECT * FROM dbo.vw_ops_health_system_snapshot")
run_all_checks(SINGLE_ENGINE)  # re-run PASS/WARN/FAIL validation after the loop stops
```

**Pause / resume / stop without restarting the kernel** (run from a new cell
while the loop above is still executing, or from another notebook connected
to the same database):
```python
set_requested_state(SINGLE_ENGINE, SIMULATOR_NAME, 'PAUSE')
set_requested_state(SINGLE_ENGINE, SIMULATOR_NAME, 'RUN')
set_requested_state(SINGLE_ENGINE, SIMULATOR_NAME, 'STOP')
```

**Reset and start clean** (clears current-state only, never event history or
clinical tables): set `RESET_CURRENT_STATE = True` in the config cell and
re-run from the top, or call `reset_current_state(SINGLE_ENGINE)` directly.
""")

    nb['cells'] = cells
    nb['metadata'] = {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                       'language_info': {'name': 'python'}}
    return nb


if __name__ == '__main__':
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)

    setup_nb = build_setup_notebook()
    setup_path = NOTEBOOKS_DIR / 'Hospital_Operations_Setup.ipynb'
    with open(setup_path, 'w', encoding='utf-8') as f:
        nbf.write(setup_nb, f)
    print(f'Wrote {setup_path}')

    realtime_nb = build_realtime_notebook()
    realtime_path = NOTEBOOKS_DIR / 'Hospital_Operations_Realtime_Simulator.ipynb'
    with open(realtime_path, 'w', encoding='utf-8') as f:
        nbf.write(realtime_nb, f)
    print(f'Wrote {realtime_path}')
