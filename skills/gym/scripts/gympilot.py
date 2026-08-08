#!/usr/bin/env python3
"""GymPilot: dependency-free, profile-local workout CLI and PWA server."""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import hmac
import http.cookies
import ipaddress
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import stat
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SCHEMA_VERSION = 1
MAX_ROUTINES = 14
MAX_EXERCISES_PER_ROUTINE = 50
MAX_PLANNED_SETS = 100
MAX_REPS = 100000
SQLITE_INT_MAX = 9223372036854775807
WEB_ROOT = Path(__file__).resolve().parent.parent / "assets" / "web"
PROFILE_ONBOARDING_FIELDS = ("display_name", "locale", "units", "goal")


def data_dir() -> Path:
    root = Path(os.environ.get("HERMES_HOME") or "~/.hermes").expanduser().absolute()
    override = os.environ.get("GYMPILOT_DATA_DIR") or None
    selected = Path(override).expanduser().absolute() if override else root / "gympilot"
    reject_symlink_components(selected)
    return selected.resolve(strict=False)


def db_path() -> Path:
    return data_dir() / "gympilot.db"


def reject_symlink_components(path: Path) -> None:
    absolute=path.expanduser().absolute()
    current=Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try: mode=os.lstat(current).st_mode
        except FileNotFoundError: break
        if stat.S_ISLNK(mode):
            if sys.platform == "darwin" and str(current) in {"/var","/tmp","/etc"}: continue
            raise ValueError(f"symlink paths are not allowed for private data: {current}")


def directory_descriptor(path: Path, *, create: bool = False, require_new: bool = False) -> int:
    absolute=path.absolute()
    flags=os.O_RDONLY | getattr(os,"O_DIRECTORY",0) | getattr(os,"O_NOFOLLOW",0)
    descriptor=os.open(absolute.anchor,flags)
    try:
        for index,part in enumerate(absolute.parts[1:]):
            final=index==len(absolute.parts)-2
            created=False
            try: child=os.open(part,flags,dir_fd=descriptor)
            except FileNotFoundError:
                if not create: raise
                os.mkdir(part,0o700,dir_fd=descriptor); created=True
                child=os.open(part,flags,dir_fd=descriptor)
            if final and require_new and not created:
                os.close(child); raise FileExistsError(f"private directory already exists: {absolute}")
            os.close(descriptor); descriptor=child
        return descriptor
    except BaseException:
        os.close(descriptor); raise


def private_directory(path: Path, enforce_existing: bool = True, require_new: bool = False) -> None:
    reject_symlink_components(path)
    if os.name == "nt":
        existed=path.exists(); path.mkdir(parents=True,exist_ok=not require_new,mode=0o700); reject_symlink_components(path)
        if not existed: os.chmod(path,0o700)
        return
    descriptor=directory_descriptor(path,create=True,require_new=require_new)
    try:
        if enforce_existing: os.fchmod(descriptor,0o700)
    finally: os.close(descriptor)


