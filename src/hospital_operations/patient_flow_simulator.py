"""Patient-flow simulation: admission -> bed assignment -> internal transfer ->
discharge-pending -> discharge -> cleaning -> available.

Newly simulated stays add encounter-linked clinical context and complete the
clinical admission on discharge. Existing encounter and admission identifiers
are reused; no unrelated clinical history is rewritten.

All timestamps advance using the simulator's `simulated_datetime` (wall clock
* speed_multiplier, computed by realtime_engine.py) so movements stay
internally consistent (a transfer can't complete before it starts, etc.).
"""
from __future__ import annotations

import math
import random
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import insert_rows, transaction, upsert_row
from .models import ScenarioProfile

# Absolute floor on simulated dwell, applied underneath the benchmark-derived
# length of stay so a drawn value can never discharge a patient instantly.
_MIN_DWELL_HOURS = 2.0

# Hard ceiling on a single drawn stay, as a multiple of that category's mean.
# Real length-of-stay distributions have a long right tail, but an unbounded
# lognormal draw can occasionally produce a year-long demo stay.
_LOS_OUTLIER_CAP_MULTIPLE = 6.0


def _draw_los_hours(mean_days: float, median_days: float, rng: random.Random) -> float:
    """Draw one length of stay (hours) from a right-skewed lognormal fitted to
    a published mean and median.

    Real length-of-stay distributions are right-skewed: a few long stays pull
    the mean above the median. A lognormal is fully determined by those two
    published statistics, so the fit is derived rather than guessed:

        median = exp(mu)              =>  mu    = ln(median)
        mean   = exp(mu + sigma^2/2)  =>  sigma = sqrt(2 * ln(mean / median))

    Falls back to a symmetric jitter when a source reports no usable median or
    a median at/above the mean (which no lognormal can represent).
    """
    mean_days = max(float(mean_days), 0.01)
    median_days = max(float(median_days), 0.0)
    if median_days <= 0 or median_days >= mean_days:
        drawn = mean_days * rng.uniform(0.7, 1.3)
    else:
        mu = math.log(median_days)
        sigma = math.sqrt(2.0 * math.log(mean_days / median_days))
        drawn = rng.lognormvariate(mu, sigma)
    capped = min(drawn, mean_days * _LOS_OUTLIER_CAP_MULTIPLE)
    return max(capped * 24.0, _MIN_DWELL_HOURS)


