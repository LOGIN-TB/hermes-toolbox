#!/usr/bin/env python3
"""Regression tests for the fail-closed public-skill validator."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
class ValidateSkillsFailClosedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="toolbox-validator-")
        self.root = Path(self.temp.name) / "repo"
        shutil.copytree(
            SOURCE_ROOT,
            self.root,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"),
        )
        self.git("init", "-q")
        self.git("config", "user.email", "validator@example.invalid")
        self.git("config", "user.name", "Validator Test")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def validate(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "tests/validate_skills.py"], cwd=self.root,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

    def assert_rejected(self, label: str) -> None:
        result = self.validate()
        self.assertNotEqual(result.returncode, 0, f"{label} was accepted:\n{result.stdout}")

    def mutate_catalog(self, mutation) -> None:
        path = self.root / "skills/catalog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mutation(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.git("add", str(path.relative_to(self.root)))

    def test_clean_fixture_passes(self) -> None:
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_german_curation_contract_is_complete_and_pinned(self) -> None:
        curation = self.root / "skills/curation.json"
        self.assertTrue(curation.is_file(), "skills/curation.json fehlt")
        data = json.loads(curation.read_text(encoding="utf-8"))
        target = {
            "ai-seo", "seo-audit", "product-marketing", "social", "cold-email",
            "competitors", "competitor-profiling", "content-strategy", "copywriting",
            "customer-research", "image", "lead-magnets", "marketing-ideas",
        }
        self.assertEqual({entry["name"] for entry in data["skills"]}, target)
        catalog = json.loads((self.root / "skills/catalog.json").read_text(encoding="utf-8"))
        by_name = {entry["name"]: entry for entry in catalog["skills"]}
        for entry in data["skills"]:
            name = entry["name"]
            self.assertEqual(entry["content_language"], "de")
            self.assertEqual(entry["default_market"], "DE")
            self.assertEqual(entry["upstream_commit"], by_name[name]["upstream_commit"])
            self.assertEqual(by_name[name]["language"], "de")
            skill = (self.root / f"skills/{name}/SKILL.md").read_text(encoding="utf-8")
            for heading in (
                "## Deutscher/DACH-Kontext", "## Ausgabeformat", "## Prüfliste",
                "## Herkunft und Abweichungen",
            ):
                self.assertIn(heading, skill)
            self.assertIn("-hermes.2", skill)

    def test_curation_commit_language_market_and_membership_are_fail_closed(self) -> None:
        mutations = {
            "commit": lambda d: d["skills"][0].__setitem__("upstream_commit", "0" * 40),
            "language": lambda d: d["skills"][0].__setitem__("content_language", "en"),
            "market": lambda d: d["skills"][0].__setitem__("default_market", "US"),
            "missing": lambda d: d["skills"].pop(),
            "unknown-field": lambda d: d["skills"][0].__setitem__("extra", "x"),
            "bad-date": lambda d: d["skills"][0].__setitem__("last_reviewed", "not-a-date"),
            "future-date": lambda d: d["skills"][0].__setitem__("last_reviewed", "2999-01-01"),
            "bad-version": lambda d: d["skills"][0].__setitem__("local_version", "v2-hermes.2"),
            "short-summary": lambda d: d["skills"][0].__setitem__("change_summary", "x"),
            "meaningless-summary": lambda d: d["skills"][0].__setitem__("change_summary", "x" * 40),
            "duplicate-summary": lambda d: d["skills"][1].__setitem__(
                "change_summary", d["skills"][0]["change_summary"]
            ),
            "leading-zero-version": lambda d: d["skills"][0].__setitem__("local_version", "02.2.0-hermes.2"),
            "bad-categories": lambda d: d["skills"][0].__setitem__("change_categories", ["x"]),
            "duplicate-domain": lambda d: d["skills"][0].__setitem__("legal_review_domains", ["DSGVO", "DSGVO"]),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                self.git("reset", "--hard", "-q", "HEAD")
                path = self.root / "skills/curation.json"
                data = json.loads(path.read_text(encoding="utf-8"))
                mutation(data)
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                self.git("add", str(path.relative_to(self.root)))
                self.assert_rejected(label)

    def test_german_skill_rejects_legal_assurance_and_english_standard_heading(self) -> None:
        skill = self.root / "skills/ai-seo/SKILL.md"
        original = skill.read_text(encoding="utf-8")
        mutations = {
            "legal-assurance": original + "\nDiese Umsetzung ist DSGVO-konform.\n",
            "english-heading": original + "\n## Output Format\n",
            "unnatural-description": original.replace(
                "description: \"Sichtbarkeit", "description: \"Nutzen, wenn Sichtbarkeit"
            ),
            "spaced-unnatural-description": original.replace(
                "description: \"Sichtbarkeit", "description: \"Nutzen , wenn Sichtbarkeit"
            ),
        }
        for label, content in mutations.items():
            with self.subTest(label=label):
                self.git("reset", "--hard", "-q", "HEAD")
                skill.write_text(content, encoding="utf-8")
                self.git("add", str(skill.relative_to(self.root)))
                self.assert_rejected(label)

    def test_frontmatter_and_documented_provenance_are_pinned(self) -> None:
        skill = self.root / "skills/ai-seo/SKILL.md"
        original = skill.read_text(encoding="utf-8")
        mutations = {
            "missing-frontmatter-commit": original.replace(
                "    upstream_commit: 7868cb9251fad80a73d26e488a5ad5f6c4a9f335\n", ""
            ),
            "wrong-frontmatter-homepage": original.replace(
                "https://github.com/coreyhaines31/marketingskills/tree/7868cb9251fad80a73d26e488a5ad5f6c4a9f335/skills/ai-seo",
                "https://example.invalid/ai-seo",
            ),
        }
        for label, content in mutations.items():
            with self.subTest(label=label):
                self.git("reset", "--hard", "-q", "HEAD")
                skill.write_text(content, encoding="utf-8")
                self.git("add", str(skill.relative_to(self.root)))
                self.assert_rejected(label)

        self.git("reset", "--hard", "-q", "HEAD")
        changes = self.root / "docs/UPSTREAM-AENDERUNGEN.md"
        changes.write_text(
            changes.read_text(encoding="utf-8").replace(
                "7868cb9251fad80a73d26e488a5ad5f6c4a9f335", "0" * 40, 1
            ),
            encoding="utf-8",
        )
        self.git("add", str(changes.relative_to(self.root)))
        self.assert_rejected("documented upstream commit")

    def test_duplicate_json_and_yaml_keys_are_rejected(self) -> None:
        catalog = self.root / "skills/catalog.json"
        catalog.write_text(
            catalog.read_text(encoding="utf-8").replace(
                '"language": "de",', '"language": "en",\n      "language": "de",', 1
            ),
            encoding="utf-8",
        )
        self.git("add", str(catalog.relative_to(self.root)))
        self.assert_rejected("duplicate JSON key")

        self.git("reset", "--hard", "-q", "HEAD")
        skill = self.root / "skills/ai-seo/SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "    upstream_commit: 7868cb9251fad80a73d26e488a5ad5f6c4a9f335",
                "    upstream_commit: " + "0" * 40 + "\n"
                "    upstream_commit: 7868cb9251fad80a73d26e488a5ad5f6c4a9f335",
                1,
            ),
            encoding="utf-8",
        )
        self.git("add", str(skill.relative_to(self.root)))
        self.assert_rejected("duplicate YAML key")

    def test_catalog_kind_language_origin_commit_author_and_membership_are_pinned(self) -> None:
        mutations = {
            "kind": lambda d: d["skills"][1].__setitem__("kind", "application"),
            "language": lambda d: d["skills"][1].__setitem__("language", "en"),
            "origin": lambda d: d["skills"][1].__setitem__("origin", "other/repo"),
            "commit": lambda d: d["skills"][1].__setitem__("upstream_commit", "0" * 40),
            "author": lambda d: d["skills"][1].__setitem__("author", "Mallory"),
            "extra": lambda d: d["skills"].append({
                "name": "extra", "kind": "application", "language": "en",
                "origin": "example/repo", "author": "Example",
            }),
        }
        for label, mutation in mutations.items():
            with self.subTest(label=label):
                self.git("reset", "--hard", "-q", "HEAD")
                self.mutate_catalog(mutation)
                self.assert_rejected(label)

    def test_unknown_and_wrongly_typed_fields_are_rejected(self) -> None:
        for label, mutation in {
            "unknown": lambda d: d["skills"][1].__setitem__("extra", "x"),
            "wrong-type": lambda d: d["skills"][1].__setitem__("language", []),
            "missing": lambda d: d["skills"][1].pop("origin"),
        }.items():
            with self.subTest(label=label):
                self.git("reset", "--hard", "-q", "HEAD")
                self.mutate_catalog(mutation)
                self.assert_rejected(label)

    def test_repository_privacy_and_secret_patterns_are_rejected(self) -> None:
        probes = {
            "unix-home": "/Users/" + "alice/private.txt",
            "windows-home": "C:\\Users\\" + "alice\\private.txt",
            "file-url": "file" + ":///Users/alice/private.txt",
            "local-host": "https://alice-mac" + ".local:8443/private",
            "private-ip-url": "https://192.168." + "42.9:8443/private",
            "loopback-url": "http://127.0." + "0.1:8765/private",
            "private-key": "-----BEGIN " + "PRIVATE KEY-----\nAAAA",
            "github-token": "ghp_" + "A" * 30,
            "aws-key": "AKIA" + "A" * 16,
            "bearer": "Bearer " + "A" * 24,
            "credential-url": "https://alice:" + "secret@example.com/path",
            "literal-secret": "api_" + "key = \"example-secret-value\"",
        }
        for label, content in probes.items():
            with self.subTest(label=label):
                self.git("reset", "--hard", "-q", "HEAD")
                path = self.root / "PROBE.txt"
                path.write_text(content, encoding="utf-8")
                self.git("add", "PROBE.txt")
                self.assert_rejected(label)

    def test_nul_unexpected_mode_and_invalid_yaml_are_rejected(self) -> None:
        probe = self.root / "PROBE.bin"
        probe.write_bytes(b"public\x00private")
        self.git("add", "PROBE.bin")
        self.assert_rejected("NUL outside approved assets")

        self.git("reset", "--hard", "-q", "HEAD")
        skill = self.root / "skills/ai-seo/SKILL.md"
        skill.chmod(0o755)
        self.git("add", str(skill.relative_to(self.root)))
        self.assert_rejected("unexpected executable Git mode")

        self.git("reset", "--hard", "-q", "HEAD")
        skill = self.root / "skills/ai-seo/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(text.replace("name: ai-seo", "name: [ai-seo"), encoding="utf-8")
        self.git("add", str(skill.relative_to(self.root)))
        self.assert_rejected("syntactically invalid YAML frontmatter")

    def test_symlink_unexpected_file_and_unstaged_divergence_are_rejected(self) -> None:
        link = self.root / "bad-link"
        link.symlink_to("README.md")
        self.git("add", "bad-link")
        self.assert_rejected("repository symlink")

        self.git("reset", "--hard", "-q", "HEAD")
        extra = self.root / "skills/ai-seo/references/extra.txt"
        extra.parent.mkdir()
        extra.write_text("unreferenced", encoding="utf-8")
        self.git("add", str(extra.relative_to(self.root)))
        self.assert_rejected("unexpected document-skill file")

        self.git("reset", "--hard", "-q", "HEAD")
        readme = self.root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nunstaged\n", encoding="utf-8")
        self.assert_rejected("unstaged divergence")


if __name__ == "__main__":
    unittest.main()
