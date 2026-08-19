"""Shared constants / conceptual "models" for the Hospital Operations package.

These are plain constants and small helper dataclasses (not an ORM layer -- the
rest of the repository uses pandas + raw SQL, not an ORM, so this package
follows the same convention for consistency).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Staffing
# ---------------------------------------------------------------------------
STAFF_ROLES = [
    ("CN", "Charge Nurse"),
    ("RN", "Registered Nurse"),
    ("PCT", "Patient Care Technician"),
    ("NP", "Nurse Practitioner"),
    ("RT", "Respiratory Therapist"),
    ("HOSP", "Hospitalist"),
    ("ATT", "Attending Physician"),
    ("CM", "Case Manager"),
    ("TRANS", "Transporter"),
    ("EVS", "Environmental Services"),
    ("BME", "Biomedical Engineer"),
]
PHYSICIAN_ROLE_CODES = {"HOSP", "ATT"}  # roles allowed to reuse an existing doctors.provider_id

SHIFT_SEED = [
    ("DAY", "Day", "07:00:00", "15:00:00", False),
    ("EVE", "Evening", "15:00:00", "23:00:00", False),
    ("NOC", "Night", "23:00:00", "07:00:00", True),
]

# ---------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------
EQUIPMENT_TYPES = [
    "Ventilator", "Infusion Pump", "Patient Monitor", "Portable X-Ray", "Ultrasound",
    "Dialysis Machine", "MRI", "CT Scanner", "Defibrillator", "ECMO",
]
CRITICAL_EQUIPMENT_TYPES = {"Ventilator", "ECMO", "Defibrillator", "Dialysis Machine"}

# unit_type -> [(equipment_type, count_expression)] where count_expression is
# either an int (fixed count per unit) or a tuple ('per_bed', ratio) meaning
# ratio * licensed_bed_count (rounded up, minimum 1).
EQUIPMENT_BY_UNIT_TYPE = {
    "Critical Care": [
        ("Ventilator", ("per_bed", 0.6)), ("Patient Monitor", ("per_bed", 1.0)),
        ("Infusion Pump", ("per_bed", 2.0)), ("Defibrillator", 2), ("ECMO", 1),
        ("Dialysis Machine", 1),
    ],
    "Emergency": [
        ("Patient Monitor", ("per_bed", 0.75)), ("Defibrillator", 3),
        ("Portable X-Ray", 2), ("Ultrasound", 1),
    ],
    "Medical/Surgical": [
        ("Patient Monitor", ("per_bed", 0.4)), ("Infusion Pump", ("per_bed", 1.0)),
    ],
    "Specialty": [("Infusion Pump", ("per_bed", 0.8)), ("Patient Monitor", ("per_bed", 0.3))],
    "Recovery": [("Patient Monitor", ("per_bed", 0.8)), ("Infusion Pump", ("per_bed", 0.6))],
    "Rehabilitation": [("Patient Monitor", ("per_bed", 0.2))],
    "Observation": [("Patient Monitor", ("per_bed", 0.5)), ("Infusion Pump", ("per_bed", 0.5))],
    "Diagnostic": [("MRI", 1), ("CT Scanner", 1), ("Ultrasound", 2), ("Portable X-Ray", 1)],
    "Medical": [("Infusion Pump", ("per_bed", 0.8)), ("Patient Monitor", ("per_bed", 0.3))],
    "default": [("Patient Monitor", ("per_bed", 0.3))],
}

# ---------------------------------------------------------------------------
# Room / bed state machines
# ---------------------------------------------------------------------------
ROOM_OPERATIONAL_STATUSES = ["Available", "Occupied", "Reserved", "Cleaning", "Maintenance", "Closed", "Isolation"]
BED_OPERATIONAL_STATUSES = ["Available", "Reserved", "Occupied", "Discharge Pending", "Cleaning", "Maintenance", "Blocked"]

# ---------------------------------------------------------------------------
# Patient flow
# ---------------------------------------------------------------------------
MOVEMENT_TYPES = [
    "Admission", "Internal Transfer", "ICU Transfer", "Step-Down Transfer",
    "Procedure Transfer", "Discharge", "Environmental Relocation", "Maintenance Relocation",
]

# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
ALERT_CATEGORIES = ["Capacity", "Staffing", "Patient Flow", "Equipment", "Environmental", "Safety", "Clinical Operations"]
ALERT_SEVERITIES = ["Info", "Warning", "Critical"]

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
SCENARIOS = [
    "NORMAL_OPERATIONS", "FRIDAY_ED_SURGE", "WINTER_RESPIRATORY_SURGE",
    "ICU_CAPACITY_CRISIS", "STAFFING_SHORTAGE", "EQUIPMENT_FAILURE", "DISCHARGE_BOTTLENECK",
]


@dataclass
class ScenarioProfile:
    """A named bundle of tunable probabilities/thresholds. Scenarios are
    configuration profiles, not separate simulator code paths (Principle:
    "Scenarios must be implemented as configuration profiles, not separate
    copies of the simulator")."""
    name: str
    admission_rate_multiplier: float = 1.0
    ed_boarding_multiplier: float = 1.0
    icu_pressure_multiplier: float = 1.0
    equipment_failure_rate: float = 0.01
    staffing_absence_rate: float = 0.05
    discharge_delay_multiplier: float = 1.0
    icu_occupancy_alert_threshold: float = 0.90
    ed_occupancy_alert_threshold: float = 0.90
    rn_coverage_alert_threshold: float = 0.85


SCENARIO_PROFILES = {
    "NORMAL_OPERATIONS": ScenarioProfile("NORMAL_OPERATIONS"),
    "FRIDAY_ED_SURGE": ScenarioProfile(
        "FRIDAY_ED_SURGE", admission_rate_multiplier=1.4, ed_boarding_multiplier=2.0,
        ed_occupancy_alert_threshold=0.85,
    ),
    "WINTER_RESPIRATORY_SURGE": ScenarioProfile(
        "WINTER_RESPIRATORY_SURGE", admission_rate_multiplier=1.3, icu_pressure_multiplier=1.5,
        equipment_failure_rate=0.02,
    ),
    "ICU_CAPACITY_CRISIS": ScenarioProfile(
        "ICU_CAPACITY_CRISIS", icu_pressure_multiplier=2.2, icu_occupancy_alert_threshold=0.80,
        discharge_delay_multiplier=1.5,
    ),
    "STAFFING_SHORTAGE": ScenarioProfile(
        "STAFFING_SHORTAGE", staffing_absence_rate=0.25, rn_coverage_alert_threshold=0.95,
    ),
    "EQUIPMENT_FAILURE": ScenarioProfile("EQUIPMENT_FAILURE", equipment_failure_rate=0.15),
    "DISCHARGE_BOTTLENECK": ScenarioProfile(
        "DISCHARGE_BOTTLENECK", discharge_delay_multiplier=2.5, ed_boarding_multiplier=1.5,
    ),
}


def get_scenario_profile(name: Optional[str]) -> ScenarioProfile:
    return SCENARIO_PROFILES.get((name or "NORMAL_OPERATIONS").upper(), SCENARIO_PROFILES["NORMAL_OPERATIONS"])
