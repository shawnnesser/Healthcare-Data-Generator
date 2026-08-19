"""Idempotent schema deployment for Hospital Operations.

Reads the versioned .sql files under sql/hospital_operations/ (the single
source of truth for DDL - see docs/HOSPITAL_OPERATIONS_DATA_DICTIONARY.md)
and executes them in order. Every .sql file is itself idempotent (IF NOT
EXISTS guards / CREATE OR ALTER), so re-running deploy_schema() is always
safe (Principle: "Make all schema creation and seed operations idempotent").
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

from sqlalchemy import text
from sqlalchemy.engine import Engine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SQL_DIR = _REPO_ROOT / "sql" / "hospital_operations"

SCHEMA_FILES = [
    "001_create_operations_schema.sql",
    "002_create_reference_tables.sql",
    "003_create_current_state_tables.sql",
    "004_create_event_tables.sql",
    "005_create_indexes.sql",
    "006_create_snapshot_views.sql",
]
DROP_FILE = "008_drop_operations_objects.sql"


def _split_batches(sql_text: str) -> List[str]:
    """Split a SQL Server script on standalone `GO` batch separators."""
    batches = re.split(r"^\s*GO\s*$", sql_text, flags=re.IGNORECASE | re.MULTILINE)
    return [b.strip() for b in batches if b.strip()]


def _run_file(engine: Engine, path: Path) -> int:
    sql_text = path.read_text(encoding="utf-8")
    batches = _split_batches(sql_text)
    executed = 0
    with engine.begin() as conn:
        for batch in batches:
            conn.execute(text(batch))
            executed += 1
    return executed


def deploy_schema(engine: Engine, sql_dir: Path | None = None, verbose: bool = True) -> dict:
    """Execute 001-006 in order. Returns {filename: batches_executed}."""
    sql_dir = sql_dir or _SQL_DIR
    results = {}
    for filename in SCHEMA_FILES:
        path = sql_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing schema file: {path}")
        batches = _run_file(engine, path)
        results[filename] = batches
        if verbose:
            print(f"  \u2713 {filename} ({batches} batch(es))")
    return results


def drop_schema(engine: Engine, sql_dir: Path | None = None, verbose: bool = True) -> int:
    """Execute 008_drop_operations_objects.sql (removes ONLY ops_*/vw_ops_* objects)."""
    sql_dir = sql_dir or _SQL_DIR
    path = sql_dir / DROP_FILE
    batches = _run_file(engine, path)
    if verbose:
        print(f"  \u2713 {DROP_FILE} ({batches} batch(es)) -- clinical tables untouched")
    return batches


def list_ops_tables(engine: Engine) -> List[str]:
    from .db import query_db
    df = query_db("SELECT name FROM sys.tables WHERE name LIKE 'ops[_]%' ORDER BY name", engine)
    return df["name"].tolist() if not df.empty else []


def list_ops_views(engine: Engine) -> List[str]:
    from .db import query_db
    df = query_db("SELECT name FROM sys.views WHERE name LIKE 'vw[_]ops[_]%' ORDER BY name", engine)
    return df["name"].tolist() if not df.empty else []
