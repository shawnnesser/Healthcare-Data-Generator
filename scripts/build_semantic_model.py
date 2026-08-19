"""
Build script: generates
  1. docs/ERD_Diagram.jpg -- an entity-relationship diagram covering the
     Healthcare Data Generator clinical tables AND the Hospital Operations
     ops_* tables, and
  2. fabric_items/Healthcare_Data_Model/{model.bim,definition.pbism} -- a
     Power BI semantic model (TMSL format) over the SAME two sets of tables,
     deployable to Fabric via scripts/deploy_semantic_model.py.

Both artifacts are generated from the SAME live schema (fetched via
INFORMATION_SCHEMA-equivalent sys.tables/sys.columns) and the SAME hand
-curated relationship list below, so the diagram and the semantic model never
drift apart. Re-run this script any time the schema changes:

    python scripts/build_semantic_model.py

Storage mode design (composite model):
  - IMPORT: small/slow-changing reference & dimension tables (hospitals,
    departments, doctors, patients, insurance, date_dim, floors, rooms, beds,
    and the Hospital Operations reference/hierarchy tables ops_building,
    ops_unit, ops_room_attribute, ops_shift, ops_staff, ops_equipment).
  - DIRECTQUERY: large/fast-changing fact & event tables (encounters,
    admissions, diagnoses, procedures, medications, labs, billing,
    hospital_department_beds, patient_bed_assignments) AND every remaining
    Hospital Operations current-state/event/control table (ops_bed_state,
    ops_room_state, ops_staffing_state, ops_equipment_state,
    ops_discharge_readiness, ops_operational_alert, ops_staff_assignment,
    ops_*_event, ops_patient_movement, ops_simulation_*) -- these change
    every iteration while the Realtime Simulator is running, so DirectQuery
    is what lets report viewers see live data without a scheduled refresh.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"
MODEL_DIR = REPO_ROOT / "fabric_items" / "Healthcare_Data_Model"

FABRIC_SERVER = "5mx5ymqwo74ezmng6awpg76wx4-f2smxdwfuzzenbkp2vylj5c5ca.database.fabric.microsoft.com"
FABRIC_DB = "Healthcare ODS-63ba7f40-a784-49f0-ae76-387233bc2616"

# Tables intentionally excluded from both the ERD and the semantic model:
# copilot_test_write (scratch/test table), run_logs (legacy generator-run
# audit trail), notebook_diagnostics (headless-run debugging breadcrumbs).
EXCLUDED_TABLES = {"copilot_test_write", "run_logs", "notebook_diagnostics"}

# Tables kept in Import storage mode -- everything else in the fetched
# schema defaults to DirectQuery (see module docstring for rationale).
IMPORT_TABLES = {
    "hospitals", "departments", "doctors", "patients", "insurance", "date_dim",
    "floors", "rooms", "beds",
    "ops_building", "ops_unit", "ops_room_attribute", "ops_shift", "ops_staff", "ops_equipment",
}

CLINICAL_TABLES = [
    "date_dim", "hospitals", "departments", "hospital_department_beds", "patients", "doctors",
    "encounters", "admissions", "diagnoses", "procedures", "medications", "labs", "insurance",
    "billing", "floors", "rooms", "beds", "patient_bed_assignments",
]
OPS_TABLES = [
    "ops_building", "ops_unit", "ops_room_attribute", "ops_shift", "ops_staff", "ops_staff_assignment",
    "ops_equipment", "ops_equipment_state", "ops_equipment_event", "ops_bed_state", "ops_bed_state_event",
    "ops_room_state", "ops_staffing_state", "ops_discharge_readiness", "ops_operational_alert",
    "ops_alert_event", "ops_patient_movement", "ops_simulation_control", "ops_simulation_run",
    "ops_simulation_checkpoint", "ops_simulation_event_log",
]

# (from_table, from_column, to_table, to_column, active)
RELATIONSHIPS = [
    # --- Clinical ---
    ("departments", "hospital_id", "hospitals", "hospital_id", True),
    ("hospital_department_beds", "hospital_id", "hospitals", "hospital_id", True),
    ("hospital_department_beds", "department_id", "departments", "department_id", True),
    ("patients", "hospital_id", "hospitals", "hospital_id", True),
    ("doctors", "hospital_id", "hospitals", "hospital_id", True),
    ("encounters", "hospital_id", "hospitals", "hospital_id", True),
    ("encounters", "department_id", "departments", "department_id", True),
    ("encounters", "patient_id", "patients", "patient_id", True),
    ("encounters", "provider_id", "doctors", "provider_id", True),
    ("encounters", "encounter_date", "date_dim", "date", True),
    ("admissions", "encounter_id", "encounters", "encounter_id", True),
    ("admissions", "patient_id", "patients", "patient_id", True),
    ("admissions", "hospital_id", "hospitals", "hospital_id", True),
    ("admissions", "department_id", "departments", "department_id", True),
    ("diagnoses", "encounter_id", "encounters", "encounter_id", True),
    ("diagnoses", "patient_id", "patients", "patient_id", True),
    ("procedures", "encounter_id", "encounters", "encounter_id", True),
    ("procedures", "hospital_id", "hospitals", "hospital_id", True),
    ("medications", "encounter_id", "encounters", "encounter_id", True),
    ("medications", "patient_id", "patients", "patient_id", True),
    ("medications", "prescribing_provider_id", "doctors", "provider_id", True),
    ("labs", "encounter_id", "encounters", "encounter_id", True),
    ("labs", "patient_id", "patients", "patient_id", True),
    ("insurance", "patient_id", "patients", "patient_id", True),
    ("billing", "encounter_id", "encounters", "encounter_id", True),
    ("billing", "patient_id", "patients", "patient_id", True),
    ("floors", "hospital_id", "hospitals", "hospital_id", True),
    ("rooms", "hospital_id", "hospitals", "hospital_id", True),
    ("beds", "room_id", "rooms", "room_id", True),
    ("beds", "hospital_id", "hospitals", "hospital_id", False),  # via rooms already; avoid ambiguity
    ("patient_bed_assignments", "admission_id", "admissions", "admission_id", True),
    ("patient_bed_assignments", "patient_id", "patients", "patient_id", False),  # via admissions already
    ("patient_bed_assignments", "bed_id", "beds", "bed_id", True),
    # --- Hospital Operations ---
    ("ops_building", "hospital_id", "hospitals", "hospital_id", True),
    ("ops_unit", "hospital_id", "hospitals", "hospital_id", False),  # via ops_building already
    ("ops_unit", "building_id", "ops_building", "building_id", True),
    ("ops_unit", "department_id", "departments", "department_id", True),
    ("ops_room_attribute", "room_id", "rooms", "room_id", True),
    ("ops_room_attribute", "unit_id", "ops_unit", "unit_id", True),
    ("ops_staff", "primary_hospital_id", "hospitals", "hospital_id", False),  # via primary_unit_id already
    ("ops_staff", "primary_unit_id", "ops_unit", "unit_id", True),
    ("ops_staff", "existing_provider_id", "doctors", "provider_id", True),
    ("ops_staff_assignment", "staff_id", "ops_staff", "staff_id", True),
    ("ops_staff_assignment", "unit_id", "ops_unit", "unit_id", True),
    ("ops_staff_assignment", "shift_id", "ops_shift", "shift_id", True),
    ("ops_staff_assignment", "encounter_id", "encounters", "encounter_id", True),
    ("ops_staff_assignment", "bed_id", "beds", "bed_id", True),
    ("ops_staff_assignment", "room_id", "rooms", "room_id", True),
    ("ops_equipment", "hospital_id", "hospitals", "hospital_id", False),  # via ops_unit already
    ("ops_equipment", "building_id", "ops_building", "building_id", False),  # via ops_unit already
    ("ops_equipment", "unit_id", "ops_unit", "unit_id", True),
    ("ops_equipment", "room_id", "rooms", "room_id", True),
    ("ops_equipment_state", "equipment_id", "ops_equipment", "equipment_id", True),
    ("ops_equipment_event", "equipment_id", "ops_equipment", "equipment_id", True),
    ("ops_bed_state", "bed_id", "beds", "bed_id", True),
    ("ops_bed_state", "encounter_id", "encounters", "encounter_id", True),
    ("ops_bed_state", "patient_id", "patients", "patient_id", False),  # via encounter_id already
    ("ops_bed_state", "admission_id", "admissions", "admission_id", False),  # via encounter_id already
    ("ops_bed_state_event", "bed_id", "beds", "bed_id", True),
    ("ops_room_state", "room_id", "rooms", "room_id", True),
    ("ops_staffing_state", "unit_id", "ops_unit", "unit_id", True),
    ("ops_staffing_state", "charge_nurse_staff_id", "ops_staff", "staff_id", True),
    ("ops_discharge_readiness", "encounter_id", "encounters", "encounter_id", True),
    ("ops_discharge_readiness", "patient_id", "patients", "patient_id", False),  # via encounter_id already
    ("ops_operational_alert", "hospital_id", "hospitals", "hospital_id", False),  # via unit_id where present
    ("ops_operational_alert", "unit_id", "ops_unit", "unit_id", True),
    ("ops_operational_alert", "room_id", "rooms", "room_id", True),
    ("ops_operational_alert", "bed_id", "beds", "bed_id", True),
    ("ops_operational_alert", "equipment_id", "ops_equipment", "equipment_id", True),
    ("ops_operational_alert", "encounter_id", "encounters", "encounter_id", True),
    ("ops_alert_event", "alert_id", "ops_operational_alert", "alert_id", True),
    ("ops_patient_movement", "encounter_id", "encounters", "encounter_id", True),
    ("ops_patient_movement", "patient_id", "patients", "patient_id", False),  # via encounter_id already
    ("ops_patient_movement", "hospital_id", "hospitals", "hospital_id", False),  # via encounter_id already
    ("ops_patient_movement", "to_unit_id", "ops_unit", "unit_id", True),
    ("ops_patient_movement", "from_unit_id", "ops_unit", "unit_id", False),  # 2nd relationship to same table
    ("ops_simulation_checkpoint", "simulation_run_id", "ops_simulation_run", "simulation_run_id", True),
    ("ops_simulation_event_log", "simulation_run_id", "ops_simulation_run", "simulation_run_id", True),
]


def _get_engine_connection():
    import pyodbc
    try:
        token_json = subprocess.run(
            ["az", "account", "get-access-token", "--resource", "https://database.windows.net/"],
            capture_output=True, text=True, check=True,
        ).stdout
    except Exception:
        token_json = subprocess.run(
            ["az.cmd", "account", "get-access-token", "--resource", "https://database.windows.net/"],
            capture_output=True, text=True, check=True,
        ).stdout
    token = json.loads(token_json)["accessToken"]
    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};Server=tcp:{FABRIC_SERVER},1433;"
        f"Database={FABRIC_DB};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, attrs_before={1256: token_struct}, timeout=15)


def fetch_schema() -> dict:
    conn = _get_engine_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.name AS table_name, c.name AS column_name, ty.name AS sql_type,
               c.max_length, c.precision, c.scale, c.is_nullable, c.column_id
        FROM sys.tables t
        JOIN sys.columns c ON t.object_id = c.object_id
        JOIN sys.types ty ON c.user_type_id = ty.user_type_id
        WHERE t.name NOT LIKE 'sys%'
        ORDER BY t.name, c.column_id
    """)
    schema: dict = {}
    for table_name, column_name, sql_type, max_length, precision, scale, is_nullable, column_id in cur.fetchall():
        if table_name in EXCLUDED_TABLES:
            continue
        schema.setdefault(table_name, []).append({
            "column": column_name, "sql_type": sql_type, "max_length": max_length,
            "precision": precision, "scale": scale, "nullable": bool(is_nullable),
        })
    conn.close()
    return schema


