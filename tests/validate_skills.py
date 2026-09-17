#!/usr/bin/env python3
"""Fail-closed validation for the public Hermes Toolbox skill catalog."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from typing import NoReturn
from urllib.parse import quote
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
CATALOG = SKILLS / "catalog.json"
CURATION = SKILLS / "curation.json"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?)\n---(?:\n|\Z)", re.DOTALL)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
HERMES_SUPPORT_REF_RE = re.compile(
    r"(?:\]\(|`|(?:^|[\s\"']))((?:references|templates|scripts|assets|examples)/[^\s)`\"'<>]+)",
    re.MULTILINE,
)
PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s`'\"])(?:/(?:Users|home|root)/|[A-Za-z]:\\Users\\)[^\s`'\"]+"
)
FILE_URL_RE = re.compile("file" + r"://", re.I)
LOCAL_HOST_URL_RE = re.compile(r"https?://(?:[^/@\s]+@)?[^/\s]+\.local(?::\d+)?(?:/|\s|$)", re.I)
SECRET_RE = re.compile(
    r"(?im)^\s*(?:api[_-]?key|password|passwd|secret|access[_-]?token)\s*=\s*['\"][^'\"\r\n]{6,}['\"]\s*(?:#.*)?$"
)
PRIVATE_KEY_RE = re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
TOKEN_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._~+/=-]{16,})"
)
CREDENTIAL_URL_RE = re.compile(r"https?://[^\s/:@]+:[^\s/@]+@", re.I)
HTTP_URL_RE = re.compile(r"https?://[^\s`'\"<>]+", re.I)
ALLOWED_SUPPORT_ROOTS = {"assets", "references", "scripts", "templates", "evals"}
ALLOWED_KINDS = {"application", "curated-document"}
ALLOWED_LANGUAGES = {"de", "en"}
CATALOG_KEYS = {"schema_version", "skills"}
ENTRY_KEYS = {"name", "kind", "language", "origin", "upstream_commit", "author"}
COREY_COMMIT = "7868cb9251fad80a73d26e488a5ad5f6c4a9f335"
LOGIN_COMMIT = "e80bcfdb34dee7cc94265fc8ce54f156f440e4c8"
COREY_AUTHOR = "Corey Haines; Hermes-curated adaptation"
EXPECTED_SKILLS = {
    "gym": ("application", "de", "LOGIN-TB/hermes-toolbox", None, "LOGIN-TB contributors"),
    "ai-seo": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "seo-audit": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "product-marketing": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "social": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "cold-email": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "competitors": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "competitor-profiling": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "content-strategy": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "copywriting": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "customer-research": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "image": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "lead-magnets": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "marketing-ideas": ("curated-document", "de", "coreyhaines31/marketingskills", COREY_COMMIT, COREY_AUTHOR),
    "vermenschlichen": ("curated-document", "de", "LOGIN-TB/claude-skills", LOGIN_COMMIT, "LOGIN-TB; Hermes-curated adaptation"),
    "zustellbarkeit": ("application", "de", "LOGIN-TB/hermes-toolbox", None, "LOGIN-TB contributors"),
}
GERMAN_CURATED_SKILLS = {
    name for name, (kind, _language, origin, _commit, _author) in EXPECTED_SKILLS.items()
    if kind == "curated-document" and origin == "coreyhaines31/marketingskills"
}
CURATION_KEYS = {"schema_version", "skills"}
CURATION_ENTRY_KEYS = {
    "name", "upstream_repository", "upstream_path", "upstream_commit", "local_version",
    "content_language", "default_market", "change_categories", "change_summary",
    "legal_review_domains", "last_reviewed",
}
REQUIRED_CHANGE_CATEGORIES = {
    "übersetzt", "umstrukturiert", "DACH ergänzt", "Hermes angepasst", "Sicherheit ergänzt",
}
LOCAL_VERSION_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-hermes\.2$")
EXPECTED_HOMEPAGES = {
    name: f"https://github.com/coreyhaines31/marketingskills/tree/{COREY_COMMIT}/skills/{name}"
    for name in GERMAN_CURATED_SKILLS
}
REQUIRED_GERMAN_HEADINGS = {
    "## Deutscher/DACH-Kontext", "## Ausgabeformat", "## Prüfliste",
    "## Herkunft und Abweichungen",
}
FORBIDDEN_LEGAL_ASSURANCE_RE = re.compile(
    r"(?i)\b(?:DSGVO[- ]konform|rechtssicher|in Deutschland erlaubt)\b"
)
FORBIDDEN_ENGLISH_STANDARD_HEADING_RE = re.compile(
    r"^## (?:Overview|When to Use|Output(?: Format)?|Deliverable|Checklist|Scope|Workflow|Evidence|Common Pitfalls|Boundaries)\s*$",
    re.MULTILINE,
)


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def construct_unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, f"found duplicate key {key!r}", key_node.start_mark
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping
)


def reject_duplicate_json_key(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_unique(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_json_key)


def fail(message: str) -> NoReturn:
    raise AssertionError(message)


def public_url_is_private(text: str) -> bool:
    for raw_url in HTTP_URL_RE.findall(text):
        host = urlsplit(raw_url.rstrip(".,);]")).hostname
        if not host:
            continue
        if host.lower() == "localhost" or host.lower().endswith(".local"):
            return True
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            continue
        if address.is_loopback or address.is_private or address.is_link_local:
            return True
        if isinstance(address, ipaddress.IPv4Address) and address in ipaddress.ip_network("100.64.0.0/10"):
            return True
    return False


def relative_targets(markdown: str) -> list[str]:
    targets: list[str] = []
    for target in LINK_RE.findall(markdown):
        target = target.strip().split("#", 1)[0]
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
            continue
        targets.append(target)
    return targets


def validate() -> list[dict]:
    unstaged = subprocess.run(
        ["git", "diff", "--quiet", "--"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if unstaged.returncode != 0:
        fail("working-tree bytes differ from the staged tree")

    catalog = load_json_unique(CATALOG)
    if not isinstance(catalog, dict) or set(catalog) != CATALOG_KEYS:
        fail("skills/catalog.json must contain exactly schema_version and skills")
    if catalog.get("schema_version") != 1:
        fail("skills/catalog.json must use schema_version 1")
    entries = catalog.get("skills")
    if not isinstance(entries, list) or not entries:
        fail("skills/catalog.json must contain a non-empty skills list")

    names = [entry.get("name") for entry in entries]
    if len(names) != len(set(names)):
        fail("catalog contains duplicate skill names")
    if any(not isinstance(name, str) or not NAME_RE.fullmatch(name) for name in names):
        fail("catalog contains an invalid skill name")
    if set(names) != set(EXPECTED_SKILLS) or len(names) != len(EXPECTED_SKILLS):
        fail("catalog must contain exactly the canonical Hermes Toolbox skills")
    for entry in entries:
        if not isinstance(entry, dict):
            fail("every catalog skill entry must be an object")
        allowed_keys = ENTRY_KEYS if entry.get("kind") == "curated-document" else ENTRY_KEYS - {"upstream_commit"}
        if set(entry) != allowed_keys:
            fail(f"catalog entry {entry.get('name')} has missing or unknown fields")
        if any(not isinstance(entry.get(field), str) or not entry[field] for field in allowed_keys):
            fail(f"catalog entry {entry.get('name')} has a non-string or empty field")
        if entry.get("kind") not in ALLOWED_KINDS:
            fail(f"catalog entry {entry.get('name')} has an unsupported kind")
        if entry.get("language") not in ALLOWED_LANGUAGES:
            fail(f"catalog entry {entry.get('name')} has an unsupported language")

    curation = load_json_unique(CURATION)
    if not isinstance(curation, dict) or set(curation) != CURATION_KEYS:
        fail("skills/curation.json must contain exactly schema_version and skills")
    if curation.get("schema_version") != 1 or not isinstance(curation.get("skills"), list):
        fail("skills/curation.json must use schema_version 1 and contain a skills list")
    curation_entries = curation["skills"]
    curation_names = [entry.get("name") for entry in curation_entries if isinstance(entry, dict)]
    if len(curation_entries) != len(curation_names) or set(curation_names) != GERMAN_CURATED_SKILLS or len(curation_names) != len(set(curation_names)):
        fail("skills/curation.json must contain every German curated skill exactly once")
    catalog_by_name = {entry["name"]: entry for entry in entries}
    curation_by_name = {}
    seen_summaries: set[str] = set()
    for entry in curation_entries:
        name = entry.get("name")
        if set(entry) != CURATION_ENTRY_KEYS:
            fail(f"curation entry {name} has missing or unknown fields")
        for field in CURATION_ENTRY_KEYS - {"change_categories", "legal_review_domains"}:
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                fail(f"curation entry {name} has a non-string or empty field {field}")
        for field in ("change_categories", "legal_review_domains"):
            value = entry.get(field)
            if (
                not isinstance(value, list)
                or not value
                or len(value) != len(set(value))
                or any(not isinstance(item, str) or not item.strip() for item in value)
            ):
                fail(f"curation entry {name} has an invalid {field}")
        if set(entry["change_categories"]) != REQUIRED_CHANGE_CATEGORIES:
            fail(f"curation entry {name} must use the canonical change categories")
        summary = entry["change_summary"].strip()
        if len(summary) < 40 or len(set(re.findall(r"\w+", summary.lower()))) < 8:
            fail(f"curation entry {name} has an insufficient change summary")
        normalized_summary = re.sub(r"\s+", " ", summary).casefold()
        if normalized_summary in seen_summaries:
            fail(f"curation entry {name} duplicates another change summary")
        seen_summaries.add(normalized_summary)
        if not LOCAL_VERSION_RE.fullmatch(entry["local_version"]):
            fail(f"curation entry {name} has an invalid local version")
        try:
            reviewed = date.fromisoformat(entry["last_reviewed"])
        except ValueError:
            fail(f"curation entry {name} has an invalid ISO review date")
        if reviewed > date.today():
            fail(f"curation entry {name} has a future review date")
        catalog_entry = catalog_by_name[name]
        expected_path = f"skills/{name}/SKILL.md"
        if (
            entry["upstream_repository"] != catalog_entry["origin"]
            or entry["upstream_path"] != expected_path
            or entry["upstream_commit"] != catalog_entry["upstream_commit"]
            or entry["content_language"] != "de"
            or catalog_entry["language"] != "de"
            or entry["default_market"] != "DE"
            or not entry["local_version"].endswith("-hermes.2")
        ):
            fail(f"curation provenance, language, market, path, or version differs for {name}")
        curation_by_name[name] = entry

    git_modes = subprocess.run(
        ["git", "ls-files", "-s"], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if git_modes.returncode != 0:
        fail(f"could not inspect tracked skill file modes: {git_modes.stderr}")
    for line in git_modes.stdout.splitlines():
        mode, _object, _stage_and_path = line.split(maxsplit=2)
        if mode != "100644":
            fail(f"unexpected tracked Git mode (only 100644 is allowed): {line}")

    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if tracked.returncode != 0:
        fail(f"could not enumerate tracked files: {tracked.stderr.decode(errors='replace')}")
    for raw_path in tracked.stdout.split(b"\0"):
        if not raw_path:
            continue
        rel_path = raw_path.decode("utf-8")
        path = ROOT / rel_path
        if not path.is_file():
            fail(f"tracked path is not a regular file: {rel_path}")
        data = path.read_bytes()
        approved_binary_asset = rel_path.startswith("skills/") and "/assets/" in rel_path
        if b"\0" in data:
            if approved_binary_asset:
                continue
            fail(f"NUL byte outside an approved skill asset: {rel_path}")
        try:
            public_text = data.decode("utf-8")
        except UnicodeDecodeError:
            if approved_binary_asset:
                continue
            fail(f"non-UTF-8 file outside an approved skill asset: {rel_path}")
        if PRIVATE_PATH_RE.search(public_text):
            fail(f"workstation-specific absolute path in tracked file {rel_path}")
        if FILE_URL_RE.search(public_text) or LOCAL_HOST_URL_RE.search(public_text) or public_url_is_private(public_text):
            fail(f"workstation-specific URL in tracked file {rel_path}")
        if (
            SECRET_RE.search(public_text)
            or PRIVATE_KEY_RE.search(public_text)
            or TOKEN_RE.search(public_text)
            or CREDENTIAL_URL_RE.search(public_text)
        ):
            fail(f"possible embedded secret in tracked file {rel_path}")

    actual = sorted(path.parent.name for path in SKILLS.glob("*/SKILL.md"))
    if sorted(names) != actual:
        fail(f"catalog/directory mismatch: catalog={sorted(names)}, actual={actual}")

    seen_frontmatter_names: set[str] = set()
    for entry in entries:
        name = entry["name"]
        skill_dir = SKILLS / name
        skill_md = skill_dir / "SKILL.md"
        if skill_dir.is_symlink() or skill_md.is_symlink():
            fail(f"symlinks are forbidden in skill package: {name}")
        text = skill_md.read_text(encoding="utf-8")
        if "\x00" in text:
            fail(f"NUL byte in {skill_md.relative_to(ROOT)}")
        match = FRONTMATTER_RE.match(text)
        if not match:
            fail(f"invalid YAML frontmatter delimiters in {skill_md.relative_to(ROOT)}")
        frontmatter = match.group("body")
        try:
            metadata = yaml.load(frontmatter, Loader=UniqueKeyLoader)
        except yaml.YAMLError as exc:
            fail(f"invalid YAML frontmatter in {skill_md.relative_to(ROOT)}: {exc}")
        if not isinstance(metadata, dict):
            fail(f"YAML frontmatter must be a mapping in {skill_md.relative_to(ROOT)}")
        scalars = {}
        for key in ("name", "description", "version", "author", "license"):
            value = metadata.get(key)
            if not isinstance(value, str) or not value.strip():
                fail(f"frontmatter field {key!r} must be a non-empty string in {name}")
            scalars[key] = value.strip()
        fm_name = scalars["name"]
        description = scalars["description"]
        version = scalars["version"]
        author = scalars["author"]
        license_name = scalars["license"]
        if fm_name != name:
            fail(f"frontmatter name {fm_name!r} does not match directory {name!r}")
        if fm_name in seen_frontmatter_names:
            fail(f"duplicate frontmatter name: {fm_name}")
        seen_frontmatter_names.add(fm_name)
        if not description or not version or not author or license_name != "MIT":
            fail(f"invalid description/version/author/license in {name}")
        if name in GERMAN_CURATED_SKILLS and re.match(r"(?i)^Nutzen\s*,\s*wenn\b", description):
            fail(f"German curated skill {name} contains an unnatural trigger description")
        expected_kind, expected_language, expected_origin, expected_commit, expected_author = EXPECTED_SKILLS[name]
        if (
            entry["kind"] != expected_kind
            or entry["language"] != expected_language
            or entry["origin"] != expected_origin
            or entry.get("upstream_commit") != expected_commit
            or entry["author"] != expected_author
            or author != expected_author
        ):
            fail(f"catalog or author attribution differs from the canonical manifest for {name}")

        if entry.get("kind") == "curated-document":
            for field in ("origin", "upstream_commit", "language"):
                if not entry.get(field):
                    fail(f"catalog entry {name} lacks {field}")
            commit = entry["upstream_commit"]
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                fail(f"catalog entry {name} has no immutable upstream commit")
            hermes_metadata = metadata.get("metadata", {}).get("hermes", {}) if isinstance(metadata.get("metadata"), dict) else {}
            if not isinstance(hermes_metadata, dict):
                fail(f"frontmatter metadata.hermes must be a mapping in {name}")
            if hermes_metadata.get("upstream_commit") != commit:
                fail(f"frontmatter upstream commit differs from catalog for {name}")
            if name in GERMAN_CURATED_SKILLS and hermes_metadata.get("homepage") != EXPECTED_HOMEPAGES[name]:
                fail(f"frontmatter homepage differs from canonical upstream for {name}")
            if name in GERMAN_CURATED_SKILLS:
                curation_entry = curation_by_name[name]
                if version != curation_entry["local_version"] or not version.endswith("-hermes.2"):
                    fail(f"German curated skill {name} must use the documented -hermes.2 version")
                missing_headings = REQUIRED_GERMAN_HEADINGS - {line.strip() for line in text.splitlines()}
                if missing_headings:
                    fail(f"German curated skill {name} lacks required headings: {sorted(missing_headings)}")
                if FORBIDDEN_LEGAL_ASSURANCE_RE.search(text):
                    fail(f"German curated skill {name} contains an unqualified legal assurance")
                if FORBIDDEN_ENGLISH_STANDARD_HEADING_RE.search(text):
                    fail(f"German curated skill {name} contains an English standard heading")
            elif not version.endswith("-hermes.1"):
                fail(f"curated skill {name} must use a -hermes.1 version")
            packaged_files = [
                path.relative_to(skill_dir).as_posix()
                for path in skill_dir.rglob("*")
                if path.is_file()
                and not any(part in {"__pycache__", ".pytest_cache"} for part in path.relative_to(skill_dir).parts)
            ]
            if packaged_files != ["SKILL.md"]:
                fail(f"curated document skill {name} may contain only SKILL.md: {packaged_files}")
            inferred_support = {
                match.group(1).rstrip(".,;:")
                for match in HERMES_SUPPORT_REF_RE.finditer(text.replace("\\", "/"))
            }
            if inferred_support:
                fail(f"curated document skill {name} triggers Hermes support-file inference: {sorted(inferred_support)}")

        if PRIVATE_PATH_RE.search(text):
            fail(f"workstation-specific absolute path in {name}")
        if SECRET_RE.search(text):
            fail(f"possible embedded secret in {name}")

        for target in relative_targets(text):
            pure = PurePosixPath(target)
            if pure.is_absolute() or ".." in pure.parts:
                fail(f"unsafe relative link {target!r} in {name}")
            if pure.parts and pure.parts[0] not in ALLOWED_SUPPORT_ROOTS:
                fail(f"unsupported relative link root {target!r} in {name}")
            if not (skill_dir / pure).is_file():
                fail(f"missing relative link target {target!r} in {name}")

        for path in skill_dir.rglob("*"):
            if any(part in {"__pycache__", ".pytest_cache"} for part in path.relative_to(skill_dir).parts):
                continue
            if path.is_symlink():
                fail(f"symlink forbidden: {path.relative_to(ROOT)}")
            if path.is_file():
                rel = path.relative_to(skill_dir)
                if rel != Path("SKILL.md") and rel.parts[0] not in ALLOWED_SUPPORT_ROOTS:
                    fail(f"unexpected file in skill package: {path.relative_to(ROOT)}")
                data = path.read_bytes()
                if b"\x00" in data and rel.parts[0] not in {"assets"}:
                    fail(f"unexpected binary file: {path.relative_to(ROOT)}")

    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    changes = (ROOT / "docs/UPSTREAM-AENDERUNGEN.md").read_text(encoding="utf-8")
    canonical_provenance = f"Gemeinsamer Upstream ist `coreyhaines31/marketingskills`, fixiert auf Commit `{COREY_COMMIT}`."
    if canonical_provenance not in changes:
        fail("docs/UPSTREAM-AENDERUNGEN.md lacks canonical repository and commit provenance")
    for entry in entries:
        if entry.get("kind") == "curated-document" and entry["upstream_commit"] not in notices:
            fail(f"THIRD_PARTY_NOTICES.md lacks the upstream commit for {entry['name']}")
    for name in GERMAN_CURATED_SKILLS:
        curation_entry = curation_by_name[name]
        section = re.search(
            rf"^## `{re.escape(name)}`\n(?P<body>.*?)(?=^## `|^## Pflegeprozess)",
            changes, re.MULTILINE | re.DOTALL,
        )
        if not section:
            fail(f"docs/UPSTREAM-AENDERUNGEN.md lacks a section for {name}")
        body = section.group("body")
        if curation_entry["local_version"] not in body or curation_entry["upstream_path"] not in body:
            fail(f"documented local version or upstream path differs for {name}")

    expected_licenses = {
        "licenses/coreyhaines31-marketingskills-MIT.txt": "b70d71e24e40fce5da8f4b6f9cd862096a048e433db7f3c8cac5e348e6d34591",
        "licenses/login-tb-claude-skills-MIT.txt": "2d97b62dab1823f076a157a1b0cffa85e11ba6728a51833b73abd010ff633a1c",
    }
    for rel_path, expected_digest in expected_licenses.items():
        data = (ROOT / rel_path).read_bytes()
        actual_digest = hashlib.sha256(data).hexdigest()
        if actual_digest != expected_digest:
            fail(f"third-party license digest mismatch for {rel_path}")

    print(f"validated_skills={len(entries)}")
    return entries


def smoke_with_hermes(entries: list[dict], hermes: str, base_url: str) -> None:
    base_url = base_url.rstrip("/")
    if not base_url.startswith("https://"):
        fail("--base-url must be an HTTPS URL to an immutable public tree")

    def run_remote(command: list[str], env: dict[str, str], name: str, action: str) -> subprocess.CompletedProcess[str]:
        last = None
        for attempt in range(1, 4):
            result = subprocess.run(
                command, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            output = result.stdout.lower()
            fetch_failed = "could not fetch" in output
            if result.returncode == 0 and not fetch_failed:
                return result
            last = result
            if not fetch_failed or attempt == 3:
                break
            time.sleep(attempt * 2)
        fail(f"Hermes {action} failed for {name}:\n{last.stdout if last else 'no result'}")

    for entry in entries:
        if entry.get("kind") != "curated-document":
            continue
        name = entry["name"]
        url = f"{base_url}/skills/{quote(name)}/SKILL.md"
        with tempfile.TemporaryDirectory(prefix=f"hermes-toolbox-{name}-") as home:
            env = os.environ.copy()
            env["HERMES_HOME"] = home
            inspect = run_remote(
                [hermes, "skills", "inspect", url], env, name, "inspect",
            )
            if "error:" in inspect.stdout.lower():
                fail(f"Hermes inspect failed for {name}:\n{inspect.stdout}")
            install = run_remote(
                [hermes, "skills", "install", url, "--category", "toolbox", "--name", name, "--yes"],
                env, name, "install",
            )
            if "error:" in install.stdout.lower():
                fail(f"Hermes install failed for {name}:\n{install.stdout}")
            candidates = list((Path(home) / "skills").rglob(f"{name}/SKILL.md"))
            if len(candidates) != 1:
                fail(f"Hermes installed {name} at {len(candidates)} paths instead of exactly one")
            installed = candidates[0]
            source_bytes = (SKILLS / name / "SKILL.md").read_bytes()
            installed_bytes = installed.read_bytes()
            if source_bytes != installed_bytes:
                fail(f"installed bytes differ for {name}")
            digest = hashlib.sha256(source_bytes).hexdigest()
            print(f"hermes_smoke={name} sha256={digest}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-smoke", action="store_true")
    parser.add_argument("--hermes", default="hermes")
    parser.add_argument("--base-url")
    args = parser.parse_args()
    entries = validate()
    if args.hermes_smoke:
        if not args.base_url:
            fail("--hermes-smoke requires --base-url")
        smoke_with_hermes(entries, args.hermes, args.base_url)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
