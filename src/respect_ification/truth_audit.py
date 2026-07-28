# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, Iterable, List

from respect_compat.matrix_runtime import CompatibilityMatrix


_CANAPP_REPAIR_FAMILIES = {
    "RCF-ANDROID-LAUNCH": {
        "implementation_targets": [
            "CanApp Android manifest and production launch handling",
            "owner-controlled Digital Asset Links publication when applicable",
        ],
        "source_seams": ["manifest", "launch", "build"],
        "evidence_class": "submitted APK plus attributable Android routing",
    },
    "RCF-CANAPP-LIFECYCLE": {
        "implementation_targets": [
            "CanApp production lifecycle and xAPI client disposal",
        ],
        "source_seams": ["lifecycle", "xapi"],
        "evidence_class": "suite-observed disposal before test-forced process cleanup",
    },
    "RCF-DESCRIPTOR": {
        "implementation_targets": [
            "source-derived CanApp descriptor at the declared publication origin",
        ],
        "source_seams": ["catalog_discovery", "selection", "launch"],
        "evidence_class": "live served descriptor and reachable linked behavior",
    },
    "RCF-HTTP": {
        "implementation_targets": [
            "real publication server behavior for source-derived resources",
        ],
        "source_seams": ["catalog_discovery", "remote_acquisition"],
        "evidence_class": "live HTTP request and response exchange",
    },
    "RCF-MANIFEST": {
        "implementation_targets": [
            "truthful legacy CanApp descriptor and its reachable resources",
        ],
        "source_seams": ["manifest", "launch", "catalog_discovery"],
        "evidence_class": "served artifact, linked-resource, and schema observations",
    },
    "RCF-OPDS": {
        "implementation_targets": [
            "source-derived OPDS and Readium publication graph",
            "CanApp selection and loading of the exact acquired lesson",
        ],
        "source_seams": [
            "catalog_discovery",
            "selection",
            "storage_or_loading",
            "remote_acquisition",
        ],
        "evidence_class": "live catalog traversal tied to real lesson resources",
    },
    "RCF-RUSTICI-LAUNCH": {
        "implementation_targets": [
            "CanApp production launch parsing, lesson selection, and session state",
        ],
        "source_seams": ["launch", "selection", "xapi"],
        "evidence_class": "suite-issued launch values observed in real runtime behavior",
    },
    "RCF-XAPI": {
        "implementation_targets": [
            "CanApp production xAPI statement, retrieval, and response-processing code",
        ],
        "source_seams": ["xapi", "completion", "selection", "lifecycle"],
        "evidence_class": "nonce-bound requests and responses caused by real lesson behavior",
    },
    "RCF-XAPI-AUTH": {
        "implementation_targets": [
            "CanApp production session authentication and actor binding",
        ],
        "source_seams": ["launch", "xapi"],
        "evidence_class": "suite-issued credentials and actor observed in real requests",
    },
    "RCF-XAPI-HTTP": {
        "implementation_targets": [
            "Web CanApp production xAPI transport",
        ],
        "source_seams": ["launch", "xapi"],
        "evidence_class": "live request to the suite-issued endpoint",
    },
    "RCF-XAPI-IPC": {
        "implementation_targets": [
            "Native CanApp production xAPI-over-IPC client",
            "CanApp Android package visibility declaration",
        ],
        "source_seams": ["manifest", "xapi", "lifecycle"],
        "evidence_class": "submitted APK plus suite-observed interprocess exchange",
    },
}

_COMMON_FORBIDDEN_SUBSTITUTES = [
    "owner-authored pass flag or result assertion",
    "fixture metadata presented as arbitrary-CanApp runtime evidence",
    "debug-only or Test-Suite-recognizing CanApp behavior",
    "suite companion behavior credited to the CanApp",
    "placeholder or invented publication fact",
    "structurally valid artifact disconnected from real lesson selection and runtime",
]


def _raw_rows(matrix: CompatibilityMatrix) -> Dict[str, Dict[str, Any]]:
    return {item["row_id"]: item for item in matrix.raw["rows"]}


def build_matrix_truth_audit(
    matrix: CompatibilityMatrix,
) -> Dict[str, Any]:
    raw_rows = _raw_rows(matrix)
    audit_rows: List[Dict[str, Any]] = []
    for row in sorted(matrix.rows.values(), key=lambda item: item.row_id):
        raw = raw_rows[row.row_id]
        if row.owner == "canapp":
            family = _CANAPP_REPAIR_FAMILIES.get(row.feature_id)
            if family is None:
                raise ValueError(
                    f"CanApp Matrix row has no Kit truth contract: {row.row_id}"
                )
            audit_rows.append(
                {
                    "row_id": row.row_id,
                    "title": row.title,
                    "owner": row.owner,
                    "kit_disposition": "durable_canapp_repair_required",
                    "repair_family": row.feature_id,
                    "implementation_targets": list(
                        family["implementation_targets"]
                    ),
                    "source_seams": list(family["source_seams"]),
                    "required_evidence_class": family["evidence_class"],
                    "applicability_predicate": row.applicability_predicate,
                    "canapp_behavior": raw["canapp_behavior"],
                    "positive_case": raw["positive_case"],
                    "negative_case": raw["negative_case"],
                    "test_action": raw["test_action"],
                    "required_tooling": list(row.required_tooling),
                    "forbidden_substitutes": list(
                        _COMMON_FORBIDDEN_SUBSTITUTES
                    ),
                    "durable_product_change_required": True,
                }
            )
        else:
            audit_rows.append(
                {
                    "row_id": row.row_id,
                    "title": row.title,
                    "owner": row.owner,
                    "kit_disposition": "protected_non_canapp_requirement",
                    "repair_family": None,
                    "implementation_targets": [],
                    "source_seams": [],
                    "required_evidence_class": (
                        "evidence from the named non-CanApp requirement owner"
                    ),
                    "applicability_predicate": row.applicability_predicate,
                    "canapp_behavior": raw["canapp_behavior"],
                    "positive_case": raw["positive_case"],
                    "negative_case": raw["negative_case"],
                    "test_action": raw["test_action"],
                    "required_tooling": list(row.required_tooling),
                    "forbidden_substitutes": [
                        "CanApp repair task for behavior owned by another actor",
                        "CanApp evidence substituted for RESPECT or Test Suite behavior",
                    ],
                    "durable_product_change_required": False,
                }
            )
    canapp_count = sum(
        item["owner"] == "canapp" for item in audit_rows
    )
    core = {
        "artifact_type": "respect_ification_matrix_truth_audit",
        "format_version": "1.0.0",
        "matrix_id": matrix.matrix_id,
        "matrix_version": matrix.matrix_version,
        "matrix_semantic_hash": matrix.semantic_hash,
        "summary": {
            "row_count": len(audit_rows),
            "canapp_repair_row_count": canapp_count,
            "protected_non_canapp_row_count": len(audit_rows) - canapp_count,
            "uncovered_row_count": 0,
        },
        "rows": audit_rows,
    }
    return core


def select_truth_contracts(
    audit: Dict[str, Any],
    row_ids: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    by_id = {item["row_id"]: item for item in audit["rows"]}
    selected = {}
    for row_id in row_ids:
        item = by_id.get(row_id)
        if item is None:
            raise ValueError(f"unknown Matrix truth-audit row: {row_id}")
        if item["kit_disposition"] != "durable_canapp_repair_required":
            raise ValueError(
                f"Kit cannot create a CanApp repair for {row_id} "
                f"owned by {item['owner']}"
            )
        selected[row_id] = item
    return selected
