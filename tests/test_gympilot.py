from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib.util
import csv
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "gym" / "scripts" / "gympilot.py"
WEB = ROOT / "skills" / "gym" / "assets" / "web"


def load_module():
    spec = importlib.util.spec_from_file_location("gympilot", CLI)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GymPilotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "hermes"
        self.env = {**os.environ, "HERMES_HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1"}

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, check=True, input_text=None):
        result = subprocess.run(
            [sys.executable, str(CLI), "--json", *map(str, args)],
            env=self.env, text=True, input=input_text, capture_output=True,
        )
        payload = json.loads(result.stdout) if result.stdout.strip() else None
        if check and result.returncode:
            self.fail(f"CLI failed: {result.stderr}\n{result.stdout}")
        return result, payload

    def routine(self, name="Push", *days):
        args = ["routine", "add", name]
        for day in days or (1,):
            args += ["--weekday", day]
        return self.cli(*args)[1]

    def exercise(self, routine_id, name="Press", sets=3, low=8, high=12):
        return self.cli(
            "exercise", "add", routine_id, name, "--sets", sets,
            "--min-reps", low, "--max-reps", high,
        )[1]

    def test_fresh_profile_schema_constraints_and_status(self):
        _, created = self.cli("init")
        self.assertEqual(created["schema_version"], 1)
        db = self.home / "gympilot" / "gympilot.db"
        self.assertTrue(db.is_file())
        self.assertFalse((ROOT / "skills" / "gym" / "gympilot.db").exists())
        with sqlite3.connect(db) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"schema_migrations", "user_profile", "onboarding_state", "routines", "routine_days", "exercises", "equipment_aliases", "routine_exercises", "sessions", "workout_sets", "auth_config", "web_sessions"} <= tables)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 1)
            side = next(r for r in con.execute("PRAGMA table_info(workout_sets)") if r[1] == "side")
            self.assertEqual(side[3], 1)
            self.assertEqual(side[4], "''")
            indexes = {r[1] for r in con.execute("PRAGMA index_list(sessions)")}
            self.assertIn("idx_one_active_session", indexes)
        _, status = self.cli("status")
        self.assertEqual(status["data_dir"], str((self.home / "gympilot").resolve()))

    def test_onboarding_resumes_into_persisted_training_plan_and_rejects_password(self):
        self.cli("init")
        basics = {"display_name": "Alex", "locale": "de", "units": "metric", "goal": "Kraft"}
        for field, value in basics.items():
            self.cli("onboarding", "set", field, value)
        result, payload = self.cli("onboarding", "set", "routine_count", "999999999999999999999", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must not exceed", payload["error"])
        self.cli("onboarding", "set", "routine_count", "1")
        self.cli("onboarding", "set", "routine_1_name", "Ganzkörper")
        _, interrupted = self.cli("onboarding", "status")
        self.assertEqual(interrupted["next_field"], "routine_1_weekdays")
        self.assertFalse(interrupted["complete"])

        # A separate process resumes from durable state.
        self.cli("onboarding", "set", "routine_1_weekdays", "1,4")
        self.cli("onboarding", "set", "routine_1_exercise_count", "1")
        self.cli("onboarding", "set", "routine_1_exercise_1_name", "Kniebeuge")
        self.cli("onboarding", "set", "routine_1_exercise_1_sets", "3")
        self.cli("onboarding", "set", "routine_1_exercise_1_min_reps", "5")
        rejected, payload = self.cli("onboarding", "set", "routine_1_exercise_1_max_reps", "4", check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("below minimum", payload["error"])
        self.assertEqual(self.cli("onboarding", "status")[1]["next_field"], "routine_1_exercise_1_max_reps")
        _, complete = self.cli("onboarding", "set", "routine_1_exercise_1_max_reps", "8")
        self.assertTrue(complete["complete"])
        self.assertEqual(complete["phase"], "complete")
        _, plan = self.cli("plan")
        self.assertEqual(plan[0]["name"], "Ganzkörper")
        self.assertEqual(plan[0]["weekdays"], [1, 4])
        self.assertEqual(plan[0]["exercises"][0]["name"], "Kniebeuge")

        result, payload = self.cli("onboarding", "set", "password", "secret", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("password", payload["error"])
        self.assertNotIn(b"secret", (self.home / "gympilot" / "gympilot.db").read_bytes())
        result, payload = self.cli("onboarding", "set", "routine_count", "2", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("already complete", payload["error"])
        self.assertEqual(len(self.cli("plan")[1]), 1)

    def test_concurrent_final_onboarding_answer_is_atomic(self):
        self.cli("init")
        values = [
            ("display_name", "Alex"), ("locale", "de"), ("units", "metric"), ("goal", "Kraft"),
            ("routine_count", "1"), ("routine_1_name", "Ganzkörper"), ("routine_1_weekdays", "1"),
            ("routine_1_exercise_count", "1"), ("routine_1_exercise_1_name", "Kniebeuge"),
            ("routine_1_exercise_1_sets", "3"), ("routine_1_exercise_1_min_reps", "5"),
        ]
        for field, value in values:
            self.cli("onboarding", "set", field, value)
        barrier = threading.Barrier(2)
        def finish(value):
            barrier.wait()
            return subprocess.run(
                [sys.executable, str(CLI), "--json", "onboarding", "set", "routine_1_exercise_1_max_reps", value],
                env=self.env, text=True, capture_output=True,
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(finish, ("8", "12")))
        self.assertEqual(sorted(result.returncode for result in results), [0, 2])
        status = self.cli("onboarding", "status")[1]
        plan = self.cli("plan")[1]
        self.assertEqual(status["answers"]["plan_materialized"], "1")
        self.assertEqual(int(status["answers"]["routine_1_exercise_1_max_reps"]), plan[0]["exercises"][0]["max_reps"])

    def test_duplicate_active_session_is_rejected_by_cli_and_database(self):
        self.cli("init")
        routine = self.routine()
        first = self.cli("session", "start", "--routine", routine["id"])[1]
        result, payload = self.cli("session", "start", "--routine", routine["id"], check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(first["id"]), payload["error"])
        db = self.home / "gympilot" / "gympilot.db"
        with sqlite3.connect(db) as con, self.assertRaises(sqlite3.IntegrityError):
            con.execute("INSERT INTO sessions(routine_id,session_date,started_at) VALUES(?,?,?)", (routine["id"], "2026-01-01", "x"))

    def test_active_routine_cannot_disappear_and_dates_are_strict(self):
        self.cli("init")
        routine = self.routine("Aktiv", 1)
        invalid, payload = self.cli("session", "start", "--routine", routine["id"], "--date", "08.08.2026", check=False)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("YYYY-MM-DD", payload["error"])
        session = self.cli("session", "start", "--routine", routine["id"], "--date", "2026-08-08")[1]
        blocked, payload = self.cli("routine", "deactivate", routine["id"], check=False)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("active session", payload["error"])
        # Defensive read path: even an external DB edit cannot hide a running session.
        with sqlite3.connect(self.home / "gympilot" / "gympilot.db") as con:
            con.execute("UPDATE routines SET active=0 WHERE id=?", (routine["id"],))
            con.commit()
        today = self.cli("today")[1]
        self.assertEqual(today["active_session"]["id"], session["id"])
        self.assertEqual(today["routine"]["id"], routine["id"])

    def test_set_must_belong_to_active_session_routine_and_side_uniqueness(self):
        self.cli("init")
        push = self.routine("Push", 1)
        pull = self.routine("Pull", 2)
        press = self.exercise(push["id"], "Press")
        row = self.exercise(pull["id"], "Row")
        session = self.cli("session", "start", "--routine", push["id"])[1]
        result, payload = self.cli("set", "log", session["id"], row["id"], "--weight", 40, "--reps", 10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not belong", payload["error"])
        logged = self.cli("set", "log", session["id"], press["id"], "--weight", 42.25, "--reps", 10, "--number", 1)[1]
        self.assertEqual(logged["side"], "")
        for value in ("inf", "-inf", "nan"):
            result, payload = self.cli("set", "log", session["id"], press["id"], f"--weight={value}", "--reps", 10, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("finite", payload["error"])
        result, payload = self.cli("set", "correct", logged["id"], "--rpe", "nan", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("finite", payload["error"])
        huge, payload = self.cli("set", "log", session["id"], press["id"], "--weight", 10, "--reps", "9" * 100, check=False)
        self.assertEqual(huge.returncode, 2)
        self.assertIn("too large", payload["error"])
        duplicate, _ = self.cli("set", "log", session["id"], press["id"], "--weight", 43, "--reps", 9, "--number", 1, check=False)
        self.assertEqual(duplicate.returncode, 2)

    def test_weekday_assignment_is_unambiguous_on_add_and_update(self):
        self.cli("init")
        push = self.routine("Push", 1)
        result, payload = self.cli("routine", "add", "Pull", "--weekday", 1, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("weekday 1", payload["error"])
        pull = self.routine("Pull", 2)
        result, payload = self.cli("routine", "update", pull["id"], "--weekday", 1, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("weekday 1", payload["error"])
        self.cli("routine", "deactivate", push["id"])
        updated = self.cli("routine", "update", pull["id"], "--name", "Back", "--weekday", 1, "--notes", "Neu")[1]
        self.assertEqual(updated["name"], "Back")
        self.assertEqual(updated["weekdays"], [1])

    def test_plan_adjustments_preserve_workout_history(self):
        self.cli("init")
        routine = self.routine()
        exercise = self.exercise(routine["id"])
        session = self.cli("session", "start", "--routine", routine["id"], "--date", "2026-01-01")[1]
        logged = self.cli("set", "log", session["id"], exercise["id"], "--weight", 40, "--reps", 10)[1]
        self.cli("session", "finish", session["id"])
        updated = self.cli(
            "exercise", "update", routine["id"], exercise["id"], "--name", "Bankdrücken",
            "--sets", 4, "--min-reps", 6, "--max-reps", 9, "--notes", "Pause", "--unilateral",
        )[1]
        self.assertEqual(updated["name"], "Bankdrücken")
        self.assertEqual(updated["planned_sets"], 4)
        self.assertEqual(updated["unilateral"], 1)
        self.cli("exercise", "remove", routine["id"], exercise["id"])
        self.assertEqual(self.cli("plan")[1][0]["exercises"], [])
        db = self.home / "gympilot" / "gympilot.db"
        with sqlite3.connect(db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM workout_sets WHERE id=?", (logged["id"],)).fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM exercises WHERE id=?", (exercise["id"],)).fetchone()[0], 1)

    def test_today_uses_previous_same_routine_and_separates_current_sets(self):
        self.cli("init")
        push = self.routine("Push", 1)
        pull = self.routine("Pull", 2)
        press = self.exercise(push["id"], "Press", sets=2)
        row = self.exercise(pull["id"], "Row")

        old_push = self.cli("session", "start", "--routine", push["id"], "--date", "2026-01-01")[1]
        self.cli("set", "log", old_push["id"], press["id"], "--weight", 42.25, "--reps", 10)
        self.cli("session", "finish", old_push["id"])
        pull_session = self.cli("session", "start", "--routine", pull["id"], "--date", "2026-01-03")[1]
        self.cli("set", "log", pull_session["id"], row["id"], "--weight", 80, "--reps", 8)
        self.cli("session", "finish", pull_session["id"])
        recent_push = self.cli("session", "start", "--routine", push["id"], "--date", "2026-01-05")[1]
        self.cli("set", "log", recent_push["id"], press["id"], "--weight", 45.5, "--reps", 9)
        self.cli("set", "log", recent_push["id"], press["id"], "--weight", 45.75, "--reps", 8)
        self.cli("session", "finish", recent_push["id"])
        current = self.cli("session", "start", "--routine", push["id"], "--date", "2026-01-08")[1]
        self.cli("set", "log", current["id"], press["id"], "--weight", 46.25, "--reps", 8)

        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        today = gym.today_data(routine_id=push["id"])
        self.assertEqual(today["routine"]["last_comparable_session_date"], "2026-01-05")
        detail = today["routine"]["exercises"][0]
        self.assertEqual([(s["weight_kg"], s["reps"]) for s in detail["last_sets"]], [(45.5, 9), (45.75, 8)])
        self.assertEqual([(s["weight_kg"], s["reps"]) for s in detail["current_sets"]], [(46.25, 8)])
        self.assertEqual(detail["current_progress"], {"completed_sets": 1, "planned_sets": 2})

    def test_password_hash_is_one_way_and_verifies(self):
        gym = load_module()
        encoded = gym.hash_password("correct horse")
        self.assertTrue(encoded.startswith(("scrypt$", "pbkdf2-sha256$")))
        self.assertNotIn("correct horse", encoded)
        self.assertTrue(gym.verify_password("correct horse", encoded))
        self.assertFalse(gym.verify_password("wrong", encoded))

    def test_server_private_api_is_never_cached_and_web_assets_are_functional(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        server = gym.make_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            for endpoint in ("/api/health", "/api/today", "/api/plan", "/api/overview"):
                conn.request("GET", endpoint)
                response = conn.getresponse()
                response.read()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Cache-Control"), "no-store")
                self.assertIn("no-cache", response.getheader("Pragma"))
            conn.request("GET", "/service-worker.js")
            response = conn.getresponse()
            sw = response.read().decode()
            self.assertNotIn("/api/", json.loads((WEB / "manifest.webmanifest").read_text()).get("icons", []))
            self.assertIn("pathname.startsWith('/api/')", sw)
            self.assertIn("cache: 'no-store'", sw)
            self.assertNotIn("/api/today", sw.split("SHELL=", 1)[-1].split(";", 1)[0])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
        app = (WEB / "app.js").read_text()
        index = (WEB / "index.html").read_text()
        self.assertIn("last_sets", app)
        self.assertIn("current_sets", app)
        self.assertIn("data-view", index)
        self.assertIn("apple-touch-icon", index)

    def test_png_icons_are_valid_and_declared(self):
        manifest = json.loads((WEB / "manifest.webmanifest").read_text())
        declared = {Path(icon["src"]).name: icon["sizes"] for icon in manifest["icons"]}
        expected = {"icon-192.png": 192, "icon-512.png": 512}
        self.assertEqual(set(expected), set(declared))
        for name, size in {**expected, "apple-touch-icon.png": 180, "favicon-32.png": 32}.items():
            data = (WEB / "icons" / name).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), (size, size))

    def test_equipment_alias_is_validated_stored_and_exported(self):
        self.cli("init")
        routine = self.routine("Beine", 5)
        press = self.exercise(routine["id"], "Beinpresse")
        curl = self.exercise(routine["id"], "Beinbeuger")
        alias = self.cli("equipment", "add", press["id"], "Beinpresse Studio A")[1]
        listed = self.cli("equipment", "list")[1]
        self.assertEqual(listed[0]["exercise_name"], "Beinpresse")
        session = self.cli("session", "start", "--routine", routine["id"])[1]
        wrong, payload = self.cli("set", "log", session["id"], curl["id"], "--weight", 40, "--reps", 10, "--equipment", alias["id"], check=False)
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("does not belong", payload["error"])
        logged = self.cli("set", "log", session["id"], press["id"], "--weight", 87.5, "--reps", 10, "--equipment", alias["id"])[1]
        self.assertEqual(logged["equipment_alias_id"], alias["id"])
        pounds = self.cli("set", "log", session["id"], press["id"], "--weight", 100, "--unit", "lb", "--reps", 8, "--equipment", alias["id"])[1]
        self.assertAlmostEqual(pounds["weight_kg"], 45.359237)
        self.cli("session", "finish", session["id"])
        today = self.cli("today")[1]
        selected = next(item for item in today["plan"] if item["id"] == routine["id"])
        self.assertEqual(selected["exercises"][0]["equipment_aliases"][0]["alias"], "Beinpresse Studio A")
        exported = self.cli("export")[1]
        self.assertIn("Beinpresse Studio A", Path(exported["csv"]).read_text(encoding="utf-8"))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(Path(exported["json"]).parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(Path(exported["json"]).stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(exported["csv"]).stat().st_mode), 0o600)

        backup = self.cli("backup")[1]
        with sqlite3.connect(backup["path"]) as backed_up:
            self.assertEqual(backed_up.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(backed_up.execute("SELECT COUNT(*) FROM workout_sets").fetchone()[0], 2)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(Path(backup["path"]).parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(Path(backup["path"]).stat().st_mode), 0o600)

    def test_private_paths_reject_symlink_redirection(self):
        redirected = Path(self.tmp.name) / "redirected"
        redirected.mkdir()
        linked_home = Path(self.tmp.name) / "linked-home"
        linked_home.symlink_to(redirected, target_is_directory=True)
        env = {**self.env, "HERMES_HOME": str(linked_home)}
        result = subprocess.run([sys.executable, str(CLI), "--json", "init"], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("symlink", json.loads(result.stdout)["error"])

        isolated = Path(self.tmp.name) / "isolated"
        env = {**self.env, "HERMES_HOME": str(isolated)}
        subprocess.run([sys.executable, str(CLI), "--json", "init"], env=env, text=True, capture_output=True, check=True)
        data = isolated / "gympilot"
        for name, command in (("exports", "export"), ("backups", "backup")):
            link = data / name
            link.symlink_to(redirected, target_is_directory=True)
            result = subprocess.run([sys.executable, str(CLI), "--json", command], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("symlink", json.loads(result.stdout)["error"])
            link.unlink()

        empty_home = Path(self.tmp.name) / "empty-home"
        env = {**self.env, "HOME": str(empty_home), "HERMES_HOME": "", "GYMPILOT_DATA_DIR": ""}
        result = subprocess.run([sys.executable, str(CLI), "--json", "init"], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((empty_home / ".hermes" / "gympilot" / "gympilot.db").is_file())

        gym = load_module()
        self.assertLessEqual(len(gym.onboarding_sequence({"routine_count": "9" * 100})), 50)

    @unittest.skipIf(os.name == "nt", "descriptor-relative backup is POSIX-only")
    def test_backup_descriptor_resists_final_path_swap(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        victim = Path(self.tmp.name) / "victim.db"
        with sqlite3.connect(victim) as con:
            con.execute("CREATE TABLE marker(value TEXT)")
            con.execute("INSERT INTO marker VALUES('untouched')")
        original = gym.prepare_private_file
        def swap_after_open(path):
            descriptor = original(path)
            path.unlink()
            path.symlink_to(victim)
            return descriptor
        gym.prepare_private_file = swap_after_open
        with self.assertRaisesRegex(ValueError, "path changed"):
            gym.command(gym.parser().parse_args(["backup"]))
        with sqlite3.connect(victim) as con:
            self.assertEqual(con.execute("SELECT value FROM marker").fetchone()[0], "untouched")

    def test_export_uses_one_read_snapshot(self):
        self.cli("init")
        routine=self.routine("Snapshot",1); exercise=self.exercise(routine["id"],"Rudern")
        session=self.cli("session","start","--routine",routine["id"])[1]
        self.cli("set","log",session["id"],exercise["id"],"--weight",20,"--reps",10)
        gym=load_module(); os.environ["HERMES_HOME"]=str(self.home)
        original=gym.rows; calls=0
        def insert_between_queries(cursor):
            nonlocal calls
            result=original(cursor); calls+=1
            if calls==8:
                with sqlite3.connect(gym.db_path()) as writer:
                    writer.execute("PRAGMA foreign_keys=ON")
                    writer.execute("INSERT INTO workout_sets(session_id,exercise_id,set_number,side,weight_kg,reps,notes,recorded_at) VALUES(?,?,?,?,?,?,?,?)",(session["id"],exercise["id"],2,"",21,9,"",gym.now()))
            return result
        gym.rows=insert_between_queries
        exported=gym.command(gym.parser().parse_args(["export"]))
        payload=json.loads(Path(exported["json"]).read_text())
        with open(exported["csv"],newline="",encoding="utf-8") as source: csv_rows=list(csv.reader(source))
        self.assertEqual(len(payload["workout_sets"]),1)
        self.assertEqual(len(csv_rows)-1,1)
        with sqlite3.connect(gym.db_path()) as con: self.assertEqual(con.execute("SELECT COUNT(*) FROM workout_sets").fetchone()[0],2)

    def test_huge_cli_integer_returns_json_error(self):
        result=subprocess.run([sys.executable,str(CLI),"--json","routine","deactivate","9"*5000],env=self.env,text=True,capture_output=True)
        self.assertEqual(result.returncode,2)
        self.assertEqual(result.stderr,"")
        self.assertIn("too large",json.loads(result.stdout)["error"])

    def test_server_rejects_public_wildcard(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        with self.assertRaises(ValueError):
            gym.make_server("0.0.0.0", 0)
        if socket.has_ipv6:
            try:
                server = gym.make_server("::1", 0)
            except OSError as exc:
                self.skipTest(f"IPv6 loopback unavailable: {exc}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = http.client.HTTPConnection("::1", server.server_port, timeout=5)
                conn.request("GET", "/api/health")
                response = conn.getresponse(); response.read()
                self.assertEqual(response.status, 200)
            finally:
                server.shutdown(); server.server_close(); thread.join(5)

    def test_host_header_body_limits_rate_limiter_and_profile_isolation(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        live = gym.connect()
        live.execute("SELECT COUNT(*) FROM user_profile").fetchone()
        if os.name != "nt":
            for suffix in ("", "-wal", "-shm"):
                candidate = Path(f"{gym.db_path()}{suffix}")
                if candidate.exists(): self.assertEqual(stat.S_IMODE(candidate.stat().st_mode), 0o600)
        live.close()
        limiter = gym.RateLimiter()
        with ThreadPoolExecutor(max_workers=20) as pool:
            accepted = list(pool.map(lambda _: limiter.begin("client"), range(20)))
        self.assertEqual(sum(accepted), 5)

        server = gym.make_server("127.0.0.1", 0)
        reserved = [server.request_slots.acquire(blocking=False) for _ in range(33)]
        self.assertEqual(sum(reserved), 32)
        for acquired in reserved:
            if acquired:
                server.request_slots.release()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            malformed = (
                "attacker.example", "attacker.example@127.0.0.1",
                "127.0.0.1:evil", f"127.0.0.1:{server.server_port + 1}",
                "127.0.0.1,attacker.example", "[127.0.0.1]",
            )
            for authority in malformed:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.putrequest("GET", "/api/today", skip_host=True)
                conn.putheader("Host", authority)
                conn.endheaders()
                response = conn.getresponse(); response.read()
                self.assertEqual(response.status, 421, authority)

            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.putrequest("GET", "/api/today", skip_host=True)
            conn.putheader("Host", f"127.0.0.1:{server.server_port}")
            conn.putheader("Host", f"127.0.0.1:{server.server_port}")
            conn.endheaders()
            response = conn.getresponse(); response.read()
            self.assertEqual(response.status, 421)

            framing_headers = (
                [],
                [("Content-Length", "+2"), ("Content-Type", "application/json")],
                [("Content-Length", "-0"), ("Content-Type", "application/json")],
                [("Content-Length", "2,2"), ("Content-Type", "application/json")],
                [("Content-Length", "2"), ("Content-Length", "2"), ("Content-Type", "application/json")],
                [("Content-Length", "2"), ("Content-Length", "3"), ("Content-Type", "application/json")],
                [("Transfer-Encoding", "chunked"), ("Content-Type", "application/json")],
                [("Transfer-Encoding", "chunked"), ("Content-Length", "2"), ("Content-Type", "application/json")],
            )
            for headers in framing_headers:
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.putrequest("POST", "/api/login", skip_host=True)
                conn.putheader("Host", f"127.0.0.1:{server.server_port}")
                for name, value in headers:
                    conn.putheader(name, value)
                conn.endheaders()
                response = conn.getresponse(); response.read()
                self.assertEqual(response.status, 400, headers)

            for length, expected in (("-1", 400), ("9000", 413)):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                conn.putrequest("POST", "/api/login", skip_host=True)
                conn.putheader("Host", f"127.0.0.1:{server.server_port}")
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", length)
                conn.endheaders()
                response = conn.getresponse(); response.read()
                self.assertEqual(response.status, expected)
        finally:
            server.shutdown(); server.server_close(); thread.join(5)

        first_db = self.home / "gympilot" / "gympilot.db"
        self.routine("Nur Profil A", 3)
        second_home = Path(self.tmp.name) / "other-profile"
        second_env = {**self.env, "HERMES_HOME": str(second_home)}
        result = subprocess.run([sys.executable, str(CLI), "--json", "init"], env=second_env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(first_db, second_home / "gympilot" / "gympilot.db")
        with sqlite3.connect(first_db) as first, sqlite3.connect(second_home / "gympilot" / "gympilot.db") as second:
            self.assertEqual(first.execute("SELECT COUNT(*) FROM routines").fetchone()[0], 1)
            self.assertEqual(second.execute("SELECT COUNT(*) FROM routines").fetchone()[0], 0)

        deadline_server = gym.make_server("127.0.0.1", 0)
        deadline_server.request_deadline = 0.2
        deadline_thread = threading.Thread(target=deadline_server.serve_forever, daemon=True)
        deadline_thread.start()
        try:
            raw = socket.create_connection(("127.0.0.1", deadline_server.server_port), timeout=2)
            raw.sendall(f"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{deadline_server.server_port}\r\n".encode())
            time.sleep(0.35)
            try: raw.sendall(b"\r\n")
            except OSError: pass
            raw.settimeout(1)
            try: response = raw.recv(4096)
            except (OSError, TimeoutError): response = b""
            raw.close()
            self.assertNotIn(b" 200 ", response)
        finally:
            deadline_server.shutdown(); deadline_server.server_close(); deadline_thread.join(5)

    def test_web_login_cookie_logout_and_no_store(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        with gym.connect() as con:
            con.execute("INSERT INTO auth_config VALUES(1,?,?)", (gym.hash_password("a strong password"), gym.now()))
            con.commit()
        server = gym.make_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("GET", "/api/today")
            unauthorized = conn.getresponse()
            unauthorized.read()
            self.assertEqual(unauthorized.status, 401)
            self.assertEqual(unauthorized.getheader("Cache-Control"), "no-store")
            for malformed in (
                '{"password":"a strong password","extra":NaN}',
                '{"password":"wrong","password":"a strong password"}',
                '{"password":"a strong password","extra":Infinity}',
                '{"password":1234567890}',
                '{"password":"a strong password","extra":{}}',
                '[' * 1100 + '0' + ']' * 1100,
            ):
                conn.request("POST", "/api/login", malformed, {"Content-Type": "application/json"})
                rejected = conn.getresponse(); rejected.read()
                self.assertEqual(rejected.status, 400)
            body = json.dumps({"password": "a strong password"})
            conn.request("POST", "/api/login", body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            response.read()
            cookie = response.getheader("Set-Cookie")
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Strict", cookie)
            conn.request("POST", "/api/logout", "{}", {"Cookie": cookie.split(";", 1)[0], "Content-Type": "application/json"})
            logout = conn.getresponse()
            logout.read()
            self.assertEqual(logout.getheader("Cache-Control"), "no-store")
            self.assertIn("Max-Age=0", logout.getheader("Set-Cookie") or "")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == "__main__":
    unittest.main()
