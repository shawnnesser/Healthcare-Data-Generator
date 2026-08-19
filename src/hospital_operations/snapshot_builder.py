"""Application snapshot refresh.

All `vw_ops_*` snapshot objects (see
sql/hospital_operations/006_create_snapshot_views.sql) are plain SQL VIEWs
computed live from current-state tables, not materialized tables -- so there
is nothing to "rebuild"; refreshing a snapshot only means making sure the
current-state tables the views read from are up to date. This module does
that (room aggregate rollups) and provides a thin convenience reader used by
the real-time loop's heartbeat.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy.engine import Engine

from .db import query_db
from .room_state_simulator import refresh_room_aggregates


def refresh_snapshots(engine: Engine, run_id: Optional[int] = None) -> None:
    """Bring current-state aggregates the views depend on up to date."""
    refresh_room_aggregates(engine, run_id)


def get_health_system_summary(engine: Engine) -> dict:
    df = query_db("SELECT * FROM dbo.vw_ops_health_system_snapshot", engine)
    return df.iloc[0].to_dict() if not df.empty else {}


def get_hospital_summary(engine: Engine, hospital_id: Optional[int] = None) -> pd.DataFrame:
    if hospital_id:
        return query_db("SELECT * FROM dbo.vw_ops_hospital_snapshot WHERE hospital_id = :h", engine, {"h": hospital_id})
    return query_db("SELECT * FROM dbo.vw_ops_hospital_snapshot", engine)