_TYPE_MAP = {
    "bigint": "int64", "int": "int64", "smallint": "int64", "tinyint": "int64",
    "bit": "boolean",
    "decimal": "decimal", "numeric": "decimal", "money": "decimal", "smallmoney": "decimal",
    "float": "double", "real": "double",
    "date": "dateTime", "datetime": "dateTime", "datetime2": "dateTime", "smalldatetime": "dateTime", "time": "string",
    "varchar": "string", "nvarchar": "string", "char": "string", "nchar": "string", "text": "string", "ntext": "string",
}


def _tom_data_type(sql_type: str) -> str:
    return _TYPE_MAP.get(sql_type.lower(), "string")


def _format_string(sql_type: str) -> str | None:
    t = sql_type.lower()
    if t in ("date",):
        return "Long Date"
    if t in ("datetime", "datetime2", "smalldatetime"):
        return "General Date"
    if t in ("decimal", "numeric", "money", "smallmoney", "float", "real"):
        return "0.00"
    return None


# Explicit single-column primary key per table (only where a true unique
# single-column key exists). Tables intentionally OMITTED here have a
# composite/natural key with no single unique column (floors: hospital_id +
# floor_number; hospital_department_beds: hospital_id + department_id +
# date) -- marking any one column "isKey" on those would fail validation on
# refresh since Analysis Services enforces uniqueness for isKey columns.
PRIMARY_KEYS = {
    "hospitals": "hospital_id", "departments": "department_id", "patients": "patient_id",
    "doctors": "provider_id", "encounters": "encounter_id", "admissions": "admission_id",
    "diagnoses": "diagnosis_id", "procedures": "procedure_id", "medications": "medication_id",
    "labs": "lab_id", "insurance": "insurance_id", "billing": "billing_id",
    "rooms": "room_id", "beds": "bed_id", "patient_bed_assignments": "assignment_id",
    "date_dim": "date",
    "ops_building": "building_id", "ops_unit": "unit_id", "ops_room_attribute": "room_id",
    "ops_shift": "shift_id", "ops_staff": "staff_id", "ops_staff_assignment": "staff_assignment_id",
    "ops_equipment": "equipment_id", "ops_equipment_state": "equipment_id",
    "ops_equipment_event": "equipment_event_id", "ops_bed_state": "bed_id",
    "ops_bed_state_event": "bed_state_event_id", "ops_room_state": "room_id",
    "ops_staffing_state": "unit_id", "ops_discharge_readiness": "encounter_id",
    "ops_operational_alert": "alert_id", "ops_alert_event": "alert_event_id",
    "ops_patient_movement": "movement_id", "ops_simulation_control": "control_id",
    "ops_simulation_run": "simulation_run_id", "ops_simulation_event_log": "simulation_event_log_id",
}


