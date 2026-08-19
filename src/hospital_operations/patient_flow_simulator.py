"""Patient-flow simulation: admission -> bed assignment -> internal transfer ->
discharge-pending -> discharge -> cleaning -> available.

IMPORTANT scope boundary (see docs/HOSPITAL_OPERATIONS_ARCHITECTURE.md): this
module NEVER writes to the clinical `admissions`/`encounters` tables owned by
the Healthcare Data Generator. "Discharge" here means the OPERATIONAL bed is
released (ops_bed_state -> Cleaning -> Available); the clinical
`admissions.discharge_datetime` remains whatever the generator itself set (or
NULL). This keeps the two systems decoupled per Principle #1/#2.

All timestamps advance using the simulator's `simulated_datetime` (wall clock
* speed_multiplier, computed by realtime_engine.py) so movements stay
internally consistent (a transfer can't complete before it starts, etc.).
"""
from __future__ import annotations

import random
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import get_next_id, insert_rows, query_db, transaction, upsert_row
from .models import ScenarioProfile

# Minimum simulated dwell time (hours) before a bed becomes eligible for
# discharge-pending consideration -- keeps demos from discharging patients
# the instant they're admitted.
_MIN_DWELL_HOURS = 2.0


def _pick_target_unit(units: pd.DataFrame, hospital_id: int, encounter_type: str, rng: random.Random) -> Optional[pd.Series]:
    hosp_units = units[units["hospital_id"] == hospital_id]
    if hosp_units.empty:
        return None
    if encounter_type == "Emergency":
        preferred = hosp_units[hosp_units["unit_type"] == "Emergency"]
        if not preferred.empty:
            return preferred.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]
    non_critical = hosp_units[hosp_units["unit_type"] != "Critical Care"]
    pool = non_critical if not non_critical.empty else hosp_units
    return pool.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]


def _find_available_bed(engine: Engine, hospital_id: int, floor_number: int) -> Optional[int]:
    df = query_db(
        "SELECT TOP 1 bs.bed_id FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
        "WHERE b.hospital_id = :h AND b.floor_number = :f AND bs.occupancy_status = 'Available' ORDER BY bs.bed_id",
        engine, {"h": hospital_id, "f": floor_number},
    )
    return int(df.iloc[0]["bed_id"]) if not df.empty else None


