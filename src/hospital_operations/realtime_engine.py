"""Real-time simulation loop: ties patient-flow, room/bed, staffing,
equipment, and alert modules together into bounded, checkpointed iterations.

Design notes (see docs/HOSPITAL_OPERATIONS_ARCHITECTURE.md):
  * Each sub-step (patient flow, room cleaning, staffing, equipment, alerts)
    commits its own state+event rows atomically within itself (see the
    `transaction()` blocks inside patient_flow_simulator/room_state_simulator/
    equipment_simulator/alert_engine) -- there is no cross-step mega
    transaction, but every state change and its corresponding append-only
    event row always commit or roll back together.
  * simulated time = simulated_start + (wall_elapsed * speed_multiplier),
    so a run resumed after a pause continues to advance consistently.
  * The loop reads `ops_simulation_control.requested_state` every iteration:
    RUN continues, PAUSE heartbeats and waits, STOP exits cleanly.
  * KeyboardInterrupt (manual cell interrupt) is caught for a graceful
    shutdown: final checkpoint, run marked STOPPED_BY_USER, summary printed.
"""
from __future__ import annotations

import random
import time
from typing import Optional

import pandas as pd
from sqlalchemy.engine import Engine

from . import checkpoint as ckpt
from . import snapshot_builder
from .alert_engine import evaluate_alerts
from .config import SimulatorConfig
from .db import query_db
from .equipment_simulator import simulate_equipment_iteration
from .logging_utils import get_logger, heartbeat_line
from .models import get_scenario_profile
from .patient_flow_simulator import simulate_patient_flow_iteration
from .room_state_simulator import simulate_room_cleaning_iteration
from .staffing_generator import compute_staffing_state


def _simulated_now(sim_time_base: pd.Timestamp, wall_start: float, speed_multiplier: float) -> pd.Timestamp:
    wall_elapsed_seconds = time.monotonic() - wall_start
    return sim_time_base + pd.Timedelta(seconds=wall_elapsed_seconds * speed_multiplier)


def run_one_iteration(engine: Engine, run_id: int, iteration_number: int, simulated_now: pd.Timestamp,
                       cfg: SimulatorConfig, rng: random.Random) -> dict:
    """Run every enabled sub-step once and return a metrics dict for the heartbeat."""
    scenario = get_scenario_profile(cfg.scenario_name)
    metrics = {"admitted": 0, "discharge_progressed": 0, "discharged": 0, "transferred": 0,
               "rooms_cleaned": 0, "equipment_events": 0, "equipment_failures": 0, "equipment_recoveries": 0,
               "alerts_opened": 0, "alerts_escalated": 0, "alerts_resolved": 0}

    if cfg.enable_patient_flow:
        metrics.update(simulate_patient_flow_iteration(engine, simulated_now, run_id, scenario, cfg.batch_size, rng))
        metrics["rooms_cleaned"] = simulate_room_cleaning_iteration(engine, run_id, rng)

    if cfg.enable_staffing_events:
        compute_staffing_state(engine, run_id, staffing_absence_rate=scenario.staffing_absence_rate)

    if cfg.enable_equipment_events:
        eq_metrics = simulate_equipment_iteration(engine, simulated_now, run_id, scenario.equipment_failure_rate, cfg.batch_size, rng)
        metrics["equipment_events"] = eq_metrics["events"]
        metrics["equipment_failures"] = eq_metrics["failures"]
        metrics["equipment_recoveries"] = eq_metrics["recoveries"]

    if cfg.enable_alerts:
        alert_metrics = evaluate_alerts(engine, simulated_now, run_id, scenario)
        metrics["alerts_opened"] = alert_metrics["opened"]
        metrics["alerts_escalated"] = alert_metrics["escalated"]
        metrics["alerts_resolved"] = alert_metrics["resolved"]

    if cfg.enable_snapshot_refresh:
        snapshot_builder.refresh_snapshots(engine, run_id)

    return metrics