def open_private_text(path: Path, *, newline: str | None = None):
    reject_symlink_components(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    parent = directory_descriptor(path.parent) if os.name != "nt" else None
    try: descriptor = os.open(path.name if parent is not None else path, flags, 0o600, dir_fd=parent)
    finally:
        if parent is not None: os.close(parent)
    if os.name != "nt":
        os.fchmod(descriptor, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8", newline=newline)


def prepare_private_file(path: Path) -> int:
    reject_symlink_components(path.parent)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    parent = directory_descriptor(path.parent) if os.name != "nt" else None
    try: descriptor = os.open(path.name if parent is not None else path, flags, 0o600, dir_fd=parent)
    finally:
        if parent is not None: os.close(parent)
    if os.name != "nt": os.fchmod(descriptor,0o600)
    return descriptor


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


MIGRATIONS = {1: """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_profile(id INTEGER PRIMARY KEY CHECK(id=1), display_name TEXT NOT NULL DEFAULT '', locale TEXT NOT NULL DEFAULT 'de', units TEXT NOT NULL DEFAULT 'metric', goal TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS onboarding_state(field TEXT PRIMARY KEY, value TEXT NOT NULL, confirmed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS routines(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, notes TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS routine_days(id INTEGER PRIMARY KEY, routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE, weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7), UNIQUE(routine_id, weekday));
CREATE TABLE IF NOT EXISTS exercises(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, notes TEXT NOT NULL DEFAULT '', unilateral INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS equipment_aliases(id INTEGER PRIMARY KEY, exercise_id INTEGER NOT NULL REFERENCES exercises(id), alias TEXT NOT NULL UNIQUE COLLATE NOCASE, notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS routine_exercises(id INTEGER PRIMARY KEY, routine_id INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE, exercise_id INTEGER NOT NULL REFERENCES exercises(id), position INTEGER NOT NULL, planned_sets INTEGER NOT NULL CHECK(planned_sets>0), min_reps INTEGER NOT NULL CHECK(min_reps>0), max_reps INTEGER NOT NULL CHECK(max_reps>=min_reps), notes TEXT NOT NULL DEFAULT '', UNIQUE(routine_id, exercise_id), UNIQUE(routine_id, position));
CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, routine_id INTEGER NOT NULL REFERENCES routines(id), session_date TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT, notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS workout_sets(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, exercise_id INTEGER NOT NULL REFERENCES exercises(id), equipment_alias_id INTEGER REFERENCES equipment_aliases(id), set_number INTEGER NOT NULL CHECK(set_number>0), side TEXT NOT NULL DEFAULT '', weight_kg REAL NOT NULL CHECK(weight_kg>=0 AND weight_kg<=100000), reps INTEGER NOT NULL CHECK(reps>0), rpe REAL CHECK(rpe IS NULL OR (rpe>=1 AND rpe<=10)), notes TEXT NOT NULL DEFAULT '', recorded_at TEXT NOT NULL, corrected_at TEXT, UNIQUE(session_id, exercise_id, set_number, side));
CREATE TABLE IF NOT EXISTS auth_config(id INTEGER PRIMARY KEY CHECK(id=1), password_hash TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS web_sessions(token_hash TEXT PRIMARY KEY, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_sets_session ON workout_sets(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(session_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_session ON sessions((1)) WHERE completed_at IS NULL;
CREATE TRIGGER IF NOT EXISTS trg_routine_day_unambiguous_insert BEFORE INSERT ON routine_days
WHEN (SELECT active FROM routines WHERE id=NEW.routine_id)=1 AND EXISTS(
  SELECT 1 FROM routine_days d JOIN routines r ON r.id=d.routine_id
  WHERE d.weekday=NEW.weekday AND r.active=1 AND d.routine_id<>NEW.routine_id)
BEGIN SELECT RAISE(ABORT, 'weekday already assigned to another active routine'); END;
CREATE TRIGGER IF NOT EXISTS trg_routine_day_unambiguous_update BEFORE UPDATE OF weekday,routine_id ON routine_days
WHEN (SELECT active FROM routines WHERE id=NEW.routine_id)=1 AND EXISTS(
  SELECT 1 FROM routine_days d JOIN routines r ON r.id=d.routine_id
  WHERE d.weekday=NEW.weekday AND r.active=1 AND d.routine_id<>NEW.routine_id)
BEGIN SELECT RAISE(ABORT, 'weekday already assigned to another active routine'); END;
CREATE TRIGGER IF NOT EXISTS trg_routine_activation_unambiguous BEFORE UPDATE OF active ON routines
WHEN NEW.active=1 AND OLD.active=0 AND EXISTS(
  SELECT 1 FROM routine_days own JOIN routine_days other ON other.weekday=own.weekday
  JOIN routines r ON r.id=other.routine_id
  WHERE own.routine_id=NEW.id AND other.routine_id<>NEW.id AND r.active=1)
BEGIN SELECT RAISE(ABORT, 'weekday already assigned to another active routine'); END;
"""}


def connect() -> sqlite3.Connection:
    private_directory(data_dir())
    if os.path.lexists(db_path()) and db_path().is_symlink(): raise ValueError("the GymPilot database must not be a symlink")
    if not os.path.lexists(db_path()):
        try:
            descriptor=prepare_private_file(db_path()); os.close(descriptor)
        except FileExistsError: pass
    if db_path().is_symlink(): raise ValueError("the GymPilot database must not be a symlink")
    if os.name != "nt": os.chmod(db_path(),0o600)
    con = sqlite3.connect(db_path(), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    if os.name != "nt":
        for suffix in ("","-wal","-shm"):
            try: os.chmod(f"{db_path()}{suffix}",0o600)
            except FileNotFoundError: pass
    return con


def initialize() -> dict:
    private_directory(data_dir())
    with connect() as con:
        current = con.execute("PRAGMA user_version").fetchone()[0]
        for version in range(current + 1, SCHEMA_VERSION + 1):
            con.executescript(MIGRATIONS[version])
            con.execute("INSERT INTO schema_migrations VALUES(?,?)", (version, now()))
            con.execute(f"PRAGMA user_version={version}")
        con.execute("INSERT OR IGNORE INTO user_profile(id,updated_at) VALUES(1,?)", (now(),))
        con.commit()
    if os.name != "nt": os.chmod(db_path(),0o600)
    return {"ok": True, "schema_version": SCHEMA_VERSION, "database": str(db_path())}


def ensure() -> None:
    initialize()


def rows(rows_) -> list[dict]:
    return [dict(r) for r in rows_]


def plan() -> list[dict]:
    ensure()
    with connect() as con:
        routines = rows(con.execute("SELECT * FROM routines WHERE active=1 ORDER BY name"))
        for routine in routines:
            routine["weekdays"] = [r[0] for r in con.execute("SELECT weekday FROM routine_days WHERE routine_id=? ORDER BY weekday", (routine["id"],))]
            routine["exercises"] = rows(con.execute("""SELECT e.id,e.name,e.notes exercise_notes,e.unilateral,re.position,re.planned_sets,re.min_reps,re.max_reps,re.notes FROM routine_exercises re JOIN exercises e ON e.id=re.exercise_id WHERE re.routine_id=? AND e.active=1 ORDER BY re.position""", (routine["id"],)))
            for exercise in routine["exercises"]:
                exercise["equipment_aliases"] = rows(con.execute("SELECT id,alias,notes FROM equipment_aliases WHERE exercise_id=? ORDER BY alias", (exercise["id"],)))
        return routines


def today_data(routine_id: int | None = None) -> dict:
    """Return the selected routine with comparable and in-progress sets separated."""
    ensure()
    weekday = date.today().isoweekday()
    with connect() as con:
        profile = dict(con.execute("SELECT * FROM user_profile WHERE id=1").fetchone())
        active = con.execute("SELECT * FROM sessions WHERE completed_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
        selected_id = routine_id or (active["routine_id"] if active else None)
        if selected_id is not None:
            # An already-running session remains visible even if the database was
            # edited externally and its routine became inactive.
            routine = con.execute("SELECT * FROM routines WHERE id=?" + ("" if active and active["routine_id"] == selected_id else " AND active=1"), (selected_id,)).fetchone()
        else:
            routine = con.execute("""SELECT r.* FROM routines r JOIN routine_days d ON d.routine_id=r.id WHERE d.weekday=? AND r.active=1 ORDER BY r.id LIMIT 1""", (weekday,)).fetchone()
        selected = None
        if routine:
            selected = dict(routine)
            selected["weekdays"] = [r[0] for r in con.execute("SELECT weekday FROM routine_days WHERE routine_id=? ORDER BY weekday", (routine["id"],))]
            active_id = active["id"] if active and active["routine_id"] == routine["id"] else None
            previous = con.execute("""SELECT id,session_date FROM sessions
                WHERE routine_id=? AND completed_at IS NOT NULL AND (? IS NULL OR id<>?)
                ORDER BY session_date DESC,id DESC LIMIT 1""", (routine["id"], active_id, active_id)).fetchone()
            selected["last_comparable_session_date"] = previous["session_date"] if previous else None
            exercises = rows(con.execute("""SELECT e.id,e.name,e.notes exercise_notes,e.unilateral,re.position,
                re.planned_sets,re.min_reps,re.max_reps,re.notes
                FROM routine_exercises re JOIN exercises e ON e.id=re.exercise_id
                WHERE re.routine_id=? AND e.active=1 ORDER BY re.position""", (routine["id"],)))
            for exercise in exercises:
                exercise["equipment_aliases"] = rows(con.execute("SELECT id,alias,notes FROM equipment_aliases WHERE exercise_id=? ORDER BY alias", (exercise["id"],)))
                exercise["last_sets"] = rows(con.execute("""SELECT w.id,w.set_number,w.side,w.weight_kg,w.reps,w.rpe,w.notes,w.equipment_alias_id,a.alias equipment_alias
                    FROM workout_sets w LEFT JOIN equipment_aliases a ON a.id=w.equipment_alias_id WHERE w.session_id=? AND w.exercise_id=? ORDER BY w.set_number,w.side,w.id""",
                    (previous["id"], exercise["id"]))) if previous else []
                exercise["current_sets"] = rows(con.execute("""SELECT w.id,w.set_number,w.side,w.weight_kg,w.reps,w.rpe,w.notes,w.equipment_alias_id,a.alias equipment_alias
                    FROM workout_sets w LEFT JOIN equipment_aliases a ON a.id=w.equipment_alias_id WHERE w.session_id=? AND w.exercise_id=? ORDER BY w.set_number,w.side,w.id""",
                    (active_id, exercise["id"]))) if active_id else []
                exercise["current_progress"] = {
                    "completed_sets": len(exercise["current_sets"]),
                    "planned_sets": exercise["planned_sets"],
                }
            selected["exercises"] = exercises
        last = con.execute("""SELECT s.*,r.name routine_name,(SELECT COUNT(*) FROM workout_sets w WHERE w.session_id=s.id) sets FROM sessions s JOIN routines r ON r.id=s.routine_id WHERE s.completed_at IS NOT NULL ORDER BY s.session_date DESC,s.id DESC LIMIT 1""").fetchone()
    return {"date": date.today().isoformat(), "weekday": weekday, "profile": profile,
            "routine": selected, "active_session": dict(active) if active else None,
            "last_session": dict(last) if last else None, "plan": plan()}


def onboarding_sequence(answers: dict[str, str]) -> list[str]:
    sequence = list(PROFILE_ONBOARDING_FIELDS) + ["routine_count"]
    try:
        routine_count = int(answers.get("routine_count", "0"))
    except ValueError:
        routine_count = 0
    routine_count=max(0,min(routine_count,MAX_ROUTINES))
    for routine_number in range(1, routine_count + 1):
        prefix = f"routine_{routine_number}"
        sequence += [f"{prefix}_name", f"{prefix}_weekdays", f"{prefix}_exercise_count"]
        try:
            exercise_count = int(answers.get(f"{prefix}_exercise_count", "0"))
        except ValueError:
            exercise_count = 0
        exercise_count=max(0,min(exercise_count,MAX_EXERCISES_PER_ROUTINE))
        for exercise_number in range(1, exercise_count + 1):
            ep = f"{prefix}_exercise_{exercise_number}"
            sequence += [f"{ep}_name", f"{ep}_sets", f"{ep}_min_reps", f"{ep}_max_reps"]
    return sequence


def validate_onboarding_value(field: str, value: str, answers: dict[str, str]) -> str:
    if "password" in field.lower():
        raise ValueError("passwords are never accepted in onboarding")
    allowed = set(onboarding_sequence(answers))
    # The next dynamic count expands the sequence after it is stored.
    if field not in allowed:
        raise ValueError(f"unsupported or out-of-order onboarding field: {field}; passwords are never accepted here")
    value = value.strip()
    if not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > 1000: raise ValueError(f"{field} is too long")
    if field == "units" and value not in {"metric", "imperial"}:
        raise ValueError("units must be metric or imperial")
    if field.endswith("_weekdays"):
        try:
            days = sorted({int(day.strip()) for day in value.split(",")})
        except ValueError as exc:
            raise ValueError("weekdays must be comma-separated ISO numbers 1-7") from exc
        if not days or any(day < 1 or day > 7 for day in days):
            raise ValueError("weekdays must be comma-separated ISO numbers 1-7")
        return ",".join(map(str, days))
    if field == "routine_count" or field.endswith("_exercise_count") or field.endswith("_sets") or field.endswith("_min_reps") or field.endswith("_max_reps"):
        try:
            number = int(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be a positive integer") from exc
        if number < 1:
            raise ValueError(f"{field} must be a positive integer")
        limit = MAX_ROUTINES if field=="routine_count" else MAX_EXERCISES_PER_ROUTINE if field.endswith("_exercise_count") else MAX_PLANNED_SETS if field.endswith("_sets") else MAX_REPS
        if number > limit: raise ValueError(f"{field} must not exceed {limit}")
        if field.endswith("_min_reps"):
            maximum = answers.get(field.removesuffix("_min_reps") + "_max_reps")
            if maximum is not None and number > int(maximum):
                raise ValueError("minimum reps must not exceed maximum reps")
        if field.endswith("_max_reps"):
            minimum = answers.get(field.removesuffix("_max_reps") + "_min_reps")
            if minimum is not None and number < int(minimum):
                raise ValueError("maximum reps must not be below minimum reps")
        return str(number)
    return value


def materialize_onboarding_plan(con: sqlite3.Connection, answers: dict[str, str]) -> None:
    if answers.get("plan_materialized") == "1":
        return
    for routine_number in range(1, int(answers["routine_count"]) + 1):
        prefix = f"routine_{routine_number}"
        cur = con.execute("INSERT INTO routines(name,notes,created_at) VALUES(?,?,?)", (answers[f"{prefix}_name"], "", now()))
        routine_id = cur.lastrowid
        for weekday in map(int, answers[f"{prefix}_weekdays"].split(",")):
            con.execute("INSERT INTO routine_days(routine_id,weekday) VALUES(?,?)", (routine_id, weekday))
        for exercise_number in range(1, int(answers[f"{prefix}_exercise_count"]) + 1):
            ep = f"{prefix}_exercise_{exercise_number}"
            cur = con.execute("INSERT INTO exercises(name) VALUES(?) ON CONFLICT(name) DO UPDATE SET active=1 RETURNING id", (answers[f"{ep}_name"],))
            exercise_id = cur.fetchone()[0]
            con.execute("""INSERT INTO routine_exercises(routine_id,exercise_id,position,planned_sets,min_reps,max_reps)
                VALUES(?,?,?,?,?,?)""", (routine_id, exercise_id, exercise_number, int(answers[f"{ep}_sets"]),
                int(answers[f"{ep}_min_reps"]), int(answers[f"{ep}_max_reps"])))
    con.execute("INSERT INTO onboarding_state VALUES('plan_materialized','1',?)", (now(),))


def onboarding_status(con: sqlite3.Connection) -> dict:
    answers = {r[0]: r[1] for r in con.execute("SELECT field,value FROM onboarding_state")}
    sequence = onboarding_sequence(answers)
    next_field = next((field for field in sequence if field not in answers), None)
    complete = next_field is None and bool(sequence)
    if complete:
        materialize_onboarding_plan(con, answers)
        answers["plan_materialized"] = "1"
    phase = "profile" if next_field in PROFILE_ONBOARDING_FIELDS else ("complete" if complete else "plan")
    return {"answers": answers, "next_field": next_field, "phase": phase, "complete": complete}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    if hasattr(hashlib, "scrypt"):
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"
    # Some vendor Python builds omit OpenSSL scrypt. Keep authentication usable
    # with a versioned standard-library fallback rather than accepting plaintext.
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000, dklen=32)
    return f"pbkdf2-sha256$600000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        parts = encoded.split("$")
        if parts[0] == "scrypt":
            _, n, r, p, salt, expected = parts
            if not hasattr(hashlib, "scrypt"):
                return False
            actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(expected)))
        elif parts[0] == "pbkdf2-sha256":
            _, iterations, salt, expected = parts
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations), dklen=len(bytes.fromhex(expected)))
        else:
            return False
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def auth_enabled() -> bool:
    with connect() as con:
        return con.execute("SELECT 1 FROM auth_config WHERE id=1").fetchone() is not None


