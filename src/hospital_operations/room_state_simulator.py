"""Room and bed operational-state initialization + light simulation.

Current-state tables (`ops_room_state`, `ops_bed_state`) are upserted, never
truncated. Initial state is derived from the existing `patient_bed_assignments`
table (whatever the generator's last run left behind) so Setup doesn't
contradict the clinical data it's building on top of.
"""
from __future__ import annotations

import random
from typing import Optional

import pandas as pd
from sqlalchemy.engine import Engine

from .db import query_db, transaction, upsert_row
from .logging_utils import get_logger

log = get_logger(__name__)


def initialize_bed_state(engine: Engine, run_id: Optional[int] = None) -> pd.DataFrame:
    """Seed ops_bed_state for every bed without one yet. Beds with an open
    `patient_bed_assignments` row start Occupied; everything else starts
    Available."""
    beds = query_db("SELECT bed_id, hospital_id FROM dbo.beds", engine)
    existing = query_db("SELECT bed_id FROM dbo.ops_bed_state", engine)
    existing_ids = set(existing["bed_id"].tolist()) if not existing.empty else set()
    open_assignments = query_db(
        "SELECT bed_id, admission_id, patient_id, assigned_datetime FROM dbo.patient_bed_assignments "
        "WHERE discharged_datetime IS NULL", engine,
    )
    open_by_bed = {int(r["bed_id"]): r for _, r in open_assignments.iterrows()} if not open_assignments.empty else {}

    # encounter_id is not stored on patient_bed_assignments; resolve it via admissions.
    admissions = query_db("SELECT admission_id, encounter_id FROM dbo.admissions", engine)
    encounter_by_admission = dict(zip(admissions["admission_id"], admissions["encounter_id"])) if not admissions.empty else {}

    to_init = beds[~beds["bed_id"].isin(existing_ids)]
    now = pd.Timestamp.utcnow().tz_localize(None)
    if not to_init.empty:
        with transaction(engine) as conn:
            for _, b in to_init.iterrows():
                bed_id = int(b["bed_id"])
                occ = open_by_bed.get(bed_id)
                if occ is not None:
                    admission_id = int(occ["admission_id"]) if pd.notna(occ["admission_id"]) else None
                    upsert_row(conn, "ops_bed_state", ["bed_id"], {
                        "bed_id": bed_id, "operational_status": "Occupied", "occupancy_status": "Occupied",
                        "encounter_id": encounter_by_admission.get(admission_id), "patient_id": int(occ["patient_id"]),
                        "admission_id": admission_id, "assigned_datetime": occ["assigned_datetime"],
                        "expected_release_datetime": None, "cleaning_required_flag": False,
                        "updated_datetime": now, "simulation_run_id": run_id,
                    })
                else:
                    upsert_row(conn, "ops_bed_state", ["bed_id"], {
                        "bed_id": bed_id, "operational_status": "Available", "occupancy_status": "Available",
                        "encounter_id": None, "patient_id": None, "admission_id": None,
                        "assigned_datetime": None, "expected_release_datetime": None, "cleaning_required_flag": False,
                        "updated_datetime": now, "simulation_run_id": run_id,
                    })
    return query_db("SELECT * FROM dbo.ops_bed_state", engine)


def initialize_room_state(engine: Engine, run_id: Optional[int] = None) -> pd.DataFrame:
    """Seed ops_room_state from current ops_bed_state aggregation."""
    rooms = query_db("SELECT room_id, bed_count FROM dbo.rooms", engine)
    existing = query_db("SELECT room_id FROM dbo.ops_room_state", engine)
    existing_ids = set(existing["room_id"].tolist()) if not existing.empty else set()
    to_init = rooms[~rooms["room_id"].isin(existing_ids)]
    now = pd.Timestamp.utcnow().tz_localize(None)
    if not to_init.empty:
        with transaction(engine) as conn:
            for _, r in to_init.iterrows():
                room_id = int(r["room_id"])
                occ = query_db(
                    f"SELECT COUNT(*) AS n FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
                    f"WHERE b.room_id = {room_id} AND bs.occupancy_status = 'Occupied'", conn,
                )
                occupied = int(occ.iloc[0]["n"]) if not occ.empty else 0
                available = max(0, int(r["bed_count"]) - occupied)
                upsert_row(conn, "ops_room_state", ["room_id"], {
                    "room_id": room_id,
                    "operational_status": "Occupied" if occupied > 0 else "Available",
                    "isolation_status": "None", "cleaning_status": "Clean", "maintenance_status": "None",
                    "current_patient_count": occupied, "available_bed_count": available,
                    "last_cleaned_datetime": now, "next_expected_available_datetime": None,
                    "updated_datetime": now, "simulation_run_id": run_id,
                })
    return query_db("SELECT * FROM dbo.ops_room_state", engine)


def refresh_room_aggregates(engine: Engine, run_id: Optional[int] = None) -> None:
    """Recompute current_patient_count/available_bed_count for every room from
    ops_bed_state (called each simulator iteration after bed transitions)."""
    rooms = query_db("SELECT room_id, bed_count FROM dbo.rooms", engine)
    now = pd.Timestamp.utcnow().tz_localize(None)
    with transaction(engine) as conn:
        for _, r in rooms.iterrows():
            room_id = int(r["room_id"])
            occ = query_db(
                f"SELECT COUNT(*) AS n FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
                f"WHERE b.room_id = {room_id} AND bs.occupancy_status = 'Occupied'", conn,
            )
            occupied = int(occ.iloc[0]["n"]) if not occ.empty else 0
            available = max(0, int(r["bed_count"]) - occupied)
            upsert_row(conn, "ops_room_state", ["room_id"], {
                "room_id": room_id,
                "operational_status": "Occupied" if occupied > 0 else "Available",
                "isolation_status": "None", "cleaning_status": "Clean", "maintenance_status": "None",
                "current_patient_count": occupied, "available_bed_count": available,
                "last_cleaned_datetime": now, "next_expected_available_datetime": None,
                "updated_datetime": now, "simulation_run_id": run_id,
            })


def simulate_room_cleaning_iteration(engine: Engine, run_id: Optional[int], rng: Optional[random.Random] = None) -> int:
    """Complete cleaning for a bounded number of rooms whose beds have all
    finished cleaning (small, believable per-iteration change)."""
    rng = rng or random.Random()
    cleaning_rooms = query_db(
        "SELECT DISTINCT r.room_id FROM dbo.rooms r JOIN dbo.beds b ON r.room_id = b.room_id "
        "JOIN dbo.ops_bed_state bs ON b.bed_id = bs.bed_id WHERE bs.occupancy_status = 'Cleaning'", engine,
    )
    changed = 0
    if not cleaning_rooms.empty:
        now = pd.Timestamp.utcnow().tz_localize(None)
        with transaction(engine) as conn:
            for _, r in cleaning_rooms.iterrows():
                if rng.random() < 0.4:  # cleaning completes this iteration
                    conn.execute(
                        __import__("sqlalchemy").text(
                            "UPDATE dbo.ops_bed_state SET occupancy_status = 'Available', operational_status = 'Available', "
                            "cleaning_required_flag = 0, updated_datetime = :now, simulation_run_id = :rid "
                            "WHERE bed_id IN (SELECT bed_id FROM dbo.beds WHERE room_id = :room_id) AND occupancy_status = 'Cleaning'"
                        ),
                        {"now": now, "rid": run_id, "room_id": int(r["room_id"])},
                    )
                    changed += 1
    if changed:
        refresh_room_aggregates(engine, run_id)
    return changed
