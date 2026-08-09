from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib.util
import csv
import json
import os
import plistlib
from datetime import date
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
from types import SimpleNamespace
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

    def historical_generated_draft(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        document = gym.generate_curated_plan(
            goal="general_fitness", days=[1], duration_minutes=60,
            experience="beginner", equipment=[], focus=[], avoid=[], restrictions=[],
        )
        payload = gym.canonical_plan_json(document)
        content_hash = __import__("hashlib").sha256(payload.encode()).hexdigest()
        stamp = gym.now()
        with gym.connect() as con:
            con.execute("""INSERT INTO plan_drafts
                (id,mode,payload_json,revision,content_hash,status,created_at,updated_at,confirmed_at)
                VALUES(1,'generate',?,1,?,'draft',?,?,NULL)""",
                (payload, content_hash, stamp, stamp))
            con.commit()
        return self.cli("draft", "show")[1]

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

    def test_dashboard_service_definitions_are_profile_scoped_and_gateway_independent(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)

        mac = gym.dashboard_service_definition(
            system_name="Darwin",
            user_home=Path(self.tmp.name) / "user",
            executable=Path("/usr/bin/python3"),
        )
        plist = plistlib.loads(mac["content"])
        self.assertTrue(plist["Label"].startswith("de.login.gympilot.dashboard."))
        self.assertEqual(plist["ProgramArguments"][:2], [str(Path("/usr/bin/python3").resolve()), str(CLI)])
        self.assertEqual(plist["ProgramArguments"][-4:], ["--host", "127.0.0.1", "--port", "8765"])
        self.assertEqual(plist["EnvironmentVariables"]["HERMES_HOME"], str(self.home.resolve()))
        self.assertTrue(plist["RunAtLoad"])
        self.assertNotIn("KeepAlive", plist)
        self.assertIn("Library/LaunchAgents", str(mac["path"]))

        linux = gym.dashboard_service_definition(
            system_name="Linux",
            user_home=Path(self.tmp.name) / "user",
            executable=Path("/usr/bin/python3"),
        )
        self.assertIn("Restart=no", linux["content"])
        self.assertIn("WantedBy=default.target", linux["content"])
        self.assertIn(f'Environment="HERMES_HOME={self.home.resolve()}"', linux["content"])
        self.assertIn(".config/systemd/user/gympilot-dashboard-", str(linux["path"]))

        override = Path(self.tmp.name) / "data-%t"
        os.environ["GYMPILOT_DATA_DIR"] = str(override)
        overridden = gym.dashboard_service_definition(
            system_name="Linux",
            user_home=Path(self.tmp.name) / "user",
            executable=Path("/usr/bin/python3"),
        )
        self.assertNotEqual(linux["unit"], overridden["unit"])
        self.assertIn("GYMPILOT_DATA_DIR=", overridden["content"])
        self.assertIn("data-%%t", overridden["content"])
        os.environ.pop("GYMPILOT_DATA_DIR")

        os.environ["HERMES_HOME"] = str(Path(self.tmp.name) / "other-profile")
        other = gym.dashboard_service_definition(
            system_name="Darwin",
            user_home=Path(self.tmp.name) / "user",
            executable=Path("/usr/bin/python3"),
        )
        self.assertNotEqual(mac["label"], other["label"])
        self.assertNotEqual(mac["path"], other["path"])

    def test_dashboard_service_definition_accepts_only_explicit_private_lan_host(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        definition = gym.dashboard_service_definition(
            system_name="Darwin",
            user_home=Path(self.tmp.name) / "user",
            executable=Path("/usr/bin/python3"),
            host="192.168.1.90",
        )
        plist = plistlib.loads(definition["content"])
        self.assertEqual(plist["ProgramArguments"][-4:], ["--host", "192.168.1.90", "--port", "8765"])
        self.assertEqual(definition["host"], "192.168.1.90")
        self.assertEqual(definition["url"], "http://192.168.1.90:8765")
        for unsafe in ("0.0.0.0", "::", "192.0.0.8", "192.0.2.1", "198.18.0.1", "255.255.255.255", "::ffff:255.255.255.255", "fe80::1%en 0", "fe80::1%en0?x", "fe80::1%en0#x", "fe80::1%-bad", "fe80::1%en0%evil", "8.8.8.8", "example.com"):
            with self.subTest(host=unsafe), self.assertRaisesRegex(ValueError, "concrete local, LAN, or VPN"):
                gym.dashboard_service_definition(system_name="Darwin", host=unsafe)

    def test_systemd_service_round_trips_scoped_ipv6_host(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        definition = gym.dashboard_service_definition(
            "Linux", Path(self.tmp.name) / "scoped-user", Path("/usr/bin/python3"), host="fe80::1%en0"
        )
        gym._write_service_definition(definition["path"], definition["content"])
        self.assertEqual(gym._installed_service_endpoint(definition), ("fe80::1%en0", 8765))

    def test_dashboard_service_remembers_installed_lan_host_for_status_and_restart(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name) / "lan-user"
        state = {"loaded": False}
        def runner(command, **_kwargs):
            operation = command[1] if command and command[0] == "launchctl" and len(command) > 1 else ""
            if operation == "bootout": state["loaded"] = False
            if operation in {"bootstrap", "kickstart"}: state["loaded"] = True
            if operation == "print":
                return SimpleNamespace(
                    returncode=0 if state["loaded"] else 3,
                    stdout="state = running\n" if state["loaded"] else "",
                    stderr="" if state["loaded"] else "Could not find service",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        kwargs = {
            "system_name": "Darwin", "user_home": user_home,
            "executable": Path("/usr/bin/python3"), "runner": runner,
            "health_checker": lambda: True,
        }
        installed = gym.manage_dashboard_service("install", host="192.168.1.90", **kwargs)
        self.assertEqual(installed["url"], "http://192.168.1.90:8765")
        status = gym.manage_dashboard_service("status", **kwargs)
        self.assertEqual(status["url"], "http://192.168.1.90:8765")
        restarted = gym.manage_dashboard_service("restart", **kwargs)
        self.assertEqual(restarted["url"], "http://192.168.1.90:8765")
        plist = plistlib.loads(Path(restarted["path"]).read_bytes())
        self.assertEqual(plist["ProgramArguments"][-4:], ["--host", "192.168.1.90", "--port", "8765"])

    def test_installed_service_endpoint_rejects_duplicate_host_arguments(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        definition = gym.dashboard_service_definition(
            "Linux", Path(self.tmp.name) / "endpoint-user", Path("/usr/bin/python3"), host="192.168.1.90"
        )
        tampered = definition["content"].replace(
            '"--host" "192.168.1.90"',
            '"--host" "10.0.0.2" "--host" "192.168.1.90"',
        )
        gym._write_service_definition(definition["path"], tampered)
        with self.assertRaisesRegex(ValueError, "endpoint"):
            gym._installed_service_endpoint(definition)

    def test_installed_service_endpoint_rejects_equals_style_option_injection(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        for system_name in ("Darwin", "Linux"):
            with self.subTest(system_name=system_name):
                definition = gym.dashboard_service_definition(
                    system_name, Path(self.tmp.name) / f"equals-{system_name}", Path("/usr/bin/python3"), host="192.168.1.90"
                )
                if system_name == "Darwin":
                    payload = plistlib.loads(definition["content"])
                    payload["ProgramArguments"].append("--host=10.0.0.2")
                    tampered = plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)
                else:
                    tampered = definition["content"].replace('"server"', '"--host=10.0.0.2" "server"')
                gym._write_service_definition(definition["path"], tampered)
                with self.assertRaisesRegex(ValueError, "endpoint|configuration|arguments"):
                    gym._installed_service_endpoint(definition)

    def test_rejected_service_host_does_not_initialize_profile(self):
        result, payload = self.cli("service", "install", "--host", "0.0.0.0", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIsInstance(payload, dict)
        self.assertIn("wildcard/public", payload["error"])
        self.assertFalse(self.home.exists())

    def test_service_install_cli_passes_explicit_private_host(self):
        gym = load_module()
        captured = []
        setattr(gym, "ensure", lambda: None)
        setattr(gym, "manage_dashboard_service", lambda action, host=None: captured.append((action, host)) or {"ok": True})
        args = gym.parser().parse_args(["service", "install", "--host", "192.168.1.90"])
        self.assertEqual(gym.command(args), {"ok": True})
        self.assertEqual(captured, [("install", "192.168.1.90")])
        status = gym.parser().parse_args(["service", "status"])
        gym.command(status)
        self.assertEqual(captured[-1], ("status", None))

    def test_dashboard_health_uses_the_configured_private_service_host(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        seen = []
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _size=-1):
                return json.dumps({
                    "status": "ok", "schema_version": gym.SCHEMA_VERSION,
                    "instance_id": gym.dashboard_instance_id(), "code_id": gym.SERVICE_CODE_ID,
                }).encode()
        class Opener:
            def open(self, request, **_kwargs):
                seen.append(request.full_url)
                return Response()
        self.assertTrue(gym.dashboard_health(host="192.168.1.90", opener=Opener()))
        self.assertEqual(seen, ["http://192.168.1.90:8765/api/health"])

    def test_dashboard_health_accepts_the_real_health_contract(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        gym.initialize()
        server = gym.make_server("127.0.0.1", 0)
        gym.SERVICE_PORT = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertTrue(gym.dashboard_health())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def test_service_rejects_control_characters_and_health_is_bounded(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        os.environ["GYMPILOT_DATA_DIR"] = str(Path(self.tmp.name) / "bad\npath")
        with self.assertRaisesRegex(ValueError, "control"):
            gym.dashboard_service_definition(system_name="Linux")
        os.environ.pop("GYMPILOT_DATA_DIR")

        class Response:
            status = 200
            headers = {"Content-Type": "application/json; charset=utf-8"}
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, size=-1): return b"x" * 4097
        class Opener:
            def open(self, *_args, **_kwargs): return Response()
        self.assertFalse(gym.dashboard_health(opener=Opener()))

        class WrongInstanceResponse(Response):
            def read(self, size=-1):
                return json.dumps({"status": "ok", "schema_version": gym.SCHEMA_VERSION,
                                   "instance_id": "different"}).encode()
        class WrongInstanceOpener:
            def open(self, *_args, **_kwargs): return WrongInstanceResponse()
        self.assertFalse(gym.dashboard_health(opener=WrongInstanceOpener()))

        class StaleCodeResponse(Response):
            def read(self, size=-1):
                return json.dumps({"status": "ok", "schema_version": gym.SCHEMA_VERSION,
                                   "instance_id": gym.dashboard_instance_id(),
                                   "code_id": "obsolete"}).encode()
        class StaleCodeOpener:
            def open(self, *_args, **_kwargs): return StaleCodeResponse()
        self.assertFalse(gym.dashboard_health(opener=StaleCodeOpener()))

    def test_service_parent_symlinks_are_rejected_without_mutation(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name) / "user"
        redirected = Path(self.tmp.name) / "redirected"
        redirected.mkdir()
        user_home.mkdir()
        (user_home / ".config").symlink_to(redirected, target_is_directory=True)
        victim = redirected / "systemd" / "user" / gym.dashboard_service_definition(
            "Linux", user_home, Path("/usr/bin/python3"))["unit"]
        victim.parent.mkdir(parents=True)
        victim.write_text("do not delete")
        with self.assertRaisesRegex(ValueError, "symlink"):
            gym.manage_dashboard_service(
                "uninstall", system_name="Linux", user_home=user_home,
                executable=Path("/usr/bin/python3"),
                runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("manager must not run")),
            )
        self.assertEqual(victim.read_text(), "do not delete")

    def test_service_definition_write_and_unlink_hold_parent_across_ancestor_swap(self):
        gym = load_module()
        root = Path(self.tmp.name).resolve() / "race-user"
        parent = root / ".config" / "systemd" / "user"
        parent.mkdir(parents=True)
        redirected = Path(self.tmp.name) / "redirected-race" / "user"
        redirected.mkdir(parents=True)
        target = parent / "gympilot.service"
        real_descriptor = gym.directory_descriptor
        state = {"swapped": False}

        def swapping_descriptor(path, **kwargs):
            descriptor = real_descriptor(path, **kwargs)
            if Path(path) == parent and not state["swapped"]:
                state["swapped"] = True
                original = root / ".config" / "systemd.original"
                (root / ".config" / "systemd").rename(original)
                (root / ".config" / "systemd").symlink_to(redirected.parent, target_is_directory=True)
            return descriptor

        gym.directory_descriptor = swapping_descriptor
        gym._write_service_definition(target, "safe")
        original_target = root / ".config" / "systemd.original" / "user" / target.name
        self.assertEqual(original_target.read_text(), "safe")
        self.assertFalse((redirected / target.name).exists())

        state["swapped"] = False
        (root / ".config" / "systemd").unlink()
        (root / ".config" / "systemd.original").rename(root / ".config" / "systemd")
        (redirected / target.name).write_text("victim")
        gym._unlink_service_definition(target)
        self.assertFalse((root / ".config" / "systemd.original" / "user" / target.name).exists())
        self.assertEqual((redirected / target.name).read_text(), "victim")

    def test_symlinked_user_home_is_rejected_before_service_definition_resolution(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        redirected = Path(self.tmp.name).resolve() / "redirected-home"
        redirected.mkdir()
        linked_home = Path(self.tmp.name).resolve() / "linked-home"
        linked_home.symlink_to(redirected, target_is_directory=True)
        manager_called = []
        def runner(command, **_kwargs):
            manager_called.append(command)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        for action in ("install", "uninstall"):
            with self.assertRaisesRegex(ValueError, "symlink"):
                gym.manage_dashboard_service(
                    action, system_name="Linux", user_home=linked_home,
                    executable=Path("/usr/bin/python3"), runner=runner,
                )
        self.assertEqual(manager_called, [])
        self.assertFalse((redirected / ".config" / "systemd" / "user").exists())

    def test_dashboard_service_install_restart_status_and_uninstall_use_user_manager(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name) / "user"
        os.environ["GYMPILOT_LIFECYCLE_SECRET"] = "must-not-reach-systemctl"
        self.addCleanup(os.environ.pop, "GYMPILOT_LIFECYCLE_SECRET", None)
        calls = []
        state = {"active": False}

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if operation in {"restart", "start"}: state["active"] = True
            if operation in {"disable", "stop"}: state["active"] = False
            if operation == "is-active":
                return SimpleNamespace(returncode=0 if state["active"] else 3, stdout="active\n" if state["active"] else "inactive\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        service_kwargs = {
            "system_name": "Linux", "user_home": user_home,
            "executable": Path("/usr/bin/python3"), "runner": runner,
            "health_checker": lambda: True,
        }
        installed = gym.manage_dashboard_service("install", **service_kwargs)
        service_path = Path(installed["path"])
        self.assertTrue(service_path.is_file())
        self.assertEqual(stat.S_IMODE(service_path.stat().st_mode), 0o600)
        self.assertTrue(installed["healthy"])
        self.assertIn(["systemctl", "--user", "daemon-reload"], [call[0] for call in calls])
        self.assertTrue(any(call[0][:3] == ["systemctl", "--user", "enable"] for call in calls))

        restarted = gym.manage_dashboard_service("restart", **service_kwargs)
        self.assertTrue(restarted["installed"])
        self.assertTrue(restarted["healthy"])
        self.assertTrue(any(call[0][:3] == ["systemctl", "--user", "restart"] for call in calls))

        status = gym.manage_dashboard_service("status", **service_kwargs)
        self.assertTrue(status["installed"])
        self.assertTrue(status["running"])

        removed = gym.manage_dashboard_service("uninstall", **service_kwargs)
        self.assertFalse(service_path.exists())
        self.assertFalse(removed["installed"])
        self.assertTrue(any(call[0][:3] == ["systemctl", "--user", "disable"] for call in calls))
        allowed={"PATH","HOME","USER","LOGNAME","LANG","LC_ALL","LC_CTYPE","XDG_RUNTIME_DIR","DBUS_SESSION_BUS_ADDRESS"}
        systemd_environments=[kwargs["env"] for command,kwargs in calls if command[:2]==["systemctl","--user"]]
        self.assertTrue(systemd_environments)
        for environment in systemd_environments:
            self.assertLessEqual(set(environment),allowed)
            self.assertNotIn("GYMPILOT_LIFECYCLE_SECRET",environment)

    def test_headless_linux_install_explains_linger_before_writing_unit(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name).resolve() / "headless-user"
        definition = gym.dashboard_service_definition("Linux", user_home, Path("/usr/bin/python3"))
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=1, stdout="offline\n", stderr="Failed to connect to bus")
        with self.assertRaisesRegex(OSError, "loginctl enable-linger") as raised:
            gym.manage_dashboard_service(
                "install", system_name="Linux", user_home=user_home,
                executable=Path("/usr/bin/python3"), runner=runner,
            )
        message = str(raised.exception)
        uid = os.getuid()
        self.assertIn(f"user@{uid}.service", message)
        self.assertIn(f"XDG_RUNTIME_DIR=/run/user/{uid}", message)
        self.assertIn(f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus", message)
        self.assertIn("explicit approval", message)
        self.assertFalse(os.path.lexists(definition["path"]))
        self.assertFalse(any(command[2] in {"daemon-reload", "enable", "restart"} for command, _ in calls))

    def test_linux_service_supplies_user_bus_environment_automatically(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        os.environ["GYMPILOT_TEST_SECRET"] = "must-not-reach-systemctl"
        self.addCleanup(os.environ.pop, "GYMPILOT_TEST_SECRET", None)
        user_home = Path(self.tmp.name).resolve() / "bus-user"
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if operation == "is-system-running":
                return SimpleNamespace(returncode=1, stdout="degraded\n", stderr="")
            if operation == "is-active":
                return SimpleNamespace(returncode=3, stdout="inactive\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        result = gym.manage_dashboard_service(
            "status", system_name="Linux", user_home=user_home,
            executable=Path("/usr/bin/python3"), runner=runner,
        )
        self.assertFalse(result["running"])
        uid = os.getuid()
        systemd_calls = [(command, kwargs) for command, kwargs in calls if command[:2] == ["systemctl", "--user"]]
        self.assertTrue(systemd_calls)
        for _command, kwargs in systemd_calls:
            self.assertEqual(kwargs["env"]["XDG_RUNTIME_DIR"], f"/run/user/{uid}")
            self.assertEqual(kwargs["env"]["DBUS_SESSION_BUS_ADDRESS"], f"unix:path=/run/user/{uid}/bus")
            self.assertNotIn("GYMPILOT_TEST_SECRET", kwargs["env"])

    def test_service_manager_failures_are_fail_closed_and_linux_reinstall_restarts(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name) / "user"
        calls = []
        fail_disable = False
        state = {"active": False}

        def runner(command, **_kwargs):
            calls.append(command)
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if fail_disable and operation == "disable":
                return SimpleNamespace(returncode=1, stdout="", stderr="cannot stop")
            if operation in {"restart", "start"}: state["active"] = True
            if operation in {"disable", "stop"}: state["active"] = False
            if operation == "is-active":
                return SimpleNamespace(returncode=0 if state["active"] else 3, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        kwargs = {"system_name": "Linux", "user_home": user_home,
                  "executable": Path("/usr/bin/python3"), "runner": runner,
                  "health_checker": lambda: True}
        installed = gym.manage_dashboard_service("install", **kwargs)
        self.assertTrue(any(call[:3] == ["systemctl", "--user", "restart"] for call in calls))
        calls.clear()
        gym.manage_dashboard_service("install", **kwargs)
        self.assertTrue(any(call[:3] == ["systemctl", "--user", "restart"] for call in calls))

        fail_disable = True
        with self.assertRaisesRegex(OSError, "cannot stop"):
            gym.manage_dashboard_service("uninstall", **kwargs)
        self.assertTrue(Path(installed["path"]).is_file())

        fail_disable = False
        gym.manage_dashboard_service("uninstall", **kwargs)

        service_path = Path(installed["path"])
        service_path.symlink_to(service_path.parent / "missing-unit")
        gym.manage_dashboard_service("uninstall", **kwargs)
        self.assertFalse(os.path.lexists(service_path))

    def test_launchd_loaded_but_waiting_is_not_reported_as_running(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        def runner(command, **_kwargs):
            if command[:2] == ["launchctl", "print"]:
                return SimpleNamespace(returncode=0, stdout="state = waiting\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        result = gym.manage_dashboard_service(
            "status", system_name="Darwin", user_home=Path(self.tmp.name) / "user",
            executable=Path("/usr/bin/python3"), runner=runner,
            health_checker=lambda: (_ for _ in ()).throw(AssertionError("health must not run")),
        )
        self.assertFalse(result["running"])
        self.assertFalse(result["healthy"])

    def test_launchd_restart_reloads_definition_without_kickstart_kill(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name) / "user"
        definition = gym.dashboard_service_definition("Darwin", user_home, Path("/usr/bin/python3"))
        gym._write_service_definition(definition["path"], definition["content"])
        state = {"loaded": True, "pending_bootout_checks": 0, "waiting_checks": 0}
        calls = []
        def runner(command, **_kwargs):
            calls.append(command)
            operation = command[1] if command and command[0] == "launchctl" and len(command) > 1 else ""
            if operation == "bootout": state["pending_bootout_checks"] = 2
            if operation == "bootstrap":
                if state["loaded"]:
                    return SimpleNamespace(returncode=5, stdout="", stderr="Bootstrap failed: 5: Input/output error")
                state["loaded"] = True
                state["waiting_checks"] = 1
            if operation == "print":
                if state["pending_bootout_checks"]:
                    state["pending_bootout_checks"] -= 1
                    if not state["pending_bootout_checks"]: state["loaded"] = False
                if state["loaded"] and state["waiting_checks"]:
                    state["waiting_checks"] -= 1
                    return SimpleNamespace(returncode=0, stdout="state = waiting\n", stderr="")
                return SimpleNamespace(returncode=0 if state["loaded"] else 3,
                                       stdout="state = running\n" if state["loaded"] else "",
                                       stderr="" if state["loaded"] else "Could not find service")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        result = gym.manage_dashboard_service(
            "restart", system_name="Darwin", user_home=user_home,
            executable=Path("/usr/bin/python3"), runner=runner,
            health_checker=lambda: True,
        )
        self.assertTrue(result["running"])
        self.assertTrue(any(call[:2] == ["launchctl", "bootout"] for call in calls))
        self.assertTrue(any(call[:2] == ["launchctl", "bootstrap"] for call in calls))
        self.assertFalse(any(call[:3] == ["launchctl", "kickstart", "-k"] for call in calls))

    def test_unhealthy_install_stops_service_and_reports_failure(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        calls = []
        state = {"active": False}
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if operation == "restart": state["active"] = True
            if operation == "stop": state["active"] = False
            if operation == "is-active": return SimpleNamespace(returncode=0 if state["active"] else 3, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        with self.assertRaisesRegex(ValueError, "health"):
            gym.manage_dashboard_service(
                "install", system_name="Linux", user_home=Path(self.tmp.name) / "user",
                executable=Path("/usr/bin/python3"), runner=runner,
                health_checker=lambda: False, health_timeout=0,
            )
        stop_calls = [(command, kwargs) for command, kwargs in calls if command[:3] == ["systemctl", "--user", "stop"]]
        self.assertEqual(len(stop_calls), 1)
        uid = os.getuid()
        self.assertEqual(stop_calls[0][1]["env"]["XDG_RUNTIME_DIR"], f"/run/user/{uid}")
        self.assertEqual(stop_calls[0][1]["env"]["DBUS_SESSION_BUS_ADDRESS"], f"unix:path=/run/user/{uid}/bus")

    def test_failed_health_cleanup_reports_manager_failure_and_leaves_definition(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        state = {"active": False}
        def runner(command, **_kwargs):
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if operation == "restart": state["active"] = True
            if operation == "stop": return SimpleNamespace(returncode=1, stdout="", stderr="stop failed")
            if operation == "is-active": return SimpleNamespace(returncode=0 if state["active"] else 3, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        with self.assertRaisesRegex(OSError, "cleanup.*stop failed"):
            gym.manage_dashboard_service(
                "install", system_name="Linux", user_home=Path(self.tmp.name) / "user",
                executable=Path("/usr/bin/python3"), runner=runner,
                health_checker=lambda: False, health_timeout=0,
            )
        definition = gym.dashboard_service_definition("Linux", Path(self.tmp.name) / "user", Path("/usr/bin/python3"))
        self.assertTrue(definition["path"].is_file())

    def test_linux_uninstall_removes_broken_unit_symlink_when_unit_is_inactive(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name) / "user"
        definition = gym.dashboard_service_definition("Linux", user_home, Path("/usr/bin/python3"))
        definition["path"].parent.mkdir(parents=True)
        definition["path"].symlink_to(definition["path"].parent / "missing")
        def runner(command, **_kwargs):
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if operation == "disable": return SimpleNamespace(returncode=1, stdout="", stderr="unit not found")
            if operation == "is-active": return SimpleNamespace(returncode=3, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        result = gym.manage_dashboard_service(
            "uninstall", system_name="Linux", user_home=user_home,
            executable=Path("/usr/bin/python3"), runner=runner,
        )
        self.assertFalse(os.path.lexists(definition["path"]))
        self.assertFalse(result["installed"])

    def test_manager_status_errors_never_count_as_inactive(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name) / "user"
        definition = gym.dashboard_service_definition("Linux", user_home, Path("/usr/bin/python3"))
        definition["path"].parent.mkdir(parents=True)
        definition["path"].symlink_to(definition["path"].parent / "missing")
        def bus_error_runner(command, **_kwargs):
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if operation == "disable": return SimpleNamespace(returncode=1, stdout="", stderr="unit not found")
            if operation == "is-active": return SimpleNamespace(returncode=1, stdout="", stderr="Failed to connect to bus")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        with self.assertRaisesRegex(OSError, "Failed to connect to bus"):
            gym.manage_dashboard_service(
                "uninstall", system_name="Linux", user_home=user_home,
                executable=Path("/usr/bin/python3"), runner=bus_error_runner,
            )
        self.assertTrue(os.path.lexists(definition["path"]))

        launch = gym.dashboard_service_definition("Darwin", user_home, Path("/usr/bin/python3"))
        gym._write_service_definition(launch["path"], launch["content"])
        def launch_error_runner(command, **_kwargs):
            if command[:2] == ["launchctl", "print"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="Operation not permitted")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        with self.assertRaisesRegex(OSError, "Operation not permitted"):
            gym.manage_dashboard_service(
                "uninstall", system_name="Darwin", user_home=user_home,
                executable=Path("/usr/bin/python3"), runner=launch_error_runner,
            )
        self.assertTrue(launch["path"].is_file())

    def test_service_restart_rejects_final_definition_symlinks(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        user_home = Path(self.tmp.name).resolve() / "restart-user"
        for system_name in ("Darwin", "Linux"):
            definition = gym.dashboard_service_definition(system_name, user_home, Path("/usr/bin/python3"))
            definition["path"].parent.mkdir(parents=True, exist_ok=True)
            victim = Path(self.tmp.name).resolve() / f"{system_name}.victim"
            victim.write_text("do not bootstrap")
            definition["path"].symlink_to(victim)
            calls = []
            def runner(command, **_kwargs):
                calls.append(command)
                if command[:2] == ["launchctl", "print"]:
                    return SimpleNamespace(returncode=0, stdout="state = running\n", stderr="")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            with self.assertRaisesRegex(ValueError, "not installed"):
                gym.manage_dashboard_service(
                    "restart", system_name=system_name, user_home=user_home,
                    executable=Path("/usr/bin/python3"), runner=runner,
                )
            self.assertFalse(any("bootstrap" in command or "restart" in command for command in calls))
            definition["path"].unlink()

    def test_cleanup_status_bus_error_is_explicit_and_retains_definition(self):
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        state = {"checks": 0}
        def runner(command, **_kwargs):
            operation = command[2] if command[:2] == ["systemctl", "--user"] and len(command) > 2 else ""
            if operation == "is-active":
                state["checks"] += 1
                if state["checks"] == 1: return SimpleNamespace(returncode=0, stdout="", stderr="")
                return SimpleNamespace(returncode=1, stdout="", stderr="Failed to connect to bus")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        user_home = Path(self.tmp.name) / "user"
        with self.assertRaisesRegex(OSError, "cleanup status failed.*Failed to connect to bus"):
            gym.manage_dashboard_service(
                "install", system_name="Linux", user_home=user_home,
                executable=Path("/usr/bin/python3"), runner=runner,
                health_checker=lambda: False, health_timeout=0,
            )
        definition = gym.dashboard_service_definition("Linux", user_home, Path("/usr/bin/python3"))
        self.assertTrue(definition["path"].is_file())

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
        svg = (WEB / "icons" / "icon.svg").read_text()
        self.assertIn('id="icon-background"', svg)
        self.assertEqual(svg.count('class="progress-bar"'), 3)
        self.assertIn('id="dumbbell-bar"', svg)
        self.assertIn('id="dumbbell-plates"', svg)
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
                conn.putrequest("GET", "/api/health", skip_host=True)
                conn.putheader("Host", f"[::1]:{server.server_port}")
                conn.endheaders()
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

    def test_today_api_selects_a_routine_from_the_training_navigation(self):
        first = self.routine("Oberkörper", 1)
        self.exercise(first["id"], "Brustpresse")
        second = self.routine("Beine", 5)
        self.exercise(second["id"], "Beinpresse")
        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        server = gym.make_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("GET", f"/api/today?routine={second['id']}")
            response = connection.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(payload["routine"]["id"], second["id"])
            self.assertEqual(payload["routine"]["name"], "Beine")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

    def test_overview_data_contains_cockpit_metrics_timeline_history_and_next_training(self):
        monday = self.routine("Oberkörper", 1)
        press = self.exercise(monday["id"], "Brustpresse", sets=3)
        friday = self.routine("Beine", 5)
        leg_press = self.exercise(friday["id"], "Beinpresse", sets=3)
        older = self.cli("session", "start", "--routine", monday["id"], "--date", "2026-07-27")[1]
        self.cli("set", "log", older["id"], press["id"], "--weight", 40, "--reps", 8)
        self.cli("session", "finish", older["id"])
        latest = self.cli("session", "start", "--routine", friday["id"], "--date", "2026-08-07")[1]
        self.cli("set", "log", latest["id"], leg_press["id"], "--weight", 50, "--reps", 10)
        self.cli("session", "finish", latest["id"])

        gym = load_module()
        os.environ["HERMES_HOME"] = str(self.home)
        overview = gym.overview_data(reference_date=date(2026, 8, 8))

        self.assertEqual(overview["totals"], {"sessions": 2, "sets": 2, "reps": 18, "volume": 820.0})
        self.assertEqual(overview["this_week"], {"sessions": 1, "sets": 1, "reps": 10, "volume": 500.0})
        self.assertEqual(overview["next_routine"]["name"], "Oberkörper")
        self.assertEqual(overview["next_routine"]["weekday"], 1)
        self.assertEqual(overview["next_routine"]["exercise_count"], 1)
        self.assertEqual(overview["next_routine"]["planned_sets"], 3)
        self.assertEqual(len(overview["weekly_volume"]), 12)
        self.assertEqual(overview["weekly_volume"][-1]["volume"], 500.0)
        self.assertEqual([item["routine_name"] for item in overview["recent_sessions"]], ["Beine", "Oberkörper"])
        self.assertEqual(overview["recent_sessions"][0]["volume"], 500.0)

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

    def test_skill_declares_bare_gym_entrypoint_and_home_command(self):
        skill = (ROOT / "skills" / "gym" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("version: 0.1.0-alpha.9", skill)
        self.assertIn("## `/gym`: stabiler Einstieg", skill)
        self.assertIn('python3 "$GYM_CLI" --json home', skill)
        self.assertIn("loginctl enable-linger BENUTZER", skill)
        self.assertIn("Linger niemals still aktivieren", skill)
        self.assertIn('python3 "$GYM_CLI" --json service install', skill)
        self.assertIn('python3 "$GYM_CLI" --json service status', skill)
        self.assertIn("unabhängig vom Hermes-Gateway", skill)
        self.assertIn("Telegram-Befehlsmenü", skill)
        self.assertIn("mögliche Ursache", skill)
        self.assertIn("Gateway-Logs", skill)
        self.assertNotIn("ist das konfigurierte Menülimit erreicht", skill)

    def test_home_entrypoint_guides_bare_gym_command_from_setup_to_training(self):
        first = self.cli("home")[1]
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first["slash_command"], "/gym")
        self.assertEqual(first["state"], "setup_required")
        self.assertEqual(first["primary_action"], "/gym setup")
        self.assertEqual(
            [action["command"] for action in first["actions"]],
            ["/gym setup", "/gym status"],
        )

        routine = self.routine("Ganzkörper", date.today().isoweekday())
        self.exercise(routine["id"], "Kniebeuge")
        ready = self.cli("home")[1]
        self.assertIsNotNone(ready)
        assert ready is not None
        self.assertEqual(ready["state"], "ready")
        self.assertEqual(ready["primary_action"], "/gym today")
        self.assertEqual(ready["today"]["routine"]["name"], "Ganzkörper")
        self.assertEqual(
            [action["command"] for action in ready["actions"]],
            ["/gym today", "/gym plan", "/gym status"],
        )

        session = self.cli("session", "start", "--routine", routine["id"])[1]
        active = self.cli("home")[1]
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active["state"], "training")
        self.assertEqual(active["primary_action"], "/gym today")
        self.assertEqual(active["today"]["active_session"]["id"], session["id"])

    def test_home_entrypoint_handles_a_plan_without_a_routine_today(self):
        other_day = date.today().isoweekday() % 7 + 1
        routine = self.routine("Anderer Tag", other_day)
        self.assertIsNotNone(routine)
        assert routine is not None
        self.exercise(routine["id"], "Rudern")

        home = self.cli("home")[1]
        self.assertIsNotNone(home)
        assert home is not None
        self.assertEqual(home["state"], "no_training_today")
        self.assertEqual(home["primary_action"], "/gym plan")
        self.assertIsNone(home["today"]["routine"])
        self.assertEqual(
            [action["command"] for action in home["actions"]],
            ["/gym plan", "/gym status"],
        )

    def test_home_entrypoint_prioritizes_an_active_session_over_an_externally_disabled_plan(self):
        routine = self.routine("Recovery", date.today().isoweekday())
        self.assertIsNotNone(routine)
        assert routine is not None
        self.exercise(routine["id"], "Drücken")
        session = self.cli("session", "start", "--routine", routine["id"])[1]
        self.assertIsNotNone(session)
        assert session is not None
        with sqlite3.connect(self.home / "gympilot" / "gympilot.db") as con:
            con.execute("UPDATE routines SET active=0 WHERE id=?", (routine["id"],))

        home = self.cli("home")[1]
        self.assertIsNotNone(home)
        assert home is not None
        self.assertEqual(home["state"], "training")
        self.assertEqual(home["primary_action"], "/gym today")
        self.assertEqual(home["today"]["active_session"]["id"], session["id"])
        self.assertEqual(home["today"]["routine"]["id"], routine["id"])
        self.assertEqual(home["today"]["plan"], [])

    def test_onboarding_exposes_only_import_and_manual_setup(self):
        status = self.cli("onboarding", "status")[1]
        self.assertEqual(status["setup_modes"], ["import", "manual"])
        selected = self.cli("onboarding", "mode", "import")[1]
        self.assertEqual(selected["selected_mode"], "import")
        self.assertEqual(self.cli("onboarding", "status")[1]["selected_mode"], "import")
        rejected_mode, payload = self.cli("onboarding", "mode", "generate", check=False)
        self.assertEqual(rejected_mode.returncode, 2)
        self.assertIn("invalid choice", payload["error"])
        rejected_draft, payload = self.cli("draft", "generate", check=False)
        self.assertEqual(rejected_draft.returncode, 2)
        self.assertIn("invalid choice", payload["error"])
        capabilities = self.cli("draft", "capabilities")[1]
        self.assertIsNotNone(capabilities)
        assert capabilities is not None
        self.assertEqual(set(capabilities), {"equipment", "exercises"})
        self.assertNotIn("goals", capabilities)
        self.assertNotIn("generator_version", capabilities)

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

    def test_generator_metadata_is_reserved_and_removed_after_structured_edit(self):
        draft = self.historical_generated_draft()
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
        draft = self.historical_generated_draft()
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