# Published length-of-stay benchmarks keyed by the same clinical_family values
# used by the icd_reference dimension, so a simulated stay is driven by what
# the patient has rather than by how fast the simulation clock is running.
# Sources, derivations and confidence grades: docs/LENGTH_OF_STAY_BENCHMARKS.md
#   ed_dwell_hours  - median ED dwell for admitted patients
#   los_mean_days   - mean inpatient length of stay
#   los_median_days - median inpatient length of stay (fits the lognormal)
#   icu_share       - published share of *this condition's* admissions needing
#                     critical care (a cohort rate, calibrated below)
#   icu_los_days    - mean critical-care length of stay
_LOS_BENCHMARKS = {
    "Cardiology":                 {"ed_dwell_hours": 4.0, "los_mean_days": 4.5, "los_median_days": 3.0, "icu_share": 0.55, "icu_los_days": 2.5},
    "Respiratory":                {"ed_dwell_hours": 4.0, "los_mean_days": 4.5, "los_median_days": 3.0, "icu_share": 0.45, "icu_los_days": 3.5},
    "Endocrine & Metabolic":      {"ed_dwell_hours": 4.5, "los_mean_days": 5.5, "los_median_days": 4.0, "icu_share": 0.44, "icu_los_days": 2.0},
    "Injury & Trauma":            {"ed_dwell_hours": 4.0, "los_mean_days": 6.0, "los_median_days": 4.0, "icu_share": 0.25, "icu_los_days": 3.5},
    "Musculoskeletal":            {"ed_dwell_hours": 5.0, "los_mean_days": 4.0, "los_median_days": 3.0, "icu_share": 0.10, "icu_los_days": 2.0},
    "Behavioral Health":          {"ed_dwell_hours": 10.0, "los_mean_days": 7.6, "los_median_days": 6.0, "icu_share": 0.02, "icu_los_days": 2.0},
    "Gastroenterology":           {"ed_dwell_hours": 4.0, "los_mean_days": 4.0, "los_median_days": 3.0, "icu_share": 0.43, "icu_los_days": 2.5},
    "Oncology":                   {"ed_dwell_hours": 5.5, "los_mean_days": 6.5, "los_median_days": 5.0, "icu_share": 0.12, "icu_los_days": 3.0},
    "Rehabilitation & Aftercare": {"ed_dwell_hours": 3.0, "los_mean_days": 8.0, "los_median_days": 6.0, "icu_share": 0.02, "icu_los_days": 2.0},
    "Signs & Symptoms":           {"ed_dwell_hours": 3.5, "los_mean_days": 2.5, "los_median_days": 1.5, "icu_share": 0.15, "icu_los_days": 1.5},
    "Neurology":                  {"ed_dwell_hours": 3.0, "los_mean_days": 5.5, "los_median_days": 4.0, "icu_share": 0.45, "icu_los_days": 3.0},
    "Infectious Disease":         {"ed_dwell_hours": 4.0, "los_mean_days": 6.0, "los_median_days": 4.0, "icu_share": 0.40, "icu_los_days": 4.0},
    "Ear, Nose & Throat":         {"ed_dwell_hours": 3.0, "los_mean_days": 2.5, "los_median_days": 2.0, "icu_share": 0.05, "icu_los_days": 1.5},
    "Hematology":                 {"ed_dwell_hours": 4.0, "los_mean_days": 5.0, "los_median_days": 3.5, "icu_share": 0.15, "icu_los_days": 2.5},
    "Preventive & Aftercare":     {"ed_dwell_hours": 2.5, "los_mean_days": 2.0, "los_median_days": 1.5, "icu_share": 0.02, "icu_los_days": 1.5},
    "Renal & Genitourinary":      {"ed_dwell_hours": 4.5, "los_mean_days": 4.0, "los_median_days": 3.0, "icu_share": 0.48, "icu_los_days": 2.5},
}

# All-causes fallback row (docs/LENGTH_OF_STAY_BENCHMARKS.md section 5).
_BASELINE_LOS = {"ed_dwell_hours": 4.0, "los_mean_days": 5.1, "los_median_days": 3.0,
                 "icu_share": 0.18, "icu_los_days": 3.9}

# Published share of ED admissions that go to critical care (NHAMCS, with
# "unknown" redistributed proportionally). The per-family `icu_share` values
# above are *within-condition* cohort rates -- 70% of AMI admissions reach a
# CCU -- so using them directly would put most of the census in the ICU. They
# are rescaled by a single factor to preserve the published ordering between
# conditions while landing the blended rate on the published aggregate.
_ICU_TARGET_SHARE = 0.18
_ICU_CALIBRATION = _ICU_TARGET_SHARE / (
    sum(row["icu_share"] for row in _LOS_BENCHMARKS.values()) / len(_LOS_BENCHMARKS)
)


def _los_profile(clinical_family: Optional[str]) -> dict:
    """Benchmark row for a clinical family, falling back to all-causes."""
    return _LOS_BENCHMARKS.get(clinical_family or "", _BASELINE_LOS)


def _icu_admit_probability(clinical_family: Optional[str]) -> float:
    """Calibrated probability that this family's stay needs critical care."""
    raw = _los_profile(clinical_family)["icu_share"]
    return min(1.0, max(0.0, raw * _ICU_CALIBRATION))


