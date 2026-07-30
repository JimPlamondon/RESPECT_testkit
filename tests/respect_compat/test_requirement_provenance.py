# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import json

from respect_compat.matrix_validator import (
    DEFAULT_INDEX,
    DEFAULT_MATRIX,
    DEFAULT_PROVENANCE_AUDIT,
    load_json,
    semantic_hash,
    validate_matrix,
)


def test_legacy_rows_are_frozen_and_honestly_unresolved():
    matrix = load_json(DEFAULT_MATRIX)
    audit = load_json(DEFAULT_PROVENANCE_AUDIT)
    assert len(audit["records"]) == 132
    assert {item["status"] for item in audit["records"]} == {
        "unresolved_legacy"
    }
    assert {item["origin"] for item in audit["records"]} == {None}
    assert validate_matrix(matrix, load_json(DEFAULT_INDEX), audit).errors == []


def test_changed_row_requires_exactly_one_allowed_origin():
    matrix = load_json(DEFAULT_MATRIX)
    index = load_json(DEFAULT_INDEX)
    audit = load_json(DEFAULT_PROVENANCE_AUDIT)
    matrix["rows"][0]["title"] += " changed"
    matrix["semantic_hash"] = semantic_hash(matrix)
    errors = validate_matrix(matrix, index, audit).errors
    assert any("must prove exactly one requirement origin" in item for item in errors)

    matrix["rows"][0]["requirement_origin"] = {
        "type": "respect_code_analysis",
        "analysis_revision": "respect-revision",
        "evidence_reference": "analysis:row-change",
    }
    matrix["semantic_hash"] = semantic_hash(matrix)
    assert validate_matrix(matrix, index, audit).errors == []


def test_explicit_extension_requires_owner_approval_reference():
    matrix = load_json(DEFAULT_MATRIX)
    index = load_json(DEFAULT_INDEX)
    audit = load_json(DEFAULT_PROVENANCE_AUDIT)
    feature = copy.deepcopy(matrix["features"][0])
    feature["feature_id"] = "RCF-EXPLICIT-EXTENSION"
    feature["row_ids"] = []
    feature["title"] = "Explicit TestKit extension"
    feature["requirement_origin"] = {
        "type": "explicit_testkit_extension",
        "approval_reference": "owner-decision:example",
        "extension_reference": "testkit-extension:example",
    }
    matrix["features"].append(feature)
    matrix["completeness"]["feature_count"] += 1
    matrix["semantic_hash"] = semantic_hash(matrix)
    errors = validate_matrix(matrix, index, audit).errors
    assert not any("must prove exactly one requirement origin" in item for item in errors)
