"""Database connection and generic SQL helpers for Hospital Operations.

Mirrors the existing repository's connection pattern (single pooled
SQLAlchemy engine, SingletonThreadPool, pool_pre_ping) documented in
scripts/build_fabric_notebook.py, but is a plain importable module (this
package is designed to run locally / in VS Code Jupyter against the same
Fabric SQL endpoint via CONNECTION_STRING -- see
docs/HOSPITAL_OPERATIONS_ARCHITECTURE.md for why it does not (yet) use the
Fabric-notebookutils-token path the generator uses for headless deployment).
"""
from __future__ import annotations

import contextlib
from typing import Any, Dict, Iterable, Optional, Sequence

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import SingletonThreadPool

from . import config as ops_config

_ENGINE: Optional[Engine] = None


def get_engine(connection_string: Optional[str] = None, force_new: bool = False) -> Engine:
    """Return a single process-wide SQLAlchemy engine (created on first use)."""
    global _ENGINE
    if _ENGINE is not None and not force_new:
        return _ENGINE
    conn_str = connection_string or ops_config.get_connection_string()
    _ENGINE = create_engine(
        f"mssql+pyodbc:///?odbc_connect={conn_str}",
        pool_pre_ping=True,
        pool_recycle=43200,
        poolclass=SingletonThreadPool,
    )
    with _ENGINE.connect() as conn:
        conn.execute(text("SELECT 1"))
    return _ENGINE


def query_db(sql: str, engine: Engine, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """Read-only query helper; returns an empty DataFrame (not an exception) on failure
    so callers can fail soft the same way the generator's query_db() does."""
    try:
        return pd.read_sql(text(sql), engine, params=params or {})
    except Exception as e:  # noqa: BLE001 - intentional broad catch, mirrors repo convention
        print(f"[hospital_operations.db] query error: {e}")
        return pd.DataFrame()


def execute(sql: str, engine: Engine, params: Optional[Dict[str, Any]] = None) -> None:
    """Execute a single non-query statement in its own transaction."""
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def table_exists(table: str, engine: Engine) -> bool:
    df = query_db(
        "SELECT 1 AS present FROM sys.tables WHERE name = :t AND schema_id = SCHEMA_ID('dbo')",
        engine, {"t": table},
    )
    return not df.empty


def get_next_id(table: str, id_col: str, engine: Engine) -> int:
    """Same pattern as the generator's get_next_id(): MAX(id)+1, defaulting to 1."""
    df = query_db(f"SELECT MAX({id_col}) AS max_id FROM dbo.{table}", engine)
    if df.empty or pd.isna(df.iloc[0]["max_id"]):
        return 1
    return int(df.iloc[0]["max_id"]) + 1


@contextlib.contextmanager
def transaction(engine: Engine):
    """Yield a single connection wrapping one DB transaction (used by the
    real-time loop so current-state updates and their append-only event rows
    commit or roll back together)."""
    with engine.begin() as conn:
        yield conn


def upsert_row(conn, table: str, key_cols: Sequence[str], row: Dict[str, Any]) -> None:
    """Upsert a single row into a current-state table via T-SQL MERGE.

    `conn` must be an open SQLAlchemy Connection (typically inside a
    `transaction()` block so the upsert commits atomically with any
    accompanying append-only event insert).
    """
    all_cols = list(row.keys())
    update_cols = [c for c in all_cols if c not in key_cols]
    src_select = ", ".join(f":{c} AS {c}" for c in all_cols)
    on_clause = " AND ".join(f"tgt.{c} = src.{c}" for c in key_cols)
    update_clause = ", ".join(f"{c} = src.{c}" for c in update_cols) if update_cols else None
    insert_cols = ", ".join(all_cols)
    insert_vals = ", ".join(f"src.{c}" for c in all_cols)

    merge_sql = f"""
    MERGE INTO dbo.{table} AS tgt
    USING (SELECT {src_select}) AS src
    ON {on_clause}
    {"WHEN MATCHED THEN UPDATE SET " + update_clause if update_clause else ""}
    WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals});
    """
    conn.execute(text(merge_sql), row)


def bulk_upsert(conn, table: str, key_cols: Sequence[str], rows: Iterable[Dict[str, Any]]) -> int:
    """Upsert multiple rows (small/bounded batches -- this project intentionally
    avoids large bulk-copy machinery per Principle: 'keep each event batch
    small and configurable')."""
    count = 0
    for row in rows:
        upsert_row(conn, table, key_cols, row)
        count += 1
    return count


def insert_rows(conn, table: str, rows: Iterable[Dict[str, Any]]) -> int:
    """Append-only insert helper for historical/event tables."""
    count = 0
    for row in rows:
        cols = ", ".join(row.keys())
        vals = ", ".join(f":{c}" for c in row.keys())
        conn.execute(text(f"INSERT INTO dbo.{table} ({cols}) VALUES ({vals})"), row)
        count += 1
    return count
