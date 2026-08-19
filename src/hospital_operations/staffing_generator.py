"""Synthetic staffing generation and staffing-state computation.

Physician-facing roles (Hospitalist, Attending Physician) reuse a real
`doctors.provider_id` at the same hospital via `existing_provider_id` rather
than inventing a duplicate person (Principle: "Reuse existing providers for
physicians where appropriate"). All other roles (RN, PCT, etc.) are fully
synthetic, generated with Faker.
"""
from __future__ import annotations

import random
from typing import Optional

import pandas as pd
from faker import Faker
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import get_next_id, query_db, transaction, upsert_row
from .models import PHYSICIAN_ROLE_CODES, SHIFT_SEED, STAFF_ROLES

# Non-charge nursing/tech roles generated per unit, scaled off staffed beds.
_NON_PHYSICIAN_ROLE_RATIOS = [
    ("RN", 0.25),    # 1 RN per 4 staffed beds (nurse_ratio_target overrides in staffing_state)
    ("PCT", 0.15),
]


def generate_shifts(engine: Engine) -> pd.DataFrame:
    existing = query_db("SELECT shift_code FROM dbo.ops_shift", engine)
    existing_codes = set(existing["shift_code"].tolist()) if not existing.empty else set()
    to_create = [s for s in SHIFT_SEED if s[0] not in existing_codes]
    if to_create:
        next_id = get_next_id("ops_shift", "shift_id", engine)
        with transaction(engine) as conn:
            for code, name, start, end, crosses in to_create:
                upsert_row(conn, "ops_shift", ["shift_id"], {
                    "shift_id": next_id, "shift_code": code, "shift_name": name,
                    "start_time": start, "end_time": end, "crosses_midnight_flag": crosses,
                })
                next_id += 1
    return query_db("SELECT * FROM dbo.ops_shift", engine)


def generate_staff(engine: Engine, seed: Optional[int] = None) -> pd.DataFrame:
    """Create synthetic ops_staff rows for every unit that doesn't already
    have staff (idempotent at the unit level)."""
    units = query_db("SELECT unit_id, hospital_id, unit_type, staffed_bed_count FROM dbo.ops_unit", engine)
    if units.empty:
        raise RuntimeError("No ops_unit rows found -- run hierarchy_generator.generate_hierarchy() first.")
    doctors = query_db("SELECT provider_id, hospital_id, first_name, last_name FROM dbo.doctors", engine)
    existing = query_db("SELECT DISTINCT primary_unit_id FROM dbo.ops_staff WHERE primary_unit_id IS NOT NULL", engine)
    staffed_unit_ids = set(existing["primary_unit_id"].tolist()) if not existing.empty else set()

    fake = Faker()
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    to_staff = units[~units["unit_id"].isin(staffed_unit_ids)]
    if not to_staff.empty:
        next_id = get_next_id("ops_staff", "staff_id", engine)
        with transaction(engine) as conn:
            for _, u in to_staff.iterrows():
                unit_id = int(u["unit_id"])
                hospital_id = int(u["hospital_id"])
                bed_count = max(1, int(u["staffed_bed_count"]) or 1)

                # 1 charge nurse per unit.
                next_id = _insert_staff(conn, next_id, hospital_id, unit_id, "CN", fake, existing_provider_id=None)

                for role_code, ratio in _NON_PHYSICIAN_ROLE_RATIOS:
                    n = max(1, round(bed_count * ratio))
                    for _ in range(n):
                        next_id = _insert_staff(conn, next_id, hospital_id, unit_id, role_code, fake, existing_provider_id=None)

                # Reuse 1-2 real physicians at this hospital as Hospitalist/Attending for this unit.
                hosp_docs = doctors[doctors["hospital_id"] == hospital_id]
                if not hosp_docs.empty:
                    sample = hosp_docs.sample(n=min(2, len(hosp_docs)), random_state=seed)
                    for i, (_, doc) in enumerate(sample.iterrows()):
                        role_code = "HOSP" if i == 0 else "ATT"
                        next_id = _insert_staff(
                            conn, next_id, hospital_id, unit_id, role_code, fake,
                            existing_provider_id=int(doc["provider_id"]),
                            display_name=f"{doc['first_name']} {doc['last_name']}",
                        )
    return query_db("SELECT * FROM dbo.ops_staff", engine)