def valid_host(host: str) -> bool:
    if host.lower() == "localhost": return True
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_unspecified or ip.is_global or ip.is_multicast)
    except ValueError:
        return False


class RateLimiter:
    def __init__(self):
        self.attempts: dict[str, list[float]] = {}
        self.lock = threading.Lock()
    def begin(self, key: str) -> bool:
        """Atomically reserve one login attempt before password verification."""
        with self.lock:
            cutoff = time.time() - 300
            current = [t for t in self.attempts.get(key, []) if t > cutoff]
            if len(current) >= 5:
                self.attempts[key] = current
                return False
            current.append(time.time())
            self.attempts[key] = current
            return True
    def success(self, key: str) -> None:
        with self.lock:
            self.attempts.pop(key, None)


LIMITER=RateLimiter()


def strict_json_loads(raw: bytes):
    def reject_constant(value): raise ValueError(f"non-standard JSON value: {value}")
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError(f"duplicate JSON key: {key}")
            result[key]=value
        return result
    return json.loads(raw,parse_constant=reject_constant,object_pairs_hook=unique_object)


class GymArgumentParser(argparse.ArgumentParser):
    def error(self,message):
        if "--json" in sys.argv[1:]: print(json.dumps({"ok":False,"error":message},ensure_ascii=False))
        else: print(f"Error: {message}",file=sys.stderr)
        raise SystemExit(2)


