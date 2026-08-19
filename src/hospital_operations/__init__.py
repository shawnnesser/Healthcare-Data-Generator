"""Hospital Operations - synthetic hospital operations simulation layer.

This package is a downstream, read-mostly consumer of the existing Healthcare
Data Generator's clinical database. It never modifies clinical tables
(hospitals, departments, patients, doctors, encounters, admissions, diagnoses,
procedures, medications, labs, insurance, billing, floors, rooms, beds,
patient_bed_assignments) and only reads them to build a separate operational
layer (`ops_*` tables + `vw_ops_*` views).

See docs/HOSPITAL_OPERATIONS_ARCHITECTURE.md for the full design.
"""

__all__ = [
    "config",
    "db",
    "schema",
    "models",
    "logging_utils",
    "hierarchy_generator",
    "staffing_generator",
    "equipment_generator",
    "patient_flow_simulator",
    "room_state_simulator",
    "equipment_simulator",
    "alert_engine",
    "snapshot_builder",
    "realtime_engine",
    "checkpoint",
    "validation",
]
