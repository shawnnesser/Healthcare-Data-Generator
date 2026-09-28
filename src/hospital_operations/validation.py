"""Programmatic PASS/WARN/FAIL validation checks for Hospital Operations.

Mirrors the read-only reference queries in
sql/hospital_operations/007_create_validation_queries.sql so both the Setup
notebook and the Real-Time Simulator notebook can print a compact summary
instead of requiring a human to run SQL by hand.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import query_db


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str


def _rowcount_check(engine: Engine, name: str, sql: str, warn_only: bool = False) -> CheckResult:
    # A query that cannot run is reported as a failure, never silently passed,
    # but it must not abort the remaining checks in a notebook run.
    try:
        df = pd.read_sql(text(sql), engine)
    except Exception as exc:  # noqa: BLE001 - surfaced in the summary as a FAIL
        return CheckResult(name, "FAIL", f"check could not run: {exc}")
    n = len(df)
    if n == 0:
        return CheckResult(name, "PASS", "0 violations")
    return CheckResult(name, "WARN" if warn_only else "FAIL", f"{n} row(s) violate this check")


def run_hierarchy_checks(engine: Engine) -> List[CheckResult]:
    return [
        _rowcount_check(engine, "Every ops_building references a valid hospital", """
            SELECT b.building_id FROM dbo.ops_building b
            LEFT JOIN dbo.hospitals h ON b.hospital_id = h.hospital_id WHERE h.hospital_id IS NULL"""),
        _rowcount_check(engine, "Every ops_unit references a valid building/hospital/floors row", """
            SELECT u.unit_id FROM dbo.ops_unit u
            LEFT JOIN dbo.ops_building b ON u.building_id = b.building_id
            LEFT JOIN dbo.hospitals h ON u.hospital_id = h.hospital_id
            LEFT JOIN dbo.floors f ON f.hospital_id = u.hospital_id AND f.floor_number = u.source_floor_number
            WHERE b.building_id IS NULL OR h.hospital_id IS NULL OR f.floor_number IS NULL"""),
        _rowcount_check(engine, "Every ops_room_attribute references a valid room and unit", """
            SELECT ra.room_id FROM dbo.ops_room_attribute ra
            LEFT JOIN dbo.rooms r ON ra.room_id = r.room_id
            LEFT JOIN dbo.ops_unit u ON ra.unit_id = u.unit_id
            WHERE r.room_id IS NULL OR u.unit_id IS NULL"""),
        _rowcount_check(engine, "Every ops_bed_state references a valid bed", """
            SELECT bs.bed_id FROM dbo.ops_bed_state bs
            LEFT JOIN dbo.beds b ON bs.bed_id = b.bed_id WHERE b.bed_id IS NULL"""),
    ]


def run_bed_reconciliation_checks(engine: Engine) -> List[CheckResult]:
    return [
        _rowcount_check(engine, "ops_unit.staffed_bed_count matches actual bed count on that floor", """
            SELECT u.unit_id FROM dbo.ops_unit u
            WHERE u.staffed_bed_count <> (
                SELECT COUNT(*) FROM dbo.beds b WHERE b.hospital_id = u.hospital_id AND b.floor_number = u.source_floor_number)"""),
        _rowcount_check(engine, "No bed has more than one active (Occupied) encounter", """
            SELECT bed_id FROM dbo.ops_bed_state WHERE occupancy_status = 'Occupied' GROUP BY bed_id HAVING COUNT(*) > 1"""),
        _rowcount_check(engine, "No encounter occupies more than one bed at a time", """
            SELECT encounter_id FROM dbo.ops_bed_state WHERE occupancy_status = 'Occupied' AND encounter_id IS NOT NULL
            GROUP BY encounter_id HAVING COUNT(DISTINCT bed_id) > 1"""),
        _rowcount_check(engine, "Occupied beds have patient+encounter; available/cleaning beds do not", """
            SELECT bed_id FROM dbo.ops_bed_state
            WHERE (occupancy_status = 'Occupied' AND (encounter_id IS NULL OR patient_id IS NULL))
               OR (occupancy_status IN ('Available', 'Cleaning') AND encounter_id IS NOT NULL)"""),
    ]


def run_staffing_equipment_alert_checks(engine: Engine) -> List[CheckResult]:
    return [
        _rowcount_check(engine, "Charge nurses reference valid ops_staff rows", """
            SELECT ss.unit_id FROM dbo.ops_staffing_state ss
            LEFT JOIN dbo.ops_staff s ON ss.charge_nurse_staff_id = s.staff_id
            WHERE ss.charge_nurse_staff_id IS NOT NULL AND s.staff_id IS NULL"""),
        _rowcount_check(engine, "Equipment locations are valid (unit hospital matches equipment hospital)", """
            SELECT eq.equipment_id FROM dbo.ops_equipment eq
            LEFT JOIN dbo.ops_unit u ON eq.unit_id = u.unit_id
            WHERE u.unit_id IS NULL OR u.hospital_id <> eq.hospital_id"""),
        _rowcount_check(engine, "Active alerts reference a valid hospital", """
            SELECT alert_id FROM dbo.ops_operational_alert oa
            LEFT JOIN dbo.hospitals h ON oa.hospital_id = h.hospital_id
            WHERE oa.status <> 'Resolved' AND h.hospital_id IS NULL"""),
    ]


def run_snapshot_reconciliation_checks(engine: Engine) -> List[CheckResult]:
    return [
        _rowcount_check(engine, "Hospital snapshot occupancy_pct matches occupied/staffed beds", """
            SELECT hospital_id FROM dbo.vw_ops_hospital_snapshot
            WHERE ABS(occupancy_pct - CASE WHEN staffed_beds > 0 THEN ROUND(100.0 * occupied_beds / staffed_beds, 1) ELSE 0 END) > 0.1"""),
        _rowcount_check(
            engine, "ops_unit staffed-bed sum vs latest hospital_department_beds.beds_allocated sum (informational)", """
            SELECT h.hospital_id FROM dbo.hospitals h
            WHERE ISNULL((SELECT SUM(staffed_bed_count) FROM dbo.ops_unit WHERE hospital_id = h.hospital_id), 0) <>
                  ISNULL((SELECT SUM(hdb.beds_allocated) FROM dbo.hospital_department_beds hdb
                          WHERE hdb.hospital_id = h.hospital_id AND hdb.date = (SELECT MAX(date) FROM dbo.hospital_department_beds)), 0)""",
            warn_only=True,
        ),
    ]


def run_episode_checks(engine: Engine) -> List[CheckResult]:
    return [
        _rowcount_check(engine, "Simulated episode has matching admission and patient", """
            SELECT se.encounter_id FROM dbo.ops_simulated_episode se
            LEFT JOIN dbo.admissions a ON a.admission_id = se.admission_id
            LEFT JOIN dbo.encounters e ON e.encounter_id = se.encounter_id
            WHERE a.encounter_id IS NULL OR a.encounter_id <> se.encounter_id
               OR a.patient_id <> se.patient_id OR e.patient_id <> se.patient_id"""),
        _rowcount_check(engine, "Simulated episode has matching diagnosis, lab and medication", """
            SELECT se.encounter_id FROM dbo.ops_simulated_episode se
            WHERE NOT EXISTS (SELECT 1 FROM dbo.diagnoses d WHERE d.encounter_id = se.encounter_id
                AND d.patient_id = se.patient_id AND d.onset_date >= CAST(se.created_datetime AS DATE))
               OR NOT EXISTS (SELECT 1 FROM dbo.labs l WHERE l.encounter_id = se.encounter_id
                AND l.patient_id = se.patient_id AND l.order_date >= CAST(se.created_datetime AS DATE)
                AND l.reference_range <> 'Normal')
               OR NOT EXISTS (SELECT 1 FROM dbo.medications m WHERE m.encounter_id = se.encounter_id
                AND m.patient_id = se.patient_id AND m.start_date >= CAST(se.created_datetime AS DATE))"""),
        _rowcount_check(engine, "Simulated movement links and chronology are valid", """
            SELECT pm.movement_id FROM dbo.ops_patient_movement pm
            JOIN dbo.ops_simulated_episode se ON se.encounter_id = pm.encounter_id
            WHERE pm.patient_id <> se.patient_id
               OR pm.completed_datetime IS NULL OR pm.requested_datetime > pm.completed_datetime
               OR (pm.movement_type IN ('Internal Transfer', 'ICU Transfer')
                   AND (pm.from_unit_id IS NULL OR pm.to_unit_id IS NULL))
               OR (pm.movement_type = 'ICU Transfer' AND NOT EXISTS (
                   SELECT 1 FROM dbo.ops_unit u WHERE u.unit_id = pm.to_unit_id
                     AND u.unit_type = 'Critical Care'))"""),
        _rowcount_check(engine, "Simulated discharge agrees with clinical admission", """
            SELECT se.encounter_id FROM dbo.ops_simulated_episode se
            JOIN dbo.admissions a ON a.admission_id = se.admission_id
            WHERE EXISTS (SELECT 1 FROM dbo.ops_patient_movement pm
                WHERE pm.encounter_id = se.encounter_id AND pm.movement_type = 'Discharge'
                  AND pm.movement_status = 'Completed'
                  AND (a.discharge_datetime IS NULL OR a.discharge_datetime < a.admit_datetime
                       OR DATEDIFF(SECOND, a.discharge_datetime, pm.completed_datetime) <> 0))
               OR (a.discharge_datetime IS NOT NULL AND NOT EXISTS (
                   SELECT 1 FROM dbo.ops_patient_movement pm
                   WHERE pm.encounter_id = se.encounter_id AND pm.movement_type = 'Discharge'
                     AND pm.movement_status = 'Completed'))"""),
    ]


def run_all_checks(engine: Engine) -> pd.DataFrame:
    results = (
        run_hierarchy_checks(engine)
        + run_bed_reconciliation_checks(engine)
        + run_staffing_equipment_alert_checks(engine)
        + run_snapshot_reconciliation_checks(engine)
        + run_episode_checks(engine)
    )
    return pd.DataFrame([{"check": r.name, "status": r.status, "detail": r.detail} for r in results])


def print_summary(results: pd.DataFrame) -> str:
    fail = int((results["status"] == "FAIL").sum())
    warn = int((results["status"] == "WARN").sum())
    passed = int((results["status"] == "PASS").sum())
    overall = "FAIL" if fail else ("WARN" if warn else "PASS")
    print(f"Validation summary: {passed} PASS, {warn} WARN, {fail} FAIL -> overall {overall}")
    for _, row in results.iterrows():
        marker = {"PASS": "\u2713", "WARN": "\u26a0", "FAIL": "\u2717"}[row["status"]]
        print(f"  {marker} [{row['status']}] {row['check']} -- {row['detail']}")
    return overall
