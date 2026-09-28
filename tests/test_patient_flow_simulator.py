import copy
import random
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from hospital_operations import patient_flow_simulator as flow, validation


class EpisodeDatabase:
    def __init__(self):
        self.rows = {}
        self.beds = {
            10: {"bed_id": 10, "occupancy_status": "Available"},
            20: {"bed_id": 20, "occupancy_status": "Available"},
            30: {"bed_id": 30, "occupancy_status": "Available"},
        }
        self.discharge_datetime = None
        self.fail_on = None
        self.queries = []
        self.icu_expected = True
        self.expected_release = None

    def query(self, sql, engine, params=None):
        self.queries.append((sql, dict(params or {})))
        if "FROM dbo.admissions a JOIN dbo.encounters" in sql:
            return pd.DataFrame([dict(admission_id=7, encounter_id=8, patient_id=9,
                                      hospital_id=1, encounter_type="Emergency",
                                      provider_id=3, specialty="general")])
        if sql.startswith("SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit"):
            return pd.DataFrame([
                dict(unit_id=11, hospital_id=1, source_floor_number=1, unit_type="Emergency"),
                dict(unit_id=22, hospital_id=1, source_floor_number=2, unit_type="Critical Care"),
                dict(unit_id=33, hospital_id=1, source_floor_number=3, unit_type="Medical Surgical"),
            ])
        if "SELECT TOP 1 bs.bed_id" in sql:
            bed_id = {1: 10, 2: 20, 3: 30}[params["f"]]
            return pd.DataFrame([{"bed_id": bed_id}]) if self.beds[bed_id]["occupancy_status"] == "Available" else pd.DataFrame()
        if "SELECT MAX(" in sql:
            return pd.DataFrame([{"max_id": None}])
        if "ops_discharge_readiness dr" in sql and "readiness_status = 'Ready'" in sql:
            return pd.DataFrame(self._occupied_rows(include_unit=True))
        if "ops_discharge_readiness dr" in sql:
            return pd.DataFrame([dict(encounter_id=8, outstanding_barrier_count=1,
                                      expected_release_datetime=self.expected_release,
                                      is_simulated=1)])
        if "FROM dbo.ops_bed_state bs" in sql and "ranked WHERE" in sql:
            return pd.DataFrame(self._occupied_rows(include_unit=False))
        raise AssertionError(sql)

    def _occupied_rows(self, include_unit):
        rows = []
        for bed_id, bed in self.beds.items():
            if bed["occupancy_status"] != "Occupied":
                continue
            row = dict(bed_id=bed_id, encounter_id=8, patient_id=9,
                       admission_id=bed["admission_id"], assigned_datetime=bed["assigned_datetime"],
                       hospital_id=1, floor_number={10: 1, 20: 2, 30: 3}[bed_id],
                       simulated_stay=1, is_simulated=1,
                       icu_expected_flag=self.icu_expected,
                       expected_release_datetime=bed.get("expected_release_datetime"))
            if include_unit:
                row["unit_id"] = {10: 11, 20: 22, 30: 33}[bed_id]
            rows.append(row)
        return rows

    @contextmanager
    def transaction(self, engine):
        before = copy.deepcopy((self.rows, self.beds, self.discharge_datetime))
        try:
            yield self
        except Exception:
            self.rows, self.beds, self.discharge_datetime = before
            raise

    def execute(self, statement, params=None):
        sql = str(statement)
        if "SELECT COALESCE(MAX(" in sql:
            return SimpleNamespace(scalar_one=lambda: 1)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("injected database failure")
        if "UPDATE dbo.admissions" in sql:
            self.discharge_datetime = params["now"]
            return SimpleNamespace(rowcount=1)
        if "INSERT INTO dbo." in sql:
            table = sql.split("INSERT INTO dbo.", 1)[1].split(" ", 1)[0]
            self.rows.setdefault(table, []).append(dict(params))
        return SimpleNamespace(rowcount=1)

    def insert(self, conn, table, rows):
        if self.fail_on == table:
            raise RuntimeError("injected database failure")
        self.rows.setdefault(table, []).extend(copy.deepcopy(rows))

    def upsert(self, conn, table, keys, row):
        if table == "ops_bed_state":
            self.beds[row["bed_id"]] = dict(row)
        else:
            self.rows.setdefault(table, []).append(dict(row))


