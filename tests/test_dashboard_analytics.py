import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "gym" / "scripts" / "gympilot.py"


def load_module(data_dir: str):
    os.environ["GYMPILOT_DATA_DIR"] = data_dir
    spec = importlib.util.spec_from_file_location("gympilot_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DashboardAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.gym = load_module(self.temp.name)
        self.gym.initialize()
        with self.gym.connect() as con:
            now = "2026-08-01T10:00:00+02:00"
            con.executemany(
                "INSERT INTO routines(id,name,notes,active,created_at) VALUES(?,?,?,1,?)",
                [(1, "Brust", "", now), (2, "Rücken", "", now), (3, "Beine", "", now)],
            )
            con.executemany(
                "INSERT INTO routine_days(id,routine_id,weekday) VALUES(?,?,?)",
                [(1, 1, 1), (2, 2, 3), (3, 3, 5)],
            )
            con.executemany(
                "INSERT INTO exercises(id,name,notes,unilateral,active) VALUES(?,?,?,0,1)",
                [(1, "Brustpresse", ""), (2, "Ruderzug", ""), (3, "Beinpresse", "")],
            )
            con.executemany(
                "INSERT INTO routine_exercises(id,routine_id,exercise_id,position,planned_sets,min_reps,max_reps,notes) VALUES(?,?,?,?,?,?,?,?)",
                [(1, 1, 1, 1, 3, 8, 12, ""), (2, 2, 2, 1, 3, 8, 12, ""), (3, 3, 3, 1, 3, 8, 12, "")],
            )
            sessions = [
                (1, 2, "2026-08-12", "2026-08-12T18:00:00+02:00", "2026-08-12T19:00:00+02:00"),
                (2, 1, "2026-08-17", "2026-08-17T18:00:00+02:00", "2026-08-17T19:00:00+02:00"),
                (3, 2, "2026-08-19", "2026-08-19T18:00:00+02:00", "2026-08-19T19:00:00+02:00"),
            ]
            con.executemany(
                "INSERT INTO sessions(id,routine_id,session_date,started_at,completed_at,notes) VALUES(?,?,?,?,?, '')",
                sessions,
            )
            set_rows = []
            set_id = 1
            for session_id, exercise_id, weights in [
                (1, 2, [70.0, 72.5, 75.0]),
                (2, 1, [40.0, 40.0, 40.0]),
                (3, 2, [72.5, 76.25, 80.0]),
            ]:
                for number, weight in enumerate(weights, 1):
                    set_rows.append((set_id, session_id, exercise_id, number, weight, 10, now))
                    set_id += 1
            con.executemany(
                "INSERT INTO workout_sets(id,session_id,exercise_id,set_number,weight_kg,reps,recorded_at) VALUES(?,?,?,?,?,?,?)",
                set_rows,
            )
            con.commit()

    def tearDown(self):
        self.temp.cleanup()
        os.environ.pop("GYMPILOT_DATA_DIR", None)

    def test_overview_marks_completed_days_and_selects_strictly_next_routine(self):
        overview = self.gym.overview_data(self.gym.date(2026, 8, 19))
        self.assertEqual("Beine", overview["next_routine"]["name"])
        self.assertEqual(
            [("Montag", "completed"), ("Mittwoch", "completed"), ("Freitag", "upcoming")],
            [(item["day_name"], item["status"]) for item in overview["week_schedule"]],
        )
        self.assertEqual(2, overview["week_adherence"]["completed"])
        self.assertEqual(3, overview["week_adherence"]["planned"])

    def test_progress_compares_same_routine_and_exercise(self):
        progress = self.gym.progress_data(self.gym.date(2026, 8, 19))
        routine = next(item for item in progress["routines"] if item["name"] == "Rücken")
        self.assertEqual(2, routine["sessions_count"])
        self.assertEqual(5.2, routine["change"]["volume_pct"])
        exercise = routine["exercises"][0]
        self.assertEqual(80.0, exercise["latest"]["best_weight_kg"])
        self.assertEqual(75.0, exercise["previous"]["best_weight_kg"])
        self.assertEqual(5.0, exercise["change"]["best_weight_delta_kg"])
        self.assertEqual("improved", exercise["change"]["status"])
        self.assertEqual(2, len(exercise["history"]))

    def test_heavier_top_set_with_lower_total_work_is_mixed(self):
        with self.gym.connect() as con:
            now = "2026-08-01T10:00:00+02:00"
            con.execute(
                "INSERT INTO exercises(id,name,notes,unilateral,active) VALUES(5,'Testzug','',0,1)"
            )
            con.execute(
                "INSERT INTO routine_exercises(id,routine_id,exercise_id,position,planned_sets,min_reps,max_reps,notes) VALUES(5,2,5,3,3,8,12,'')"
            )
            rows = []
            set_id = 20
            for session_id, values in [
                (1, [(50.0, 10), (50.0, 10), (50.0, 10)]),
                (3, [(55.0, 10), (40.0, 8), (40.0, 8)]),
            ]:
                for number, (weight, reps) in enumerate(values, 1):
                    rows.append((set_id, session_id, 5, number, weight, reps, now))
                    set_id += 1
            con.executemany(
                "INSERT INTO workout_sets(id,session_id,exercise_id,set_number,weight_kg,reps,recorded_at) VALUES(?,?,?,?,?,?,?)",
                rows,
            )
            con.commit()
        progress = self.gym.progress_data(self.gym.date(2026, 8, 19))
        routine = next(item for item in progress["routines"] if item["name"] == "Rücken")
        exercise = next(item for item in routine["exercises"] if item["name"] == "Testzug")
        self.assertEqual("mixed", exercise["change"]["status"])
        self.assertGreater(exercise["change"]["estimated_1rm_pct"], 0)
        self.assertLess(exercise["change"]["volume_pct"], 0)

    def test_progress_keeps_best_set_visible_below_target_rep_range(self):
        with self.gym.connect() as con:
            now = "2026-08-01T10:00:00+02:00"
            con.execute(
                "INSERT INTO exercises(id,name,notes,unilateral,active) VALUES(4,'Überzug am Kabelturm','',0,1)"
            )
            con.execute(
                "INSERT INTO routine_exercises(id,routine_id,exercise_id,position,planned_sets,min_reps,max_reps,notes) VALUES(4,2,4,2,3,12,15,'')"
            )
            rows = []
            set_id = 10
            for session_id, values in [
                (1, [(25.0, 10), (21.5, 10), (17.5, 10)]),
                (3, [(21.25, 10), (21.25, 10), (23.75, 9)]),
            ]:
                for number, (weight, reps) in enumerate(values, 1):
                    rows.append((set_id, session_id, 4, number, weight, reps, now))
                    set_id += 1
            con.executemany(
                "INSERT INTO workout_sets(id,session_id,exercise_id,set_number,weight_kg,reps,recorded_at) VALUES(?,?,?,?,?,?,?)",
                rows,
            )
            con.commit()
        progress = self.gym.progress_data(self.gym.date(2026, 8, 19))
        routine = next(item for item in progress["routines"] if item["name"] == "Rücken")
        exercise = next(item for item in routine["exercises"] if item["name"] == "Überzug am Kabelturm")
        self.assertEqual(23.75, exercise["latest"]["best_weight_kg"])
        self.assertEqual(9, exercise["latest"]["best_reps"])
        self.assertEqual(25.0, exercise["previous"]["best_weight_kg"])
        self.assertEqual(10, exercise["previous"]["best_reps"])
        self.assertEqual(0, exercise["latest"]["target_sets"])

    def test_overview_contains_latest_same_routine_comparison_and_highlight(self):
        overview = self.gym.overview_data(self.gym.date(2026, 8, 19))
        comparison = overview["latest_comparison"]
        self.assertEqual("Rücken", comparison["routine_name"])
        self.assertEqual("2026-08-12", comparison["previous_date"])
        self.assertEqual(5.2, comparison["volume_pct"])
        self.assertEqual("Ruderzug", overview["highlights"][0]["exercise_name"])
        self.assertEqual("weight", overview["highlights"][0]["kind"])


if __name__ == "__main__":
    unittest.main()
