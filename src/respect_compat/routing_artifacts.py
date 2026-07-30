# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Artifact builders that consume, but never reinterpret, classified results."""

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .routing import (
    ArtifactKind,
    AtomicResult,
    SubstituteFidelity,
)


def _canonical_hash(
    value: Dict[str, Any], excluded: Tuple[str, ...] = ()
) -> str:
    candidate = copy.deepcopy(value)
    for field_name in excluded:
        candidate.pop(field_name, None)
    encoded = json.dumps(
        candidate,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ArtifactBindings:
    target_id: str
    target_digest: str
    matrix_id: str
    matrix_version: str
    matrix_semantic_hash: str
    challenge: str
    evidence_ids: Tuple[str, ...]
    artifact_set_hash: str
    real_build_id: Optional[str] = None
    respect_revision: Optional[str] = None
    first_applicable_version: Optional[str] = None
    last_applicable_version: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        required = (
            self.target_id,
            self.target_digest,
            self.matrix_id,
            self.matrix_version,
            self.matrix_semantic_hash,
            self.challenge,
            self.artifact_set_hash,
        )
        if not all(required) or not self.evidence_ids:
            raise ValueError("complete artifact bindings are required")

    def to_json_dict(self) -> Dict[str, Any]:
        value = {
            "target_id": self.target_id,
            "target_digest": self.target_digest,
            "matrix_id": self.matrix_id,
            "matrix_version": self.matrix_version,
            "matrix_semantic_hash": self.matrix_semantic_hash,
            "challenge": self.challenge,
            "evidence_ids": list(self.evidence_ids),
            "artifact_set_hash": self.artifact_set_hash,
        }
        optional = {
            "real_build_id": self.real_build_id,
            "respect_revision": self.respect_revision,
            "first_applicable_version": self.first_applicable_version,
            "last_applicable_version": self.last_applicable_version,
        }
        value.update(
            {
                key: item
                for key, item in optional.items()
                if item is not None
            }
        )
        return value


def _with_core_hash(value: Dict[str, Any]) -> Dict[str, Any]:
    value["core_hash"] = _canonical_hash(value, ("core_hash",))
    return value


def build_promotion_packet(
    result: AtomicResult,
    bindings: ArtifactBindings,
    fidelity: SubstituteFidelity,
) -> Dict[str, Any]:
    if ArtifactKind.PROMOTION_PACKET not in result.artifacts:
        raise ValueError("classified result does not authorize a promotion packet")
    packet = {
        "artifact_type": "respect_promotion_packet",
        "format_version": "2.0.0",
        **bindings.to_json_dict(),
        "row_id": result.row_id,
        "responsible_party": result.responsible_party.value,
        "workflow_disposition": result.workflow_disposition.value,
        "substitute": {
            "id": fidelity.substitute_id,
            "version": fidelity.substitute_version,
            "owner": fidelity.owner.value,
            "fidelity_guarantees": list(fidelity.fidelity_guarantees),
            "evidence_schema": fidelity.evidence_schema,
        },
        "covered_semantics": list(fidelity.covered_semantics),
        "excluded_semantics": list(fidelity.excluded_semantics),
        "real_dependency": fidelity.real_dependency,
        "clearance": fidelity.clearance,
        "promotion_test": fidelity.promotion_test,
        "rerun_scope": fidelity.rerun_scope,
    }
    return _with_core_hash(packet)


def _verify_packet(
    packet: Dict[str, Any],
    bindings: ArtifactBindings,
    artifact_type: str,
) -> List[str]:
    errors: List[str] = []
    if packet.get("artifact_type") != artifact_type:
        errors.append("artifact type mismatch")
    if packet.get("format_version") != "2.0.0":
        errors.append("format version mismatch")
    for field_name, expected in bindings.to_json_dict().items():
        if packet.get(field_name) != expected:
            errors.append(f"{field_name} binding mismatch")
    if packet.get("core_hash") != _canonical_hash(
        packet, ("core_hash", "suite_issuance")
    ):
        errors.append("core hash mismatch")
    return sorted(set(errors))


def verify_promotion_packet(
    packet: Dict[str, Any], bindings: ArtifactBindings
) -> List[str]:
    return _verify_packet(packet, bindings, "respect_promotion_packet")


def project_kit_tasks(
    results: Iterable[AtomicResult],
) -> List[Dict[str, Any]]:
    tasks = []
    for result in results:
        if ArtifactKind.KIT_TASK not in result.artifacts:
            continue
        tasks.append(
            {
                "task_id": f"repair:{result.row_id}",
                "row_id": result.row_id,
                "responsible_party": result.responsible_party.value,
                "workflow_disposition": result.workflow_disposition.value,
            }
        )
    return sorted(tasks, key=lambda item: item["task_id"])


def _unsafe_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_unsafe_reference(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_unsafe_reference(item) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    if lowered.startswith(("file:", "http://", "https://")):
        return True
    path = PurePosixPath(value.split("#", 1)[0])
    return path.is_absolute() or ".." in path.parts or "\\" in value


def project_destination_evidence(
    evidence: Mapping[str, Dict[str, Any]],
    destination: str,
) -> List[Dict[str, Any]]:
    if destination not in {"kit", "public"}:
        raise ValueError(f"unknown evidence destination: {destination}")
    projected = []
    for evidence_id, item in evidence.items():
        if item.get("destination") != destination:
            continue
        candidate = copy.deepcopy(item)
        if candidate.get("evidence_id") != evidence_id:
            raise ValueError("evidence identifier binding mismatch")
        if _unsafe_reference(candidate):
            raise ValueError(
                f"unsafe reference in {destination} evidence {evidence_id}"
            )
        projected.append(candidate)
    return sorted(projected, key=lambda item: item["evidence_id"])
