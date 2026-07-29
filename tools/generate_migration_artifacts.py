#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


SOURCE_COMMIT = "eccf623b1978ddcd50ef16b0353193fbf2152ede"
SOURCE_REPOSITORY = "https://github.com/JimPlamondon/jims"
PR_NUMBER = 50
MATRIX_ID = "respect-compatibility-matrix-v0.1"
MATRIX_VERSION = "1.0.0"
MATRIX_SEMANTIC_HASH = "5a059124de6875ad8fa2e23c7244343f70eab6033ad26fbefeb46407d20421ee"
AUTHORING_COMMITS = [
    ("0658140c5b33a30ce2747c4f4742c87b9880513c", "RESPECT Compatible Test Suite v0.1 harness"),
    ("438e10b7fe028e73b444592d293f1c6fa5bad856", "canonical Matrix merge"),
    ("1025e89011d42e75111ef9d541110f5a516bd4af", "Matrix-driven Test Suite"),
    ("4361643cb27e4710d21c87673ef4fa4dcd23d102", "RESPECT-ification Kit"),
]
MIGRATED_AUTHORITY_ROOTS = (
    "src/respect_compat/data/fixtures/",
    "src/respect_compat/data/indexes/",
    "src/respect_compat/data/matrix/",
    "src/respect_compat/data/profiles/",
    "src/respect_compat/data/schemas/",
    "src/respect_ification/data/schemas/",
)


def run_git(source: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(source), *args])


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_hash(data: dict[str, Any], hash_field: str) -> str:
    candidate = dict(data)
    candidate.pop(hash_field, None)
    payload = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return sha256_bytes(payload)


def source_items(source: Path) -> list[dict[str, Any]]:
    raw = run_git(
        source,
        "ls-tree",
        "-rz",
        SOURCE_COMMIT,
        "--",
        "licensing-public",
        "tools/validate_respect_compatibility_matrix.py",
        "tools/bootstrap_respect_compat_standards.py",
        "tools/progress_rollup.py",
        "tools/test_progress_rollup.py",
    )
    items = []
    for record in raw.rstrip(b"\0").split(b"\0"):
        metadata, path_bytes = record.split(b"\t", 1)
        mode, object_type, blob_oid = metadata.decode().split()
        source_path = path_bytes.decode()
        payload = run_git(source, "cat-file", "blob", blob_oid)
        items.append(
            {
                "source_path": source_path,
                "mode": mode,
                "object_type": object_type,
                "blob_oid": blob_oid,
                "sha256": sha256_bytes(payload),
                "size": len(payload),
            }
        )
    return sorted(items, key=lambda item: item["source_path"].encode())


def traced_paths(source: Path, traces: list[Path]) -> list[str]:
    root = str(source.resolve()) + "/"
    observed = set()
    for trace in traces:
        for value in json.loads(trace.read_text(encoding="utf-8")):
            if value.startswith(root):
                relative = value[len(root) :]
                try:
                    matched = subprocess.check_output(
                        ["git", "-C", str(source), "ls-files", "--error-unmatch", relative],
                        stderr=subprocess.DEVNULL,
                    ).decode().splitlines()
                except subprocess.CalledProcessError:
                    continue
                if relative in matched:
                    observed.add(relative)
    return sorted(observed, key=lambda value: value.encode())


def destination_for(source_path: str) -> str | None:
    mappings = {
        "licensing-public/PURPOSE.md": "docs/PURPOSE.md",
        "licensing-public/docs/README.md": "docs/README.md",
        "licensing-public/docs/respect_compat/README.md": "docs/respect_compat/README.md",
        "licensing-public/docs/respect_ification/README.md": "docs/respect_ification/README.md",
        "licensing-public/fixtures/public/README.md": "src/respect_compat/data/fixtures/README.md",
        "licensing-public/harness/README.md": "docs/HARNESS.md",
        "licensing-public/harness/requirements.txt": "pyproject.toml",
        "licensing-public/reports/README.md": "docs/REPORTS.md",
        "licensing-public/schemas/README.md": "docs/SCHEMAS.md",
        "licensing-public/schemas/respect_compat/PROVENANCE.md": "docs/respect_compat/PROVENANCE.md",
        "licensing-public/schemas/respect_compat/compatibility_matrix.json": "src/respect_compat/data/matrix/compatibility_matrix.json",
        "licensing-public/schemas/respect_compat/compatibility_matrix.schema.json": "src/respect_compat/data/schemas/compatibility_matrix.schema.json",
        "licensing-public/schemas/respect_compat/compatibility_matrix_v0_1.json": "src/respect_compat/data/profiles/compatibility_matrix_v0_1.json",
        "licensing-public/schemas/respect_compat/source_interaction_index.json": "src/respect_compat/data/indexes/source_interaction_index.json",
        "tools/validate_respect_compatibility_matrix.py": "src/respect_compat/matrix_validator.py",
        "tools/bootstrap_respect_compat_standards.py": "src/respect_compat/standards_bootstrap.py",
    }
    if source_path in mappings:
        return mappings[source_path]
    prefixes = (
        ("licensing-public/fixtures/public/respect_compat/", "src/respect_compat/data/fixtures/"),
        ("licensing-public/harness/respect_compat/tests/", "tests/respect_compat/"),
        ("licensing-public/harness/respect_compat/", "src/respect_compat/"),
        ("licensing-public/harness/respect_ification/tests/", "tests/respect_ification/"),
        ("licensing-public/harness/respect_ification/", "src/respect_ification/"),
        ("licensing-public/schemas/respect_ification/", "src/respect_ification/data/schemas/"),
    )
    for source_prefix, destination_prefix in prefixes:
        if source_path.startswith(source_prefix):
            return destination_prefix + source_path[len(source_prefix) :]
    if source_path == "licensing-public/schemas/respect_compat/matrix_validation_report.json":
        return None
    if source_path in {"tools/progress_rollup.py", "tools/test_progress_rollup.py"}:
        return None
    raise ValueError(f"unmapped inventory path: {source_path}")


