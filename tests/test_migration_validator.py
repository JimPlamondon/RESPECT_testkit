# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import hashlib
import json
from pathlib import Path

from respect_testkit_migration.validator import (
    active_authority_files,
    authority_layout_errors,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "migration/source_manifest.json"


def canonical_hash(data, field):
    candidate = copy.deepcopy(data)
    candidate.pop(field, None)
    payload = json.dumps(
        candidate,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def mutated_manifest(tmp_path, mutate):
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mutate(data)
    data["manifest_hash"] = canonical_hash(data, "manifest_hash")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_committed_manifest_is_valid_offline():
    assert validate_manifest(MANIFEST, ROOT) == []


def test_retired_authorities_are_ignored_but_active_duplicates_fail(tmp_path):
    canonical = (
        tmp_path
        / "src/respect_compat/data/matrix/compatibility_matrix.json"
    )
    historical = (
        tmp_path
        / "src/respect_compat/data/profiles/compatibility_matrix_v0_1.json"
    )
    canonical.parent.mkdir(parents=True)
    historical.parent.mkdir(parents=True)
    canonical.write_text("{}", encoding="utf-8")
    historical.write_text("{}", encoding="utf-8")
    assert authority_layout_errors(tmp_path) == []

    retired_canonical = (
        tmp_path
        / "To_Be_Deleted/build/lib/respect_compat/data/matrix"
        / "compatibility_matrix.json"
    )
    retired_historical = (
        tmp_path
        / "To_Be_Deleted/build/lib/respect_compat/data/profiles"
        / "compatibility_matrix_v0_1.json"
    )
    retired_canonical.parent.mkdir(parents=True)
    retired_historical.parent.mkdir(parents=True)
    retired_canonical.write_text("{}", encoding="utf-8")
    retired_historical.write_text("{}", encoding="utf-8")

    assert active_authority_files(
        tmp_path, "compatibility_matrix.json"
    ) == [canonical]
    assert active_authority_files(
        tmp_path, "compatibility_matrix_v0_1.json"
    ) == [historical]
    assert authority_layout_errors(tmp_path) == []

    active_canonical = tmp_path / "active-copy/compatibility_matrix.json"
    active_historical = (
        tmp_path / "active-copy/compatibility_matrix_v0_1.json"
    )
    active_canonical.parent.mkdir()
    active_canonical.write_text("{}", encoding="utf-8")
    active_historical.write_text("{}", encoding="utf-8")

    errors = authority_layout_errors(tmp_path)
    assert any(
        error.startswith("DUPLICATE_AUTHORITY: canonical Matrix")
        for error in errors
    )
    assert any(
        error.startswith("DUPLICATE_AUTHORITY: historical profile")
        for error in errors
    )


def test_omission_fails_closed(tmp_path):
    path = mutated_manifest(tmp_path, lambda data: data["entries"].pop())
    assert any(
        error.startswith("OMISSION:")
        for error in validate_manifest(path, ROOT)
    )


def test_duplicate_source_fails_closed(tmp_path):
    path = mutated_manifest(
        tmp_path,
        lambda data: data["entries"].append(copy.deepcopy(data["entries"][-1])),
    )
    assert any(
        error.startswith("DUPLICATE_SOURCE:")
        for error in validate_manifest(path, ROOT)
    )


def test_runtime_exclusion_is_illegal(tmp_path):
    def mutate(data):
        entry = next(
            item for item in data["entries"] if item["item_class"] == "runtime"
        )
        entry["disposition"] = "excluded"
        entry["exclusion_reason"] = "reproducible_generated_evidence"
        entry.pop("destination_path")
        entry.pop("destination_sha256")
        entry.pop("adaptation_reason", None)

    path = mutated_manifest(tmp_path, mutate)
    assert any(
        error.startswith("ILLEGAL_EXCLUSION:")
        for error in validate_manifest(path, ROOT)
    )


def test_destination_path_escape_fails_closed(tmp_path):
    def mutate(data):
        entry = next(
            item
            for item in data["entries"]
            if item["disposition"] in {"migrated", "adapted"}
        )
        entry["destination_path"] = "../escape"

    path = mutated_manifest(tmp_path, mutate)
    assert any(
        error.startswith("PATH_ESCAPE:")
        for error in validate_manifest(path, ROOT)
    )


def test_missing_destination_and_hash_mismatch_fail_closed(tmp_path):
    def missing(data):
        entry = next(
            item
            for item in data["entries"]
            if item["disposition"] in {"migrated", "adapted"}
        )
        entry["destination_path"] = "missing/file"

    missing_path = mutated_manifest(tmp_path, missing)
    assert any(
        error.startswith("MISSING_DESTINATION:")
        for error in validate_manifest(missing_path, ROOT)
    )

    def mismatch(data):
        entry = next(
            item
            for item in data["entries"]
            if item["disposition"] in {"migrated", "adapted"}
        )
        entry["destination_sha256"] = "0" * 64

    mismatch_path = mutated_manifest(tmp_path, mismatch)
    assert any(
        error.startswith("HASH_MISMATCH:")
        for error in validate_manifest(mismatch_path, ROOT)
    )


def test_native_post_extraction_authority_hash_mismatch_fails_closed(
    tmp_path,
):
    def mismatch(data):
        data["native_entries"][0]["destination_sha256"] = "0" * 64

    path = mutated_manifest(tmp_path, mismatch)
    assert any(
        error.startswith("HASH_MISMATCH: native authority")
        for error in validate_manifest(path, ROOT)
    )
