"""Deterministic, offline training-plan generator for GymPilot.

The generator provides general exercise templates. It does not diagnose,
treat, rehabilitate, or claim that an exercise is medically suitable.
"""
from __future__ import annotations

import re
import unicodedata

GENERATOR_VERSION = "curated-local-v2"
GOALS = ("muscle_gain", "strength", "general_fitness", "weight_loss")
EXPERIENCE_LEVELS = ("beginner", "intermediate", "advanced")
EQUIPMENT = (
    "barbell", "bench", "cable", "dumbbell", "kettlebell",
    "machines", "rack", "resistance_band",
)
FOCUS_AREAS = (
    "back", "biceps", "chest", "core", "glutes", "hamstrings",
    "quads", "shoulders", "triceps",
)
RESTRICTIONS = ("no_overhead",)
PATTERNS = (
    "core_brace", "elbow_extension", "elbow_flexion", "hip_hinge",
    "horizontal_pull", "horizontal_push", "knee_dominant", "single_leg",
    "vertical_pull", "vertical_push",
)


def _exercise(identifier, name, pattern, areas, equipment_options=((),), *,
              accessory=False, flags=(), aliases=()):
    return {
        "id": identifier,
        "name": name,
        "pattern": pattern,
        "areas": tuple(areas),
        "equipment_options": tuple(tuple(option) for option in equipment_options),
        "accessory": accessory,
        "flags": tuple(flags),
        "aliases": tuple(aliases),
    }


