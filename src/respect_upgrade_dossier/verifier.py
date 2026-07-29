# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Narrow, non-certifying Dossier verifier."""

from typing import Any, Dict, List, Mapping

from jsonschema import Draft202012Validator

from .generator import canonical_hash
from .resources import load_schema


def verify_dossier(dossier: Mapping[str, Any]) -> Dict[str, Any]:
    errors: List[str] = [
        error.message
        for error in Draft202012Validator(
            load_schema("upgrade_dossier_v2.schema.json")
        ).iter_errors(dossier)
    ]
    if dossier.get("semantic_hash") != canonical_hash(
        dossier, "semantic_hash"
    ):
        errors.append("Dossier semantic hash mismatch")
    return {
        "artifact_type": "respect_upgrade_dossier_verification",
        "format_version": "2.0.0",
        "dossier_id": dossier.get("dossier_id"),
        "valid": not errors,
        "non_certifying": True,
        "errors": sorted(set(errors)),
    }
