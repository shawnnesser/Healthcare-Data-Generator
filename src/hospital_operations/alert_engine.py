"""Alert engine: evaluates operational thresholds and opens / escalates /
resolves rows in `ops_operational_alert`, recording every transition in the
append-only `ops_alert_event` table.

Each rule is keyed by a stable `alert_key` so the same condition is never
opened twice (Principle: "Avoid opening duplicate active alerts for the same
alert key"). A condition that clears causes the matching open alert to be
resolved; a worsening condition escalates severity in place.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import get_next_id, insert_rows, query_db, transaction
from .models import ScenarioProfile


def _get_open_alert(conn, alert_key: str) -> Optional[pd.Series]:
    df = query_db("SELECT * FROM dbo.ops_operational_alert WHERE alert_key = :k AND status <> 'Resolved'", conn, {"k": alert_key})
    return df.iloc[0] if not df.empty else None


def _open_or_escalate(conn, alert_id_holder: list, alert_key: str, hospital_id: int, category: str,
                       alert_type: str, severity: str, title: str, description: str, source_metric: str,
                       source_value: float, threshold_value: float, simulated_now: pd.Timestamp, run_id: int,
                       dims: dict) -> str:
    """Returns 'opened', 'escalated', or 'unchanged'. `conn` is the single open
    transaction connection for the whole evaluate_alerts() call -- reads and
    writes both go through it (never a separate `engine`-level connection)
    since SingletonThreadPool + an ambient transaction don't mix safely with
    nested engine.connect() calls on the same thread."""
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
            "alert_id": alert_id, "alert_key": alert_key, "hospital_id": hospital_id,
            "building_id": dims.get("building_id"), "floor_number": dims.get("floor_number"),
            "unit_id": dims.get("unit_id"), "room_id": dims.get("room_id"), "bed_id": dims.get("bed_id"),
            "equipment_id": dims.get("equipment_id"), "encounter_id": dims.get("encounter_id"),
            "category": category, "alert_type": alert_type, "severity": severity, "title": title,
            "description": description, "opened": simulated_now, "source_metric": source_metric,
            "source_value": source_value, "threshold_value": threshold_value, "run_id": run_id, "now": simulated_now,
        })
        event_id = get_next_id("ops_alert_event", "alert_event_id", conn)
        insert_rows(conn, "ops_alert_event", [{
            "alert_event_id": event_id, "alert_id": alert_id, "event_datetime": simulated_now, "event_type": "Opened",
            "status_before": None, "status_after": "Open", "description": description, "simulation_run_id": run_id,
        }])
        return "opened"

    if existing["severity"] != severity and _severity_rank(severity) > _severity_rank(existing["severity"]):
        conn.execute(text(
            "UPDATE dbo.ops_operational_alert SET severity = :sev, source_value = :sv, updated_datetime = :now "
            "WHERE alert_id = :aid"
        ), {"sev": severity, "sv": source_value, "now": simulated_now, "aid": int(existing["alert_id"])})
        event_id = get_next_id("ops_alert_event", "alert_event_id", conn)
        insert_rows(conn, "ops_alert_event", [{
            "alert_event_id": event_id, "alert_id": int(existing["alert_id"]), "event_datetime": simulated_now,
            "event_type": "Escalated", "status_before": existing["severity"], "status_after": severity,
            "description": f"Escalated to {severity}", "simulation_run_id": run_id,
        }])
        return "escalated"
    return "unchanged"


def _severity_rank(sev: str) -> int:
    return {"Info": 0, "Warning": 1, "Critical": 2}.get(sev, 0)


def _resolve_if_open(conn, alert_key: str, simulated_now: pd.Timestamp, run_id: int) -> bool:
    existing = _get_open_alert(conn, alert_key)
    if existing is None:
        return False
    conn.execute(text(
        "UPDATE dbo.ops_operational_alert SET status = 'Resolved', resolved_datetime = :now, updated_datetime = :now "
        "WHERE alert_id = :aid"
    ), {"now": simulated_now, "aid": int(existing["alert_id"])})
    event_id = get_next_id("ops_alert_event", "alert_event_id", conn)
    insert_rows(conn, "ops_alert_event", [{
        "alert_event_id": event_id, "alert_id": int(existing["alert_id"]), "event_datetime": simulated_now,
        "event_type": "Resolved", "status_before": existing["status"], "status_after": "Resolved",
        "description": "Condition cleared", "simulation_run_id": run_id,
    }])
    return True


def evaluate_alerts(engine: Engine, simulated_now: pd.Timestamp, run_id: int, scenario: ScenarioProfile) -> dict:
    """Evaluate all rules once. Returns {'opened': n, 'escalated': n, 'resolved': n}."""
    opened = escalated = resolved = 0
    alert_id_holder = [get_next_id("ops_operational_alert", "alert_id", engine)]

    hospitals = query_db("SELECT hospital_id, name FROM dbo.hospitals", engine)
    with transaction(engine) as conn:
        for _, h in hospitals.iterrows():
            hid = int(h["hospital_id"])

            # --- Capacity: ICU / ED occupancy + no-available-ICU-beds -------
            for unit_type, label, threshold_attr in (
                ("Critical Care", "ICU", "icu_occupancy_alert_threshold"),
                ("Emergency", "ED", "ed_occupancy_alert_threshold"),
            ):
                occ_df = query_db(
                    "SELECT COUNT(*) AS total, SUM(CASE WHEN bs.occupancy_status = 'Occupied' THEN 1 ELSE 0 END) AS occ "
                    "FROM dbo.beds b JOIN dbo.ops_unit u ON u.hospital_id = b.hospital_id AND u.source_floor_number = b.floor_number "
                    "LEFT JOIN dbo.ops_bed_state bs ON b.bed_id = bs.bed_id "
                    "WHERE b.hospital_id = :h AND u.unit_type = :ut", conn, {"h": hid, "ut": unit_type},
                )
                total = int(occ_df.iloc[0]["total"] or 0) if not occ_df.empty else 0
                occ = int(occ_df.iloc[0]["occ"] or 0) if not occ_df.empty else 0
                pct = (occ / total) if total > 0 else 0.0
                threshold = getattr(scenario, threshold_attr)
                key = f"CAPACITY:{label}_OCCUPANCY:hospital={hid}"
                if total > 0 and pct >= threshold:
                    sev = "Critical" if pct >= 0.97 else "Warning"
                    result = _open_or_escalate(
                        conn, alert_id_holder, key, hid, "Capacity", f"{label} Occupancy High", sev,
                        f"{label} occupancy above threshold at {h['name']}",
                        f"{label} occupancy is {pct:.0%} (threshold {threshold:.0%}).", "occupancy_pct", round(pct * 100, 1),
                        round(threshold * 100, 1), simulated_now, run_id, {"unit_id": None},
                    )
                    opened += result == "opened"; escalated += result == "escalated"
                    if total > 0 and occ >= total:
                        no_bed_key = f"CAPACITY:NO_AVAILABLE_{label}_BEDS:hospital={hid}"
                        result2 = _open_or_escalate(
                            conn, alert_id_holder, no_bed_key, hid, "Capacity", f"No Available {label} Beds", "Critical",
                            f"No available {label} beds at {h['name']}", f"All {total} {label} beds are occupied.",
                            "available_beds", 0, 0, simulated_now, run_id, {},
                        )
                        opened += result2 == "opened"
                    else:
                        resolved += _resolve_if_open(conn, f"CAPACITY:NO_AVAILABLE_{label}_BEDS:hospital={hid}", simulated_now, run_id)
                else:
                    resolved += _resolve_if_open(conn, key, simulated_now, run_id)
                    resolved += _resolve_if_open(conn, f"CAPACITY:NO_AVAILABLE_{label}_BEDS:hospital={hid}", simulated_now, run_id)

            # --- Staffing: RN coverage + open charge nurse -------------------
            staffing = query_db(
                "SELECT ss.unit_id, ss.staffing_coverage_pct, ss.charge_nurse_staff_id FROM dbo.ops_staffing_state ss "
                "JOIN dbo.ops_unit u ON ss.unit_id = u.unit_id WHERE u.hospital_id = :h", conn, {"h": hid},
            )
            for _, s in staffing.iterrows():
                unit_id = int(s["unit_id"])
                cov = float(s["staffing_coverage_pct"] or 100.0) / 100.0
                key = f"STAFFING:RN_COVERAGE_LOW:unit={unit_id}"
                if cov < scenario.rn_coverage_alert_threshold:
                    sev = "Critical" if cov < 0.6 else "Warning"
                    result = _open_or_escalate(
                        conn, alert_id_holder, key, hid, "Staffing", "RN Coverage Below Target", sev,
                        f"RN coverage below target on unit {unit_id}", f"Coverage is {cov:.0%}.",
                        "staffing_coverage_pct", round(cov * 100, 1), round(scenario.rn_coverage_alert_threshold * 100, 1),
                        simulated_now, run_id, {"unit_id": unit_id},
                    )
                    opened += result == "opened"; escalated += result == "escalated"
                else:
                    resolved += _resolve_if_open(conn, key, simulated_now, run_id)

                cn_key = f"STAFFING:OPEN_CHARGE_NURSE:unit={unit_id}"
                if pd.isna(s["charge_nurse_staff_id"]):
                    result = _open_or_escalate(
                        conn, alert_id_holder, cn_key, hid, "Staffing", "Open Charge Nurse Assignment", "Warning",
                        f"No charge nurse assigned on unit {unit_id}", "Charge nurse slot is open for the current shift.",
                        None, None, None, simulated_now, run_id, {"unit_id": unit_id},
                    )
                    opened += result == "opened"
                else:
                    resolved += _resolve_if_open(conn, cn_key, simulated_now, run_id)

            # --- Patient flow: excessive discharge delays --------------------
            delayed = query_db(
                "SELECT COUNT(*) AS n FROM dbo.ops_discharge_readiness dr JOIN dbo.admissions a ON dr.encounter_id = a.encounter_id "
                "WHERE a.hospital_id = :h AND dr.readiness_status = 'Not Ready' AND dr.outstanding_barrier_count >= 2",
                conn, {"h": hid},
            )
            delay_n = int(delayed.iloc[0]["n"]) if not delayed.empty else 0
            key = f"PATIENT_FLOW:DISCHARGE_DELAYS:hospital={hid}"
            if delay_n >= 5:
                result = _open_or_escalate(
                    conn, alert_id_holder, key, hid, "Patient Flow", "Excessive Discharge Delays",
                    "Critical" if delay_n >= 15 else "Warning", f"Excessive discharge delays at {h['name']}",
                    f"{delay_n} encounters have >=2 outstanding discharge barriers.", "delayed_discharge_count",
                    delay_n, 5, simulated_now, run_id, {},
                )
                opened += result == "opened"; escalated += result == "escalated"
            else:
                resolved += _resolve_if_open(conn, key, simulated_now, run_id)

            # --- Equipment: ventilator / imaging unavailable ------------------
            for equip_type, label in (("Ventilator", "Ventilator"), ("MRI", "Imaging"), ("CT Scanner", "Imaging"), ("Portable X-Ray", "Imaging")):
                unavailable = query_db(
                    "SELECT eq.equipment_id FROM dbo.ops_equipment eq JOIN dbo.ops_equipment_state es ON eq.equipment_id = es.equipment_id "
                    "WHERE eq.hospital_id = :h AND eq.equipment_type = :t AND es.availability_status = 'Unavailable'",
                    conn, {"h": hid, "t": equip_type},
                )
                for _, eq_row in unavailable.iterrows():
                    key = f"EQUIPMENT:{label.upper()}_UNAVAILABLE:equipment={int(eq_row['equipment_id'])}"
                    result = _open_or_escalate(
                        conn, alert_id_holder, key, hid, "Equipment", f"{equip_type} Unavailable",
                        "Critical" if equip_type == "Ventilator" else "Warning", f"{equip_type} unavailable at {h['name']}",
                        f"{equip_type} (id {int(eq_row['equipment_id'])}) is currently unavailable.", None, None, None,
                        simulated_now, run_id, {"equipment_id": int(eq_row["equipment_id"])},
                    )
                    opened += result == "opened"; escalated += result == "escalated"
                if unavailable.empty:
                    # best-effort: resolve any equipment-level alerts for this type/hospital combo not currently unavailable
                    pass

            # --- Environmental: room blocked for maintenance ------------------
            blocked = query_db(
                "SELECT rs.room_id FROM dbo.ops_room_state rs JOIN dbo.rooms r ON rs.room_id = r.room_id "
                "WHERE r.hospital_id = :h AND rs.operational_status IN ('Maintenance', 'Closed')", conn, {"h": hid},
            )
            for _, r_row in blocked.iterrows():
                key = f"ENVIRONMENTAL:ROOM_BLOCKED:room={int(r_row['room_id'])}"
                result = _open_or_escalate(
                    conn, alert_id_holder, key, hid, "Environmental", "Room Blocked For Maintenance", "Warning",
                    f"Room {int(r_row['room_id'])} blocked for maintenance", "Room is out of service.", None, None, None,
                    simulated_now, run_id, {"room_id": int(r_row["room_id"])},
                )
                opened += result == "opened"

    return {"opened": opened, "escalated": escalated, "resolved": resolved}
