# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .resources import resource


DEFAULT_MATRIX_PATH = resource("data/matrix/compatibility_matrix.json")


def semantic_hash(data: Dict[str, Any]) -> str:
    candidate = copy.deepcopy(data)
    candidate.pop("semantic_hash", None)
    payload = json.dumps(
        candidate,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class MatrixProfile:
    profile_id: str
    title: str
    lifecycle_status: str


@dataclass(frozen=True)
class MatrixFeature:
    feature_id: str
    title: str
    owner: str
    lifecycle_status: str
    requirement_status: str
    testability_status: str
    conformance_disposition: str
    profile_ids: List[str]
    row_ids: List[str]
    guidance: str


@dataclass(frozen=True)
class MatrixRow:
    row_id: str
    feature_id: str
    title: str
    owner: str
    profile_ids: List[str]
    test_case_ids: List[str]
    required_tooling: List[str]
    applicability_predicate: str
    expected_output: str
    source_refs: List[str]
    outcomes: Dict[str, Any]
    control_owner: str
    responsible_party: str
    applicability_evaluator: str
    routing_contract: str
    verification_modes: List[str]
    substitute_fidelity_contract: Optional[Dict[str, Any]]


ApplicabilityEvaluator = Callable[
    [MatrixRow, MatrixFeature, str], bool
]


def _profile_and_feature_selection(
    row: MatrixRow, feature: MatrixFeature, profile_id: str
) -> bool:
    return (
        profile_id in row.profile_ids
        and profile_id in feature.profile_ids
        and feature.testability_status
        in {
            "executable_now",
            "executable_with_tooling",
            "partially_executable",
        }
    )


APPLICABILITY_EVALUATORS: Dict[str, ApplicabilityEvaluator] = {
    "profile_and_feature_selection": _profile_and_feature_selection,
}


@dataclass(frozen=True)
class CompatibilityMatrix:
    matrix_id: str
    matrix_version: str
    semantic_hash: str
    profiles: Dict[str, MatrixProfile]
    features: Dict[str, MatrixFeature]
    rows: Dict[str, MatrixRow]
    raw: Dict[str, Any]

    def resolve_profile(self, value: str) -> MatrixProfile:
        by_id = self.profiles.get(value)
        if by_id:
            return by_id
        matches = [item for item in self.profiles.values() if item.title == value]
        if len(matches) == 1:
            return matches[0]
        raise ValueError(f"unknown Matrix profile: {value}")

    def selected_rows(self, profile_id: str) -> List[MatrixRow]:
        profile_id = self.resolve_profile(profile_id).profile_id
        selected = []
        for row in self.rows.values():
            feature = self.features[row.feature_id]
            evaluator = APPLICABILITY_EVALUATORS.get(
                row.applicability_evaluator
            )
            if evaluator is None:
                raise ValueError(
                    "unknown Matrix applicability evaluator: "
                    f"{row.applicability_evaluator}"
                )
            if not evaluator(row, feature, profile_id):
                continue
            selected.append(row)
        return sorted(selected, key=lambda item: item.row_id)

    def feature_for(self, row: MatrixRow) -> MatrixFeature:
        return self.features[row.feature_id]

    def all_test_case_ids(self) -> Iterable[str]:
        for row in self.rows.values():
            yield from row.test_case_ids


def load_matrix(path: Path = DEFAULT_MATRIX_PATH) -> CompatibilityMatrix:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("canonical Matrix root must be an object")
    for field in ("profiles", "features", "rows"):
        if not isinstance(data.get(field), list):
            raise ValueError(f"canonical Matrix {field} must be an array")
    if data.get("status") != "ready":
        raise ValueError("canonical Matrix is not ready")
    expected_hash = data.get("semantic_hash")
    actual_hash = semantic_hash(data)
    if expected_hash != actual_hash:
        raise ValueError(
            f"canonical Matrix semantic hash mismatch: expected {expected_hash}, calculated {actual_hash}"
        )
    try:
        profiles = {
            item["profile_id"]: MatrixProfile(
                profile_id=item["profile_id"],
                title=item["title"],
                lifecycle_status=item["lifecycle_status"],
            )
            for item in data["profiles"]
        }
        features = {
            item["feature_id"]: MatrixFeature(
                feature_id=item["feature_id"],
                title=item["title"],
                owner=item["requirement_owner"],
                lifecycle_status=item["lifecycle_status"],
                requirement_status=item["requirement_status"],
                testability_status=item["testability_status"],
                conformance_disposition=item["conformance_disposition"],
                profile_ids=list(item["profile_ids"]),
                row_ids=list(item["row_ids"]),
                guidance=item["respect_ification_guidance"],
            )
            for item in data["features"]
        }
        rows = {
            item["row_id"]: MatrixRow(
                row_id=item["row_id"],
                feature_id=item["feature_id"],
                title=item["title"],
                owner=item["requirement_owner"],
                profile_ids=list(item["profile_ids"]),
                test_case_ids=list(item["test_case_ids"]),
                required_tooling=list(item["required_tooling"]),
                applicability_predicate=item["applicability_predicate"],
                expected_output=item["requirement_statement"]["expected_output"],
                source_refs=list(item["source_refs"]),
                outcomes=copy.deepcopy(item["outcomes"]),
                control_owner=item["control_owner"],
                responsible_party=item["responsible_party"],
                applicability_evaluator=item[
                    "applicability_evaluator"
                ],
                routing_contract=item["routing_contract"],
                verification_modes=list(item["verification_modes"]),
                substitute_fidelity_contract=copy.deepcopy(
                    item["substitute_fidelity_contract"]
                ),
            )
            for item in data["rows"]
        }
    except (KeyError, TypeError) as error:
        raise ValueError(
            f"canonical Matrix structure is invalid: {error}"
        ) from error
    if set(rows) != {
        row_id for feature in features.values() for row_id in feature.row_ids
    }:
        raise ValueError("canonical Matrix feature-to-row closure mismatch")
    test_case_ids = [item for row in rows.values() for item in row.test_case_ids]
    if len(test_case_ids) != len(set(test_case_ids)):
        raise ValueError("canonical Matrix has duplicate test-case identifiers")
    return CompatibilityMatrix(
        matrix_id=data["matrix_id"],
        matrix_version=data["matrix_version"],
        semantic_hash=expected_hash,
        profiles=profiles,
        features=features,
        rows=rows,
        raw=data,
    )
