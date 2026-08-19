"""Physical/operational hierarchy generation: building -> unit -> room extension.

Building and unit are genuinely NEW concepts (see
docs/HOSPITAL_OPERATIONS_EXISTING_MODEL_ANALYSIS.md section 6). Room and bed
are REUSED from the existing `rooms`/`beds` tables -- this module only adds a
1:1 attribute-extension row per room, never a duplicate room/bed record.

Every function here is idempotent: re-running only inserts rows for
hospitals/floors/rooms that don't already have an ops_* counterpart, so the
Setup notebook can be safely re-run any time (including after the generator
notebook produces new hospitals/floors/rooms).
"""
from __future__ import annotations

import random
from typing import Optional

import pandas as pd
from sqlalchemy.engine import Engine

from .db import get_next_id, query_db, transaction, upsert_row

BUILDING_NAME = "Main Campus"
BUILDING_TYPE = "Acute Care"

# US-ish bounding box used only to scatter synthetic hospital coordinates
# deterministically (never a real address - see analysis doc section 9.6).
_LAT_RANGE = (30.0, 45.0)
_LON_RANGE = (-115.0, -75.0)


def generate_buildings(engine: Engine, seed: Optional[int] = None) -> pd.DataFrame:
    """Create exactly one ops_building ("Main Campus") per hospital that
    doesn't already have one. Returns the full ops_building table afterward."""
    hospitals = query_db("SELECT hospital_id, name FROM dbo.hospitals", engine)
    existing = query_db("SELECT hospital_id FROM dbo.ops_building", engine)
    existing_ids = set(existing["hospital_id"].tolist()) if not existing.empty else set()

    missing = hospitals[~hospitals["hospital_id"].isin(existing_ids)]
    if not missing.empty:
        next_id = get_next_id("ops_building", "building_id", engine)
        rng = random.Random(seed)
        with transaction(engine) as conn:
            for _, h in missing.iterrows():
                lat = round(rng.uniform(*_LAT_RANGE), 6)
                lon = round(rng.uniform(*_LON_RANGE), 6)
                upsert_row(conn, "ops_building", ["building_id"], {
                    "building_id": next_id,
                    "hospital_id": int(h["hospital_id"]),
                    "building_code": f"H{h['hospital_id']}-B1",
                    "building_name": BUILDING_NAME,
                    "building_type": BUILDING_TYPE,
                    "campus_label": f"{h['name']} Main Campus",
                    "latitude": lat,
                    "longitude": lon,
                    "floor_count": 0,  # updated by generate_units()
                    "active_flag": True,
                    "created_datetime": pd.Timestamp.utcnow().tz_localize(None),
                    "updated_datetime": pd.Timestamp.utcnow().tz_localize(None),
                })
                next_id += 1
    return query_db("SELECT * FROM dbo.ops_building", engine)


def _match_department_id(departments: pd.DataFrame, hospital_id: int, floor_department: str) -> Optional[int]:
    if departments.empty or not floor_department:
        return None
    hosp_deps = departments[departments["hospital_id"] == hospital_id]
    if hosp_deps.empty:
        return None
    floor_dep_lower = str(floor_department).lower()
    for _, dep in hosp_deps.iterrows():
        if str(dep["name"]).lower() in floor_dep_lower or floor_dep_lower in str(dep["name"]).lower():
            return int(dep["department_id"])
    return None