def _insert_staff(conn, next_id, hospital_id, unit_id, role_code, fake, existing_provider_id=None, display_name=None):
    role_name = dict(STAFF_ROLES)[role_code]
    upsert_row(conn, "ops_staff", ["staff_id"], {
        "staff_id": next_id,
        "existing_provider_id": existing_provider_id,
        "synthetic_staff_number": f"STF-{next_id:06d}",
        "display_name": display_name or fake.name(),
        "role_code": role_code,
        "role_name": role_name,
        "credential": "MD" if role_code in PHYSICIAN_ROLE_CODES else ("RN" if role_code in ("CN", "RN") else None),
        "primary_hospital_id": hospital_id,
        "primary_unit_id": unit_id,
        "active_flag": True,
        "created_datetime": pd.Timestamp.utcnow().tz_localize(None),
        "updated_datetime": pd.Timestamp.utcnow().tz_localize(None),
    })
    return next_id + 1


def generate_staff_assignments(engine: Engine, as_of: Optional[pd.Timestamp] = None, run_id: Optional[int] = None) -> pd.DataFrame:
    """Create an 'Active' staff assignment for every active ops_staff member
    for the shift covering `as_of` (default: now), skipping staff who already
    have an open assignment."""
    as_of = as_of or pd.Timestamp.utcnow().tz_localize(None)
    staff = query_db("SELECT staff_id, primary_hospital_id, primary_unit_id, role_name FROM dbo.ops_staff WHERE active_flag = 1", engine)
    shifts = query_db("SELECT shift_id, start_time, end_time, crosses_midnight_flag FROM dbo.ops_shift", engine)
    open_assignments = query_db(
        "SELECT DISTINCT staff_id FROM dbo.ops_staff_assignment WHERE status = 'Active' AND assignment_end_datetime IS NULL", engine
    )
    already_assigned = set(open_assignments["staff_id"].tolist()) if not open_assignments.empty else set()

    current_shift = _current_shift(shifts, as_of)
    to_assign = staff[~staff["staff_id"].isin(already_assigned)]
    if not to_assign.empty and current_shift is not None:
        next_id = get_next_id("ops_staff_assignment", "staff_assignment_id", engine)
        shift_id, shift_start, shift_end = current_shift
        with transaction(engine) as conn:
            for _, s in to_assign.iterrows():
                upsert_row(conn, "ops_staff_assignment", ["staff_assignment_id"], {
                    "staff_assignment_id": next_id,
                    "staff_id": int(s["staff_id"]),
                    "hospital_id": int(s["primary_hospital_id"]),
                    "unit_id": int(s["primary_unit_id"]) if pd.notna(s["primary_unit_id"]) else 0,
                    "room_id": None, "bed_id": None, "encounter_id": None,
                    "shift_id": shift_id,
                    "assignment_start_datetime": shift_start,
                    "assignment_end_datetime": None,
                    "assignment_role": s["role_name"],
                    "patient_load": 0,
                    "status": "Active",
                    "source_run_id": run_id,
                    "created_datetime": pd.Timestamp.utcnow().tz_localize(None),
                    "updated_datetime": pd.Timestamp.utcnow().tz_localize(None),
                })
                next_id += 1
    return query_db("SELECT * FROM dbo.ops_staff_assignment", engine)