EXERCISES = (
    _exercise("bw_squat", "Kniebeuge mit Körpergewicht", "knee_dominant", ("quads", "glutes"), aliases=("kniebeuge",)),
    _exercise("reverse_lunge", "Rückwärts-Ausfallschritt", "single_leg", ("quads", "glutes")),
    _exercise("glute_bridge", "Glute Bridge", "hip_hinge", ("glutes", "hamstrings")),
    _exercise("push_up", "Push-up", "horizontal_push", ("chest", "triceps"), aliases=("liegestütz", "liegestuetze")),
    _exercise("prone_y_raise", "Bauchlage-Y-Raise", "horizontal_pull", ("back", "shoulders"), accessory=True),
    _exercise("pike_push_up", "Pike Push-up", "vertical_push", ("shoulders", "triceps"), flags=("overhead",)),
    _exercise("dead_bug", "Dead Bug", "core_brace", ("core",), accessory=True),
    _exercise("bird_dog", "Bird Dog", "core_brace", ("core", "back"), accessory=True),
    _exercise("band_row", "Rudern mit Widerstandsband", "horizontal_pull", ("back", "biceps"), (("resistance_band",),)),
    _exercise("band_pulldown", "Latzug mit Widerstandsband", "vertical_pull", ("back", "biceps"), (("resistance_band",),)),
    _exercise("band_press", "Brustdrücken mit Widerstandsband", "horizontal_push", ("chest", "triceps"), (("resistance_band",),)),
    _exercise("goblet_squat", "Goblet Squat", "knee_dominant", ("quads", "glutes"), (("dumbbell",), ("kettlebell",))),
    _exercise("db_split_squat", "Kurzhantel-Split-Squat", "single_leg", ("quads", "glutes"), (("dumbbell",),)),
    _exercise("db_rdl", "Kurzhantel-RDL", "hip_hinge", ("hamstrings", "glutes"), (("dumbbell",),)),
    _exercise("db_row", "Einarmiges Kurzhantelrudern", "horizontal_pull", ("back", "biceps"), (("dumbbell",),)),
    _exercise("db_floor_press", "Kurzhantel-Floor-Press", "horizontal_push", ("chest", "triceps"), (("dumbbell",),)),
    _exercise("db_bench_press", "Kurzhantel-Bankdrücken", "horizontal_push", ("chest", "triceps"), (("dumbbell", "bench"),)),
    _exercise("db_shoulder_press", "Kurzhantel-Schulterdrücken", "vertical_push", ("shoulders", "triceps"), (("dumbbell",),), flags=("overhead",)),
    _exercise("db_curl", "Kurzhantelcurl", "elbow_flexion", ("biceps",), (("dumbbell",),), accessory=True),
    _exercise("db_triceps", "Kurzhantel-Trizepsstrecken", "elbow_extension", ("triceps",), (("dumbbell",),), accessory=True, flags=("overhead",)),
    _exercise("bb_squat", "Langhantel-Kniebeuge", "knee_dominant", ("quads", "glutes"), (("barbell", "rack"),)),
    _exercise("bb_bench_press", "Langhantel-Bankdrücken", "horizontal_push", ("chest", "triceps"), (("barbell", "bench"),), aliases=("bankdrücken", "bankdruecken")),
    _exercise("bb_rdl", "Rumänisches Kreuzheben", "hip_hinge", ("hamstrings", "glutes"), (("barbell",),)),
    _exercise("bb_row", "Langhantelrudern", "horizontal_pull", ("back", "biceps"), (("barbell",),)),
    _exercise("leg_press", "Beinpresse", "knee_dominant", ("quads", "glutes"), (("machines",),)),
    _exercise("leg_curl", "Beinbeuger Maschine", "hip_hinge", ("hamstrings",), (("machines",),), accessory=True),
    _exercise("chest_press", "Brustpresse Maschine", "horizontal_push", ("chest", "triceps"), (("machines",),)),
    _exercise("machine_row", "Rudermaschine", "horizontal_pull", ("back", "biceps"), (("machines",),)),
    _exercise("lat_pulldown", "Latzug", "vertical_pull", ("back", "biceps"), (("cable",), ("machines",))),
    _exercise("machine_shoulder_press", "Schulterpresse Maschine", "vertical_push", ("shoulders", "triceps"), (("machines",),), flags=("overhead",)),
    _exercise("cable_row", "Kabelrudern", "horizontal_pull", ("back", "biceps"), (("cable",),)),
    _exercise("cable_curl", "Kabelcurl", "elbow_flexion", ("biceps",), (("cable",),), accessory=True),
    _exercise("triceps_pressdown", "Trizepsdrücken am Kabel", "elbow_extension", ("triceps",), (("cable",),), accessory=True),
)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def _templates(count: int):
    full = (
        ("Ganzkörper", ("knee_dominant", "horizontal_push", "horizontal_pull", "core_brace"), ("hip_hinge", "vertical_pull", "vertical_push")),
        ("Ganzkörper A", ("knee_dominant", "horizontal_push", "horizontal_pull", "core_brace"), ("hip_hinge", "vertical_pull")),
        ("Ganzkörper B", ("hip_hinge", "horizontal_push", "horizontal_pull", "core_brace"), ("knee_dominant", "single_leg", "vertical_push")),
        ("Ganzkörper C", ("knee_dominant", "hip_hinge", "horizontal_push", "horizontal_pull"), ("vertical_pull", "core_brace")),
    )
    if count <= 3:
        if count == 1:
            return (full[0],)
        return full[1:count + 1]
    if count == 4:
        return (
            ("Oberkörper A", ("horizontal_push", "horizontal_pull"), ("vertical_push", "vertical_pull", "elbow_flexion", "elbow_extension")),
            ("Unterkörper A", ("knee_dominant", "hip_hinge", "core_brace"), ("single_leg",)),
            ("Oberkörper B", ("horizontal_push", "horizontal_pull"), ("vertical_pull", "vertical_push", "elbow_flexion", "elbow_extension")),
            ("Unterkörper B", ("knee_dominant", "hip_hinge", "single_leg"), ("core_brace",)),
        )
    if count == 5:
        return (
            ("Oberkörper", ("horizontal_push", "horizontal_pull"), ("vertical_push", "vertical_pull")),
            ("Unterkörper", ("knee_dominant", "hip_hinge", "core_brace"), ("single_leg",)),
            ("Push", ("horizontal_push", "vertical_push"), ("elbow_extension",)),
            ("Pull", ("horizontal_pull",), ("vertical_pull", "elbow_flexion", "core_brace")),
            ("Beine", ("knee_dominant", "hip_hinge"), ("single_leg", "core_brace")),
        )
    return (
        ("Push A", ("horizontal_push", "vertical_push"), ("elbow_extension",)),
        ("Pull A", ("horizontal_pull",), ("vertical_pull", "elbow_flexion", "core_brace")),
        ("Beine A", ("knee_dominant", "hip_hinge"), ("single_leg", "core_brace")),
        ("Push B", ("horizontal_push", "vertical_push"), ("elbow_extension",)),
        ("Pull B", ("horizontal_pull",), ("vertical_pull", "elbow_flexion", "core_brace")),
        ("Beine B", ("knee_dominant", "hip_hinge"), ("single_leg", "core_brace")),
    )