def build_table_tmsl(table_name: str, columns: list[dict], mode: str) -> dict:
    tom_columns = []
    pk_col = PRIMARY_KEYS.get(table_name)
    for col in columns:
        data_type = _tom_data_type(col["sql_type"])
        entry = {
            "name": col["column"],
            "dataType": data_type,
            "sourceColumn": col["column"],
            "summarizeBy": "none",
        }
        fmt = _format_string(col["sql_type"])
        if fmt:
            entry["formatString"] = fmt
        if col["column"] == pk_col:
            entry["isKey"] = True
        tom_columns.append(entry)

    m_expression = (
        "let\n"
        f'    Source = Sql.Database("{FABRIC_SERVER}", "{FABRIC_DB}"),\n'
        f'    dbo_Table = Source{{[Schema="dbo",Item="{table_name}"]}}[Data]\n'
        "in\n"
        "    dbo_Table"
    )
    return {
        "name": table_name,
        "columns": tom_columns,
        "partitions": [{
            "name": f"{table_name}-partition",
            "mode": mode,
            "source": {"type": "m", "expression": m_expression},
        }],
    }


def build_model_bim(schema: dict) -> dict:
    all_tables = [t for t in CLINICAL_TABLES + OPS_TABLES if t in schema]
    tables_tmsl = []
    for table_name in all_tables:
        mode = "import" if table_name in IMPORT_TABLES else "directQuery"
        tables_tmsl.append(build_table_tmsl(table_name, schema[table_name], mode))

    relationships_tmsl = []
    for i, (from_table, from_col, to_table, to_col, active) in enumerate(RELATIONSHIPS):
        if from_table not in schema or to_table not in schema:
            continue
        relationships_tmsl.append({
            "name": f"rel-{i:03d}",
            "fromTable": from_table, "fromColumn": from_col,
            "toTable": to_table, "toColumn": to_col,
            "crossFilteringBehavior": "automatic",
            **({} if active else {"isActive": False}),
        })

    return {
        "compatibilityLevel": 1567,
        "model": {
            "culture": "en-US",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "en-US",
            "tables": tables_tmsl,
            "relationships": relationships_tmsl,
            "annotations": [
                {"name": "PBI_QueryOrder", "value": json.dumps(all_tables)},
                {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
            ],
        },
    }


def build_pbism() -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "5.0",
        "settings": {"qnaEnabled": False},
    }