# Each story is (icd_code, description, chief_complaint, drug, dosage,
# frequency, lab test, value, units, reference_range, clinical_family).
# The clinical_family must match a key in icd_reference.clinical_family so the
# stay inherits that family's published length-of-stay benchmarks.
_CLINICAL_STORIES = {
    "general": ("J18.9", "Pneumonia, unspecified organism", "Shortness of breath", "Ceftriaxone", "1 g", "Once daily", "White blood cell count", "14.2", "10^3/uL", "4.0-11.0", "Respiratory"),
    "pediatric": ("J45.901", "Unspecified asthma with (acute) exacerbation", "Wheezing", "Albuterol", "2.5 mg", "As needed", "Arterial oxygen partial pressure", "68", "mmHg", "80-100", "Respiratory"),
    "cardiac": ("I50.9", "Heart failure, unspecified", "Shortness of breath", "Furosemide", "40 mg", "Once daily", "BNP", "350", "pg/mL", "0-100", "Cardiology"),
    "cancer": ("D70.9", "Neutropenia, unspecified", "Fever", "Cefepime", "2 g", "Twice daily", "White blood cell count", "1.2", "10^3/uL", "4.0-11.0", "Hematology"),
    "rehab": ("M62.81", "Muscle weakness, generalized", "Weakness", "Acetaminophen", "500 mg", "As needed", "Creatinine", "1.0", "mg/dL", "0.6-1.3", "Musculoskeletal"),
}


def _flow_query(sql, engine, params=None):
    return pd.read_sql(text(sql), engine, params=params or {})


def _flow_next_id(table, key, engine):
    value = _flow_query(f"SELECT MAX({key}) AS max_id FROM dbo.{table}", engine).iloc[0]["max_id"]
    return 1 if pd.isna(value) else int(value) + 1


def _insert_clinical_story(conn, encounter_id: int, patient_id: int, hospital_specialty: str,
                           provider_id: int, simulated_now: pd.Timestamp) -> str:
    """Create one traceable synthetic diagnosis, order and result for this stay.

    Returns the clinical family of the diagnosis so the caller can drive length
    of stay from that family's published benchmarks.
    """
    code, description, complaint, drug, dosage, frequency, test, value, units, reference, family = _CLINICAL_STORIES.get(
        hospital_specialty, _CLINICAL_STORIES["general"]
    )
    when = simulated_now.date()
    updated = conn.execute(text(
        "UPDATE dbo.encounters SET chief_complaint = :complaint "
        "WHERE encounter_id = :encounter_id AND patient_id = :patient_id"
    ), {"complaint": complaint, "encounter_id": encounter_id, "patient_id": patient_id})
    if updated.rowcount != 1:
        raise RuntimeError(f"Encounter {encounter_id} cannot be linked to patient {patient_id}")
    for table, key, columns, values in (
        ("diagnoses", "diagnosis_id",
         "encounter_id, patient_id, icd_code, description, onset_date, status",
         {"encounter_id": encounter_id, "patient_id": patient_id, "icd_code": code,
          "description": description, "onset_date": when, "status": "Active"}),
        ("medications", "medication_id",
         "encounter_id, patient_id, drug_name, dosage, frequency, start_date, end_date, prescribing_provider_id, status",
         {"encounter_id": encounter_id, "patient_id": patient_id, "drug_name": drug,
          "dosage": dosage, "frequency": frequency, "start_date": when,
          "end_date": None, "prescribing_provider_id": provider_id, "status": "Active"}),
        ("labs", "lab_id",
         "encounter_id, patient_id, test_name, test_code, order_date, result_date, value, units, reference_range, status",
         {"encounter_id": encounter_id, "patient_id": patient_id, "test_name": test,
          "test_code": None, "order_date": when, "result_date": when,
          "value": value,
          "units": units, "reference_range": reference, "status": "Completed"}),
    ):
        # IDs in the ODS are allocated by the daily generator using MAX(id)+1.
        # Hold the table lock until this transaction commits to avoid colliding
        # with a concurrent catch-up or a second simulator.
        row = conn.execute(text(
            f"SELECT COALESCE(MAX({key}), 0) + 1 FROM dbo.{table} WITH (TABLOCKX, HOLDLOCK)"
        )).scalar_one()
        params = {"new_id": int(row), **values}
        conn.execute(text(
            f"INSERT INTO dbo.{table} ({key}, {columns}) VALUES "
            f"(:new_id, {', '.join(':' + name for name in values)})"
        ), params)
    return family


