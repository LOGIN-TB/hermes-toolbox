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

    def test_catalog_kind_language_origin_commit_author_and_membership_are_pinned(self) -> None:
        mutations = {
            "kind": lambda d: d["skills"][1].__setitem__("kind", "application"),
            "language": lambda d: d["skills"][1].__setitem__("language", "de"),
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