MAIN_TARGETS = {
    "muscle_gain": {"beginner": (2, 8, 12), "intermediate": (3, 8, 12), "advanced": (4, 6, 10)},
    "strength": {"beginner": (3, 5, 6), "intermediate": (4, 4, 6), "advanced": (5, 3, 5)},
    "general_fitness": {"beginner": (2, 8, 12), "intermediate": (3, 8, 12), "advanced": (3, 8, 12)},
    "weight_loss": {"beginner": (2, 10, 15), "intermediate": (3, 10, 15), "advanced": (3, 10, 15)},
}
ACCESSORY_TARGETS = {
    "muscle_gain": {"beginner": (2, 10, 12), "intermediate": (3, 8, 12), "advanced": (3, 8, 12)},
    "strength": {"beginner": (2, 8, 12), "intermediate": (3, 8, 12), "advanced": (3, 8, 12)},
    "general_fitness": {"beginner": (2, 10, 12), "intermediate": (3, 10, 12), "advanced": (3, 10, 12)},
    "weight_loss": {"beginner": (2, 12, 15), "intermediate": (3, 12, 15), "advanced": (3, 12, 15)},
}
REST_COST = {"strength": 1.5, "muscle_gain": 1.0, "general_fitness": 0.75, "weight_loss": 0.5}


def capabilities() -> dict:
    return {
        "generator_version": GENERATOR_VERSION,
        "goals": list(GOALS),
        "experience": list(EXPERIENCE_LEVELS),
        "equipment": list(EQUIPMENT),
        "focus_areas": list(FOCUS_AREAS),
        "restrictions": list(RESTRICTIONS),
        "training_days": {"min": 1, "max": 6},
        "duration_minutes": {"min": 20, "max": 180},
        "exercises": [
            {
                "id": exercise["id"],
                "name": exercise["name"],
                "aliases": list(exercise["aliases"]),
                "areas": list(exercise["areas"]),
                "pattern": exercise["pattern"],
                "equipment_options": [list(option) for option in exercise["equipment_options"]],
            }
            for exercise in EXERCISES
        ],
    }


def _validate_values(label, values, allowed):
    if any(type(value) is not str for value in values):
        raise ValueError(f"{label} values must be strings")
    unknown = sorted(set(values) - set(allowed))
    if unknown:
        raise ValueError(f"unsupported {label}: {unknown}; supported values: {list(allowed)}")
    return sorted(set(values))


def _available(exercise, equipment):
    return any(set(option) <= equipment for option in exercise["equipment_options"])


def _target(exercise, goal, experience):
    table = ACCESSORY_TARGETS if exercise["accessory"] else MAIN_TARGETS
    sets, low, high = table[goal][experience]
    return {"name": exercise["name"], "sets": sets, "min_reps": low, "max_reps": high}


def _exercise_minutes(exercise, target, goal):
    setup = 1.5 if "barbell" in {item for option in exercise["equipment_options"] for item in option} else 0.75
    return setup + target["sets"] * (0.4 + REST_COST[goal])