def admit_patients(engine: Engine, simulated_now: pd.Timestamp, run_id: int, batch_size: int,
                    scenario: ScenarioProfile, rng: random.Random) -> int:
    """Assign an operational bed to up to `batch_size` active admissions that
    don't yet have one. Returns count of admissions processed."""
    candidates = query_db(
        "SELECT TOP (:lim) a.admission_id, a.encounter_id, a.patient_id, a.hospital_id, e.encounter_type "
        "FROM dbo.admissions a JOIN dbo.encounters e ON a.encounter_id = e.encounter_id "
        "WHERE a.discharge_datetime IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM dbo.ops_bed_state bs WHERE bs.admission_id = a.admission_id) "
        "ORDER BY a.admit_datetime DESC",
        engine, {"lim": batch_size},
    )
    if candidates.empty:
        return 0
    units = query_db("SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit", engine)
    processed = 0
    bed_event_id = get_next_id("ops_bed_state_event", "bed_state_event_id", engine)
    movement_id = get_next_id("ops_patient_movement", "movement_id", engine)
    with transaction(engine) as conn:
        for _, cand in candidates.iterrows():
            unit = _pick_target_unit(units, int(cand["hospital_id"]), cand["encounter_type"], rng)
            if unit is None:
                continue
            bed_id = _find_available_bed(conn, int(cand["hospital_id"]), int(unit["source_floor_number"]))
            if bed_id is None:
                continue  # no capacity -- alert_engine will surface this as a capacity alert
            upsert_row(conn, "ops_bed_state", ["bed_id"], {
                "bed_id": bed_id, "operational_status": "Occupied", "occupancy_status": "Occupied",
                "encounter_id": int(cand["encounter_id"]), "patient_id": int(cand["patient_id"]),
                "admission_id": int(cand["admission_id"]), "assigned_datetime": simulated_now,
                "expected_release_datetime": None, "cleaning_required_flag": False,
                "updated_datetime": simulated_now, "simulation_run_id": run_id,
            })
            insert_rows(conn, "ops_bed_state_event", [{
                "bed_state_event_id": bed_event_id, "bed_id": bed_id, "event_datetime": simulated_now,
                "event_type": "Admission", "status_before": "Available", "status_after": "Occupied",
                "encounter_id": int(cand["encounter_id"]), "patient_id": int(cand["patient_id"]),
                "reason": "Simulated admission bed assignment", "simulation_run_id": run_id,
            }])
            insert_rows(conn, "ops_patient_movement", [{
                "movement_id": movement_id, "encounter_id": int(cand["encounter_id"]), "patient_id": int(cand["patient_id"]),
                "hospital_id": int(cand["hospital_id"]), "from_unit_id": None, "from_room_id": None, "from_bed_id": None,
                "to_unit_id": int(unit["unit_id"]), "to_room_id": None, "to_bed_id": bed_id,
                "requested_datetime": simulated_now, "accepted_datetime": simulated_now,
                "started_datetime": simulated_now, "completed_datetime": simulated_now,
                "movement_type": "Admission", "movement_status": "Completed", "priority": "Routine",
                "delay_reason": None, "simulation_run_id": run_id,
            }])
            upsert_row(conn, "ops_discharge_readiness", ["encounter_id"], {
                "encounter_id": int(cand["encounter_id"]), "patient_id": int(cand["patient_id"]),
                "expected_discharge_datetime": None, "readiness_status": "Not Ready",
                "clinical_ready_flag": False, "medication_ready_flag": False, "transport_ready_flag": False,
                "destination_ready_flag": False, "education_complete_flag": False,
                "outstanding_barrier_count": 1, "primary_barrier": "Simulated: awaiting clinical progress",
                "updated_datetime": simulated_now, "simulation_run_id": run_id,
            })
            bed_event_id += 1
            movement_id += 1
            processed += 1
    return processed


def advance_discharge_readiness(engine: Engine, simulated_now: pd.Timestamp, run_id: int,
                                 batch_size: int, discharge_delay_multiplier: float, rng: random.Random) -> int:
    """Probabilistically progress discharge-readiness flags for occupied beds
    (all values explicitly SIMULATED, never a real clinical judgement)."""
    occupied = query_db(
        "SELECT TOP (:lim) dr.encounter_id, dr.outstanding_barrier_count FROM dbo.ops_discharge_readiness dr "
        "WHERE dr.readiness_status <> 'Ready' ORDER BY dr.updated_datetime ASC",
        engine, {"lim": batch_size},
    )
    if occupied.empty:
        return 0
    progressed = 0
    progress_chance = max(0.02, 0.20 / max(discharge_delay_multiplier, 0.1))
    with transaction(engine) as conn:
        for _, row in occupied.iterrows():
            if rng.random() > progress_chance:
                continue
            barriers = max(0, int(row["outstanding_barrier_count"]) - 1)
            status = "Ready" if barriers == 0 else ("Pending" if barriers <= 1 else "Not Ready")
            conn.execute(text(
                "UPDATE dbo.ops_discharge_readiness SET outstanding_barrier_count = :b, readiness_status = :s, "
                "clinical_ready_flag = CASE WHEN :b = 0 THEN 1 ELSE clinical_ready_flag END, "
                "primary_barrier = CASE WHEN :b = 0 THEN NULL ELSE primary_barrier END, "
                "expected_discharge_datetime = CASE WHEN :b = 0 THEN :now ELSE expected_discharge_datetime END, "
                "updated_datetime = :now, simulation_run_id = :rid WHERE encounter_id = :eid"
            ), {"b": barriers, "s": status, "now": simulated_now, "rid": run_id, "eid": int(row["encounter_id"])})
            progressed += 1
    return progressed


