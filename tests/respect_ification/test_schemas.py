# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json

from jsonschema import Draft202012Validator
from respect_ification.resources import resource


def test_runtime_schemas_compile():
    root = resource("data/schemas")
    schemas = sorted(root.iterdir(), key=lambda item: item.name)
    assert {item.name for item in schemas} == {
        "evidence_manifest.schema.json",
        "ledger_event.schema.json",
        "private_prep.schema.json",
        "public_prep.schema.json",
        "task_packet.schema.json",
        "work_plan.schema.json",
    }
    for path in schemas:
        Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_publication_manifest_schema_compiles():
    path = resource(
        "data/publication/publication_manifest.schema.json"
    )
    Draft202012Validator.check_schema(json.loads(path.read_text()))