def item_class(source_path: str) -> str:
    if source_path.endswith("matrix_validation_report.json"):
        return "generated"
    if source_path.endswith("compatibility_matrix.json"):
        return "matrix"
    if source_path.endswith("compatibility_matrix_v0_1.json"):
        return "profile"
    if "/schemas/" in source_path and source_path.endswith(".json"):
        return "schema"
    if source_path.endswith("source_interaction_index.json"):
        return "schema"
    if "/fixtures/" in source_path and not source_path.endswith("README.md"):
        return "fixture"
    if "/tests/" in source_path:
        return "test"
    if source_path.endswith("validate_respect_compatibility_matrix.py"):
        return "validator"
    if source_path.endswith("bootstrap_respect_compat_standards.py"):
        return "bootstrap"
    if source_path.endswith(".md"):
        return "documentation"
    if source_path.endswith("requirements.txt"):
        return "repository_scaffold"
    if source_path in {"tools/progress_rollup.py", "tools/test_progress_rollup.py"}:
        return "repository_scaffold"
    return "runtime"


def json_locations(value: Any, pointer: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from json_locations(child, f"{pointer}/{escaped}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from json_locations(child, f"{pointer}/{index}")
    elif isinstance(value, str) and ("/Users/" in value or "licensing-public/" in value):
        yield pointer or "/", value


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--trace", type=Path, action="append", default=[])
    parser.add_argument(
        "--preserve-inventory",
        action="store_true",
        help="Refresh destination hashes without changing the frozen source inventory.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.source_repo.resolve()
    if run_git(source, "rev-parse", "HEAD").decode().strip() != SOURCE_COMMIT:
        raise SystemExit("source worktree is not frozen at SOURCE_COMMIT")
    if args.preserve_inventory:
        inventory = json.loads(
            (root / "migration/source_inventory.json").read_text(encoding="utf-8")
        )
        if inventory.get("inventory_hash") != canonical_hash(
            inventory, "inventory_hash"
        ):
            raise SystemExit("committed source inventory hash is invalid")
        entries = inventory["entries"]
    else:
        entries = source_items(source)
        all_paths = [item["source_path"] for item in entries]
        static_paths = [
            value
            for value in all_paths
            if value != "licensing-public/schemas/respect_compat/matrix_validation_report.json"
        ]
        inventory = {
            "schema_version": "1.0.0",
            "source_repository": SOURCE_REPOSITORY,
            "source_pull_request": PR_NUMBER,
            "source_commit": SOURCE_COMMIT,
            "source_tree_oids": {
                "licensing-public": run_git(source, "rev-parse", f"{SOURCE_COMMIT}:licensing-public").decode().strip(),
                "validator_blob": run_git(source, "rev-parse", f"{SOURCE_COMMIT}:tools/validate_respect_compatibility_matrix.py").decode().strip(),
                "bootstrap_blob": run_git(source, "rev-parse", f"{SOURCE_COMMIT}:tools/bootstrap_respect_compat_standards.py").decode().strip(),
            },
            "matrix": {
                "identifier": MATRIX_ID,
                "version": MATRIX_VERSION,
                "semantic_hash": MATRIX_SEMANTIC_HASH,
                "features": 45,
                "rows": 87,
                "mutation_checks": 21,
            },
            "closures": {
                "git_object_enumeration": all_paths,
                "static_import_reference": static_paths,
                "baseline_file_access": traced_paths(source, args.trace),
            },
            "entries": entries,
        }
        inventory["inventory_hash"] = canonical_hash(inventory, "inventory_hash")
        write_json(root / "migration/source_inventory.json", inventory)
    manifest_entries = []
    for source_item in entries:
        source_path = source_item["source_path"]
        destination = destination_for(source_path)
        entry = {
            "source_repository": SOURCE_REPOSITORY,
            "source_commit": SOURCE_COMMIT,
            **source_item,
            "license": "Apache-2.0",
            "provenance_reference": "MIGRATION_PROVENANCE.md",
            "item_class": item_class(source_path),
            "post_cutover_jims_disposition": "remove",
        }
        if destination is None:
            if source_path.endswith("matrix_validation_report.json"):
                entry.update(
                    {
                        "disposition": "excluded",
                        "exclusion_reason": "reproducible_generated_evidence",
                    }
                )
            else:
                entry.update(
                    {
                        "disposition": "historical_only",
                        "exclusion_reason": "jims_repository_scaffold",
                        "post_cutover_jims_disposition": "preserve_historical",
                    }
                )
        else:
            destination_path = root / destination
            if not destination_path.is_file():
                raise SystemExit(f"missing mapped destination: {destination}")
            destination_hash = sha256_bytes(destination_path.read_bytes())
            disposition = "migrated" if destination_hash == source_item["sha256"] else "adapted"
            entry.update(
                {
                    "disposition": disposition,
                    "destination_path": destination,
                    "destination_sha256": destination_hash,
                }
            )
            if disposition == "adapted":
                entry["adaptation_reason"] = "standalone package layout, installed-resource access, or destination documentation"
        manifest_entries.append(entry)
    migrated_destinations = {
        item["destination_path"]
        for item in manifest_entries
        if item.get("disposition") in {"migrated", "adapted"}
    }
    native_entries = []
    for root_name in MIGRATED_AUTHORITY_ROOTS:
        for path in sorted(
            (root / root_name).rglob("*"),
            key=lambda item: item.as_posix().encode(),
        ):
            if not path.is_file() or path.name == "__pycache__":
                continue
            relative = path.relative_to(root).as_posix()
            if relative in migrated_destinations:
                continue
            if "/schemas/" in relative:
                native_item_class = "schema"
            elif "/fixtures/" in relative:
                native_item_class = "fixture"
            else:
                native_item_class = "runtime"
            native_entries.append(
                {
                    "destination_path": relative,
                    "destination_sha256": sha256_bytes(path.read_bytes()),
                    "item_class": native_item_class,
                    "provenance": "post_extraction",
                    "reason": (
                        "post-extraction TestKit authority introduced through "
                        "the repository's reviewed source/generator workflow"
                    ),
                }
            )
    manifest = {
        "schema_version": "1.1.0",
        "source_inventory": "migration/source_inventory.json",
        "source_inventory_hash": inventory["inventory_hash"],
        "entries": manifest_entries,
        "native_entries": native_entries,
    }
    manifest["manifest_hash"] = canonical_hash(manifest, "manifest_hash")
    write_json(root / "migration/source_manifest.json", manifest)
    inert = []
    for relative in (
        "src/respect_compat/data/matrix/compatibility_matrix.json",
        "src/respect_compat/data/indexes/source_interaction_index.json",
    ):
        data = json.loads((root / relative).read_text(encoding="utf-8"))
        for pointer, value in json_locations(data):
            inert.append((relative, pointer, value))
    lines = [
        "# Migration Provenance",
        "",
        f"The RESPECT testkit was extracted without history rewriting from [JiMS pull request 50](https://github.com/JimPlamondon/jims/pull/50) at merge commit `{SOURCE_COMMIT}`. Complete pre-extraction history remains in `JimPlamondon/jims`.",
        "",
        "## Authoring commits",
        "",
    ]
    lines.extend(f"- `{commit}` — {description}." for commit, description in AUTHORING_COMMITS)
    lines.extend(
        [
            "",
            "## Source lock",
            "",
            f"- Inventory: `migration/source_inventory.json`; SHA-256 (Secure Hash Algorithm 256-bit) aggregate `{inventory['inventory_hash']}`.",
            f"- Manifest: `migration/source_manifest.json`; SHA-256 aggregate `{manifest['manifest_hash']}`.",
            f"- Canonical Matrix: `{MATRIX_ID}` version `{MATRIX_VERSION}`; semantic hash `{MATRIX_SEMANTIC_HASH}`; 45 features; 87 atomic rows; 21 mutation checks.",
            "- Historical profile: `src/respect_compat/data/profiles/compatibility_matrix_v0_1.json`, preserved byte-for-byte as a distinct non-canonical runtime profile.",
            "- OPDS revision: `8fda670fc72f110abcf68ad5d26e99ecfeeabf03`.",
            "- Readium Web Publication Manifest revision: `655ee4bcea7f63e1226f166f6b128d9bea6c655b`.",
            "",
            "## Inert historical locators",
            "",
            "The following strings are byte-preserved source or provenance evidence. Runtime code does not resolve or dereference them.",
            "",
            "| Artifact | JSON pointer | Preserved value |",
            "|---|---|---|",
        ]
    )
    for artifact, pointer, value in inert:
        escaped = value.replace("|", "\\|").replace("\n", "\\n")
        lines.append(f"| `{artifact}` | `{pointer}` | `{escaped}` |")
    (root / "MIGRATION_PROVENANCE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
