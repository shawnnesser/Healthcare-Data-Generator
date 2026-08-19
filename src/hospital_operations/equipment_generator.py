"""Synthetic equipment inventory generation, seeded by unit type.

Equipment counts are derived from EQUIPMENT_BY_UNIT_TYPE in models.py, either
as a fixed count per unit or a ratio of the unit's licensed bed count.
Idempotent: only generates equipment for units that don't already have any.
"""
from __future__ import annotations

import random
from typing import Optional

import pandas as pd
from faker import Faker
from sqlalchemy.engine import Engine

from .db import get_next_id, query_db, transaction, upsert_row
from .models import CRITICAL_EQUIPMENT_TYPES, EQUIPMENT_BY_UNIT_TYPE

_MANUFACTURERS = ["Contoso Med", "Fabrikam Health", "Northwind Devices", "AdventureWorks Medical"]


def _resolve_count(count_expr, licensed_beds: int) -> int:
    if isinstance(count_expr, tuple) and count_expr[0] == "per_bed":
        return max(1, int(-(-licensed_beds * count_expr[1] // 1)))  # ceil
    return int(count_expr)


def generate_equipment(engine: Engine, seed: Optional[int] = None) -> pd.DataFrame:
    units = query_db("SELECT unit_id, hospital_id, building_id, source_floor_number, unit_type, licensed_bed_count FROM dbo.ops_unit", engine)
    if units.empty:
        raise RuntimeError("No ops_unit rows found -- run hierarchy_generator.generate_hierarchy() first.")
    existing = query_db("SELECT DISTINCT unit_id FROM dbo.ops_equipment", engine)
    equipped_units = set(existing["unit_id"].tolist()) if not existing.empty else set()

    fake = Faker()
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    rng = random.Random(seed)

    to_equip = units[~units["unit_id"].isin(equipped_units)]
    if not to_equip.empty:
        next_id = get_next_id("ops_equipment", "equipment_id", engine)
        with transaction(engine) as conn:
            for _, u in to_equip.iterrows():
                unit_type = u["unit_type"] if pd.notna(u["unit_type"]) else "default"
                plan = EQUIPMENT_BY_UNIT_TYPE.get(unit_type, EQUIPMENT_BY_UNIT_TYPE["default"])
                for equipment_type, count_expr in plan:
                    count = _resolve_count(count_expr, int(u["licensed_bed_count"]) or 1)
                    for _ in range(count):
                        criticality = "Critical" if equipment_type in CRITICAL_EQUIPMENT_TYPES else "Standard"
                        upsert_row(conn, "ops_equipment", ["equipment_id"], {
                            "equipment_id": next_id,
                            "hospital_id": int(u["hospital_id"]),
                            "building_id": int(u["building_id"]),
                            "floor_number": int(u["source_floor_number"]),
                            "unit_id": int(u["unit_id"]),
                            "room_id": None,
                            "equipment_type": equipment_type,
                            "manufacturer": rng.choice(_MANUFACTURERS),
                            "model": f"{equipment_type.split()[0][:3].upper()}-{rng.randint(100, 999)}",
                            "synthetic_serial_number": f"SN-{next_id:07d}",
                            "criticality": criticality,
                            "installation_date": (pd.Timestamp.utcnow() - pd.Timedelta(days=rng.randint(30, 2000))).date(),
                            "maintenance_interval_days": 90 if criticality == "Critical" else 180,
                            "active_flag": True,
                            "created_datetime": pd.Timestamp.utcnow().tz_localize(None),
                            "updated_datetime": pd.Timestamp.utcnow().tz_localize(None),
                        })
                        next_id += 1
    return query_db("SELECT * FROM dbo.ops_equipment", engine)


def initialize_equipment_state(engine: Engine, run_id: Optional[int] = None) -> pd.DataFrame:
    """Seed ops_equipment_state as Available/Idle for any equipment that
    doesn't yet have a state row."""
    equipment = query_db("SELECT equipment_id, maintenance_interval_days FROM dbo.ops_equipment", engine)
    existing = query_db("SELECT equipment_id FROM dbo.ops_equipment_state", engine)
    existing_ids = set(existing["equipment_id"].tolist()) if not existing.empty else set()
    to_init = equipment[~equipment["equipment_id"].isin(existing_ids)]
    now = pd.Timestamp.utcnow().tz_localize(None)
    if not to_init.empty:
        with transaction(engine) as conn:
            for _, eq in to_init.iterrows():
                upsert_row(conn, "ops_equipment_state", ["equipment_id"], {
                    "equipment_id": int(eq["equipment_id"]),
                    "status": "Available", "availability_status": "Available", "utilization_status": "Idle",
                    "battery_pct": 100.0, "temperature": None, "pressure": None, "error_code": None,
                    "maintenance_due_date": (now + pd.Timedelta(days=int(eq["maintenance_interval_days"]))).date(),
                    "last_seen_datetime": now, "updated_datetime": now, "simulation_run_id": run_id,
                })
    return query_db("SELECT * FROM dbo.ops_equipment_state", engine)