def generate_plan(*, goal, days, duration_minutes, experience, equipment,
                  focus=(), avoid=(), restrictions=()):
    if goal not in GOALS:
        raise ValueError(f"unsupported goal: {goal}; supported goals: {list(GOALS)}")
    if experience not in EXPERIENCE_LEVELS:
        raise ValueError(f"unsupported experience: {experience}; supported values: {list(EXPERIENCE_LEVELS)}")
    if type(duration_minutes) is not int or type(duration_minutes) is bool or not 20 <= duration_minutes <= 180:
        raise ValueError("duration_minutes must be an integer between 20 and 180")
    if type(days) not in (list, tuple) or any(type(day) is not int or type(day) is bool or not 1 <= day <= 7 for day in days):
        raise ValueError("days must contain ISO weekday integers 1-7")
    normalized_days = sorted(set(days))
    if len(normalized_days) != len(days):
        raise ValueError("training days must be unique")
    if not 1 <= len(normalized_days) <= 6:
        raise ValueError("generator supports 1-6 unique training days; use manual import for seven days")
    equipment = _validate_values("equipment", list(equipment), EQUIPMENT)
    focus = _validate_values("focus", list(focus), FOCUS_AREAS)
    restrictions = _validate_values("restrictions", list(restrictions), RESTRICTIONS)

    lookup = {}
    for exercise in EXERCISES:
        for value in (exercise["id"], exercise["name"], *exercise["aliases"]):
            lookup[_slug(value)] = exercise["id"]
    unknown_avoid = sorted(value for value in avoid if _slug(value) not in lookup)
    if unknown_avoid:
        raise ValueError(f"unknown avoided exercises: {unknown_avoid}")
    avoided_ids = {lookup[_slug(value)] for value in avoid}
    available_equipment = set(equipment)
    candidates = [
        exercise for exercise in EXERCISES
        if exercise["id"] not in avoided_ids
        and _available(exercise, available_equipment)
        and not ("no_overhead" in restrictions and "overhead" in exercise["flags"])
    ]

    routines = []
    selections = []
    occurrence = {pattern: 0 for pattern in PATTERNS}
    focus_hits = {area: 0 for area in focus}
    estimated_max = 0.0
    for day, (name, required, optional) in zip(normalized_days, _templates(len(normalized_days))):
        if "no_overhead" in restrictions:
            required = tuple("core_brace" if pattern == "vertical_push" else pattern for pattern in required)
            optional = tuple(pattern for pattern in optional if pattern != "vertical_push")
        chosen = []
        used_ids = set()

        def choose_pattern(pattern):
            options = [exercise for exercise in candidates if exercise["pattern"] == pattern and exercise["id"] not in used_ids]
            if not options:
                return None
            options.sort(
                key=lambda exercise: max(len(option) for option in exercise["equipment_options"]),
                reverse=True,
            )
            index = occurrence[pattern] % len(options)
            occurrence[pattern] += 1
            selected = options[index]
            used_ids.add(selected["id"])
            chosen.append(selected)
            return selected

        for pattern in required:
            if choose_pattern(pattern) is None:
                raise ValueError(f"available equipment cannot fill required movement pattern: {pattern}")

        current_minutes = 3.0 + sum(_exercise_minutes(item, _target(item, goal, experience), goal) for item in chosen)
        if current_minutes > duration_minutes:
            raise ValueError(f"minimum required plan needs {int(current_minutes + 0.999)} minutes; increase duration or use manual import")

        for pattern in optional:
            options_before = list(chosen)
            selected = choose_pattern(pattern)
            if selected is None:
                continue
            target = _target(selected, goal, experience)
            proposed = current_minutes + _exercise_minutes(selected, target, goal)
            if proposed > duration_minutes:
                chosen[:] = options_before
                used_ids.remove(selected["id"])
                continue
            current_minutes = proposed

        # Add one available focus exercise when it fits and the routine has none.
        for area in focus:
            if any(area in item["areas"] for item in chosen):
                focus_hits[area] += 1
                continue
            options = [item for item in candidates if area in item["areas"] and item["id"] not in used_ids]
            if not options:
                continue
            selected = options[0]
            target = _target(selected, goal, experience)
            proposed = current_minutes + _exercise_minutes(selected, target, goal)
            if proposed <= duration_minutes:
                chosen.append(selected)
                used_ids.add(selected["id"])
                current_minutes = proposed
                focus_hits[area] += 1

        targets = [_target(item, goal, experience) for item in chosen]
        routines.append({"name": name, "weekdays": [day], "exercises": targets})
        selections.append({
            "routine": name,
            "exercise_ids": [item["id"] for item in chosen],
            "patterns": [item["pattern"] for item in chosen],
        })
        estimated_max = max(estimated_max, current_minutes)

    unmet = [area for area, count in focus_hits.items() if count == 0]
    return {
        "routines": routines,
        "generation": {
            "generator_version": GENERATOR_VERSION,
            "goal": goal,
            "days": normalized_days,
            "duration_minutes": duration_minutes,
            "estimated_duration_minutes": int(estimated_max + 0.999),
            "experience": experience,
            "equipment": equipment,
            "preferred_body_areas": focus,
            "avoided_exercises": sorted(avoided_ids),
            "restrictions": restrictions,
            "unmet_preferences": unmet,
            "selections": selections,
            "notice": "Allgemeiner Trainingsvorschlag; keine medizinische Beurteilung.",
        },
    }
