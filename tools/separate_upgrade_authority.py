#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Remove Upgrade Dossier authority and freeze legacy TestKit provenance."""

import argparse
import copy
import hashlib
import json
from pathlib import Path


REMOVED_FEATURE_FIELDS = {
    "respect_upgrade_guidance",
    "feature_work_unit",
}
REMOVED_ROW_FIELDS = {
    "platform_gap_eligible",
    "dossier_acceptance_test",
}


def canonical_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def record_hash(value):
    candidate = copy.deepcopy(value)
    candidate.pop("requirement_origin", None)
    return digest(candidate)


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    arguments = parser.parse_args()

    matrix = json.loads(arguments.matrix.read_text(encoding="utf-8"))
    source_matrix_hash = matrix["semantic_hash"]
    for feature in matrix["features"]:
        for field in REMOVED_FEATURE_FIELDS:
            feature.pop(field, None)
    for row in matrix["rows"]:
        for field in REMOVED_ROW_FIELDS:
            row.pop(field, None)
    matrix["schema_version"] = "1.3.0"
    matrix["matrix_version"] = "1.2.0"
    matrix["semantic_hash"] = "pending"
    matrix["semantic_hash"] = digest(
        {
            key: value
            for key, value in matrix.items()
            if key != "semantic_hash"
        }
    )

    origin_schema = {
        "additionalProperties": False,
        "oneOf": [
            {
                "properties": {
                    "analysis_revision": {
                        "minLength": 1,
                        "type": "string",
                    },
                    "evidence_reference": {
                        "minLength": 1,
                        "type": "string",
                    },
                    "type": {"const": "respect_code_analysis"},
                },
                "required": [
                    "type",
                    "analysis_revision",
                    "evidence_reference",
                ],
                "type": "object",
            },
            {
                "properties": {
                    "approval_reference": {
                        "minLength": 1,
                        "type": "string",
                    },
                    "extension_reference": {
                        "minLength": 1,
                        "type": "string",
                    },
                    "type": {"const": "explicit_testkit_extension"},
                },
                "required": [
                    "type",
                    "approval_reference",
                    "extension_reference",
                ],
                "type": "object",
            },
        ],
    }
    schema = json.loads(arguments.schema.read_text(encoding="utf-8"))
    schema["properties"]["schema_version"]["const"] = "1.3.0"
    schema["$defs"]["requirement_origin"] = origin_schema
    for definition, removed in (
        ("feature", REMOVED_FEATURE_FIELDS),
        ("row", REMOVED_ROW_FIELDS),
    ):
        properties = schema["$defs"][definition]["properties"]
        required = schema["$defs"][definition]["required"]
        for field in removed:
            properties.pop(field, None)
            if field in required:
                required.remove(field)
        properties["requirement_origin"] = {
            "$ref": "#/$defs/requirement_origin"
        }

    records = []
    for kind, values, id_field in (
        ("feature", matrix["features"], "feature_id"),
        ("row", matrix["rows"], "row_id"),
    ):
        for value in sorted(values, key=lambda item: item[id_field]):
            records.append(
                {
                    "frozen_hash": record_hash(value),
                    "kind": kind,
                    "origin": None,
                    "record_id": value[id_field],
                    "status": "unresolved_legacy",
                }
            )
    audit = {
        "artifact_type": "respect_testkit_legacy_provenance_audit",
        "format_version": "1.0.0",
        "matrix_id": matrix["matrix_id"],
        "matrix_version": matrix["matrix_version"],
        "records": records,
        "source_commit": arguments.source_commit,
        "source_matrix_semantic_hash": source_matrix_hash,
    }
    audit["audit_hash"] = digest(audit)
    write_json(arguments.matrix, matrix)
    write_json(arguments.schema, schema)
    write_json(arguments.audit, audit)


if __name__ == "__main__":
    main()