def run_loop(engine: Engine, cfg: SimulatorConfig) -> dict:
    """Main real-time loop. Returns a final run summary dict. Safe to
    Keyboard-Interrupt (e.g. stopping the notebook cell) -- rolls up a clean
    shutdown instead of leaving a dangling RUNNING run."""
    log = get_logger("hospital_operations.realtime", cfg.log_level)
    simulator_name = cfg.simulator_name

    ckpt.ensure_control_row(engine, simulator_name, cfg.scenario_name, cfg.update_interval_seconds,
                             cfg.speed_multiplier, cfg.random_seed, cfg.selected_hospital_id)
    # Starting this cell always means "run" -- force past any stale PAUSE/STOP left over
    # from a previous session (e.g. someone stopped an earlier run and never reset it).
    ckpt.set_requested_state(engine, simulator_name, "RUN", updated_by="run_loop_start")

    resumable = ckpt.find_resumable_run(engine, simulator_name) if cfg.resume_from_checkpoint else None
    if resumable is not None:
        run_id = int(resumable["simulation_run_id"])
        cp = ckpt.load_latest_checkpoint(engine, simulator_name, run_id)
        start_iteration = int(cp["last_completed_iteration"]) + 1 if cp else 1
        sim_time_base = pd.Timestamp(cp["simulated_datetime"]) if cp and cp.get("simulated_datetime") is not None else pd.Timestamp.utcnow().tz_localize(None)
        log.info(f"Resuming run {run_id} from iteration {start_iteration} (simulated time {sim_time_base}).")
    else:
        run_id = ckpt.start_run(engine, simulator_name, cfg.scenario_name, cfg.random_seed, {
            "update_interval_seconds": cfg.update_interval_seconds, "speed_multiplier": cfg.speed_multiplier,
            "batch_size": cfg.batch_size, "selected_hospital_id": cfg.selected_hospital_id,
        })
        start_iteration = 1
        sim_time_base = pd.Timestamp.utcnow().tz_localize(None)
        log.info(f"Started new run {run_id} (scenario={cfg.scenario_name}).")

    rng = random.Random(cfg.random_seed)
    wall_start = time.monotonic()
    loop_start = time.monotonic()
    iteration = start_iteration
    consecutive_errors = 0
    totals = {k: 0 for k in ["admitted", "discharged", "transferred", "alerts_opened", "alerts_resolved"]}
    final_status = "COMPLETED"

    try:
        while True:
            control = ckpt.get_control_state(engine, simulator_name) or {}
            requested_state = control.get("requested_state", "RUN")

            if requested_state == "STOP":
                log.info("STOP requested via ops_simulation_control -- exiting cleanly.")
                final_status = "STOPPED_BY_USER"
                break
            if requested_state == "PAUSE":
                ckpt.update_heartbeat(engine, run_id, iteration - 1, consecutive_errors)
                log.info(heartbeat_line(run_id=run_id, state="PAUSED", iteration=iteration))
                time.sleep(cfg.update_interval_seconds)
                continue

            if cfg.max_iterations and iteration > cfg.max_iterations:
                log.info(f"Reached MAX_ITERATIONS={cfg.max_iterations} -- stopping.")
                break
            if cfg.max_runtime_minutes and (time.monotonic() - loop_start) / 60.0 >= cfg.max_runtime_minutes:
                log.info(f"Reached MAX_RUNTIME_MINUTES={cfg.max_runtime_minutes} -- stopping.")
                break

            simulated_now = _simulated_now(sim_time_base, wall_start, cfg.speed_multiplier)
            iter_start = time.monotonic()
            try:
                metrics = run_one_iteration(engine, run_id, iteration, simulated_now, cfg, rng)
                consecutive_errors = 0
            except Exception as exc:  # noqa: BLE001 - bounded retry per Principle "retry with bounded backoff"
                consecutive_errors += 1
                log.error(f"Iteration {iteration} failed ({consecutive_errors}/{cfg.max_consecutive_errors}): {exc}")
                try:
                    ckpt.log_event(engine, run_id, iteration, "Error", "iteration_failed", status="ERROR", message=str(exc))
                except Exception as log_exc:  # noqa: BLE001 - never let error-logging itself crash the loop
                    log.error(f"  (also failed to write the error to ops_simulation_event_log: {log_exc})")
                if consecutive_errors >= cfg.max_consecutive_errors:
                    log.error("Max consecutive errors reached -- stopping.")
                    final_status = "ERROR"
                    break
                time.sleep(min(30, 2 ** consecutive_errors))
                continue

            for k in totals:
                totals[k] += metrics.get(k, 0)

            write_ms = round((time.monotonic() - iter_start) * 1000, 1)
            ckpt.update_heartbeat(engine, run_id, iteration, consecutive_errors)
            if iteration % cfg.checkpoint_interval_iterations == 0:
                ckpt.save_checkpoint(engine, simulator_name, run_id, iteration, simulated_now)

            log.info(heartbeat_line(
                run_id=run_id, scenario=cfg.scenario_name, state="RUN", iteration=iteration,
                sim_time=simulated_now.isoformat(sep=" ", timespec="seconds"),
                admitted=metrics["admitted"], discharged=metrics["discharged"], transferred=metrics["transferred"],
                beds_changed=metrics["rooms_cleaned"], equip_events=metrics["equipment_events"],
                alerts_opened=metrics["alerts_opened"], alerts_resolved=metrics["alerts_resolved"],
                write_ms=write_ms, errors=consecutive_errors,
                next_checkpoint_in=cfg.checkpoint_interval_iterations - (iteration % cfg.checkpoint_interval_iterations),
            ))

            iteration += 1
            time.sleep(cfg.update_interval_seconds)
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt -- shutting down gracefully.")
        final_status = "STOPPED_BY_USER"

    ckpt.save_checkpoint(engine, simulator_name, run_id, iteration - 1, _simulated_now(sim_time_base, wall_start, cfg.speed_multiplier))
    ckpt.complete_run(engine, run_id, final_status)
    summary = {"run_id": run_id, "final_status": final_status, "iterations_completed": iteration - 1, **totals}
    log.info(f"Run {run_id} finished with status {final_status} after {iteration - 1} iteration(s).")
    return summary
