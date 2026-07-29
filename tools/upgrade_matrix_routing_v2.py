#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Apply the deterministic responsibility-routing fields to the Matrix."""

import argparse
import json
from pathlib import Path

from respect_compat.matrix_runtime import semantic_hash


OWNER_BINDINGS = {
    "canapp": ("canapp_artifact", "canapp_artifact_owner"),
    "publisher": ("publisher", "publisher"),
    "spix_foundation": ("spix_foundation", "spix_foundation"),
    "respect_launcher": ("respect_platform", "respect_platform_team"),
    "respect_service": ("respect_platform", "respect_platform_team"),
    "test_suite": ("testkit", "testkit_team"),
    "profile_owner": (
        "specification_authority",
        "specification_authority",
    ),
}


def substitute_contract(prefix: str):
    semantics = {
        "DESC": [
            "descriptor schema",
            "descriptor-to-catalog and launch relationships",
        ],
        "HTTP": [
            "publication response status and media type",
            "content length, validators, and conditional requests",
        ],
        "OPDS": [
            "catalog and publication graph",
            "declared lesson resource integrity",
        ],
    }.get(prefix)
    if semantics is None:
        return None
    return {
        "substitute_id": "local_https_publication",
        "substitute_version": "1",
        "owner": "appdev_publication",
        "covered_semantics": semantics,
        "excluded_semantics": [
            "stable owner-controlled public origin",
            "public DNS, routing, and production operations",
        ],
        "fidelity_guarantees": [
            "the substitute serves the unchanged publication bytes",
            "the same Suite oracle is used for substitute and real modes",
        ],
        "evidence_schema": "respect-substitute-evidence-v2",
        "real_dependency": "owner-controlled HTTPS publication",
        "clearance": "deploy the unchanged publication at the declared origin",
        "promotion_test": "rerun the affected rows against the declared origin",
        "rerun_scope": "affected_rows",
    }


def upgrade(data):
    data["schema_version"] = "1.2.0"
    data["matrix_version"] = "1.1.0"
    for feature in data["features"]:
        owner = feature["requirement_owner"]
        if owner in {"respect_launcher", "respect_service"}:
            guidance = (
                "Route only independently attributable, signed real-platform "
                "evidence through a platform-gap packet and Upgrade Dossier."
            )
        elif (
            feature["requirement_status"] == "upstream_gap"
            or feature["conformance_disposition"] == "upstream_gap"
        ):
            guidance = (
                "Resolve the normative behavior and preserve a feature-addressed "
                "acceptance contract before any platform implementation can close."
            )
        else:
            guidance = (
                "No RESPECT platform work is authorized by this feature; route "
                "observations through the typed responsibility classifier."
            )
        feature["respect_upgrade_guidance"] = guidance
        if (
            (
                feature["requirement_status"] == "upstream_gap"
                or feature["conformance_disposition"] == "upstream_gap"
            )
            and not feature["row_ids"]
        ):
            feature["feature_work_unit"] = {
                "feature_id": feature["feature_id"],
                "responsible_party": (
                    "specification_authority"
                    if "GAP" in feature["feature_id"]
                    else "respect_platform_team"
                ),
                "acceptance_contract": (
                    "Add a unique normative oracle, atomic Matrix rows, and "
                    "production-path positive and isolated-negative tests."
                ),
                "closure_requires_executable_acceptance": True,
            }
        else:
            feature["feature_work_unit"] = None
    for row in data["rows"]:
        owner = row["requirement_owner"]
        control_owner, responsible_party = OWNER_BINDINGS[owner]
        row["control_owner"] = control_owner
        row["responsible_party"] = responsible_party
        row["applicability_evaluator"] = "profile_and_feature_selection"
        row["routing_contract"] = "respect_compat.routing.ROUTING_TABLE"
        row["platform_gap_eligible"] = owner in {
            "respect_launcher",
            "respect_service",
        }
        row["dossier_acceptance_test"] = (
            f"matrix-row:{row['row_id']}"
            if row["platform_gap_eligible"]
            else None
        )
        if owner in {"respect_launcher", "respect_service"}:
            row["verification_modes"] = ["real", "unavailable"]
        elif owner == "test_suite":
            row["verification_modes"] = ["production_meta_test"]
        elif owner == "canapp":
            row["verification_modes"] = [
                "real",
                "substitute",
                "fixture",
                "static",
                "unavailable",
            ]
        else:
            row["verification_modes"] = ["real", "unavailable"]
        row["substitute_fidelity_contract"] = (
            substitute_contract(row["row_id"].split("-", 1)[0])
            if owner == "canapp"
            else None
        )
    data["semantic_hash"] = "pending"
    data["semantic_hash"] = semantic_hash(data)
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.matrix.read_text(encoding="utf-8"))
    args.matrix.write_text(
        json.dumps(upgrade(data), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