class PatientFlowTests(unittest.TestCase):
    def setUp(self):
        self.db = EpisodeDatabase()
        self.patches = [
            patch.object(flow, "_flow_query", self.db.query),
            patch.object(flow, "transaction", self.db.transaction),
            patch.object(flow, "insert_rows", self.db.insert),
            patch.object(flow, "upsert_row", self.db.upsert),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.now = pd.Timestamp("2026-09-25 12:00:00")

    def admit(self):
        scenario = SimpleNamespace(discharge_delay_multiplier=1.0, icu_pressure_multiplier=1.0)
        return flow.admit_patients(None, self.now, 1, 1, scenario, random.Random(0))

    def test_ed_to_icu_to_discharge_preserves_episode_and_clinical_ids(self):
        self.assertEqual(self.admit(), 1)
        marker = self.db.rows["ops_simulated_episode"][0]
        self.assertEqual((marker["admission_id"], marker["encounter_id"], marker["patient_id"]), (7, 8, 9))
        for table in ("diagnoses", "medications", "labs"):
            self.assertEqual((self.db.rows[table][0]["encounter_id"],
                              self.db.rows[table][0]["patient_id"]), (8, 9))
        self.assertEqual(self.db.rows["labs"][0]["value"], "14.2")
        self.assertEqual(self.db.rows["medications"][0]["dosage"], "1 g")
        self.assertEqual(self.db.beds[10]["admission_id"], 7)
        rng = SimpleNamespace(random=lambda: 0, randint=lambda a, b: 1)
        self.assertEqual(flow.transfer_patients(None, self.now + pd.Timedelta(hours=3),
                                                2, 1, 1.0, rng), 1)
        movement = self.db.rows["ops_patient_movement"][-1]
        self.assertEqual((movement["from_unit_id"], movement["to_unit_id"],
                          movement["movement_type"]), (11, 22, "ICU Transfer"))
        self.assertEqual(self.db.beds[20]["admission_id"], 7)
        self.assertEqual(flow.discharge_ready_patients(
            None, self.now + pd.Timedelta(hours=6), 3, 1, rng), 1)
        self.assertEqual(self.db.discharge_datetime, self.now + pd.Timedelta(hours=6))
        self.assertEqual(self.db.rows["ops_patient_movement"][-1]["from_unit_id"], 22)

    def test_clinical_failure_rolls_back_episode(self):
        self.db.fail_on = "INSERT INTO dbo.labs"
        with self.assertRaisesRegex(RuntimeError, "injected database failure"):
            self.admit()
        self.assertEqual(self.db.rows, {})
        self.assertEqual(self.db.beds[10]["occupancy_status"], "Available")

    def test_unmarked_legacy_discharge_does_not_update_admission(self):
        self.db.beds[10] = dict(bed_id=10, occupancy_status="Occupied",
                                admission_id=7, assigned_datetime=self.now)

        def legacy_query(sql, engine, params=None):
            result = self.db.query(sql, engine, params)
            if "simulated_stay" in getattr(result, "columns", []):
                result["simulated_stay"] = 0
            return result

        with patch.object(flow, "_flow_query", legacy_query):
            self.assertEqual(flow.discharge_ready_patients(
                None, self.now + pd.Timedelta(hours=3), 2, 1, random.Random(0)), 1)
        self.assertIsNone(self.db.discharge_datetime)

    def test_clinical_discharge_failure_keeps_bed_occupied(self):
        self.admit()
        original_execute = self.db.execute

        def reject_discharge(statement, params=None):
            if "UPDATE dbo.admissions" in str(statement):
                return SimpleNamespace(rowcount=0)
            return original_execute(statement, params)

        with patch.object(self.db, "execute", reject_discharge):
            with self.assertRaisesRegex(RuntimeError, "Clinical discharge"):
                flow.discharge_ready_patients(
                    None, self.now + pd.Timedelta(hours=3), 2, 1, random.Random(0))
        self.assertEqual(self.db.beds[10]["occupancy_status"], "Occupied")
        self.assertIsNone(self.db.discharge_datetime)

    def test_episode_validation_reports_violations_and_query_errors(self):
        with patch.object(validation.pd, "read_sql", return_value=pd.DataFrame([{"encounter_id": 8}])):
            checks = validation.run_episode_checks(None)
        self.assertEqual(len(checks), 4)
        self.assertTrue(all(check.status == "FAIL" for check in checks))
        # A broken query must fail loudly in the summary, not pass silently and
        # not abort the remaining checks.
        with patch.object(validation.pd, "read_sql", side_effect=RuntimeError("schema unavailable")):
            errored = validation.run_episode_checks(None)
        self.assertEqual(len(errored), 4)
        self.assertTrue(all(check.status == "FAIL" for check in errored))
        self.assertIn("schema unavailable", errored[0].detail)

    def test_non_ed_encounter_does_not_start_in_emergency(self):
        units = self.db.query(
            "SELECT unit_id, hospital_id, source_floor_number, unit_type FROM dbo.ops_unit", None)
        selected = flow._pick_target_unit(units, 1, "Inpatient", random.Random(0))
        # A direct (non-ED) admission goes to a general bed, never the ED, and
        # prefers med-surg over critical care when both have capacity.
        self.assertEqual(selected["unit_type"], "Medical Surgical")
        icu_only = units[units["unit_type"].isin(["Critical Care", "Emergency"])]
        self.assertEqual(
            flow._pick_target_unit(icu_only, 1, "Inpatient", random.Random(0))["unit_type"],
            "Critical Care")
        self.assertIsNone(flow._pick_target_unit(units[units["unit_type"] == "Emergency"],
                                                  1, "Inpatient", random.Random(0)))

    def test_length_of_stay_is_drawn_from_the_condition_not_the_clock(self):
        # Regression: length of stay used to be a geometric random walk over
        # iteration count, so it scaled with SPEED_MULTIPLIER instead of with
        # what the patient actually had.
        self.assertEqual(self.admit(), 1)
        episode = self.db.rows["ops_simulated_episode"][0]
        # The "general" story is pneumonia (J18.9), a Respiratory diagnosis.
        self.assertEqual(episode["icd_family"], "Respiratory")
        self.assertEqual(self.db.rows["diagnoses"][0]["icd_code"], "J18.9")
        self.assertGreater(episode["target_los_hours"], flow._MIN_DWELL_HOURS)
        self.assertEqual(
            episode["expected_discharge_datetime"],
            self.now + pd.Timedelta(hours=episode["target_los_hours"]),
        )
        # The plan must reach the bed so downstream steps can gate on it.
        self.assertEqual(self.db.beds[10]["expected_release_datetime"],
                         episode["expected_discharge_datetime"])

        # Barriers must not clear before the drawn stay has elapsed, however
        # many iterations run in the meantime.
        self.db.beds[10]["occupancy_status"] = "Occupied"
        self.db.expected_release = episode["expected_discharge_datetime"]
        always_progress = SimpleNamespace(random=lambda: 0.0, randint=lambda a, b: 1)
        for _ in range(50):
            self.assertEqual(flow.advance_discharge_readiness(
                None, self.now + pd.Timedelta(hours=1), 1, 10, 1.0, always_progress), 0)
        # Once the simulated clock passes it, the stay progresses.
        self.assertEqual(flow.advance_discharge_readiness(
            None, episode["expected_discharge_datetime"] + pd.Timedelta(hours=1),
            1, 10, 1.0, always_progress), 1)

    def test_only_icu_flagged_stays_escalate_from_the_emergency_department(self):
        # Regression: every ED patient selected for transfer was forced into
        # Critical Care, putting far more of the census in the ICU than the
        # published ~18% of admissions.
        # Weight by the live admission mix (general/pediatric/fallback 65%,
        # cardiac 15%, cancer 10%, rehab 10%). Calibrating against the flat
        # 16-family average instead realized ~33% ICU on a live run.
        admitted = (["general"] * 65 + ["cardiac"] * 15 + ["cancer"] * 10 + ["rehab"] * 10)
        families = [flow._story_family(s) for s in admitted]
        calibration = flow._icu_calibration(families)
        self.assertAlmostEqual(
            sum(flow._icu_admit_probability(f, calibration) for f in families) / len(families),
            flow._ICU_TARGET_SHARE, places=6)
        flat = flow._icu_calibration([])
        self.assertGreater(
            sum(flow._icu_admit_probability(f, flat) for f in families) / len(families), 0.25)

        self.db.beds[10] = dict(bed_id=10, occupancy_status="Occupied", admission_id=7,
                                assigned_datetime=self.now, expected_release_datetime=None)
        self.db.icu_expected = False
        always = SimpleNamespace(random=lambda: 0.0, randint=lambda a, b: 1)
        self.assertEqual(flow.transfer_patients(
            None, self.now + pd.Timedelta(hours=3), 2, 1, 1.0, always), 1)
        self.assertEqual(self.db.rows["ops_patient_movement"][-1]["movement_type"],
                         "Internal Transfer")
        self.assertEqual(self.db.rows["ops_patient_movement"][-1]["to_unit_id"], 33)

    def test_transfer_preserves_the_drawn_length_of_stay(self):
        release = self.now + pd.Timedelta(days=4)
        self.db.beds[10] = dict(bed_id=10, occupancy_status="Occupied", admission_id=7,
                                assigned_datetime=self.now, expected_release_datetime=release)
        always = SimpleNamespace(random=lambda: 0.0, randint=lambda a, b: 1)
        self.assertEqual(flow.transfer_patients(
            None, self.now + pd.Timedelta(hours=3), 2, 1, 1.0, always), 1)
        # Moving units must not erase the stay plan, or the patient would fall
        # back to the legacy random walk and never discharge on schedule.
        self.assertEqual(self.db.beds[20]["expected_release_datetime"], release)

    def test_selection_reserves_capacity_for_simulated_episodes(self):
        # Regression: a live database holds a large backlog of older legacy rows.
        # Selecting purely oldest-first starved new episodes so they never
        # progressed past admission, so each batch must reserve slots for them.
        self.assertEqual(flow._split_batch(10), (5, 5))
        self.assertEqual(flow._split_batch(1), (1, 0))
        self.assertEqual(flow._split_batch(3), (1, 2))

        self.db.beds[10] = dict(bed_id=10, occupancy_status="Occupied",
                                admission_id=7, assigned_datetime=self.now)
        self.db.queries.clear()
        rng = SimpleNamespace(random=lambda: 1, randint=lambda a, b: 1)
        flow.advance_discharge_readiness(None, self.now, 1, 10, 1.0, rng)
        flow.transfer_patients(None, self.now + pd.Timedelta(hours=3), 1, 10, 1.0, rng)
        flow.discharge_ready_patients(None, self.now + pd.Timedelta(hours=3), 1, 10, rng)

        partitioned = [(sql, params) for sql, params in self.db.queries if "ranked WHERE" in sql]
        self.assertEqual(len(partitioned), 3)
        for sql, params in partitioned:
            self.assertIn("PARTITION BY", sql)
            self.assertEqual((params["sim_lim"], params["legacy_lim"]), (5, 5))


if __name__ == "__main__":
    unittest.main()
