"""Simulation control, run, and checkpoint bookkeeping.

Backs the restart/resume model described in
docs/HOSPITAL_OPERATIONS_ARCHITECTURE.md: `ops_simulation_control` is the
current-state row a human (or dashboard) can flip to PAUSE/STOP without
killing the kernel; `ops_simulation_run` is one append-mostly row per
notebook run (heartbeat + final status); `ops_simulation_checkpoint` is the
current-state "last committed iteration" a restarted run resumes from.
"""
from __future__ import annotations

import json
import socket
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import get_next_id, query_db, transaction, upsert_row

STALE_HEARTBEAT_MINUTES = 5


def ensure_control_row(engine: Engine, simulator_name: str, scenario_name: str,
                        update_interval_seconds: int, speed_multiplier: float,
                        random_seed: Optional[int], selected_hospital_id: Optional[int]) -> dict:
    """Create the control row for this simulator if absent (idempotent);
    never overwrites an existing `requested_state` set by a human/dashboard."""
    existing = query_db(
        "SELECT * FROM dbo.ops_simulation_control WHERE simulator_name = :n", engine, {"n": simulator_name}
    )
    if existing.empty:
        control_id = get_next_id("ops_simulation_control", "control_id", engine)
        with transaction(engine) as conn:
            upsert_row(conn, "ops_simulation_control", ["control_id"], {
                "control_id": control_id, "simulator_name": simulator_name, "requested_state": "RUN",
                "update_interval_seconds": update_interval_seconds, "speed_multiplier": speed_multiplier,
                "random_seed": random_seed, "scenario_name": scenario_name,
                "selected_hospital_id": selected_hospital_id,
                "last_updated_datetime": pd.Timestamp.utcnow().tz_localize(None), "updated_by": "setup",
            })
        existing = query_db("SELECT * FROM dbo.ops_simulation_control WHERE simulator_name = :n", engine, {"n": simulator_name})
    return existing.iloc[0].to_dict()


def get_control_state(engine: Engine, simulator_name: str) -> Optional[dict]:
    df = query_db("SELECT * FROM dbo.ops_simulation_control WHERE simulator_name = :n", engine, {"n": simulator_name})
    return df.iloc[0].to_dict() if not df.empty else None


def set_requested_state(engine: Engine, simulator_name: str, requested_state: str, updated_by: str = "notebook") -> None:
    """RUN | PAUSE | STOP -- can be called from a separate cell/notebook while the loop is running."""
    assert requested_state in ("RUN", "PAUSE", "STOP")
    with transaction(engine) as conn:
        conn.execute(text(
            "UPDATE dbo.ops_simulation_control SET requested_state = :s, last_updated_datetime = SYSUTCDATETIME(), "
            "updated_by = :u WHERE simulator_name = :n"
        ), {"s": requested_state, "u": updated_by, "n": simulator_name})


def find_resumable_run(engine: Engine, simulator_name: str, stale_minutes: int = STALE_HEARTBEAT_MINUTES) -> Optional[dict]:
    """Return the most recent RUNNING run for this simulator whose heartbeat
    is stale (crashed/interrupted without a clean STOP), or None."""
    df = query_db(
        "SELECT TOP 1 * FROM dbo.ops_simulation_run WHERE simulator_name = :n AND current_status = 'RUNNING' "
        "ORDER BY simulation_run_id DESC", engine, {"n": simulator_name},
    )
    if df.empty:
        return None
    row = df.iloc[0]
    last_hb = row["last_successful_iteration_datetime"] or row["started_datetime"]
    age_minutes = (pd.Timestamp.utcnow().tz_localize(None) - pd.Timestamp(last_hb)).total_seconds() / 60.0
    if age_minutes >= stale_minutes:
        return row.to_dict()
    return None


def start_run(engine: Engine, simulator_name: str, scenario_name: str, random_seed: Optional[int],
              config: dict) -> int:
    run_id = get_next_id("ops_simulation_run", "simulation_run_id", engine)
    now = pd.Timestamp.utcnow().tz_localize(None)
    with transaction(engine) as conn:
        upsert_row(conn, "ops_simulation_run", ["simulation_run_id"], {
            "simulation_run_id": run_id, "simulator_name": simulator_name, "scenario_name": scenario_name,
            "random_seed": random_seed, "started_datetime": now, "ended_datetime": None,
            "current_status": "RUNNING", "iteration_count": 0, "last_successful_iteration_datetime": now,
            "error_count": 0, "hostname": socket.gethostname(), "configuration_json": json.dumps(config, default=str),
        })
    return run_id


def update_heartbeat(engine: Engine, run_id: int, iteration_count: int, error_count: int = 0) -> None:
    with transaction(engine) as conn:
        conn.execute(text(
            "UPDATE dbo.ops_simulation_run SET iteration_count = :it, error_count = :err, "
            "last_successful_iteration_datetime = SYSUTCDATETIME() WHERE simulation_run_id = :rid"
        ), {"it": iteration_count, "err": error_count, "rid": run_id})


def complete_run(engine: Engine, run_id: int, status: str) -> None:
    """status: COMPLETED | STOPPED_BY_USER | ERROR"""
    with transaction(engine) as conn:
        conn.execute(text(
            "UPDATE dbo.ops_simulation_run SET current_status = :s, ended_datetime = SYSUTCDATETIME() "
            "WHERE simulation_run_id = :rid"
        ), {"s": status, "rid": run_id})


def save_checkpoint(engine: Engine, simulator_name: str, run_id: int, iteration: int,
                     simulated_datetime: pd.Timestamp, random_state_json: Optional[str] = None,
                     extra: Optional[dict] = None) -> None:
    with transaction(engine) as conn:
        upsert_row(conn, "ops_simulation_checkpoint", ["simulator_name", "simulation_run_id"], {
            "simulator_name": simulator_name, "simulation_run_id": run_id,
            "last_completed_iteration": iteration, "simulated_datetime": simulated_datetime,
            "random_state": random_state_json,
            "checkpoint_datetime": pd.Timestamp.utcnow().tz_localize(None),
            "checkpoint_json": json.dumps(extra or {}, default=str),
        })


def load_latest_checkpoint(engine: Engine, simulator_name: str, run_id: int) -> Optional[dict]:
    df = query_db(
        "SELECT * FROM dbo.ops_simulation_checkpoint WHERE simulator_name = :n AND simulation_run_id = :rid",
        engine, {"n": simulator_name, "rid": run_id},
    )
    return df.iloc[0].to_dict() if not df.empty else None


def log_event(engine: Engine, run_id: int, iteration_number: int, category: str, action: str,
              status: str = "OK", message: Optional[str] = None, entity_type: Optional[str] = None,
              entity_id: Optional[str] = None) -> None:
    event_id = get_next_id("ops_simulation_event_log", "simulation_event_log_id", engine)
    if message is not None and len(message) > 1000:
        message = message[:997] + "..."
    with transaction(engine) as conn:
        conn.execute(text(
            "INSERT INTO dbo.ops_simulation_event_log (simulation_event_log_id, simulation_run_id, iteration_number, "
            "event_datetime, event_category, entity_type, entity_id, action, status, message) VALUES "
            "(:id, :rid, :it, SYSUTCDATETIME(), :cat, :etype, :eid, :action, :status, :msg)"
        ), {
            "id": event_id, "rid": run_id, "it": iteration_number, "cat": category, "etype": entity_type,
            "eid": entity_id, "action": action, "status": status, "msg": message,
        })
