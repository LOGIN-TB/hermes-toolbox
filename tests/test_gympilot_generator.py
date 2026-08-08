from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills" / "gym" / "scripts" / "gympilot_generator.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("gympilot_generator", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GymPilotGeneratorTest(unittest.TestCase):
    def test_bodyweight_beginner_gets_bounded_full_body_plan(self):
        generator = load_generator()
        plan = generator.generate_plan(
            goal="general_fitness",
            days=[3],
            duration_minutes=30,
            experience="beginner",
            equipment=[],
            focus=[],
            avoid=[],
            restrictions=[],
        )
        self.assertEqual([routine["name"] for routine in plan["routines"]], ["Ganzkörper"])
        self.assertLessEqual(plan["generation"]["estimated_duration_minutes"], 30)
        patterns = set(plan["generation"]["selections"][0]["patterns"])
        self.assertTrue({"knee_dominant", "horizontal_push", "horizontal_pull", "core_brace"} <= patterns)
        names = [exercise["name"] for exercise in plan["routines"][0]["exercises"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(names)

    def test_equivalent_inputs_produce_identical_canonical_plan(self):
        generator = load_generator()
        common = {
            "goal": "muscle_gain",
            "duration_minutes": 60,
            "experience": "intermediate",
            "focus": ["chest", "chest"],
            "restrictions": [],
        }
        first = generator.generate_plan(
            days=[4, 1], equipment=["bench", "dumbbell"], avoid=["Push-up"], **common
        )
        second = generator.generate_plan(
            days=[1, 4], equipment=["dumbbell", "bench", "bench"], avoid=["push-up"], **common
        )
        self.assertEqual(first, second)

    def test_horizontal_push_uses_deterministic_equipment_fallback(self):
        generator = load_generator()
        base = {
            "goal": "muscle_gain",
            "days": [2],
            "duration_minutes": 30,
            "experience": "intermediate",
            "focus": [],
            "avoid": [],
            "restrictions": [],
        }
        cases = (
            (["barbell", "bench", "rack"], "Langhantel-Bankdrücken"),
            (["dumbbell", "bench"], "Kurzhantel-Bankdrücken"),
            ([], "Push-up"),
        )
        for equipment, expected in cases:
            plan = generator.generate_plan(equipment=equipment, **base)
            names = [item["name"] for item in plan["routines"][0]["exercises"]]
            self.assertIn(expected, names)

    def test_library_and_split_invariants(self):
        generator = load_generator()
        self.assertGreaterEqual(len(generator.EXERCISES), 24)
        self.assertEqual(len({item["id"] for item in generator.EXERCISES}), len(generator.EXERCISES))
        self.assertEqual(len({item["name"] for item in generator.EXERCISES}), len(generator.EXERCISES))
        for item in generator.EXERCISES:
            self.assertIn(item["pattern"], generator.PATTERNS)
            self.assertTrue(set(item["areas"]) <= set(generator.FOCUS_AREAS))
            for option in item["equipment_options"]:
                self.assertTrue(set(option) <= set(generator.EQUIPMENT))
        expected_names = {
            1: ["Ganzkörper"],
            2: ["Ganzkörper A", "Ganzkörper B"],
            3: ["Ganzkörper A", "Ganzkörper B", "Ganzkörper C"],
            4: ["Oberkörper A", "Unterkörper A", "Oberkörper B", "Unterkörper B"],
            5: ["Oberkörper", "Unterkörper", "Push", "Pull", "Beine"],
            6: ["Push A", "Pull A", "Beine A", "Push B", "Pull B", "Beine B"],
        }
        full_equipment = list(generator.EQUIPMENT)
        for count, names in expected_names.items():
            plan = generator.generate_plan(
                goal="general_fitness", days=list(range(1, count + 1)), duration_minutes=90,
                experience="intermediate", equipment=full_equipment,
                focus=[], avoid=[], restrictions=[],
            )
            self.assertEqual([routine["name"] for routine in plan["routines"]], names)

    def test_capabilities_expose_curated_exercises_and_aliases(self):
        generator = load_generator()
        result = generator.capabilities()
        self.assertEqual(result["generator_version"], "curated-local-v2")
        self.assertEqual(len(result["exercises"]), len(generator.EXERCISES))
        push_up = next(item for item in result["exercises"] if item["id"] == "push_up")
        self.assertEqual(push_up["name"], "Push-up")
        self.assertIn("liegestütz", push_up["aliases"])

    def test_goal_prescriptions_and_invalid_preferences_are_explicit(self):
        generator = load_generator()
        plan = generator.generate_plan(
            goal="strength", days=[1, 2, 4, 5], duration_minutes=90,
            experience="advanced", equipment=list(generator.EQUIPMENT),
            focus=["chest"], avoid=[], restrictions=["no_overhead"],
        )
        self.assertEqual([routine["name"] for routine in plan["routines"]],
                         ["Oberkörper A", "Unterkörper A", "Oberkörper B", "Unterkörper B"])
        main_targets = [
            exercise for routine in plan["routines"] for exercise in routine["exercises"]
            if exercise["name"] not in {"Kurzhantelcurl", "Kabelcurl", "Trizepsdrücken am Kabel", "Dead Bug", "Bird Dog"}
        ]
        self.assertTrue(any((item["sets"], item["min_reps"], item["max_reps"]) == (5, 3, 5) for item in main_targets))
        for kwargs in (
            {"equipment": ["dumbells"]},
            {"focus": ["neck"]},
            {"restrictions": ["knee_safe"]},
            {"avoid": ["Unbekannte Übung"]},
        ):
            params: dict[str, object] = dict(
                goal="general_fitness", days=[1], duration_minutes=45,
                experience="beginner", equipment=[], focus=[], avoid=[], restrictions=[]
            )
            params.update(kwargs)
            with self.assertRaises(ValueError):
                generator.generate_plan(**params)

    def test_no_overhead_is_supported_for_every_automatic_day_count(self):
        generator = load_generator()
        overhead_names = {exercise["name"] for exercise in generator.EXERCISES if "overhead" in exercise["flags"]}
        for days in range(1, 7):
            plan = generator.generate_plan(
                goal="general_fitness",
                days=list(range(1, days + 1)),
                duration_minutes=90,
                experience="intermediate",
                equipment=list(generator.EQUIPMENT),
                focus=[],
                avoid=[],
                restrictions=["no_overhead"],
            )
            selected = {
                exercise["name"]
                for routine in plan["routines"]
                for exercise in routine["exercises"]
            }
            self.assertTrue(selected)
            self.assertFalse(selected & overhead_names, days)
        with self.assertRaises(ValueError):
            generator.generate_plan(goal="general_fitness", days=list(range(1, 8)),
                                    duration_minutes=90, experience="beginner",
                                    equipment=[], focus=[], avoid=[], restrictions=[])


if __name__ == "__main__":
    unittest.main()
