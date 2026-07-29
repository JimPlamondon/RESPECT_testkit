# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed Dossier generator for qualifying platform-gap packets."""

import copy
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from respect_compat.routing_artifacts import (
    ArtifactBindings,
    verify_platform_gap_packet,
)

from .resources import load_schema
from .trust import FailClosedTrustPolicy, TrustPolicy


def canonical_hash(value: Mapping[str, Any], *excluded: str) -> str:
    candidate = copy.deepcopy(dict(value))
    for field_name in excluded:
        candidate.pop(field_name, None)
    return hashlib.sha256(
        json.dumps(
            candidate,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _contains_unsafe_reference(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_unsafe_reference(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_unsafe_reference(item) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    if lowered.startswith(("file:", "http://", "https://")):
        return True
    path = PurePosixPath(value.split("#", 1)[0])
    return path.is_absolute() or ".." in path.parts or "\\" in value


def _bindings(packet: Mapping[str, Any]) -> ArtifactBindings:
    return ArtifactBindings(
        target_id=packet["target_id"],
        target_digest=packet["target_digest"],
        matrix_id=packet["matrix_id"],
        matrix_version=packet["matrix_version"],
        matrix_semantic_hash=packet["matrix_semantic_hash"],
        challenge=packet["challenge"],
        evidence_ids=tuple(packet["evidence_ids"]),
        artifact_set_hash=packet["artifact_set_hash"],
        real_build_id=packet["real_build_id"],
        respect_revision=packet["respect_revision"],
        first_applicable_version=packet["first_applicable_version"],
        last_applicable_version=packet.get("last_applicable_version"),
    )


def validate_platform_packet(
    packet: Mapping[str, Any],
    trust_policy: TrustPolicy,
) -> None:
    reference_bearing_fields = (
        "target_id",
        "evidence_ids",
        "real_build_id",
        "respect_revision",
    )
    if any(
        _contains_unsafe_reference(packet.get(field_name))
        for field_name in reference_bearing_fields
    ):
        raise ValueError("platform-gap packet contains an unsafe reference")
    validator = Draft202012Validator(
        load_schema("platform_gap_packet_acceptance_v2.schema.json")
    )
    errors = sorted(validator.iter_errors(packet), key=lambda item: list(item.path))
    if errors:
        raise ValueError(f"invalid platform-gap packet: {errors[0].message}")
    packet_dict = dict(packet)
    if verify_platform_gap_packet(packet_dict, _bindings(packet_dict)):
        raise ValueError("platform-gap packet binding verification failed")
    if not trust_policy.approve_platform_packet(packet):
        raise ValueError("platform-gap packet is not issued by an approved Suite key")


def generate_dossier(
    packet: Mapping[str, Any],
    details: Mapping[str, Any],
    trust_policy: TrustPolicy = FailClosedTrustPolicy(),
) -> Dict[str, Any]:
    validate_platform_packet(packet, trust_policy)
    required_details = {
        "affected_features",
        "affected_profiles",
        "normative_source",
        "applicability",
        "independently_attributable_behavior",
        "upgrade_guidance",
        "security_implications",
        "privacy_implications",
        "compatibility_considerations",
        "migration_considerations",
        "deployment_considerations",
        "rollback_considerations",
        "acceptance_contract",
        "dependencies",
    }
    missing = required_details - set(details)
    if missing:
        raise ValueError(f"Dossier details missing: {', '.join(sorted(missing))}")
    dossier_id = "respect-upgrade-" + canonical_hash(
        {
            "packet": packet["core_hash"],
            "row": packet["row_id"],
            "build": packet["real_build_id"],
        }
    )[:24]
    dossier = {
        "artifact_type": "respect_upgrade_dossier",
        "format_version": "2.0.0",
        "dossier_id": dossier_id,
        "state": "identified",
        "affected_features": list(details["affected_features"]),
        "affected_rows": [packet["row_id"]],
        "affected_profiles": list(details["affected_profiles"]),
        "normative_source": details["normative_source"],
        "applicability": details["applicability"],
        "pinned_respect": {
            "real_build_id": packet["real_build_id"],
            "respect_revision": packet["respect_revision"],
            "first_applicable_version": packet["first_applicable_version"],
            "last_applicable_version": packet.get("last_applicable_version"),
        },
        "independently_attributable_behavior": details[
            "independently_attributable_behavior"
        ],
        "upgrade_guidance": details["upgrade_guidance"],
        "security_implications": details["security_implications"],
        "privacy_implications": details["privacy_implications"],
        "compatibility_considerations": details[
            "compatibility_considerations"
        ],
        "migration_considerations": details["migration_considerations"],
        "deployment_considerations": details["deployment_considerations"],
        "rollback_considerations": details["rollback_considerations"],
        "acceptance_contract": details["acceptance_contract"],
        "dependencies": list(details["dependencies"]),
        "evidence_bindings": {
            key: copy.deepcopy(packet[key])
            for key in (
                "target_id",
                "target_digest",
                "matrix_id",
                "matrix_version",
                "matrix_semantic_hash",
                "challenge",
                "evidence_ids",
                "artifact_set_hash",
            )
        },
        "source_packet_core_hash": packet["core_hash"],
    }
    dossier["semantic_hash"] = canonical_hash(dossier, "semantic_hash")
    errors = list(
        Draft202012Validator(
            load_schema("upgrade_dossier_v2.schema.json")
        ).iter_errors(dossier)
    )
    if errors:
        raise ValueError(f"generated Dossier is invalid: {errors[0].message}")
    return dossier
