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

    def sample_plan(self, name="Ganzkörper", day=1, sets=3):
        return {"routines": [{"name": name, "weekdays": [day], "exercises": [
            {"name": "Kniebeuge", "sets": sets, "min_reps": 5, "max_reps": 8}
        ]}]}

    def confirm_draft(self, draft):
        return self.cli("draft", "confirm", "--revision", draft["revision"],
                        "--content-hash", draft["content_hash"])[1]

    def test_draft_has_monotone_revision_and_hash_of_canonical_plan_json(self):
        source = self.sample_plan()
        first = self.cli("draft", "import", json.dumps(source, indent=2))[1]
        canonical = json.dumps(source, ensure_ascii=False, allow_nan=False,
                               sort_keys=True, separators=(",", ":"))
        self.assertEqual(first["revision"], 1)
        self.assertEqual(first["content_hash"], __import__("hashlib").sha256(canonical.encode()).hexdigest())
        replacement = self.cli("draft", "import", json.dumps(self.sample_plan(day=2)),
                               "--replace-revision", first["revision"])[1]
        self.assertEqual(replacement["revision"], 2)
        self.assertNotEqual(replacement["content_hash"], first["content_hash"])

    def test_draft_confirm_requires_matching_revision_and_content_hash(self):
        draft = self.cli("draft", "import", json.dumps(self.sample_plan()))[1]
        missing, _ = self.cli("draft", "confirm", check=False)
        self.assertEqual(missing.returncode, 2)
        stale, payload = self.cli("draft", "confirm", "--revision", draft["revision"] + 1,
                                  "--content-hash", draft["content_hash"], check=False)
        self.assertEqual(stale.returncode, 2)
        self.assertIn("revision", payload["error"])
        wrong_hash, payload = self.cli("draft", "confirm", "--revision", draft["revision"],
                                       "--content-hash", "0" * 64, check=False)
        self.assertEqual(wrong_hash.returncode, 2)
        self.assertIn("hash", payload["error"])
        self.assertEqual(self.cli("draft", "show")[1]["status"], "draft")

    def test_draft_discard_requires_revision_and_preserves_plan_and_history(self):
        routine = self.routine("Alt", 1)
        exercise = self.exercise(routine["id"])
        session = self.cli("session", "start", "--routine", routine["id"], "--date", "2026-01-01")[1]
        logged = self.cli("set", "log", session["id"], exercise["id"], "--weight", 40, "--reps", 8)[1]
        self.cli("session", "finish", session["id"])
        draft = self.cli("draft", "import", json.dumps(self.sample_plan("Neu", 2)))[1]
        missing, _ = self.cli("draft", "discard", check=False)
        self.assertEqual(missing.returncode, 2)
        stale, payload = self.cli("draft", "discard", "--revision", draft["revision"] + 1, check=False)
        self.assertEqual(stale.returncode, 2)
        self.assertIn("revision", payload["error"])
        discarded = self.cli("draft", "discard", "--revision", draft["revision"])[1]
        self.assertEqual(discarded["status"], "discarded")
        self.assertEqual(self.cli("plan")[1][0]["name"], "Alt")
        with sqlite3.connect(self.home / "gympilot" / "gympilot.db") as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM sessions WHERE id=?", (session["id"],)).fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM workout_sets WHERE id=?", (logged["id"],)).fetchone()[0], 1)

    def test_confirm_returns_canonical_materialized_plan_exactly_matching_draft(self):
        source = {"routines": [
            {"name": "Zuerst", "weekdays": [4], "exercises": [
                {"name": "Rudern", "sets": 3, "min_reps": 8, "max_reps": 12}
            ]},
            {"name": "Danach", "weekdays": [1], "exercises": [
                {"name": "Kniebeuge", "sets": 3, "min_reps": 5, "max_reps": 8}
            ]},
        ]}
        draft = self.cli("draft", "import", json.dumps(source))[1]
        confirmed = self.confirm_draft(draft)
        self.assertEqual(confirmed["materialized_plan"], draft["plan"])
        self.assertEqual(confirmed["plan"], draft["plan"])
        _, saved = self.cli("plan")
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual([routine["name"] for routine in saved], ["Zuerst", "Danach"])

    def test_draft_payload_strict_json_bounds_depth_integers_fields_and_types(self):
        valid = self.sample_plan()
        malformed = [
            json.dumps({**valid, "unknown": True}),
            json.dumps({"routines": [{**valid["routines"][0], "unknown": 1}]}),
            json.dumps({"routines": [{**valid["routines"][0], "name": 7}]}),
            '{"routines":[{"name":"X","weekdays":[1],"exercises":[{"name":"Y","sets":' + "9" * 100 + ',"min_reps":1,"max_reps":2}]}]}',
            json.dumps({**valid, "generation": {"unknown": [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[1]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]}}),
        ]
        for raw in malformed:
            result, payload = self.cli("draft", "import", raw, check=False)
            self.assertEqual(result.returncode, 2, raw[:100])
            self.assertTrue(payload["error"])
        oversized, payload = self.cli("draft", "import", " " * 100001, check=False)
        self.assertEqual(oversized.returncode, 2)
        self.assertIn("too long", payload["error"])

    def test_structurally_invalid_weekdays_return_json_error_without_traceback(self):
        invalid = self.sample_plan()
        invalid["routines"][0]["weekdays"] = [[1]]
        result, payload = self.cli("draft", "import", json.dumps(invalid), check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("weekdays", payload["error"])

    def test_v1_to_v2_migration_preserves_sentinels_without_inventing_draft_or_equipment_and_newer_fails_closed(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        data = self.home / "gympilot"
        data.mkdir(parents=True)
        db = data / "gympilot.db"
        with sqlite3.connect(db) as con:
            con.executescript(gym.MIGRATIONS[1])
            con.execute("INSERT INTO schema_migrations VALUES(1,'sentinel-time')")
            con.execute("INSERT INTO user_profile(id,display_name,updated_at) VALUES(1,'Sentinel User','t')")
            routine = con.execute("INSERT INTO routines(name,created_at) VALUES('Sentinel Routine','t')").lastrowid
            exercise = con.execute("INSERT INTO exercises(name) VALUES('Sentinel Exercise')").lastrowid
            alias = con.execute("INSERT INTO equipment_aliases(exercise_id,alias,created_at) VALUES(?,?,?)", (exercise, "Sentinel Alias", "t")).lastrowid
            session = con.execute("INSERT INTO sessions(routine_id,session_date,started_at,completed_at) VALUES(?,?,?,?)", (routine, "2026-01-01", "t", "t")).lastrowid
            con.execute("INSERT INTO workout_sets(session_id,exercise_id,equipment_alias_id,set_number,weight_kg,reps,recorded_at) VALUES(?,?,?,?,?,?,?)", (session, exercise, alias, 1, 42.0, 7, "t"))
            con.execute("PRAGMA user_version=1")
        gym.initialize()
        with sqlite3.connect(db) as con:
            self.assertEqual(con.execute("SELECT display_name FROM user_profile").fetchone()[0], "Sentinel User")
            self.assertEqual(con.execute("SELECT alias FROM equipment_aliases").fetchone()[0], "Sentinel Alias")
            self.assertEqual(con.execute("SELECT weight_kg,reps FROM workout_sets").fetchone(), (42.0, 7))
            self.assertEqual(con.execute("SELECT equipment_json FROM studio_profile").fetchone()[0], "[]")
            self.assertEqual(con.execute("SELECT COUNT(*) FROM plan_drafts").fetchone()[0], 0)
        newer_home = Path(self.tmp.name) / "newer"
        (newer_home / "gympilot").mkdir(parents=True)
        with sqlite3.connect(newer_home / "gympilot" / "gympilot.db") as con:
            con.execute("PRAGMA user_version=99")
        newer_db = newer_home / "gympilot" / "gympilot.db"
        newer_db.parent.chmod(0o755)
        before_bytes = newer_db.read_bytes()
        before_mode = stat.S_IMODE(newer_db.stat().st_mode)
        before_directory_mode = stat.S_IMODE(newer_db.parent.stat().st_mode)
        before_files = sorted(path.name for path in newer_db.parent.iterdir())
        os.environ["HERMES_HOME"] = str(newer_home)
        with self.assertRaisesRegex(ValueError, "newer|version"):
            gym.initialize()
        self.assertEqual(newer_db.read_bytes(), before_bytes)
        self.assertEqual(stat.S_IMODE(newer_db.stat().st_mode), before_mode)
        self.assertEqual(stat.S_IMODE(newer_db.parent.stat().st_mode), before_directory_mode)
        self.assertEqual(sorted(path.name for path in newer_db.parent.iterdir()), before_files)

        wal_home = self.home.parent / "newer-wal"
        (wal_home / "gympilot").mkdir(parents=True)
        wal_db = wal_home / "gympilot" / "gympilot.db"
        with sqlite3.connect(wal_db) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("CREATE TABLE sentinel(value TEXT)")
            con.execute("INSERT INTO sentinel VALUES('keep')")
            con.execute("PRAGMA user_version=99")
            con.commit()
            wal_before = {path.name: path.read_bytes() for path in wal_db.parent.iterdir()}
            os.environ["HERMES_HOME"] = str(wal_home)
            with self.assertRaisesRegex(ValueError, "newer|version"):
                gym.initialize()
            self.assertEqual(
                {path.name: path.read_bytes() for path in wal_db.parent.iterdir()}, wal_before
            )

    def test_unknown_newer_replacement_after_inspection_is_never_mutated(self):
        gym = load_module()
        race_home = self.home.parent / "replacement-race"
        data = race_home / "gympilot"
        data.mkdir(parents=True, mode=0o755)
        database = data / "gympilot.db"
        replacement = data / "replacement.db"
        with sqlite3.connect(database) as con:
            con.execute("PRAGMA user_version=2")
        with sqlite3.connect(replacement) as con:
            con.execute("CREATE TABLE sentinel(value TEXT)")
            con.execute("INSERT INTO sentinel VALUES('replacement must stay unchanged')")
            con.execute("PRAGMA user_version=99")
        database.chmod(0o640)
        replacement.chmod(0o640)
        replacement_bytes = replacement.read_bytes()
        directory_mode = stat.S_IMODE(data.stat().st_mode)
        os.environ["HERMES_HOME"] = str(race_home)
        original_inspection = gym.existing_schema_version_read_only

        def inspect_then_replace():
            version = original_inspection()
            os.replace(replacement, database)
            return version

        setattr(gym, "existing_schema_version_read_only", inspect_then_replace)
        try:
            with self.assertRaisesRegex(ValueError, "changed|replaced|newer|version"):
                gym.initialize()
        finally:
            setattr(gym, "existing_schema_version_read_only", original_inspection)
        self.assertEqual(database.read_bytes(), replacement_bytes)
        self.assertEqual(stat.S_IMODE(database.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(data.stat().st_mode), directory_mode)
        self.assertEqual(sorted(path.name for path in data.iterdir()), ["gympilot.db"])

    def test_fresh_initialization_rejects_a_database_that_appears_during_creation(self):
        gym = load_module()
        race_home = self.home.parent / "fresh-creation-race"
        os.environ["HERMES_HOME"] = str(race_home)
        original_prepare = gym.prepare_private_file
        appeared = {}

        def create_before_exclusive_open(path):
            if path == gym.db_path() and not path.exists():
                with sqlite3.connect(path) as connection:
                    connection.execute("PRAGMA user_version=99")
                path.chmod(0o640)
                appeared["bytes"] = path.read_bytes()
                appeared["mode"] = stat.S_IMODE(path.stat().st_mode)
            return original_prepare(path)

        setattr(gym, "prepare_private_file", create_before_exclusive_open)
        try:
            with self.assertRaisesRegex(ValueError, "appeared.*retry"):
                gym.initialize()
        finally:
            setattr(gym, "prepare_private_file", original_prepare)
        database = race_home / "gympilot" / "gympilot.db"
        self.assertEqual(database.read_bytes(), appeared["bytes"])
        self.assertEqual(stat.S_IMODE(database.stat().st_mode), appeared["mode"])
        self.assertEqual(sorted(path.name for path in database.parent.iterdir()), ["gympilot.db"])


    def test_v1_to_v2_migration_recovers_from_interrupted_column_addition(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        data = self.home / "gympilot"
        data.mkdir(parents=True)
        db = data / "gympilot.db"
        with sqlite3.connect(db) as con:
            con.executescript(gym.MIGRATIONS[1])
            con.execute("INSERT INTO schema_migrations VALUES(1,'sentinel-time')")
            con.execute("INSERT INTO routines(name,created_at) VALUES('Vorhanden','t')")
            con.execute("ALTER TABLE routines ADD COLUMN plan_position INTEGER NOT NULL DEFAULT 0 CHECK(plan_position>=0)")
            con.execute("PRAGMA user_version=1")
        gym.initialize()
        gym.initialize()
        with sqlite3.connect(db) as con:
            columns = [row[1] for row in con.execute("PRAGMA table_info(routines)")]
            self.assertEqual(columns.count("plan_position"), 1)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT plan_position FROM routines WHERE name='Vorhanden'").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM plan_drafts").fetchone()[0], 0)

    def test_skill_links_every_direct_install_runtime_asset(self):
        skill = (ROOT / "skills" / "gym" / "SKILL.md").read_text(encoding="utf-8")
        expected = {
            "scripts/gympilot.py",
            "scripts/gympilot_generator.py",
            "assets/web/index.html",
            "assets/web/app.js",
            "assets/web/styles.css",
            "assets/web/manifest.webmanifest",
            "assets/web/service-worker.js",
            "assets/web/icons/icon-192.png",
            "assets/web/icons/icon-512.png",
            "assets/web/icons/apple-touch-icon.png",
            "assets/web/icons/favicon-32.png",
            "assets/web/icons/icon.svg",
        }
        for relative in expected:
            self.assertIn(f"]({relative})", skill, relative)
            self.assertTrue((ROOT / "skills" / "gym" / relative).is_file(), relative)

    def test_export_json_explicitly_includes_studio_profile_and_plan_drafts(self):
        self.cli("studio-profile", "update", "--equipment", "dumbbell")
        draft = self.cli("draft", "import", json.dumps(self.sample_plan()))[1]
        exported = self.cli("export")[1]
        payload = json.loads(Path(exported["json"]).read_text(encoding="utf-8"))
        self.assertEqual(json.loads(payload["studio_profile"][0]["equipment_json"]), ["dumbbell"])
        self.assertEqual(payload["plan_drafts"][0]["revision"], draft["revision"])
        self.assertEqual(payload["plan_drafts"][0]["content_hash"], draft["content_hash"])

    def test_show_is_read_only_and_import_does_not_silently_overwrite(self):
        draft = self.cli("draft", "import", json.dumps(self.sample_plan()))[1]
        db = self.home / "gympilot" / "gympilot.db"
        with sqlite3.connect(db) as con:
            before = list(con.iterdump())
        shown = self.cli("draft", "show")[1]
        with sqlite3.connect(db) as con:
            after = list(con.iterdump())
        self.assertEqual(shown, draft)
        self.assertEqual(after, before)
        rejected, payload = self.cli("draft", "import", json.dumps(self.sample_plan(day=2)), check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("replace-revision", payload["error"])
        stale, payload = self.cli("draft", "import", json.dumps(self.sample_plan(day=2)),
                                  "--replace-revision", draft["revision"] + 1, check=False)
        self.assertEqual(stale.returncode, 2)
        self.assertIn("revision", payload["error"])
        self.assertEqual(self.cli("draft", "show")[1], draft)

    def test_parallel_confirm_allows_exactly_one_winner(self):
        draft = self.cli("draft", "import", json.dumps(self.sample_plan()))[1]
        barrier = threading.Barrier(2)
        def confirm(_):
            barrier.wait()
            return subprocess.run([
                sys.executable, str(CLI), "--json", "draft", "confirm",
                "--revision", str(draft["revision"]), "--content-hash", draft["content_hash"],
            ], env=self.env, text=True, capture_output=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(confirm, range(2)))
        self.assertEqual(sorted(result.returncode for result in results), [0, 2])
        self.assertEqual(self.cli("draft", "show")[1]["status"], "confirmed")
        self.assertEqual(len(self.cli("plan")[1]), 1)

    def test_confirm_active_session_rolls_back_plan_and_draft_completely(self):
        old = self.routine("Alt", 1)
        exercise = self.exercise(old["id"])
        session = self.cli("session", "start", "--routine", old["id"])[1]
        self.cli("set", "log", session["id"], exercise["id"], "--weight", 40, "--reps", 8)
        draft = self.cli("draft", "import", json.dumps(self.sample_plan("Neu", 2)))[1]
        db = self.home / "gympilot" / "gympilot.db"
        with sqlite3.connect(db) as con:
            before = list(con.iterdump())
        blocked, payload = self.cli("draft", "confirm", "--revision", draft["revision"],
                                    "--content-hash", draft["content_hash"], check=False)
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("active session", payload["error"])
        with sqlite3.connect(db) as con:
            self.assertEqual(list(con.iterdump()), before)
        self.assertEqual(self.cli("draft", "show")[1]["status"], "draft")
        self.assertEqual(self.cli("plan")[1][0]["name"], "Alt")

    def test_structured_draft_update_uses_revision_cas_and_rehashes_content(self):
        draft = self.cli("draft", "import", json.dumps(self.sample_plan()))[1]
        missing, _ = self.cli("draft", "routine-update", 1, "--day", 2, check=False)
        self.assertEqual(missing.returncode, 2)
        changed = self.cli("draft", "routine-update", 1, "--day", 2,
                           "--revision", draft["revision"])[1]
        self.assertEqual(changed["revision"], draft["revision"] + 1)
        self.assertNotEqual(changed["content_hash"], draft["content_hash"])
        stale, payload = self.cli("draft", "exercise-update", 1, 1, "--sets", 4,
                                  "--revision", draft["revision"], check=False)
        self.assertEqual(stale.returncode, 2)
        self.assertIn("revision", payload["error"])

    def test_draft_indices_and_noop_updates_fail_closed(self):
        source = {"routines": [
            {"name": "A", "weekdays": [1], "exercises": [
                {"name": "A1", "sets": 3, "min_reps": 8, "max_reps": 12}
            ]},
            {"name": "B", "weekdays": [2], "exercises": [
                {"name": "B1", "sets": 3, "min_reps": 8, "max_reps": 12}
            ]},
        ]}
        draft = self.cli("draft", "import", json.dumps(source))[1]
        self.assertIsNotNone(draft)
        assert draft is not None
        for args in (
            ("draft", "routine-update", 0, "--name", "Falsch", "--revision", draft["revision"]),
            ("draft", "routine-update", -1, "--name", "Falsch", "--revision", draft["revision"]),
            ("draft", "exercise-update", 1, 0, "--name", "Falsch", "--revision", draft["revision"]),
            ("draft", "exercise-update", 1, -1, "--name", "Falsch", "--revision", draft["revision"]),
        ):
            result, payload = self.cli(*args, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIsNotNone(payload)
        self.assertEqual(self.cli("draft", "show")[1], draft)
        result, payload = self.cli(
            "draft", "routine-update", 1, "--revision", draft["revision"], check=False
        )
        self.assertEqual(result.returncode, 2)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("change", payload["error"])
        self.assertEqual(self.cli("draft", "show")[1], draft)

    def test_confirm_revalidates_stored_payload_hash_inside_transaction(self):
        draft = self.cli("draft", "import", json.dumps(self.sample_plan()))[1]
        tampered = self.sample_plan(day=2)
        with sqlite3.connect(self.home / "gympilot" / "gympilot.db") as con:
            con.execute("UPDATE plan_drafts SET payload_json=? WHERE id=1", (json.dumps(tampered),))
        rejected, payload = self.cli("draft", "confirm", "--revision", draft["revision"],
                                     "--content-hash", draft["content_hash"], check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("hash", payload["error"])
        self.assertEqual(self.cli("plan")[1], [])

    def test_fresh_profile_schema_constraints_and_status(self):
        _, created = self.cli("init")
        self.assertEqual(created["schema_version"], 2)
        db = self.home / "gympilot" / "gympilot.db"
        self.assertTrue(db.is_file())
        self.assertFalse((ROOT / "skills" / "gym" / "gympilot.db").exists())
        with sqlite3.connect(db) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"schema_migrations", "user_profile", "onboarding_state", "studio_profile", "plan_drafts", "routines", "routine_days", "exercises", "equipment_aliases", "routine_exercises", "sessions", "workout_sets", "auth_config", "web_sessions"} <= tables)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)
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

    def test_complete_manual_onboarding_status_is_read_only(self):
        self.cli("init")
        values = [
            ("display_name", "Alex"), ("locale", "de"), ("units", "metric"), ("goal", "Kraft"),
            ("routine_count", "1"), ("routine_1_name", "Ganzkörper"), ("routine_1_weekdays", "1"),
            ("routine_1_exercise_count", "1"), ("routine_1_exercise_1_name", "Kniebeuge"),
            ("routine_1_exercise_1_sets", "3"), ("routine_1_exercise_1_min_reps", "5"),
        ]
        for field, value in values:
            self.cli("onboarding", "set", field, value)
        db = self.home / "gympilot" / "gympilot.db"
        with sqlite3.connect(db) as con:
            con.execute(
                "INSERT INTO onboarding_state(field,value,confirmed_at) VALUES(?,?,?)",
                ("routine_1_exercise_1_max_reps", "8", "2026-01-01T00:00:00Z"),
            )
        _, status = self.cli("onboarding", "status")
        self.assertIsNotNone(status)
        assert status is not None
        self.assertTrue(status["complete"])
        self.assertNotIn("plan_materialized", status["answers"])
        self.assertEqual(self.cli("plan")[1], [])

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
        self.assertEqual(
            sorted(result.returncode for result in results),
            [0, 2],
            [(result.returncode, result.stdout, result.stderr) for result in results],
        )
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

    def test_confirming_a_new_draft_can_reuse_existing_routine_names(self):
        plan = {"routines": [{"name": "Ganzkörper", "weekdays": [1], "exercises": [
            {"name": "Kniebeuge", "sets": 3, "min_reps": 5, "max_reps": 8}
        ]}]}
        first = self.cli("draft", "import", json.dumps(plan))[1]
        self.confirm_draft(first)
        plan["routines"][0]["weekdays"] = [2]
        plan["routines"][0]["exercises"][0]["sets"] = 4
        second = self.cli("draft", "import", json.dumps(plan), "--replace-revision", first["revision"])[1]
        self.confirm_draft(second)
        current = self.cli("plan")[1]
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["weekdays"], [2])
        self.assertEqual(current[0]["exercises"][0]["planned_sets"], 4)

    def test_onboarding_exposes_and_persists_three_setup_modes(self):
        status = self.cli("onboarding", "status")[1]
        self.assertEqual(status["setup_modes"], ["import", "generate", "manual"])
        selected = self.cli("onboarding", "mode", "generate")[1]
        self.assertEqual(selected["selected_mode"], "generate")
        self.assertEqual(self.cli("onboarding", "status")[1]["selected_mode"], "generate")

    def test_structured_draft_updates_preserve_history_on_atomic_replacement(self):
        old = self.routine("Alt", 1)
        exercise = self.exercise(old["id"], "Press")
        session = self.cli("session", "start", "--routine", old["id"], "--date", "2026-01-01")[1]
        logged = self.cli("set", "log", session["id"], exercise["id"], "--weight", 40, "--reps", 8)[1]
        self.cli("session", "finish", session["id"])
        source = {"routines": [{"name": "Neu", "weekdays": [2], "exercises": [
            {"name": "Kniebeuge", "sets": 3, "min_reps": 5, "max_reps": 8}
        ]}]}
        draft = self.cli("draft", "import", json.dumps(source))[1]
        changed = self.cli("draft", "routine-update", 1, "--name", "Neu 2", "--day", 3, "--revision", draft["revision"])[1]
        self.assertEqual(changed["plan"]["routines"][0]["name"], "Neu 2")
        changed = self.cli("draft", "exercise-update", 1, 1, "--sets", 4, "--min-reps", 6, "--max-reps", 10, "--revision", changed["revision"])[1]
        self.assertEqual(changed["plan"]["routines"][0]["exercises"][0]["sets"], 4)
        self.confirm_draft(changed)
        with sqlite3.connect(self.home / "gympilot" / "gympilot.db") as con:
            self.assertEqual(con.execute("SELECT routine_id,session_date FROM sessions WHERE id=?", (session["id"],)).fetchone(), (old["id"], "2026-01-01"))
            self.assertEqual(con.execute("SELECT session_id,weight_kg,reps FROM workout_sets WHERE id=?", (logged["id"],)).fetchone(), (session["id"], 40.0, 8))

    def test_generator_is_deterministic_local_and_uses_all_preferences(self):
        self.cli("studio-profile", "update", "--equipment", "barbell", "--equipment", "bench", "--equipment", "dumbbell")
        args = ("draft", "generate", "--goal", "muscle_gain", "--day", 1, "--day", 4,
                "--duration", 45, "--experience", "intermediate", "--focus", "chest",
                "--avoid", "Push-up", "--restriction", "no_overhead")
        first = self.cli(*args)[1]
        second = self.cli(*args, "--replace-revision", first["revision"])[1]
        self.assertEqual(first["plan"], second["plan"])
        metadata = first["plan"]["generation"]
        self.assertEqual(metadata["goal"], "muscle_gain")
        self.assertEqual(metadata["days"], [1, 4])
        self.assertEqual(metadata["duration_minutes"], 45)
        self.assertEqual(metadata["experience"], "intermediate")
        self.assertEqual(metadata["preferred_body_areas"], ["chest"])
        self.assertEqual(metadata["avoided_exercises"], ["push_up"])
        self.assertEqual(metadata["restrictions"], ["no_overhead"])
        self.assertEqual(metadata["equipment"], ["barbell", "bench", "dumbbell"])
        names = [exercise["name"] for routine in first["plan"]["routines"] for exercise in routine["exercises"]]
        self.assertIn("Langhantel-Bankdrücken", names)
        self.assertNotIn("Push-up", names)
        self.assertEqual(len(first["plan"]["routines"]), 2)

    def test_generator_supports_all_goals_and_rejects_duplicate_days(self):
        revision = None
        for goal in ("muscle_gain", "strength", "general_fitness", "weight_loss"):
            args = ["draft", "generate", "--goal", goal, "--day", 2, "--duration", 30,
                    "--experience", "beginner"]
            if revision is not None: args += ["--replace-revision", revision]
            result = self.cli(*args)[1]
            revision = result["revision"]
            self.assertEqual(result["plan"]["generation"]["goal"], goal)
        rejected, payload = self.cli("draft", "generate", "--goal", "strength", "--day", 2, "--day", 2,
                                     "--duration", 30, "--experience", "beginner", check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("unique", payload["error"])
        rejected, payload = self.cli("draft", "generate", "--goal", "strength", "--day", 2,
                                     "--duration", 30, "--experience", "beginner", "--restriction", "unknown", check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("invalid choice", payload["error"])

    def test_generator_metadata_is_reserved_and_removed_after_structured_edit(self):
        draft = self.cli(
            "draft", "generate", "--goal", "general_fitness", "--day", 1,
            "--duration", 60, "--experience", "beginner",
        )[1]
        self.assertIsNotNone(draft)
        assert draft is not None
        rejected, payload = self.cli(
            "draft", "import", json.dumps(draft["plan"]),
            "--replace-revision", draft["revision"], check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("generation", payload["error"])
        first_sets = draft["plan"]["routines"][0]["exercises"][0]["sets"]
        changed = self.cli(
            "draft", "exercise-update", 1, 1, "--sets", min(first_sets + 1, 8),
            "--revision", draft["revision"],
        )[1]
        self.assertIsNotNone(changed)
        assert changed is not None
        self.assertNotIn("generation", changed["plan"])

    def test_confirm_rejects_semantically_forged_generator_metadata(self):
        draft = self.cli(
            "draft", "generate", "--goal", "general_fitness", "--day", 1,
            "--duration", 60, "--experience", "beginner",
        )[1]
        self.assertIsNotNone(draft)
        assert draft is not None
        forged = json.loads(json.dumps(draft["plan"]))
        forged["generation"]["equipment"] = ["dumbbell"]
        canonical = json.dumps(forged, ensure_ascii=False, allow_nan=False,
                               sort_keys=True, separators=(",", ":"))
        forged_hash = __import__("hashlib").sha256(canonical.encode()).hexdigest()
        with sqlite3.connect(self.home / "gympilot" / "gympilot.db") as con:
            con.execute("UPDATE plan_drafts SET payload_json=?,content_hash=? WHERE id=1",
                        (canonical, forged_hash))
        rejected, payload = self.cli(
            "draft", "confirm", "--revision", draft["revision"],
            "--content-hash", forged_hash, check=False,
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("provenance", payload["error"])
        shown = self.cli("draft", "show")[1]
        self.assertIsNotNone(shown)
        assert shown is not None
        self.assertEqual(shown["status"], "draft")
        self.assertEqual(self.cli("plan")[1], [])

    def test_cli_generator_uses_curated_splits_and_controlled_studio_vocabulary(self):
        equipment = ("barbell", "bench", "cable", "dumbbell", "machines", "rack")
        self.cli("studio-profile", "update", *(part for item in equipment for part in ("--equipment", item)))
        _, draft = self.cli(
            "draft", "generate", "--goal", "strength",
            "--day", 1, "--day", 2, "--day", 4, "--day", 5,
            "--duration", 90, "--experience", "advanced", "--focus", "chest",
        )
        self.assertIsNotNone(draft)
        assert draft is not None
        self.assertEqual(
            [routine["name"] for routine in draft["plan"]["routines"]],
            ["Oberkörper A", "Unterkörper A", "Oberkörper B", "Unterkörper B"],
        )
        metadata = draft["plan"]["generation"]
        self.assertEqual(metadata["generator_version"], "curated-local-v2")
        self.assertLessEqual(metadata["estimated_duration_minutes"], 90)
        rejected, payload = self.cli(
            "studio-profile", "update", "--equipment", "dumbells", check=False
        )
        self.assertEqual(rejected.returncode, 2)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIn("unsupported equipment", payload["error"])

    def test_imported_draft_resumes_previews_and_materializes_only_on_confirm(self):
        plan = {"routines": [{"name": "Ganzkörper", "weekdays": [1, 4], "exercises": [
            {"name": "Kniebeuge", "sets": 3, "min_reps": 5, "max_reps": 8}
        ]}]}
        draft = self.cli("draft", "import", json.dumps(plan))[1]
        self.assertEqual(draft["mode"], "import")
        self.assertEqual(self.cli("plan")[1], [])
        resumed = self.cli("draft", "show")[1]
        self.assertEqual(resumed["plan"], plan)
        confirmed = self.confirm_draft(draft)
        self.assertTrue(confirmed["materialized"])
        self.assertEqual(self.cli("plan")[1][0]["exercises"][0]["name"], "Kniebeuge")
        again, payload = self.cli("draft", "confirm", "--revision", confirmed["revision"],
                                  "--content-hash", confirmed["content_hash"], check=False)
        self.assertEqual(again.returncode, 2)
        self.assertIn("already confirmed", payload["error"])

    def test_imported_draft_rejects_nonstandard_or_invalid_plan_json(self):
        for raw in (
            '{"routines":NaN}',
            '{"routines":[],"routines":[]}',
            json.dumps({"routines": [{"name": "X", "weekdays": [1, 1], "exercises": []}]}),
            json.dumps({"routines": [{"name": "X", "weekdays": [1], "exercises": [{"name": "Y", "sets": 3, "min_reps": 9, "max_reps": 8}]}]}),
        ):
            result, payload = self.cli("draft", "import", raw, check=False)
            self.assertEqual(result.returncode, 2, raw)
            self.assertTrue(payload["error"])

    def test_bulk_text_inputs_are_bounded(self):
        rejected, payload = self.cli("studio-profile", "update", "--equipment", "x" * 1001, check=False)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("too long", payload["error"])

    def test_equipment_profile_is_persistent_and_editable_via_cli(self):
        created = self.cli("studio-profile", "update", "--equipment", "barbell", "--equipment", "bench")[1]
        self.assertEqual(created["equipment"], ["barbell", "bench"])
        updated = self.cli("studio-profile", "update", "--equipment", "dumbbell")[1]
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated["equipment"], ["dumbbell"])
        self.assertEqual(self.cli("studio-profile", "show")[1], updated)
        cleared = self.cli("studio-profile", "update")[1]
        self.assertIsNotNone(cleared)
        assert cleared is not None
        self.assertEqual(cleared["equipment"], [])
        self.assertEqual(self.cli("studio-profile", "show")[1]["equipment"], [])
        with sqlite3.connect(self.home / "gympilot" / "gympilot.db") as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM plan_drafts").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
