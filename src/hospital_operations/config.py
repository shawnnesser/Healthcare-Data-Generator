"""Configuration for the Hospital Operations package.

Follows the same conventions as the existing repository (see .env.example /
README.md "Secrets & Configuration"): CONNECTION_STRING / FABRIC_CONNECTION_STRING
env vars, optional `.env` file (never committed), no hardcoded credentials.
New tuning knobs are prefixed HOSPITAL_OPS_ (documented in .env.example).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass


def _env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name)
    return val if val not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    try:
        return int(val) if val not in (None, "") else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    try:
        return float(val) if val not in (None, "") else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val in (None, ""):
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def get_connection_string() -> str:
    """Resolve the SQL connection string using the repo's existing priority order:
    CONNECTION_STRING env var -> FABRIC_CONNECTION_STRING env var -> .env file.
    Raises RuntimeError with a clear message if none is configured (never
    hardcodes credentials).
    """
    conn = _env_str("CONNECTION_STRING") or _env_str("FABRIC_CONNECTION_STRING")
    if not conn:
        raise RuntimeError(
            "No database connection configured. Set CONNECTION_STRING (or "
            "FABRIC_CONNECTION_STRING) as an environment variable or in a "
            "local .env file. See .env.example."
        )
    return conn


@dataclass
class SimulatorConfig:
    """Real-time simulator parameters. All can be overridden via notebook
    parameters/widgets; defaults come from HOSPITAL_OPS_* environment
    variables (see .env.example). A value of 0 for runtime/iterations means
    unlimited (subject to simulation_control STOP or user interrupt)."""

    simulator_name: str = "Hospital_Operations_Realtime_Simulator"
    scenario_name: str = field(default_factory=lambda: _env_str("HOSPITAL_OPS_SCENARIO", "NORMAL_OPERATIONS"))
    update_interval_seconds: int = field(default_factory=lambda: _env_int("HOSPITAL_OPS_UPDATE_INTERVAL_SECONDS", 10))
    speed_multiplier: float = field(default_factory=lambda: _env_float("HOSPITAL_OPS_SPEED_MULTIPLIER", 60.0))
    random_seed: Optional[int] = field(default_factory=lambda: _env_int("HOSPITAL_OPS_RANDOM_SEED", 42))
    max_runtime_minutes: int = field(default_factory=lambda: _env_int("HOSPITAL_OPS_MAX_RUNTIME_MINUTES", 0))
    max_iterations: int = field(default_factory=lambda: _env_int("HOSPITAL_OPS_MAX_ITERATIONS", 0))
    batch_size: int = field(default_factory=lambda: _env_int("HOSPITAL_OPS_BATCH_SIZE", 10))
    selected_hospital_id: Optional[int] = field(default_factory=lambda: (
        int(os.environ["HOSPITAL_OPS_SELECTED_HOSPITAL_ID"])
        if os.environ.get("HOSPITAL_OPS_SELECTED_HOSPITAL_ID") not in (None, "") else None
    ))
    reset_current_state: bool = field(default_factory=lambda: _env_bool("HOSPITAL_OPS_RESET_CURRENT_STATE", False))
    resume_from_checkpoint: bool = field(default_factory=lambda: _env_bool("HOSPITAL_OPS_RESUME_FROM_CHECKPOINT", True))
    enable_patient_flow: bool = field(default_factory=lambda: _env_bool("HOSPITAL_OPS_ENABLE_PATIENT_FLOW", True))
    enable_staffing_events: bool = field(default_factory=lambda: _env_bool("HOSPITAL_OPS_ENABLE_STAFFING_EVENTS", True))
    enable_equipment_events: bool = field(default_factory=lambda: _env_bool("HOSPITAL_OPS_ENABLE_EQUIPMENT_EVENTS", True))
    enable_alerts: bool = field(default_factory=lambda: _env_bool("HOSPITAL_OPS_ENABLE_ALERTS", True))
    enable_snapshot_refresh: bool = field(default_factory=lambda: _env_bool("HOSPITAL_OPS_ENABLE_SNAPSHOT_REFRESH", True))
    log_level: str = field(default_factory=lambda: _env_str("HOSPITAL_OPS_LOG_LEVEL", "INFO"))
    heartbeat_interval_seconds: int = field(default_factory=lambda: _env_int("HOSPITAL_OPS_HEARTBEAT_INTERVAL_SECONDS", 10))
    checkpoint_interval_iterations: int = field(default_factory=lambda: _env_int("HOSPITAL_OPS_CHECKPOINT_INTERVAL", 10))
    max_consecutive_errors: int = field(default_factory=lambda: _env_int("HOSPITAL_OPS_MAX_CONSECUTIVE_ERRORS", 5))

    def with_overrides(self, **overrides) -> "SimulatorConfig":
        valid = {f.name for f in fields(self)}
        clean = {k: v for k, v in overrides.items() if k in valid and v is not None}
        return replace_dataclass(self, **clean)


def replace_dataclass(instance, **overrides):
    from dataclasses import replace
    return replace(instance, **overrides)


def load_simulator_config(**overrides) -> SimulatorConfig:
    """Build a SimulatorConfig from environment defaults, then apply any
    explicit notebook-parameter overrides (non-None values only)."""
    return SimulatorConfig().with_overrides(**overrides)