def write_semantic_model_files(schema: dict) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_bim = build_model_bim(schema)
    (MODEL_DIR / "model.bim").write_text(json.dumps(model_bim, indent=2), encoding="utf-8")
    (MODEL_DIR / "definition.pbism").write_text(json.dumps(build_pbism(), indent=2), encoding="utf-8")
    print(f"Wrote {MODEL_DIR / 'model.bim'} ({len(model_bim['model']['tables'])} tables, "
          f"{len(model_bim['model']['relationships'])} relationships)")
    print(f"Wrote {MODEL_DIR / 'definition.pbism'}")


def build_erd(schema: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

    clinical = [t for t in CLINICAL_TABLES if t in schema]
    ops = [t for t in OPS_TABLES if t in schema]

    def layout_columns(tables, n_cols):
        return {t: (i % n_cols, i // n_cols) for i, t in enumerate(tables)}

    clinical_pos = layout_columns(clinical, 5)
    ops_pos = layout_columns(ops, 5)
    clinical_rows = max(y for _, y in clinical_pos.values()) + 1
    ops_rows = max(y for _, y in ops_pos.values()) + 1

    box_w, box_h, gap_x, gap_y = 3.2, 1.9, 0.9, 0.9
    section_gap = 1.8

    fig_w = 5 * (box_w + gap_x) + 2
    fig_h = (clinical_rows + ops_rows) * (box_h + gap_y) + section_gap + 3
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")

    positions = {}

    def place(pos_map, rows_used, y_offset, color, label):
        for table, (col, row) in pos_map.items():
            x = 1 + col * (box_w + gap_x)
            y = fig_h - y_offset - row * (box_h + gap_y) - box_h
            positions[table] = (x, y, box_w, box_h)
            ax.add_patch(FancyBboxPatch((x, y), box_w, box_h, boxstyle="round,pad=0.06",
                                         linewidth=1.1, edgecolor="#333333", facecolor=color))
            cols = schema[table]
            pk = PRIMARY_KEYS.get(table)
            key_cols = [c["column"] for c in cols if c["column"].endswith("_id")][:6]
            title = table
            body = "\n".join(f"* {c}" if c == pk else c for c in key_cols)
            ax.text(x + box_w / 2, y + box_h - 0.28, title, ha="center", va="top",
                    fontsize=9.5, fontweight="bold")
            ax.text(x + box_w / 2, y + box_h - 0.55, body, ha="center", va="top", fontsize=7.2)
        ax.text(1, fig_h - y_offset + 0.35, label, fontsize=15, fontweight="bold")

    place(clinical_pos, clinical_rows, 0.8, "#DCE9F9", "Healthcare Data Generator -- Clinical Tables")
    place(ops_pos, ops_rows, 0.8 + clinical_rows * (box_h + gap_y) + section_gap, "#E3F3E1",
          "Hospital Operations -- ops_* Tables")

    for from_table, from_col, to_table, to_col, active in RELATIONSHIPS:
        if from_table not in positions or to_table not in positions:
            continue
        x1, y1, w1, h1 = positions[from_table]
        x2, y2, w2, h2 = positions[to_table]
        c1 = (x1 + w1 / 2, y1 + h1 / 2)
        c2 = (x2 + w2 / 2, y2 + h2 / 2)
        style = "-|>" if active else "->"
        arrow_color = "#5B7FBF" if active else "#B0B0B0"
        ax.add_patch(FancyArrowPatch(c1, c2, arrowstyle=style, mutation_scale=8,
                                      linewidth=0.6, color=arrow_color, alpha=0.55,
                                      connectionstyle="arc3,rad=0.05", shrinkA=25, shrinkB=25))

    ax.set_title(
        "Healthcare Data Generator + Hospital Operations Simulator -- Entity Relationship Diagram\n"
        "(blue = clinical, green = ops_*; solid arrow = active relationship, faint = inactive/secondary path)",
        fontsize=13, pad=20,
    )
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DOCS_DIR / "ERD_Diagram.jpg"
    fig.tight_layout()
    fig.savefig(out_path, format="jpg", pil_kwargs={"quality": 92})
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    schema = fetch_schema()
    print(f"Fetched schema for {len(schema)} tables.")
    build_erd(schema)
    write_semantic_model_files(schema)
