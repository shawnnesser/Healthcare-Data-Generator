"""Per-iteration equipment state transitions + append-only equipment events."""
from __future__ import annotations

import random

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import get_next_id, insert_rows, query_db, transaction, upsert_row

_TRANSITIONS = {
    "Available": [("InUse", 0.15)],
    "InUse": [("Available", 0.20)],
    "Warning": [("Unavailable", 0.30), ("Available", 0.40)],
    "Unavailable": [("Maintenance", 0.50)],
    "Maintenance": [("Available", 0.60)],
}


def simulate_equipment_iteration(engine: Engine, simulated_now: pd.Timestamp, run_id: int,
                                  equipment_failure_rate: float, batch_size: int, rng: random.Random) -> dict:
    """Apply small, bounded equipment status changes for this iteration:
    random failures (Warning/Unavailable), routine InUse<->Available
    transitions, and maintenance completions."""
    states = query_db(
        "SELECT es.equipment_id, es.status, eq.equipment_type, eq.criticality FROM dbo.ops_equipment_state es "
        "JOIN dbo.ops_equipment eq ON es.equipment_id = eq.equipment_id ORDER BY NEWID() OFFSET 0 ROWS FETCH NEXT (:lim) ROWS ONLY",
        engine, {"lim": batch_size},
    )
    if states.empty:
        return {"events": 0, "failures": 0, "recoveries": 0}

    event_id = get_next_id("ops_equipment_event", "equipment_event_id", engine)
    events = 0
    failures = 0
    recoveries = 0
    with transaction(engine) as conn:
        for _, row in states.iterrows():
            equipment_id = int(row["equipment_id"])
            current = row["status"]

            # Scenario-driven random failure injection (independent of the routine transition table).
            if current == "Available" and rng.random() < equipment_failure_rate:
                new_status, severity, event_type = "Unavailable", "Critical", "Failure"
                failures += 1
            else:
                options = _TRANSITIONS.get(current, [])
                new_status = current
                for candidate, prob in options:
                    if rng.random() < prob:
                        new_status = candidate
                        break
                if new_status == current:
                    continue
                severity = "Warning" if new_status in ("Warning", "Unavailable") else "Info"
                event_type = "Status Change"
                if current in ("Unavailable", "Maintenance") and new_status == "Available":
                    recoveries += 1

            availability = "Available" if new_status in ("Available", "InUse") else "Unavailable"
            utilization = "InUse" if new_status == "InUse" else "Idle"
            upsert_row(conn, "ops_equipment_state", ["equipment_id"], {
                "equipment_id": equipment_id, "status": new_status, "availability_status": availability,
                "utilization_status": utilization, "battery_pct": None, "temperature": None, "pressure": None,
                "error_code": "ERR-001" if new_status == "Unavailable" else None,
                "maintenance_due_date": None, "last_seen_datetime": simulated_now,
                "updated_datetime": simulated_now, "simulation_run_id": run_id,
            })
            insert_rows(conn, "ops_equipment_event", [{
                "equipment_event_id": event_id, "equipment_id": equipment_id, "event_datetime": simulated_now,
                "event_type": event_type, "severity": severity, "metric_name": None, "metric_value": None,
                "metric_unit": None, "status_before": current, "status_after": new_status,
                "description": f"Simulated {event_type.lower()} for {row['equipment_type']}",
                "simulation_run_id": run_id,
            }])
            event_id += 1
            events += 1
    return {"events": events, "failures": failures, "recoveries": recoveries}