def generate_units(engine: Engine) -> pd.DataFrame:
    """One ops_unit per existing `floors` row (natural key hospital_id +
    floor_number), skipping floors that already have a unit."""
    floors = query_db("SELECT hospital_id, floor_number, department, bed_type, capacity FROM dbo.floors", engine)
    if floors.empty:
        raise RuntimeError(
            "No rows found in `floors` -- the Healthcare Data Generator must be run at "
            "least once before Hospital Operations Setup (see runbook prerequisites)."
        )
    departments = query_db("SELECT department_id, hospital_id, name FROM dbo.departments", engine)
    buildings = query_db("SELECT building_id, hospital_id FROM dbo.ops_building", engine)
    existing_units = query_db("SELECT hospital_id, source_floor_number FROM dbo.ops_unit", engine)
    existing_keys = set(
        zip(existing_units["hospital_id"], existing_units["source_floor_number"])
    ) if not existing_units.empty else set()

    building_by_hospital = dict(zip(buildings["hospital_id"], buildings["building_id"])) if not buildings.empty else {}

    to_create = [
        f for _, f in floors.iterrows()
        if (int(f["hospital_id"]), int(f["floor_number"])) not in existing_keys
    ]
    if to_create:
        next_id = get_next_id("ops_unit", "unit_id", engine)
        with transaction(engine) as conn:
            for f in to_create:
                hospital_id = int(f["hospital_id"])
                floor_number = int(f["floor_number"])
                dept_id = _match_department_id(departments, hospital_id, f["department"])
                capacity = int(f["capacity"]) if pd.notna(f["capacity"]) else 0
                unit_type = str(f["bed_type"]) if pd.notna(f["bed_type"]) else "Medical/Surgical"
                upsert_row(conn, "ops_unit", ["unit_id"], {
                    "unit_id": next_id,
                    "hospital_id": hospital_id,
                    "building_id": building_by_hospital.get(hospital_id, 0),
                    "source_floor_number": floor_number,
                    "source_department": str(f["department"]) if pd.notna(f["department"]) else None,
                    "department_id": dept_id,
                    "unit_code": f"H{hospital_id}-F{floor_number}",
                    "unit_name": str(f["department"]) if pd.notna(f["department"]) else f"Floor {floor_number}",
                    "unit_type": unit_type,
                    "clinical_specialty": str(f["department"]) if pd.notna(f["department"]) else None,
                    "licensed_bed_count": capacity,
                    "staffed_bed_count": capacity,
                    "nurse_ratio_target": 2.0 if unit_type == "Critical Care" else (3.0 if unit_type == "Emergency" else 4.0),
                    "active_flag": True,
                    "created_datetime": pd.Timestamp.utcnow().tz_localize(None),
                    "updated_datetime": pd.Timestamp.utcnow().tz_localize(None),
                })
                next_id += 1

    # Keep ops_building.floor_count in sync (best-effort, not a hard constraint).
    with transaction(engine) as conn:
        counts = query_db(
            "SELECT hospital_id, COUNT(DISTINCT source_floor_number) AS n FROM dbo.ops_unit GROUP BY hospital_id",
            conn,
        )
        for _, row in counts.iterrows():
            conn.execute(
                __import__("sqlalchemy").text(
                    "UPDATE dbo.ops_building SET floor_count = :n, updated_datetime = SYSUTCDATETIME() WHERE hospital_id = :h"
                ),
                {"n": int(row["n"]), "h": int(row["hospital_id"])},
            )

    return query_db("SELECT * FROM dbo.ops_unit", engine)


_ISOLATION_PRONE_TYPES = {"Critical Care", "Emergency"}


def generate_room_attributes(engine: Engine, seed: Optional[int] = None) -> pd.DataFrame:
    """1:1 extension row per existing `rooms` room (deterministic floor-plan
    coordinates + capability flags), skipping rooms that already have one."""
    rooms = query_db("SELECT room_id, hospital_id, floor_number, room_number, bed_count, room_type FROM dbo.rooms", engine)
    if rooms.empty:
        raise RuntimeError("No rows found in `rooms` -- run the Healthcare Data Generator first.")
    units = query_db("SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit", engine)
    existing = query_db("SELECT room_id FROM dbo.ops_room_attribute", engine)
    existing_ids = set(existing["room_id"].tolist()) if not existing.empty else set()

    unit_lookup = {
        (int(u["hospital_id"]), int(u["source_floor_number"])): (int(u["unit_id"]), u["unit_type"])
        for _, u in units.iterrows()
    }

    to_create = rooms[~rooms["room_id"].isin(existing_ids)]
    if not to_create.empty:
        rng = random.Random(seed)
        cols_per_row = 8
        cell_size = 4.0
        with transaction(engine) as conn:
            for _, r in to_create.iterrows():
                key = (int(r["hospital_id"]), int(r["floor_number"]))
                unit_id, unit_type = unit_lookup.get(key, (0, "Medical/Surgical"))
                room_number = int(r["room_number"])
                floor_x = ((room_number - 1) % cols_per_row) * cell_size
                floor_y = ((room_number - 1) // cols_per_row) * cell_size
                isolation_prob = 0.30 if unit_type in _ISOLATION_PRONE_TYPES else 0.05
                isolation = rng.random() < isolation_prob
                neg_pressure = isolation and rng.random() < 0.5
                telemetry = unit_type in {"Critical Care", "Medical/Surgical", "Emergency"} and rng.random() < 0.7
                upsert_row(conn, "ops_room_attribute", ["room_id"], {
                    "room_id": int(r["room_id"]),
                    "unit_id": unit_id,
                    "room_name": f"Room {room_number}",
                    "isolation_capable_flag": isolation,
                    "negative_pressure_flag": neg_pressure,
                    "telemetry_capable_flag": telemetry,
                    "private_room_flag": str(r["room_type"]) == "Single",
                    "floor_x": floor_x,
                    "floor_y": floor_y,
                    "width": cell_size - 0.5,
                    "height": cell_size - 0.5,
                    "active_flag": True,
                    "created_datetime": pd.Timestamp.utcnow().tz_localize(None),
                    "updated_datetime": pd.Timestamp.utcnow().tz_localize(None),
                })
    return query_db("SELECT * FROM dbo.ops_room_attribute", engine)


def generate_hierarchy(engine: Engine, seed: Optional[int] = None) -> dict:
    """Convenience wrapper running building -> unit -> room-attribute generation in order."""
    buildings = generate_buildings(engine, seed=seed)
    units = generate_units(engine)
    rooms = generate_room_attributes(engine, seed=seed)
    return {"buildings": len(buildings), "units": len(units), "room_attributes": len(rooms)}