def _pick_target_unit(units: pd.DataFrame, hospital_id: int, encounter_type: str, rng: random.Random) -> Optional[pd.Series]:
    hosp_units = units[units["hospital_id"] == hospital_id]
    if hosp_units.empty:
        return None
    if encounter_type == "Emergency":
        preferred = hosp_units[hosp_units["unit_type"] == "Emergency"]
        if preferred.empty:
            return None
        return preferred.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]
    pool = hosp_units[hosp_units["unit_type"] != "Emergency"]
    if pool.empty:
        return None
    non_critical = pool[pool["unit_type"] != "Critical Care"]
    pool = non_critical if not non_critical.empty else pool
    return pool.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]


def _find_available_bed(engine: Engine, hospital_id: int, floor_number: int) -> Optional[int]:
    df = _flow_query(
        "SELECT TOP 1 bs.bed_id FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id "
        "WHERE b.hospital_id = :h AND b.floor_number = :f AND bs.occupancy_status = 'Available' ORDER BY bs.bed_id",
        engine, {"h": hospital_id, "f": floor_number},
    )
    return int(df.iloc[0]["bed_id"]) if not df.empty else None


def admit_patients(engine: Engine, simulated_now: pd.Timestamp, run_id: int, batch_size: int,
                    scenario: ScenarioProfile, rng: random.Random) -> int:
    """Assign an operational bed to up to `batch_size` active admissions that
    don't yet have one. Returns count of admissions processed."""
    candidates = _flow_query(
        "SELECT TOP (:lim) a.admission_id, a.encounter_id, a.patient_id, a.hospital_id, "
        "e.encounter_type, e.provider_id, h.specialty "
        "FROM dbo.admissions a JOIN dbo.encounters e ON a.encounter_id = e.encounter_id "
        "JOIN dbo.hospitals h ON h.hospital_id = a.hospital_id "
        "WHERE a.discharge_datetime IS NULL AND a.patient_id = e.patient_id "
        "AND a.hospital_id = e.hospital_id AND a.admit_datetime <= :now "
        "AND a.admit_datetime >= DATEADD(DAY, -1, :now) "
        "AND NOT EXISTS (SELECT 1 FROM dbo.ops_patient_movement pm "
        "WHERE pm.encounter_id = a.encounter_id AND pm.movement_type = 'Admission') "
        "AND NOT EXISTS (SELECT 1 FROM dbo.ops_simulated_episode se WHERE se.encounter_id = a.encounter_id) "
        "AND NOT EXISTS (SELECT 1 FROM dbo.ops_bed_state bs WHERE bs.encounter_id = a.encounter_id) "
        "ORDER BY a.admit_datetime DESC",
        engine, {"lim": batch_size * 20, "now": simulated_now},
    )
    if candidates.empty:
        return 0
    units = _flow_query("SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit", engine)
    processed = 0
    bed_event_id = _flow_next_id("ops_bed_state_event", "bed_state_event_id", engine)
    movement_id = _flow_next_id("ops_patient_movement", "movement_id", engine)
    with transaction(engine) as conn:
        for _, cand in candidates.iterrows():
            if processed >= batch_size:
                break
            unit = _pick_target_unit(units, int(cand["hospital_id"]), cand["encounter_type"], rng)
            if unit is None:
                continue
            bed_id = _find_available_bed(conn, int(cand["hospital_id"]), int(unit["source_floor_number"]))
            if bed_id is None:
                continue  # no capacity -- alert_engine will surface this as a capacity alert
            family = _insert_clinical_story(conn, int(cand["encounter_id"]), int(cand["patient_id"]),
                                            str(cand["specialty"]), int(cand["provider_id"]), simulated_now)
            profile = _los_profile(family)
            # Draw this stay's length from its family's published benchmarks.
            # Scenario delay is applied to the drawn stay rather than to a
            # per-iteration probability, so length of stay stays a function of
            # the condition and not of SPEED_MULTIPLIER.
            target_los_hours = _draw_los_hours(
                profile["los_mean_days"], profile["los_median_days"], rng
            ) * max(0.1, scenario.discharge_delay_multiplier)
            ed_dwell_hours = max(0.25, profile["ed_dwell_hours"] * rng.uniform(0.6, 1.6))
            icu_expected = rng.random() < _icu_admit_probability(family)
            if icu_expected:
                target_los_hours += profile["icu_los_days"] * 24.0
            # Round before deriving the timestamp so the stored target and the
            # expected discharge always reconcile for anyone comparing
            # target_los_hours against DATEDIFF on the episode.
            target_los_hours = round(float(target_los_hours), 2)
            expected_discharge = simulated_now + pd.Timedelta(hours=target_los_hours)
            insert_rows(conn, "ops_simulated_episode", [{
                "encounter_id": int(cand["encounter_id"]), "admission_id": int(cand["admission_id"]),
                "patient_id": int(cand["patient_id"]), "simulation_run_id": run_id,
                "created_datetime": simulated_now,
                "icd_family": family,
                "target_los_hours": target_los_hours,
                "ed_dwell_hours": round(float(ed_dwell_hours), 2),
                "icu_expected_flag": bool(icu_expected),
                "expected_discharge_datetime": expected_discharge,
            }])
            upsert_row(conn, "ops_bed_state", ["bed_id"], {
                "bed_id": bed_id, "operational_status": "Occupied", "occupancy_status": "Occupied",
                "encounter_id": int(cand["encounter_id"]), "patient_id": int(cand["patient_id"]),
                "admission_id": int(cand["admission_id"]), "assigned_datetime": simulated_now,
                "expected_release_datetime": expected_discharge, "cleaning_required_flag": False,
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
                "expected_discharge_datetime": expected_discharge, "readiness_status": "Not Ready",
                "clinical_ready_flag": False, "medication_ready_flag": False, "transport_ready_flag": False,
                "destination_ready_flag": False, "education_complete_flag": False,
                "outstanding_barrier_count": 1, "primary_barrier": "Simulated: awaiting clinical progress",
                "updated_datetime": simulated_now, "simulation_run_id": run_id,
            })
            bed_event_id += 1
            movement_id += 1
            processed += 1
    return processed


