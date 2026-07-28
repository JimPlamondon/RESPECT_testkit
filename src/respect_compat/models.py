# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ResultState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    INCOMPLETE = "incomplete"
    DEFERRED = "deferred"
    HARNESS_ERROR = "harness_error"
    BLOCKED = "blocked"

    # Compatibility aliases for the partial v0.1 fixture harness.
    WARNING = "incomplete"
    SKIPPED = "not_applicable"


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    result: ResultState
    source_uri: str
    expected: Any
    observed: Any
    message: str
    evidence: str
    profile: str
    target: str
    security_mode: str
    field_path: Optional[str] = None
    disposition: Optional[str] = None

    def to_json_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["result"] = self.result.value
        return {key: data[key] for key in sorted(data)}


def worst_exit_code(results: list[RuleResult]) -> int:
    return 1 if any(result.result == ResultState.FAIL for result in results) else 0


class RequirementOwner(str, Enum):
    CANAPP = "canapp"
    RESPECT_LAUNCHER = "respect_launcher"
    RESPECT_SERVICE = "respect_service"
    TEST_SUITE = "test_suite"
    PROFILE_OWNER = "profile_owner"


@dataclass(frozen=True)
class ActorHealth:
    actor_id: str
    healthy: bool
    positive_control: str
    negative_control: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    kind: str
    source: str
    observed: Any
    target_digest: str
    scenario_nonce: str
    actor_id: Optional[str] = None

    def to_json_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MatrixRowResult:
    row_id: str
    test_case_ids: List[str]
    feature_id: str
    owner: RequirementOwner
    state: ResultState
    expected: Any
    observed: Any
    message: str
    target_digest: str
    scenario_nonce: str
    evidence: List[EvidenceRecord]
    source_refs: List[str]
    failure_domain: str
    repair_guidance: Optional[str] = None

    @property
    def contributes_to_canapp_verdict(self) -> bool:
        return self.owner == RequirementOwner.CANAPP

    def to_json_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["owner"] = self.owner.value
        data["state"] = self.state.value
        data["contributes_to_canapp_verdict"] = self.contributes_to_canapp_verdict
        return data


@dataclass(frozen=True)
class Coverage:
    selected: List[str]
    executed: List[str]
    passed: List[str]
    failed: List[str]
    not_applicable: List[str]
    incomplete: List[str]
    deferred: List[str]
    harness_error: List[str]
    blocked: List[str]

    def to_json_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CertificationProvision:
    code: str
    label: str
    explanation: str
    affected_rows: List[str]
    evidence: Dict[str, Any]
    clearance: str
    rerun_scope: str
    responsible_party: str

    def to_json_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CertificationVerdict:
    certified: bool
    state: str
    display: str
    reason: str
    provisions: List[CertificationProvision] = field(default_factory=list)

    def to_json_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["provisions"] = [
            provision.to_json_dict() for provision in self.provisions
        ]
        return data


@dataclass(frozen=True)
class SuiteRun:
    suite_version: str
    run_id: str
    matrix_id: str
    matrix_version: str
    matrix_semantic_hash: str
    profile_id: str
    mode: str
    target_uri: str
    target_adapter: str
    target_digest: str
    scenario_nonce: str
    results: List[MatrixRowResult]
    coverage: Coverage
    verdict: CertificationVerdict
    actor_health: List[ActorHealth]
    capabilities: List[str]
    evidence_environment: Dict[str, Any]

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "suite_version": self.suite_version,
            "run_id": self.run_id,
            "matrix_id": self.matrix_id,
            "matrix_version": self.matrix_version,
            "matrix_semantic_hash": self.matrix_semantic_hash,
            "profile_id": self.profile_id,
            "mode": self.mode,
            "target_uri": self.target_uri,
            "target_adapter": self.target_adapter,
            "target_digest": self.target_digest,
            "scenario_nonce": self.scenario_nonce,
            "capabilities": sorted(self.capabilities),
            "evidence_environment": self.evidence_environment,
            "actor_health": [item.to_json_dict() for item in self.actor_health],
            "coverage": self.coverage.to_json_dict(),
            "verdict": self.verdict.to_json_dict(),
            "results": [item.to_json_dict() for item in self.results],
        }