def _current_shift(shifts: pd.DataFrame, as_of: pd.Timestamp):
    if shifts.empty:
        return None
    hour = as_of.hour
    for _, s in shifts.iterrows():
        start_h = int(str(s["start_time"]).split(":")[0])
        end_h = int(str(s["end_time"]).split(":")[0])
        if s["crosses_midnight_flag"]:
            in_shift = hour >= start_h or hour < end_h
        else:
            in_shift = start_h <= hour < end_h
        if in_shift:
            shift_start = as_of.normalize() + pd.Timedelta(hours=start_h)
            if s["crosses_midnight_flag"] and hour < end_h:
                shift_start -= pd.Timedelta(days=1)
            return int(s["shift_id"]), shift_start, None
    first = shifts.iloc[0]
    return int(first["shift_id"]), as_of.normalize(), None


def compute_staffing_state(engine: Engine, run_id: Optional[int] = None, staffing_absence_rate: float = 0.0) -> pd.DataFrame:
    """Recompute ops_staffing_state for every unit from current active
    assignments + current bed occupancy. `staffing_absence_rate` (from a
    scenario profile) simulates call-outs by reducing present_rn_count below
    scheduled_rn_count."""
    units = query_db("SELECT unit_id, nurse_ratio_target FROM dbo.ops_unit", engine)
    if units.empty:
        return pd.DataFrame()
    now = pd.Timestamp.utcnow().tz_localize(None)
    rng = random.Random()

    with transaction(engine) as conn:
        for _, u in units.iterrows():
            unit_id = int(u["unit_id"])
            occupied = query_db(
                "SELECT COUNT(*) AS n FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
                "JOIN dbo.ops_unit uu ON uu.hospital_id = b.hospital_id AND uu.source_floor_number = b.floor_number "
                f"WHERE uu.unit_id = {unit_id} AND bs.occupancy_status = 'Occupied'", conn,
            )
            occupied_beds = int(occupied.iloc[0]["n"]) if not occupied.empty else 0
            required_rn = max(1, round(occupied_beds / max(u["nurse_ratio_target"], 0.5)))

            scheduled = query_db(
                "SELECT s.role_code, COUNT(*) AS n FROM dbo.ops_staff_assignment sa JOIN dbo.ops_staff s ON sa.staff_id = s.staff_id "
                f"WHERE sa.unit_id = {unit_id} AND sa.status = 'Active' GROUP BY s.role_code", conn,
            )
            scheduled_rn = int(scheduled.loc[scheduled["role_code"].isin(["RN", "CN"]), "n"].sum()) if not scheduled.empty else 0
            scheduled_pct = int(scheduled.loc[scheduled["role_code"] == "PCT", "n"].sum()) if not scheduled.empty else 0
            present_rn = scheduled_rn
            if staffing_absence_rate > 0:
                absences = sum(1 for _ in range(scheduled_rn) if rng.random() < staffing_absence_rate)
                present_rn = max(0, scheduled_rn - absences)
            present_pct = scheduled_pct

            charge = query_db(
                "SELECT TOP 1 sa.staff_id FROM dbo.ops_staff_assignment sa JOIN dbo.ops_staff s ON sa.staff_id = s.staff_id "
                f"WHERE sa.unit_id = {unit_id} AND sa.status = 'Active' AND s.role_code = 'CN'", conn,
            )
            charge_id = int(charge.iloc[0]["staff_id"]) if not charge.empty else None
            open_shift = max(0, required_rn - present_rn)
            coverage_pct = round(100.0 * present_rn / required_rn, 1) if required_rn > 0 else 100.0
            status = "Critical" if coverage_pct < 70 else ("Watch" if coverage_pct < 90 else "Normal")

            upsert_row(conn, "ops_staffing_state", ["unit_id"], {
                "unit_id": unit_id, "snapshot_datetime": now,
                "scheduled_rn_count": scheduled_rn, "present_rn_count": present_rn, "required_rn_count": required_rn,
                "scheduled_pct_count": scheduled_pct, "present_pct_count": present_pct,
                "open_shift_count": open_shift, "charge_nurse_staff_id": charge_id,
                "staffing_coverage_pct": coverage_pct, "staffing_status": status, "simulation_run_id": run_id,
            })
    return query_db("SELECT * FROM dbo.ops_staffing_state", engine)