def _split_batch(batch_size: int) -> tuple[int, int]:
    """Reserve roughly half of a batch for simulator-created episodes.

    A live database carries a large backlog of pre-existing operational rows
    whose timestamps are always older than a freshly created episode. Selecting
    purely oldest-first therefore starves new stays, so they never progress past
    admission. Reserving part of each batch keeps new journeys moving while
    preserving ambient movement for the legacy population.
    """
    simulated_limit = max(1, batch_size // 2)
    return simulated_limit, max(0, batch_size - simulated_limit)


def advance_discharge_readiness(engine: Engine, simulated_now: pd.Timestamp, run_id: int,
                                 batch_size: int, discharge_delay_multiplier: float, rng: random.Random) -> int:
    """Probabilistically progress discharge-readiness flags for occupied beds
    (all values explicitly SIMULATED, never a real clinical judgement)."""
    simulated_limit, legacy_limit = _split_batch(batch_size)
    occupied = _flow_query(
        "SELECT encounter_id, outstanding_barrier_count, expected_release_datetime, is_simulated FROM ("
        "  SELECT dr.encounter_id, dr.outstanding_barrier_count, bs.expected_release_datetime,"
        "    CASE WHEN se.encounter_id IS NULL THEN 0 ELSE 1 END AS is_simulated,"
        "    ROW_NUMBER() OVER (PARTITION BY CASE WHEN se.encounter_id IS NULL THEN 0 ELSE 1 END"
        "      ORDER BY dr.updated_datetime ASC) AS rn"
        "  FROM dbo.ops_discharge_readiness dr"
        "  LEFT JOIN dbo.ops_simulated_episode se ON se.encounter_id = dr.encounter_id"
        "  LEFT JOIN dbo.ops_bed_state bs ON bs.encounter_id = dr.encounter_id"
        "  WHERE dr.readiness_status <> 'Ready'"
        ") ranked WHERE (is_simulated = 1 AND rn <= :sim_lim) OR (is_simulated = 0 AND rn <= :legacy_lim)",
        engine, {"sim_lim": simulated_limit, "legacy_lim": legacy_limit},
    )
    if occupied.empty:
        return 0
    progressed = 0
    # Legacy rows carry no drawn length of stay, so they keep the original
    # probabilistic walk to preserve ambient movement in the demo database.
    progress_chance = max(0.02, 0.20 / max(discharge_delay_multiplier, 0.1))
    with transaction(engine) as conn:
        for _, row in occupied.iterrows():
            expected_release = row["expected_release_datetime"]
            if int(row["is_simulated"]) == 1 and pd.notna(expected_release):
                # A simulated stay clears its barriers only once the simulated
                # clock reaches the length of stay drawn for its condition.
                if simulated_now < pd.Timestamp(expected_release):
                    continue
            elif rng.random() > progress_chance:
                continue
            barriers = max(0, int(row["outstanding_barrier_count"]) - 1)
            status = "Ready" if barriers == 0 else ("Pending" if barriers <= 1 else "Not Ready")
            conn.execute(text(
                "UPDATE dbo.ops_discharge_readiness SET outstanding_barrier_count = :b, readiness_status = :s, "
                "clinical_ready_flag = CASE WHEN :b = 0 THEN 1 ELSE clinical_ready_flag END, "
                "primary_barrier = CASE WHEN :b = 0 THEN NULL ELSE primary_barrier END, "
                "expected_discharge_datetime = COALESCE(expected_discharge_datetime, "
                "  CASE WHEN :b = 0 THEN :now ELSE NULL END), "
                "updated_datetime = :now, simulation_run_id = :rid WHERE encounter_id = :eid"
            ), {"b": barriers, "s": status, "now": simulated_now, "rid": run_id, "eid": int(row["encounter_id"])})
            progressed += 1
    return progressed


def seed_discharge_readiness_for_occupied(engine: Engine, run_id: int | None = None) -> int:
    """Initialize readiness for pre-existing occupied beds during setup."""
    missing = _flow_query(
        "SELECT bs.encounter_id, bs.patient_id FROM dbo.ops_bed_state bs "
        "LEFT JOIN dbo.ops_discharge_readiness dr ON bs.encounter_id = dr.encounter_id "
        "WHERE bs.occupancy_status = 'Occupied' AND bs.encounter_id IS NOT NULL AND dr.encounter_id IS NULL", engine
    )
    if missing.empty:
        return 0
    now = pd.Timestamp.utcnow().tz_localize(None)
    with transaction(engine) as conn:
        for _, row in missing.iterrows():
            upsert_row(conn, "ops_discharge_readiness", ["encounter_id"], {
                "encounter_id": int(row["encounter_id"]), "patient_id": int(row["patient_id"]),
                "expected_discharge_datetime": None, "readiness_status": "Not Ready",
                "clinical_ready_flag": False, "medication_ready_flag": False, "transport_ready_flag": False,
                "destination_ready_flag": False, "education_complete_flag": False, "outstanding_barrier_count": 1,
                "primary_barrier": "Simulated: awaiting clinical progress", "updated_datetime": now,
                "simulation_run_id": run_id,
            })
    return len(missing)


def discharge_ready_patients(engine: Engine, simulated_now: pd.Timestamp, run_id: int, batch_size: int, rng: random.Random) -> int:
    """Release ready beds; complete clinical admissions for simulator-created stays."""
    simulated_limit, legacy_limit = _split_batch(batch_size)
    ready = _flow_query(
        "SELECT bed_id, encounter_id, patient_id, admission_id, assigned_datetime, hospital_id, unit_id, simulated_stay FROM ("
        "  SELECT bs.bed_id, bs.encounter_id, bs.patient_id, bs.admission_id, bs.assigned_datetime,"
        "    b.hospital_id, u.unit_id,"
        "    CASE WHEN se.encounter_id IS NULL THEN 0 ELSE 1 END AS simulated_stay,"
        "    ROW_NUMBER() OVER (PARTITION BY CASE WHEN se.encounter_id IS NULL THEN 0 ELSE 1 END"
        "      ORDER BY bs.assigned_datetime ASC) AS rn"
        "  FROM dbo.ops_bed_state bs"
        "  JOIN dbo.beds b ON bs.bed_id = b.bed_id"
        "  JOIN dbo.ops_unit u ON u.hospital_id = b.hospital_id AND u.source_floor_number = b.floor_number"
        "  LEFT JOIN dbo.ops_simulated_episode se ON se.encounter_id = bs.encounter_id"
        "    AND se.admission_id = bs.admission_id AND se.patient_id = bs.patient_id"
        "  JOIN dbo.ops_discharge_readiness dr ON bs.encounter_id = dr.encounter_id"
        "  WHERE bs.occupancy_status = 'Occupied' AND dr.readiness_status = 'Ready'"
        "    AND bs.assigned_datetime <= :cutoff"
        ") ranked WHERE (simulated_stay = 1 AND rn <= :sim_lim) OR (simulated_stay = 0 AND rn <= :legacy_lim)",
        engine,
        {"sim_lim": simulated_limit, "legacy_lim": legacy_limit,
         "cutoff": simulated_now - pd.Timedelta(hours=_MIN_DWELL_HOURS)},
    )
    if ready.empty:
        return 0
    bed_event_id = _flow_next_id("ops_bed_state_event", "bed_state_event_id", engine)
    movement_id = _flow_next_id("ops_patient_movement", "movement_id", engine)
    released = 0
    with transaction(engine) as conn:
        for _, row in ready.iterrows():
            bed_id = int(row["bed_id"])
            if int(row["simulated_stay"]) == 1:
                if pd.isna(row["admission_id"]):
                    raise RuntimeError(f"Simulated encounter {row['encounter_id']} lost its admission ID")
                result = conn.execute(text(
                    "UPDATE dbo.admissions SET discharge_datetime = :now "
                    "WHERE admission_id = :aid AND encounter_id = :eid AND patient_id = :pid "
                    "AND discharge_datetime IS NULL AND admit_datetime <= :now"
                ), {"now": simulated_now, "aid": int(row["admission_id"]),
                    "eid": int(row["encounter_id"]), "pid": int(row["patient_id"])})
                if result.rowcount != 1:
                    raise RuntimeError(f"Clinical discharge could not be recorded for admission {row['admission_id']}")
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
                "hospital_id": int(row["hospital_id"]), "from_unit_id": int(row["unit_id"]),
                "from_room_id": None, "from_bed_id": bed_id,
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
    simulated_limit, legacy_limit = _split_batch(batch_size)
    occupied = _flow_query(
        "SELECT bed_id, encounter_id, patient_id, admission_id, assigned_datetime, hospital_id, floor_number, "
        "expected_release_datetime, is_simulated, icu_expected_flag FROM ("
        "  SELECT bs.bed_id, bs.encounter_id, bs.patient_id, bs.admission_id, bs.assigned_datetime,"
        "    b.hospital_id, b.floor_number, bs.expected_release_datetime, se.icu_expected_flag,"
        "    CASE WHEN se.encounter_id IS NULL THEN 0 ELSE 1 END AS is_simulated,"
        "    ROW_NUMBER() OVER (PARTITION BY CASE WHEN se.encounter_id IS NULL THEN 0 ELSE 1 END"
        "      ORDER BY CASE WHEN u.unit_type = 'Emergency' THEN 0 ELSE 1 END, NEWID()) AS rn"
        "  FROM dbo.ops_bed_state bs JOIN dbo.beds b ON bs.bed_id = b.bed_id"
        "  JOIN dbo.ops_unit u ON u.hospital_id = b.hospital_id AND u.source_floor_number = b.floor_number"
        "  LEFT JOIN dbo.ops_simulated_episode se ON se.encounter_id = bs.encounter_id"
        "  WHERE bs.occupancy_status = 'Occupied' AND bs.assigned_datetime <= :cutoff"
        ") ranked WHERE (is_simulated = 1 AND rn <= :sim_lim) OR (is_simulated = 0 AND rn <= :legacy_lim)",
        engine,
        {"sim_lim": simulated_limit, "legacy_lim": legacy_limit,
         "cutoff": simulated_now - pd.Timedelta(hours=_MIN_DWELL_HOURS)},
    )
    if occupied.empty:
        return 0
    units = _flow_query("SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit", engine)
    movement_id = _flow_next_id("ops_patient_movement", "movement_id", engine)
    bed_event_id = _flow_next_id("ops_bed_state_event", "bed_state_event_id", engine)
    moved = 0
    with transaction(engine) as conn:
        for _, row in occupied.iterrows():
            hosp_units = units[(units["hospital_id"] == row["hospital_id"]) &
                               (units["source_floor_number"] != row["floor_number"]) &
                               (units["unit_type"] != "Emergency")]
            if hosp_units.empty:
                continue
            source_units = units[(units["hospital_id"] == row["hospital_id"]) &
                                 (units["source_floor_number"] == row["floor_number"])]
            if source_units.empty:
                raise RuntimeError(f"No operational unit for occupied bed {row['bed_id']}")
            source_unit = source_units.iloc[0]
            from_emergency = source_unit["unit_type"] == "Emergency"
            if from_emergency:
                # ED patients move on quickly; the modelled decision is *where*
                # they go, not whether they leave. Only the share flagged at
                # admit escalates to critical care -- previously every ED
                # transfer was forced into Critical Care, which put roughly
                # twice the published proportion of the census in the ICU.
                chance = 0.60
                if int(row["is_simulated"]) == 1 and pd.notna(row["icu_expected_flag"]):
                    wants_icu = bool(row["icu_expected_flag"])
                else:
                    wants_icu = rng.random() < _ICU_TARGET_SHARE
            else:
                chance = min(0.5, 0.05 * icu_pressure_multiplier)
                wants_icu = False
            if rng.random() > chance:
                continue
            critical = hosp_units[hosp_units["unit_type"] == "Critical Care"]
            if wants_icu:
                if not critical.empty:
                    hosp_units = critical
            else:
                non_critical = hosp_units[hosp_units["unit_type"] != "Critical Care"]
                if not non_critical.empty:
                    hosp_units = non_critical
            target_unit = hosp_units.sample(n=1, random_state=rng.randint(0, 2**31)).iloc[0]
            new_bed_id = _find_available_bed(conn, int(row["hospital_id"]), int(target_unit["source_floor_number"]))
            if new_bed_id is None:
                continue
            old_bed_id = int(row["bed_id"])
            upsert_row(conn, "ops_bed_state", ["bed_id"], {
                "bed_id": new_bed_id, "operational_status": "Occupied", "occupancy_status": "Occupied",
                "encounter_id": int(row["encounter_id"]), "patient_id": int(row["patient_id"]),
                "admission_id": int(row["admission_id"]) if pd.notna(row["admission_id"]) else None,
                "assigned_datetime": simulated_now,
                "expected_release_datetime": row["expected_release_datetime"]
                    if pd.notna(row["expected_release_datetime"]) else None,
                "cleaning_required_flag": False,
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
                "hospital_id": int(row["hospital_id"]), "from_unit_id": int(source_unit["unit_id"]),
                "from_room_id": None, "from_bed_id": old_bed_id,
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
    transferred = transfer_patients(engine, simulated_now, run_id, max(1, batch_size // 4), scenario.icu_pressure_multiplier, rng)
    discharged = discharge_ready_patients(engine, simulated_now, run_id, max(1, batch_size // 3), rng)
    return {"admitted": admitted, "discharge_progressed": progressed, "discharged": discharged, "transferred": transferred}