def discharge_ready_patients(engine: Engine, simulated_now: pd.Timestamp, run_id: int, batch_size: int, rng: random.Random) -> int:
    """Release the operational bed for encounters whose ops_discharge_readiness
    is 'Ready' (bed -> Cleaning; does NOT touch clinical admissions table)."""
    ready = query_db(
        "SELECT TOP (:lim) bs.bed_id, bs.encounter_id, bs.patient_id, b.hospital_id FROM dbo.ops_bed_state bs "
        "JOIN dbo.beds b ON bs.bed_id = b.bed_id "
        "JOIN dbo.ops_discharge_readiness dr ON bs.encounter_id = dr.encounter_id "
        "WHERE bs.occupancy_status = 'Occupied' AND dr.readiness_status = 'Ready'",
        engine, {"lim": batch_size},
    )
    if ready.empty:
        return 0
    bed_event_id = get_next_id("ops_bed_state_event", "bed_state_event_id", engine)
    movement_id = get_next_id("ops_patient_movement", "movement_id", engine)
    released = 0
    with transaction(engine) as conn:
        for _, row in ready.iterrows():
            bed_id = int(row["bed_id"])
            upsert_row(conn, "ops_bed_state", ["bed_id"], {
                "bed_id": bed_id, "operational_status": "Cleaning", "occupancy_status": "Cleaning",
                "encounter_id": None, "patient_id": None, "admission_id": None,
                "assigned_datetime": None, "expected_release_datetime": None, "cleaning_required_flag": True,
                "updated_datetime": simulated_now, "simulation_run_id": run_id,
            })
            insert_rows(conn, "ops_bed_state_event", [{
                "bed_state_event_id": bed_event_id, "bed_id": bed_id, "event_datetime": simulated_now,
                "event_type": "Discharge", "status_before": "Occupied", "status_after": "Cleaning",
                "encounter_id": int(row["encounter_id"]), "patient_id": int(row["patient_id"]),
                "reason": "Simulated operational discharge (bed released for cleaning)", "simulation_run_id": run_id,
            }])
            insert_rows(conn, "ops_patient_movement", [{
                "movement_id": movement_id, "encounter_id": int(row["encounter_id"]), "patient_id": int(row["patient_id"]),
                "hospital_id": int(row["hospital_id"]), "from_unit_id": None, "from_room_id": None, "from_bed_id": bed_id,
                "to_unit_id": None, "to_room_id": None, "to_bed_id": None,
                "requested_datetime": simulated_now, "accepted_datetime": simulated_now,
                "started_datetime": simulated_now, "completed_datetime": simulated_now,
                "movement_type": "Discharge", "movement_status": "Completed", "priority": "Routine",
                "delay_reason": None, "simulation_run_id": run_id,
            }])
            bed_event_id += 1
            movement_id += 1
            released += 1
    return released


