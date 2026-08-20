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

    def test_progress_keeps_equipment_trajectories_separate(self):
        with self.gym.connect() as con:
            now = "2026-08-01T10:00:00+02:00"
            con.executemany(
                "INSERT INTO equipment_aliases(id,exercise_id,alias,created_at) VALUES(?,?,?,?)",
                [(1, 2, "Ruderzug A", now), (2, 2, "Ruderzug B", now)],
            )
            con.execute("UPDATE workout_sets SET equipment_alias_id=1 WHERE id IN (1,7)")
            con.execute("UPDATE workout_sets SET equipment_alias_id=2 WHERE id IN (2,3,8,9)")
            con.commit()

        progress = self.gym.progress_data(self.gym.date(2026, 8, 19))
        routine = next(item for item in progress["routines"] if item["name"] == "Rücken")
        exercise = routine["exercises"][0]

        self.assertEqual([2], exercise["latest"]["equipment_key"])
        self.assertEqual("Ruderzug B", exercise["latest"]["equipment_alias"])
        self.assertEqual(2, exercise["latest"]["sets"])
        self.assertEqual(1562.5, exercise["latest"]["volume"])
        self.assertEqual(2, len(exercise["history"]))
        self.assertTrue(all(item["equipment_key"] == [2] for item in exercise["history"]))

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

    def test_status_thresholds_use_unrounded_percentages(self):
        with self.gym.connect() as con:
            now = "2026-08-01T10:00:00+02:00"
            con.execute(
                "INSERT INTO exercises(id,name,notes,unilateral,active) VALUES(6,'Grenzwertzug','',0,1)"
            )
            con.execute(
                "INSERT INTO routine_exercises(id,routine_id,exercise_id,position,planned_sets,min_reps,max_reps,notes) "
                "VALUES(6,2,6,4,1,8,12,'')"
            )
            con.executemany(
                "INSERT INTO workout_sets(id,session_id,exercise_id,set_number,weight_kg,reps,recorded_at) "
                "VALUES(?,?,?,?,?,?,?)",
                [(200, 1, 6, 1, 100.0, 10, now), (201, 3, 6, 1, 100.96, 10, now)],
            )
            con.commit()

        progress = self.gym.progress_data(self.gym.date(2026, 8, 19))
        routine = next(item for item in progress["routines"] if item["name"] == "Rücken")
        exercise = next(item for item in routine["exercises"] if item["name"] == "Grenzwertzug")

        self.assertEqual(1.0, exercise["change"]["estimated_1rm_pct"])
        self.assertEqual(1.0, exercise["change"]["volume_pct"])
        self.assertEqual("stable", exercise["change"]["status"])

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

    def test_overview_keeps_latest_activity_outside_chart_window(self):
        with self.gym.connect() as con:
            con.execute("DELETE FROM sessions")
            con.execute(
                "INSERT INTO sessions(id,routine_id,session_date,started_at,completed_at,notes) "
                "VALUES(10,2,'2026-01-10','2026-01-10T18:00:00+01:00',"
                "'2026-01-10T19:00:00+01:00','')"
            )
            con.execute(
                "INSERT INTO workout_sets(id,session_id,exercise_id,set_number,weight_kg,reps,recorded_at) "
                "VALUES(100,10,2,1,70,10,'2026-01-10T18:10:00+01:00')"
            )
            con.commit()

        overview = self.gym.overview_data(self.gym.date(2026, 8, 19))

        self.assertEqual(["2026-01-10"], [item["session_date"] for item in overview["recent_sessions"]])
        self.assertEqual("2026-01-10", overview["latest_comparison"]["session_date"])
        self.assertTrue(all(item["volume"] == 0 for item in overview["weekly_volume"]))


if __name__ == "__main__":
    unittest.main()
