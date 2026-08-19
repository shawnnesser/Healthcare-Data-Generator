"""Logging helpers for the Hospital Operations package.

Keeps SQL as the durable log (ops_simulation_event_log) but also emits
console logging so a human watching the notebook sees a compact heartbeat
instead of thousands of lines (Principle: "compact status block per
heartbeat instead of printing thousands of lines").
"""
from __future__ import annotations

import logging
import sys


def get_logger(name: str = "hospital_operations", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(handler)
    return logger


def heartbeat_line(**kwargs) -> str:
    """Render a single compact heartbeat status line from keyword fields."""
    parts = [f"{k}={v}" for k, v in kwargs.items()]
    return "HEARTBEAT | " + " | ".join(parts)