def transfer_patients(engine: Engine, simulated_now: pd.Timestamp, run_id: int, batch_size: int,
                       icu_pressure_multiplier: float, rng: random.Random) -> int:
    """Occasionally move an occupied patient to a different unit on the same
    hospital (e.g. escalation to a Critical Care unit)."""
    if rng.random() > min(0.5, 0.05 * icu_pressure_multiplier):
        return 0
    occupied = query_db(
        "SELECT TOP (:lim) bs.bed_id, bs.encounter_id, bs.patient_id, b.hospital_id, b.floor_number "
        "FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id WHERE bs.occupancy_status = 'Occupied' "
        "ORDER BY NEWID()", engine, {"lim": batch_size},
    )
    if occupied.empty:
        return 0
    units = query_db("SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit", engine)
    movement_id = get_next_id("ops_patient_movement", "movement_id", engine)
    bed_event_id = get_next_id("ops_bed_state_event", "bed_state_event_id", engine)
    moved = 0
    with transaction(engine) as conn:
        for _, row in occupied.iterrows():
            hosp_units = units[(units["hospital_id"] == row["hospital_id"]) & (units["source_floor_number"] != row["floor_number"])]
            if hosp_units.empty:
                continue
            target_unit = hosp_units.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]
            new_bed_id = _find_available_bed(conn, int(row["hospital_id"]), int(target_unit["source_floor_number"]))
            if new_bed_id is None:
                continue
            old_bed_id = int(row["bed_id"])
            upsert_row(conn, "ops_bed_state", ["bed_id"], {
                "bed_id": new_bed_id, "operational_status": "Occupied", "occupancy_status": "Occupied",
                "encounter_id": int(row["encounter_id"]), "patient_id": int(row["patient_id"]), "admission_id": None,
                "assigned_datetime": simulated_now, "expected_release_datetime": None, "cleaning_required_flag": False,
                "updated_datetime": simulated_now, "simulation_run_id": run_id,
            })
            upsert_row(conn, "ops_bed_state", ["bed_id"], {
                "bed_id": old_bed_id, "operational_status": "Cleaning", "occupancy_status": "Cleaning",
                "encounter_id": None, "patient_id": None, "admission_id": None,
                "assigned_datetime": None, "expected_release_datetime": None, "cleaning_required_flag": True,
                "updated_datetime": simulated_now, "simulation_run_id": run_id,
            })
            insert_rows(conn, "ops_bed_state_event", [{
                "bed_state_event_id": bed_event_id, "bed_id": old_bed_id, "event_datetime": simulated_now,
                "event_type": "Internal Transfer", "status_before": "Occupied", "status_after": "Cleaning",
                "encounter_id": int(row["encounter_id"]), "patient_id": int(row["patient_id"]),
                "reason": "Simulated internal transfer", "simulation_run_id": run_id,
            }])
            insert_rows(conn, "ops_patient_movement", [{
                "movement_id": movement_id, "encounter_id": int(row["encounter_id"]), "patient_id": int(row["patient_id"]),
                "hospital_id": int(row["hospital_id"]), "from_unit_id": None, "from_room_id": None, "from_bed_id": old_bed_id,
                "to_unit_id": int(target_unit["unit_id"]), "to_room_id": None, "to_bed_id": new_bed_id,
                "requested_datetime": simulated_now, "accepted_datetime": simulated_now,
                "started_datetime": simulated_now, "completed_datetime": simulated_now,
                "movement_type": "Internal Transfer" if target_unit["unit_type"] != "Critical Care" else "ICU Transfer",
                "movement_status": "Completed", "priority": "Urgent" if target_unit["unit_type"] == "Critical Care" else "Routine",
                "delay_reason": None, "simulation_run_id": run_id,
            }])
            bed_event_id += 1
            movement_id += 1
            moved += 1
    return moved


def simulate_patient_flow_iteration(engine: Engine, simulated_now: pd.Timestamp, run_id: int,
                                     scenario: ScenarioProfile, batch_size: int, rng: random.Random) -> dict:
    """Run one bounded batch of patient-flow changes for this iteration."""
    admitted = admit_patients(engine, simulated_now, run_id, max(1, batch_size // 3), scenario, rng)
    progressed = advance_discharge_readiness(engine, simulated_now, run_id, batch_size, scenario.discharge_delay_multiplier, rng)
    discharged = discharge_ready_patients(engine, simulated_now, run_id, max(1, batch_size // 3), rng)
    transferred = transfer_patients(engine, simulated_now, run_id, max(1, batch_size // 4), scenario.icu_pressure_multiplier, rng)
    return {"admitted": admitted, "discharge_progressed": progressed, "discharged": discharged, "transferred": transferred}
