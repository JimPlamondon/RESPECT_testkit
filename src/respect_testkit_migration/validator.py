# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from respect_compat.matrix_runtime import load_matrix
from respect_compat.matrix_validator import load_json, run_mutation_checks
from respect_compat.resources import resource


FORBIDDEN_EXCLUSION_CLASSES = {
    "runtime",
    "matrix",
    "profile",
    "schema",
    "fixture",
    "test",
    "validator",
    "bootstrap",
}
MIGRATED_AUTHORITY_ROOTS = (
    "src/respect_compat/data/fixtures/",
    "src/respect_compat/data/indexes/",
    "src/respect_compat/data/matrix/",
    "src/respect_compat/data/profiles/",
    "src/respect_compat/data/schemas/",
    "src/respect_ification/data/schemas/",
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_hash(data: dict[str, Any], hash_field: str) -> str:
    candidate = dict(data)
    candidate.pop(hash_field, None)
    payload = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return sha256_bytes(payload)


def git(source: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(source), *args])


def validate_manifest(
    manifest_path: Path,
    repository_root: Path,
    source_repo: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        inventory_path = repository_root / manifest["source_inventory"]
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        schema = json.loads((repository_root / "migration/source_manifest.schema.json").read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError) as error:
        return [f"SCHEMA: {error}"]
    for error in sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda item: list(item.path)):
        errors.append(f"SCHEMA: {error.json_path}: {error.message}")
    if manifest.get("manifest_hash") != canonical_hash(manifest, "manifest_hash"):
        errors.append("INVENTORY_DRIFT: manifest aggregate hash mismatch")
    if inventory.get("inventory_hash") != canonical_hash(inventory, "inventory_hash"):
        errors.append("INVENTORY_DRIFT: inventory aggregate hash mismatch")
    if manifest.get("source_inventory_hash") != inventory.get("inventory_hash"):
        errors.append("INVENTORY_DRIFT: manifest inventory hash does not bind committed inventory")
    inventory_entries = inventory.get("entries", [])
    manifest_entries = manifest.get("entries", [])
    inventory_paths = [item.get("source_path") for item in inventory_entries]
    manifest_paths = [item.get("source_path") for item in manifest_entries]
    if inventory_paths != sorted(inventory_paths, key=lambda value: value.encode() if isinstance(value, str) else b""):
        errors.append("SCHEMA: inventory paths are not sorted bytewise")
    if manifest_paths != sorted(manifest_paths, key=lambda value: value.encode() if isinstance(value, str) else b""):
        errors.append("SCHEMA: manifest paths are not sorted bytewise")
    if len(manifest_paths) != len(set(manifest_paths)):
        errors.append("DUPLICATE_SOURCE: manifest source paths are not unique")
    if inventory_paths != manifest_paths:
        missing = sorted(set(inventory_paths) - set(manifest_paths))
        extra = sorted(set(manifest_paths) - set(inventory_paths))
        errors.append(f"OMISSION: inventory/manifest mismatch missing={missing} extra={extra}")
    inventory_by_path = {item.get("source_path"): item for item in inventory_entries}
    for closure_name, closure_paths in inventory.get("closures", {}).items():
        outside = sorted(set(closure_paths) - set(inventory_paths))
        if outside:
            errors.append(f"OMISSION: {closure_name} paths absent from inventory: {outside}")
    declared_destinations = set()
    for entry in manifest_entries:
        source_path = entry.get("source_path", "<unknown>")
        inventory_entry = inventory_by_path.get(source_path)
        if inventory_entry is not None:
            for field in ("mode", "object_type", "blob_oid", "sha256", "size"):
                if entry.get(field) != inventory_entry.get(field):
                    errors.append(f"INVENTORY_DRIFT: {source_path}: {field}")
        disposition = entry.get("disposition")
        item_class = entry.get("item_class")
        if disposition in {"excluded", "historical_only"} and item_class in FORBIDDEN_EXCLUSION_CLASSES:
            errors.append(f"ILLEGAL_EXCLUSION: {source_path}: {item_class}")
        if disposition in {"migrated", "adapted"}:
            relative = entry.get("destination_path")
            if not isinstance(relative, str):
                errors.append(f"MISSING_DESTINATION: {source_path}")
                continue
            candidate = (repository_root / relative).resolve()
            try:
                candidate.relative_to(repository_root.resolve())
            except ValueError:
                errors.append(f"PATH_ESCAPE: {source_path}: {relative}")
                continue
            if not candidate.is_file():
                errors.append(f"MISSING_DESTINATION: {source_path}: {relative}")
                continue
            declared_destinations.add(relative)
            actual_hash = sha256_bytes(candidate.read_bytes())
            if actual_hash != entry.get("destination_sha256"):
                errors.append(f"HASH_MISMATCH: {source_path}: declared destination hash")
            if disposition == "migrated" and actual_hash != entry.get("sha256"):
                errors.append(f"HASH_MISMATCH: {source_path}: migrated bytes changed")
        elif disposition not in {"excluded", "historical_only"}:
            errors.append(f"ILLEGAL_DISPOSITION: {source_path}: {disposition}")
    actual_authorities = {
        path.relative_to(repository_root).as_posix()
        for root_name in MIGRATED_AUTHORITY_ROOTS
        for path in (repository_root / root_name).rglob("*")
        if path.is_file() and path.name != "__pycache__"
    }
    undeclared = sorted(actual_authorities - declared_destinations)
    if undeclared:
        errors.append(f"UNDECLARED_DESTINATION: {undeclared}")
    canonical = list(repository_root.rglob("compatibility_matrix.json"))
    historical = list(repository_root.rglob("compatibility_matrix_v0_1.json"))
    if canonical != [repository_root / "src/respect_compat/data/matrix/compatibility_matrix.json"]:
        errors.append(f"DUPLICATE_AUTHORITY: canonical Matrix locations={canonical}")
    if historical != [repository_root / "src/respect_compat/data/profiles/compatibility_matrix_v0_1.json"]:
        errors.append(f"DUPLICATE_AUTHORITY: historical profile locations={historical}")
    try:
        matrix = load_matrix()
        matrix_data = load_json(resource("data/matrix/compatibility_matrix.json"))
        index_data = load_json(resource("data/indexes/source_interaction_index.json"))
        mutations = run_mutation_checks(matrix_data, index_data)
        if (
            matrix.matrix_id != inventory["matrix"]["identifier"]
            or matrix.matrix_version != inventory["matrix"]["version"]
            or matrix.semantic_hash != inventory["matrix"]["semantic_hash"]
            or len(matrix.features) != inventory["matrix"]["features"]
            or len(matrix.rows) != inventory["matrix"]["rows"]
            or len(mutations) != inventory["matrix"]["mutation_checks"]
            or not all(item["passed"] for item in mutations)
        ):
            errors.append("MATRIX_DRIFT: Matrix identity, counts, semantic hash, or mutations changed")
    except (KeyError, OSError, TypeError, ValueError) as error:
        errors.append(f"MATRIX_DRIFT: {error}")
    if source_repo is not None:
        source_repo = source_repo.resolve()
        expected_commit = inventory.get("source_commit")
        try:
            if git(source_repo, "rev-parse", "HEAD").decode().strip() != expected_commit:
                errors.append("INVENTORY_DRIFT: source worktree HEAD differs from frozen commit")
            for entry in inventory_entries:
                source_path = entry["source_path"]
                tree_line = git(source_repo, "ls-tree", expected_commit, "--", source_path).decode().strip()
                if not tree_line:
                    errors.append(f"INVENTORY_DRIFT: missing source path {source_path}")
                    continue
                metadata, observed_path = tree_line.split("\t", 1)
                mode, object_type, blob_oid = metadata.split()
                payload = git(source_repo, "cat-file", "blob", blob_oid)
                observed = {
                    "source_path": observed_path,
                    "mode": mode,
                    "object_type": object_type,
                    "blob_oid": blob_oid,
                    "sha256": sha256_bytes(payload),
                    "size": len(payload),
                }
                for field, value in observed.items():
                    if entry.get(field) != value:
                        errors.append(f"INVENTORY_DRIFT: {source_path}: source {field}")
        except (OSError, subprocess.CalledProcessError, ValueError) as error:
            errors.append(f"INVENTORY_DRIFT: source verification failed: {error}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path)
    args = parser.parse_args()
    repository_root = Path.cwd().resolve()
    errors = validate_manifest(args.manifest.resolve(), repository_root, args.source_repo)
    print(json.dumps({"errors": errors, "valid": not errors}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