def safe_int(value: str) -> int:
    if len(value)>20 or re.fullmatch(r"[+-]?[0-9]+",value) is None: raise argparse.ArgumentTypeError("integer is invalid or too large")
    return int(value)


class GymPilotServer(ThreadingHTTPServer):
    allowed_hosts: set[str]
    daemon_threads = True
    request_deadline = 15.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_slots = threading.BoundedSemaphore(32)

    def process_request(self, request, client_address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()


class GymPilotIPv6Server(GymPilotServer):
    address_family = socket.AF_INET6


def parse_host_authority(raw: str) -> tuple[str, int | None] | None:
    """Strictly parse an HTTP Host authority without accepting URL userinfo."""
    if not raw or raw != raw.strip() or any(ord(char) < 33 or ord(char) == 127 for char in raw):
        return None
    if any(char in raw for char in "@/,\\?#"):
        return None
    host: str
    port_text: str | None = None
    if raw.startswith("["):
        match = re.fullmatch(r"\[([^\]]+)\](?::([0-9]+))?", raw)
        if not match:
            return None
        host, port_text = match.groups()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return None
        if address.version != 6:
            return None
        host = address.compressed
    else:
        if raw.count(":") > 1:
            return None
        if ":" in raw:
            host, port_text = raw.rsplit(":", 1)
            if not host or not port_text:
                return None
        else:
            host = raw
        if host.lower() == "localhost":
            host = "localhost"
        else:
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                return None
            if address.version != 4:
                return None
            host = address.compressed
    if port_text is None:
        return host, None
    if not port_text.isascii() or not port_text.isdigit():
        return None
    port = int(port_text)
    if not 1 <= port <= 65535:
        return None
    return host, port


class Handler(BaseHTTPRequestHandler):
    server_version = "GymPilot/0.1"
    def setup(self):
        super().setup()
        self.connection.settimeout(15)
        self.deadline_timer=threading.Timer(getattr(self.server,"request_deadline",15.0),self.expire_request)
        self.deadline_timer.daemon=True
        self.deadline_timer.start()
    def handle(self):
        try: super().handle()
        except (BrokenPipeError,ConnectionResetError,OSError): pass
    def finish(self):
        self.deadline_timer.cancel()
        super().finish()
    def expire_request(self):
        try: self.connection.shutdown(socket.SHUT_RDWR)
        except OSError: pass
    def log_message(self, fmt, *args): pass
    def headers_common(self, cache="no-store"):
        self.send_header("Cache-Control", cache)
        if cache == "no-store":
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "DENY"); self.send_header("Referrer-Policy", "no-referrer"); self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
    def send_json(self, payload, status=200):
        body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode(); self.send_response(status); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.headers_common(); self.end_headers(); self.wfile.write(body)
    def token(self):
        cookie=http.cookies.SimpleCookie(self.headers.get("Cookie","")); return cookie.get("gympilot_session").value if cookie.get("gympilot_session") else ""
    def host_allowed(self):
        values=self.headers.get_all("Host",[])
        if len(values)!=1: return False
        parsed=parse_host_authority(values[0])
        if parsed is None: return False
        hostname,port=parsed
        if port is not None and port != getattr(self.server,"server_port",None): return False
        return hostname in getattr(self.server,"allowed_hosts",set())
    def authorized(self):
        if not auth_enabled(): return True
        token=self.token()
        if not token: return False
        with connect() as con:
            return con.execute("SELECT 1 FROM web_sessions WHERE token_hash=? AND expires_at>?",(hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone() is not None
    def do_GET(self):
        if not self.host_allowed(): return self.send_json({"error":"unrecognized host"},421)
        parsed=urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if parsed.path != "/api/health" and not self.authorized(): return self.send_json({"error":"authentication required"},401)
            try:
                if parsed.path=="/api/health": return self.send_json({"status":"ok","schema_version":SCHEMA_VERSION,"auth_required":auth_enabled()})
                if parsed.path=="/api/today": return self.send_json(today_data())
                if parsed.path=="/api/plan": return self.send_json(plan())
                if parsed.path=="/api/overview":
                    with connect() as con:
                        d=dict(con.execute("SELECT COUNT(DISTINCT s.id) sessions,COUNT(w.id) sets,COALESCE(SUM(w.reps),0) reps,ROUND(COALESCE(SUM(w.weight_kg*w.reps),0),1) volume FROM sessions s LEFT JOIN workout_sets w ON w.session_id=s.id").fetchone())
                    return self.send_json(d)
            except sqlite3.Error as exc: return self.send_json({"error":str(exc)},400)
            return self.send_json({"error":"not found"},404)
        self.serve_static(parsed.path)
    def do_POST(self):
        if not self.host_allowed(): return self.send_json({"error":"unrecognized host"},421)
        path=urlparse(self.path).path
        if self.headers.get_all("Transfer-Encoding",[]): self.close_connection=True; return self.send_json({"error":"transfer encoding is not supported"},400)
        lengths=self.headers.get_all("Content-Length",[])
        if len(lengths)!=1: self.close_connection=True; return self.send_json({"error":"exactly one content length is required"},400)
        if not lengths[0].isascii() or not lengths[0].isdigit(): self.close_connection=True; return self.send_json({"error":"invalid content length"},400)
        if len(lengths[0]) > 10: self.close_connection=True; return self.send_json({"error":"invalid content length"},400)
        size=int(lengths[0])
        if size < 0: self.close_connection=True; return self.send_json({"error":"invalid content length"},400)
        if size > 8192: self.close_connection=True; return self.send_json({"error":"request body too large"},413)
        if size and self.headers.get("Content-Type","").split(";",1)[0].strip().lower() != "application/json":
            self.close_connection=True; return self.send_json({"error":"content type must be application/json"},415)
        try: payload=strict_json_loads(self.rfile.read(size) or b"{}")
        except (json.JSONDecodeError,UnicodeDecodeError,ValueError,RecursionError): return self.send_json({"error":"invalid JSON"},400)
        if not isinstance(payload,dict): return self.send_json({"error":"JSON body must be an object"},400)
        if path=="/api/login":
            if set(payload)!={"password"} or type(payload.get("password")) is not str or not (1<=len(payload["password"])<=1024): return self.send_json({"error":"login requires exactly one string password"},400)
            key=self.client_address[0]
            if not LIMITER.begin(key): return self.send_json({"error":"too many attempts"},429)
            with connect() as con: row=con.execute("SELECT password_hash FROM auth_config WHERE id=1").fetchone()
            if not row or not verify_password(payload["password"],row[0]): return self.send_json({"error":"invalid credentials"},401)
            LIMITER.success(key)
            token=secrets.token_urlsafe(32); expires=int(time.time())+86400
            with connect() as con: con.execute("INSERT INTO web_sessions VALUES(?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),int(time.time()),expires)); con.commit()
            body=json.dumps({"ok":True}).encode(); self.send_response(200); self.send_header("Set-Cookie",f"gympilot_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400"); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.headers_common(); self.end_headers(); self.wfile.write(body); return
        if path=="/api/logout":
            with connect() as con: con.execute("DELETE FROM web_sessions WHERE token_hash=?",(hashlib.sha256(self.token().encode()).hexdigest(),)); con.commit()
            body=json.dumps({"ok":True}).encode(); self.send_response(200); self.send_header("Set-Cookie","gympilot_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.headers_common(); self.end_headers(); self.wfile.write(body); return
        return self.send_json({"error":"not found"},404)
    def serve_static(self, path):
        rel="index.html" if path in {"","/"} else path.lstrip("/"); candidate=(WEB_ROOT/rel).resolve()
        if WEB_ROOT not in candidate.parents: return self.send_json({"error":"forbidden"},403)
        if not candidate.is_file(): candidate=WEB_ROOT/"index.html"
        body=candidate.read_bytes(); mime=mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(200); self.send_header("Content-Type",mime); self.send_header("Content-Length",str(len(body))); self.headers_common("no-cache"); self.end_headers(); self.wfile.write(body)


def make_server(host="127.0.0.1", port=8765):
    if not valid_host(host): raise ValueError("host must be a concrete local, LAN, or VPN address; wildcard/public hosts are forbidden")
    normalized="localhost" if host.lower()=="localhost" else ipaddress.ip_address(host).compressed
    server_class=GymPilotIPv6Server if normalized != "localhost" and ipaddress.ip_address(normalized).version==6 else GymPilotServer
    server=server_class((host,port),Handler)
    server.allowed_hosts={normalized}
    try:
        if ipaddress.ip_address(host).is_loopback: server.allowed_hosts.add("localhost")
    except ValueError:
        if host.lower()=="localhost": server.allowed_hosts.add("127.0.0.1")
    return server


def validate_arguments(args) -> None:
    if sys.version_info < (3,11): raise ValueError("GymPilot requires Python 3.11 or newer")
    integer_limits={
        "id":(1,SQLITE_INT_MAX),"routine":(1,SQLITE_INT_MAX),"exercise":(1,SQLITE_INT_MAX),
        "session":(1,SQLITE_INT_MAX),"equipment":(1,SQLITE_INT_MAX),"sets":(1,MAX_PLANNED_SETS),
        "min_reps":(1,MAX_REPS),"max_reps":(1,MAX_REPS),"reps":(1,MAX_REPS),
        "number":(1,10000),"port":(0,65535),
    }
    text_limits={"name":200,"alias":200,"side":100,"notes":4000,"exercise_notes":4000,"value":1000}
    for field,value in vars(args).items():
        if value is None or isinstance(value,bool): continue
        if field in integer_limits and isinstance(value,int):
            low,high=integer_limits[field]
            if value < low or value > high: raise ValueError(f"{field} must be between {low} and {high}")
        if field in text_limits and isinstance(value,str) and len(value)>text_limits[field]:
            raise ValueError(f"{field} is too long")


def command(args):
    validate_arguments(args)
    ensure()
    if args.command=="init": return initialize()
    if args.command=="status":
        with connect() as con: counts={t:con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("routines","exercises","equipment_aliases","sessions","workout_sets")}
        return {"ok":True,"schema_version":SCHEMA_VERSION,"data_dir":str(data_dir()),"database":str(db_path()),"auth_enabled":auth_enabled(),**counts}
    if args.command=="onboarding":
        with connect() as con:
            if args.action=="set":
                con.execute("BEGIN IMMEDIATE")
                answers={r[0]:r[1] for r in con.execute("SELECT field,value FROM onboarding_state")}
                if "password" in args.field.lower(): raise ValueError("passwords are never accepted in onboarding")
                if answers.get("plan_materialized")=="1": raise ValueError("setup is already complete; use /gym plan to change the saved plan")
                value=validate_onboarding_value(args.field,args.value,answers)
                con.execute("INSERT INTO onboarding_state VALUES(?,?,?) ON CONFLICT(field) DO UPDATE SET value=excluded.value,confirmed_at=excluded.confirmed_at",(args.field,value,now()))
                if args.field in PROFILE_ONBOARDING_FIELDS:
                    con.execute(f"UPDATE user_profile SET {args.field}=?,updated_at=? WHERE id=1",(value,now()))
            return onboarding_status(con)
    if args.command=="routine":
        if args.action=="add":
            with connect() as con:
                for day in sorted(set(args.weekday)):
                    conflict=con.execute("""SELECT r.name FROM routine_days d JOIN routines r ON r.id=d.routine_id
                        WHERE d.weekday=? AND r.active=1 LIMIT 1""",(day,)).fetchone()
                    if conflict: raise ValueError(f"weekday {day} is already assigned to active routine {conflict['name']}")
                cur=con.execute("INSERT INTO routines(name,notes,created_at) VALUES(?,?,?)",(args.name,args.notes,now())); rid=cur.lastrowid
                for day in sorted(set(args.weekday)): con.execute("INSERT INTO routine_days(routine_id,weekday) VALUES(?,?)",(rid,day))
                con.commit()
                result=dict(con.execute("SELECT * FROM routines WHERE id=?",(rid,)).fetchone())
                result["weekdays"]=sorted(set(args.weekday)); return result
        if args.action=="update":
            with connect() as con:
                row=con.execute("SELECT * FROM routines WHERE id=? AND active=1",(args.id,)).fetchone()
                if not row: raise ValueError("active routine not found")
                name=args.name if args.name is not None else row["name"]
                notes=args.notes if args.notes is not None else row["notes"]
                con.execute("UPDATE routines SET name=?,notes=? WHERE id=?",(name,notes,args.id))
                if args.weekday is not None:
                    for day in sorted(set(args.weekday)):
                        conflict=con.execute("""SELECT r.name FROM routine_days d JOIN routines r ON r.id=d.routine_id
                            WHERE d.weekday=? AND r.active=1 AND r.id<>? LIMIT 1""",(day,args.id)).fetchone()
                        if conflict: raise ValueError(f"weekday {day} is already assigned to active routine {conflict['name']}")
                    con.execute("DELETE FROM routine_days WHERE routine_id=?",(args.id,))
                    for day in sorted(set(args.weekday)): con.execute("INSERT INTO routine_days(routine_id,weekday) VALUES(?,?)",(args.id,day))
                con.commit()
                result=dict(con.execute("SELECT * FROM routines WHERE id=?",(args.id,)).fetchone())
                result["weekdays"]=[r[0] for r in con.execute("SELECT weekday FROM routine_days WHERE routine_id=? ORDER BY weekday",(args.id,))]
                return result
        if args.action=="deactivate":
            with connect() as con:
                if con.execute("SELECT 1 FROM sessions WHERE routine_id=? AND completed_at IS NULL",(args.id,)).fetchone(): raise ValueError("cannot deactivate a routine with an active session; finish the session first")
                cur=con.execute("UPDATE routines SET active=0 WHERE id=? AND active=1",(args.id,))
                if not cur.rowcount: raise ValueError("active routine not found")
                con.commit(); return dict(con.execute("SELECT * FROM routines WHERE id=?",(args.id,)).fetchone())
        return plan()
    if args.command=="exercise":
        if args.action=="add":
            with connect() as con:
                if not con.execute("SELECT 1 FROM routines WHERE id=? AND active=1",(args.routine,)).fetchone(): raise ValueError("active routine not found")
                cur=con.execute("INSERT INTO exercises(name,notes,unilateral) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET active=1 RETURNING id",(args.name,args.notes,int(args.unilateral))); eid=cur.fetchone()[0]
                pos=con.execute("SELECT COALESCE(MAX(position),0)+1 FROM routine_exercises WHERE routine_id=?",(args.routine,)).fetchone()[0]
                con.execute("INSERT INTO routine_exercises(routine_id,exercise_id,position,planned_sets,min_reps,max_reps,notes) VALUES(?,?,?,?,?,?,?)",(args.routine,eid,pos,args.sets,args.min_reps,args.max_reps,args.notes)); con.commit(); return dict(con.execute("SELECT * FROM exercises WHERE id=?",(eid,)).fetchone())
        if args.action=="update":
            with connect() as con:
                row=con.execute("""SELECT e.*,re.planned_sets,re.min_reps,re.max_reps,re.notes routine_notes
                    FROM routine_exercises re JOIN exercises e ON e.id=re.exercise_id
                    WHERE re.routine_id=? AND re.exercise_id=?""",(args.routine,args.exercise)).fetchone()
                if not row: raise ValueError("exercise is not assigned to routine")
                if args.sets is not None and args.sets < 1: raise ValueError("sets must be positive")
                low=args.min_reps if args.min_reps is not None else row["min_reps"]
                high=args.max_reps if args.max_reps is not None else row["max_reps"]
                if low < 1 or high < low: raise ValueError("rep target must satisfy 1 <= min-reps <= max-reps")
                unilateral=row["unilateral"] if args.unilateral is None else int(args.unilateral)
                con.execute("UPDATE exercises SET name=?,notes=?,unilateral=? WHERE id=?",(
                    args.name if args.name is not None else row["name"],
                    args.exercise_notes if args.exercise_notes is not None else row["notes"],unilateral,args.exercise))
                con.execute("UPDATE routine_exercises SET planned_sets=?,min_reps=?,max_reps=?,notes=? WHERE routine_id=? AND exercise_id=?",(
                    args.sets if args.sets is not None else row["planned_sets"],low,high,
                    args.notes if args.notes is not None else row["routine_notes"],args.routine,args.exercise))
                con.commit()
                return dict(con.execute("""SELECT e.id,e.name,e.notes exercise_notes,e.unilateral,re.position,re.planned_sets,re.min_reps,re.max_reps,re.notes
                    FROM routine_exercises re JOIN exercises e ON e.id=re.exercise_id WHERE re.routine_id=? AND re.exercise_id=?""",(args.routine,args.exercise)).fetchone())
        if args.action=="remove":
            with connect() as con:
                cur=con.execute("DELETE FROM routine_exercises WHERE routine_id=? AND exercise_id=?",(args.routine,args.exercise))
                if not cur.rowcount: raise ValueError("exercise is not assigned to routine")
                con.commit(); return {"ok":True,"routine_id":args.routine,"exercise_id":args.exercise,"history_preserved":True}
        with connect() as con: return rows(con.execute("SELECT * FROM exercises WHERE active=1 ORDER BY name"))
    if args.command=="equipment":
        with connect() as con:
            if args.action=="add":
                if not con.execute("SELECT 1 FROM exercises WHERE id=? AND active=1",(args.exercise,)).fetchone(): raise ValueError("active exercise not found")
                cur=con.execute("INSERT INTO equipment_aliases(exercise_id,alias,notes,created_at) VALUES(?,?,?,?)",(args.exercise,args.alias,args.notes,now())); con.commit()
                return dict(con.execute("SELECT * FROM equipment_aliases WHERE id=?",(cur.lastrowid,)).fetchone())
            if args.action=="remove":
                if con.execute("SELECT 1 FROM workout_sets WHERE equipment_alias_id=?",(args.id,)).fetchone(): raise ValueError("equipment alias is used by workout history and cannot be removed")
                cur=con.execute("DELETE FROM equipment_aliases WHERE id=?",(args.id,))
                if not cur.rowcount: raise ValueError("equipment alias not found")
                con.commit(); return {"ok":True,"id":args.id}
            return rows(con.execute("""SELECT a.id,a.alias,a.notes,a.exercise_id,e.name exercise_name
                FROM equipment_aliases a JOIN exercises e ON e.id=a.exercise_id ORDER BY a.alias"""))
    if args.command=="plan": return plan()
    if args.command=="today": return today_data()
    if args.command=="session":
        with connect() as con:
            if args.action=="start":
                existing=con.execute("SELECT * FROM sessions WHERE completed_at IS NULL ORDER BY id LIMIT 1").fetchone()
                if existing: raise ValueError(f"active session {existing['id']} already exists; finish or continue it")
                rid=args.routine
                if rid is None:
                    row=con.execute("""SELECT d.routine_id FROM routine_days d JOIN routines r ON r.id=d.routine_id
                        WHERE d.weekday=? AND r.active=1 ORDER BY d.id LIMIT 1""",(date.today().isoweekday(),)).fetchone()
                    if not row: raise ValueError("no routine scheduled today; provide --routine")
                    rid=row[0]
                if not con.execute("SELECT 1 FROM routines WHERE id=? AND active=1",(rid,)).fetchone(): raise ValueError("active routine not found")
                session_date=args.date or date.today().isoformat()
                try: parsed_date=date.fromisoformat(session_date)
                except ValueError as exc: raise ValueError("date must use ISO format YYYY-MM-DD") from exc
                if parsed_date.isoformat()!=session_date: raise ValueError("date must use ISO format YYYY-MM-DD")
                cur=con.execute("INSERT INTO sessions(routine_id,session_date,started_at,notes) VALUES(?,?,?,?)",(rid,session_date,now(),args.notes)); con.commit(); return dict(con.execute("SELECT * FROM sessions WHERE id=?",(cur.lastrowid,)).fetchone())
            stamp=now(); cur=con.execute("UPDATE sessions SET completed_at=?,notes=CASE WHEN ?='' THEN notes ELSE ? END WHERE id=? AND completed_at IS NULL",(stamp,args.notes,args.notes,args.id));
            if not cur.rowcount: raise ValueError("active session not found")
            con.commit(); return dict(con.execute("SELECT * FROM sessions WHERE id=?",(args.id,)).fetchone())
    if args.command=="set":
        with connect() as con:
            if args.action=="log":
                session=con.execute("SELECT * FROM sessions WHERE id=? AND completed_at IS NULL",(args.session,)).fetchone()
                if not session: raise ValueError("active session not found")
                if not con.execute("SELECT 1 FROM routine_exercises WHERE routine_id=? AND exercise_id=?",(session["routine_id"],args.exercise)).fetchone():
                    raise ValueError("exercise does not belong to the session routine")
                if args.equipment is not None and not con.execute("SELECT 1 FROM equipment_aliases WHERE id=? AND exercise_id=?",(args.equipment,args.exercise)).fetchone():
                    raise ValueError("equipment alias does not belong to the exercise")
                side=args.side or ""
                num=args.number or con.execute("SELECT COALESCE(MAX(set_number),0)+1 FROM workout_sets WHERE session_id=? AND exercise_id=? AND side=?",(args.session,args.exercise,side)).fetchone()[0]
                if not math.isfinite(args.weight) or (args.rpe is not None and not math.isfinite(args.rpe)): raise ValueError("weight and RPE must be finite numbers")
                weight_kg=args.weight if args.unit=="kg" else args.weight*0.45359237
                cur=con.execute("INSERT INTO workout_sets(session_id,exercise_id,equipment_alias_id,set_number,side,weight_kg,reps,rpe,notes,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(args.session,args.exercise,args.equipment,num,side,weight_kg,args.reps,args.rpe,args.notes,now())); con.commit(); return dict(con.execute("SELECT * FROM workout_sets WHERE id=?",(cur.lastrowid,)).fetchone())
            fields=[]; values=[]
            for col in ("weight_kg","reps","rpe","notes"):
                val=getattr(args,col)
                if col in {"weight_kg","rpe"} and val is not None and not math.isfinite(val): raise ValueError(f"{col} must be a finite number")
                if val is not None: fields.append(f"{col}=?"); values.append(val)
            if not fields: raise ValueError("provide a value to correct")
            values += [now(),args.id]; cur=con.execute(f"UPDATE workout_sets SET {','.join(fields)},corrected_at=? WHERE id=?",values)
            if not cur.rowcount: raise ValueError("set not found")
            con.commit(); return dict(con.execute("SELECT * FROM workout_sets WHERE id=?",(args.id,)).fetchone())
    if args.command=="export":
        parent=data_dir()/"exports"; private_directory(parent)
        target=parent/f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}"; private_directory(target,require_new=True)
        with connect() as con:
            con.execute("BEGIN")
            payload={t:rows(con.execute(f"SELECT * FROM {t}")) for t in ("user_profile","routines","routine_days","exercises","equipment_aliases","routine_exercises","sessions","workout_sets")}
            jp=target/"gympilot.json"
            with open_private_text(jp) as f: json.dump(payload,f,ensure_ascii=False,indent=2,allow_nan=False)
            cp=target/"sets.csv"; out=con.execute("SELECT s.session_date,r.name routine,e.name exercise,a.alias equipment,w.set_number,w.side,w.weight_kg,w.reps,w.rpe,w.notes FROM workout_sets w JOIN sessions s ON s.id=w.session_id JOIN routines r ON r.id=s.routine_id JOIN exercises e ON e.id=w.exercise_id LEFT JOIN equipment_aliases a ON a.id=w.equipment_alias_id ORDER BY s.id,w.id");
            with open_private_text(cp,newline="") as f: writer=csv.writer(f); writer.writerow([d[0] for d in out.description]); writer.writerows(out)
        return {"json":str(jp),"csv":str(cp)}
    if args.command=="backup":
        parent=data_dir()/"backups"; private_directory(parent)
        target=parent/f"gympilot-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}.db"
        descriptor=prepare_private_file(target)
        try:
            if os.name != "nt":
                with connect() as source, sqlite3.connect(f"/dev/fd/{descriptor}") as destination:
                    destination.execute("PRAGMA journal_mode=OFF"); destination.execute("PRAGMA locking_mode=EXCLUSIVE")
                    source.backup(destination)
                os.fsync(descriptor)
                created=os.fstat(descriptor)
                with sqlite3.connect(f"file:/dev/fd/{descriptor}?mode=ro&immutable=1",uri=True) as check:
                    if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise ValueError("backup integrity check failed")
                current=os.stat(target,follow_symlinks=False)
                if (created.st_dev,created.st_ino)!=(current.st_dev,current.st_ino): raise ValueError("backup path changed during verification")
            else:
                os.close(descriptor); descriptor=-1
                with connect() as source, sqlite3.connect(target) as destination: source.backup(destination)
        finally:
            if descriptor >= 0: os.close(descriptor)
        return {"path":str(target)}
    if args.command=="security":
        if args.action=="enable":
            p1=getpass.getpass("New GymPilot password: "); p2=getpass.getpass("Repeat password: ")
            if len(p1)<10 or p1!=p2: raise ValueError("passwords must match and contain at least 10 characters")
            with connect() as con: con.execute("INSERT INTO auth_config VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash,updated_at=excluded.updated_at",(hash_password(p1),now())); con.execute("DELETE FROM web_sessions"); con.commit()
        else:
            with connect() as con: con.execute("DELETE FROM auth_config"); con.execute("DELETE FROM web_sessions"); con.commit()
        return {"auth_enabled":auth_enabled()}


def parser():
    p=GymArgumentParser(description="GymPilot local workout tracker"); p.add_argument("--json",action="store_true"); sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("init"); sub.add_parser("status"); sub.add_parser("plan"); sub.add_parser("today")
    o=sub.add_parser("onboarding"); osub=o.add_subparsers(dest="action",required=True); osub.add_parser("status"); s=osub.add_parser("set"); s.add_argument("field"); s.add_argument("value")
    r=sub.add_parser("routine"); rs=r.add_subparsers(dest="action",required=True); rs.add_parser("list")
    a=rs.add_parser("add"); a.add_argument("name"); a.add_argument("--weekday",type=safe_int,action="append",required=True,choices=range(1,8)); a.add_argument("--notes",default="")
    a=rs.add_parser("update"); a.add_argument("id",type=safe_int); a.add_argument("--name"); a.add_argument("--weekday",type=safe_int,action="append",choices=range(1,8)); a.add_argument("--notes")
    a=rs.add_parser("deactivate"); a.add_argument("id",type=safe_int)
    e=sub.add_parser("exercise"); es=e.add_subparsers(dest="action",required=True); es.add_parser("list")
    a=es.add_parser("add"); a.add_argument("routine",type=safe_int); a.add_argument("name"); a.add_argument("--sets",type=safe_int,required=True); a.add_argument("--min-reps",type=safe_int,required=True); a.add_argument("--max-reps",type=safe_int,required=True); a.add_argument("--unilateral",action="store_true"); a.add_argument("--notes",default="")
    a=es.add_parser("update"); a.add_argument("routine",type=safe_int); a.add_argument("exercise",type=safe_int); a.add_argument("--name"); a.add_argument("--sets",type=safe_int); a.add_argument("--min-reps",type=safe_int); a.add_argument("--max-reps",type=safe_int); a.add_argument("--notes",dest="exercise_notes"); a.add_argument("--routine-notes",dest="notes"); side=a.add_mutually_exclusive_group(); side.add_argument("--unilateral",dest="unilateral",action="store_true"); side.add_argument("--bilateral",dest="unilateral",action="store_false"); a.set_defaults(unilateral=None)
    a=es.add_parser("remove"); a.add_argument("routine",type=safe_int); a.add_argument("exercise",type=safe_int)
    q=sub.add_parser("equipment"); qs=q.add_subparsers(dest="action",required=True); qs.add_parser("list"); a=qs.add_parser("add"); a.add_argument("exercise",type=safe_int); a.add_argument("alias"); a.add_argument("--notes",default=""); a=qs.add_parser("remove"); a.add_argument("id",type=safe_int)
    s=sub.add_parser("session"); ss=s.add_subparsers(dest="action",required=True); a=ss.add_parser("start"); a.add_argument("--routine",type=safe_int); a.add_argument("--date"); a.add_argument("--notes",default=""); a=ss.add_parser("finish"); a.add_argument("id",type=safe_int); a.add_argument("--notes",default="")
    s=sub.add_parser("set"); ss=s.add_subparsers(dest="action",required=True); a=ss.add_parser("log"); a.add_argument("session",type=safe_int); a.add_argument("exercise",type=safe_int); a.add_argument("--weight",type=float,required=True); a.add_argument("--unit",choices=("kg","lb"),default="kg"); a.add_argument("--reps",type=safe_int,required=True); a.add_argument("--number",type=safe_int); a.add_argument("--side",default=""); a.add_argument("--equipment",type=safe_int); a.add_argument("--rpe",type=float); a.add_argument("--notes",default=""); a=ss.add_parser("correct"); a.add_argument("id",type=safe_int); a.add_argument("--weight",dest="weight_kg",type=float); a.add_argument("--reps",type=safe_int); a.add_argument("--rpe",type=float); a.add_argument("--notes")
    for name in ("export","backup"): sub.add_parser(name)
    sec=sub.add_parser("security"); secs=sec.add_subparsers(dest="action",required=True); secs.add_parser("enable"); secs.add_parser("disable")
    srv=sub.add_parser("server"); srv.add_argument("--host",default="127.0.0.1"); srv.add_argument("--port",type=safe_int,default=8765)
    return p


def main():
    args=parser().parse_args()
    try:
        validate_arguments(args)
        if args.command=="server":
            ensure(); server=make_server(args.host,args.port); print(f"GymPilot: http://{args.host}:{server.server_port}",flush=True); server.serve_forever(); return
        result=command(args); print(json.dumps(result,ensure_ascii=False,allow_nan=False) if args.json else human(result))
    except (ValueError,sqlite3.Error,OSError,OverflowError) as exc:
        if args.json: print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False))
        else: print(f"Error: {exc}",file=sys.stderr)
        raise SystemExit(2)


def human(value):
    if isinstance(value,list): return "\n".join(f"- {v.get('name',v)}" for v in value) or "No entries."
    return "\n".join(f"{k}: {v}" for k,v in value.items())

if __name__=="__main__": main()
