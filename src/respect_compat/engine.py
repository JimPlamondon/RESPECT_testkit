# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .matrix_runtime import CompatibilityMatrix, MatrixRow
from .models import (
    ActorHealth,
    CertificationProvision,
    CertificationVerdict,
    Coverage,
    EvidenceRecord,
    MatrixRowResult,
    RequirementOwner,
    ResultState,
    SuiteRun,
)
from .provisions import (
    classify_evidence_environment,
    derive_provisions,
    provisional_display,
)
from .target import CanAppTarget


SUITE_VERSION = "1.0.0"
Executor = Callable[["ExecutionContext", MatrixRow], MatrixRowResult]


@dataclass
class ExecutionContext:
    matrix: CompatibilityMatrix
    target: CanAppTarget
    profile_id: str
    mode: str
    run_id: str
    scenario_nonce: str
    actors: List[ActorHealth] = field(default_factory=list)

    def evidence(
        self,
        row: MatrixRow,
        kind: str,
        source: str,
        observed: object,
        actor_id: Optional[str] = None,
    ) -> EvidenceRecord:
        evidence_id = hashlib.sha256(
            f"{self.run_id}:{row.row_id}:{kind}:{source}:{json.dumps(observed, sort_keys=True, default=str)}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        return EvidenceRecord(
            evidence_id=evidence_id,
            kind=kind,
            source=source,
            observed=observed,
            target_digest=self.target.digest,
            scenario_nonce=self.scenario_nonce,
            actor_id=actor_id,
        )

    def result(
        self,
        row: MatrixRow,
        state: ResultState,
        observed: object,
        message: str,
        evidence: List[EvidenceRecord],
    ) -> MatrixRowResult:
        feature = self.matrix.feature_for(row)
        repair = feature.guidance if row.owner == RequirementOwner.CANAPP.value and state == ResultState.FAIL else None
        return MatrixRowResult(
            row_id=row.row_id,
            test_case_ids=row.test_case_ids,
            feature_id=row.feature_id,
            owner=RequirementOwner(row.owner),
            state=state,
            expected=row.expected_output,
            observed=observed,
            message=message,
            target_digest=self.target.digest,
            scenario_nonce=self.scenario_nonce,
            evidence=evidence,
            source_refs=row.source_refs,
            failure_domain=row.outcomes[state.value]["failure_domain"],
            repair_guidance=repair,
        )


class ExecutorRegistry:
    def __init__(self) -> None:
        self._executors: Dict[str, Executor] = {}

    def register(self, row_id: str, executor: Executor) -> None:
        if row_id in self._executors:
            raise ValueError(f"duplicate Matrix row executor: {row_id}")
        self._executors[row_id] = executor

    def register_many(self, row_ids: List[str], executor: Executor) -> None:
        for row_id in row_ids:
            self.register(row_id, executor)

    def executor_for(self, row_id: str) -> Optional[Executor]:
        return self._executors.get(row_id)

    @property
    def row_ids(self) -> set[str]:
        return set(self._executors)


def _coverage(selected: List[str], results: List[MatrixRowResult]) -> Coverage:
    by_state = {state: [] for state in ResultState}
    for result in results:
        by_state[result.state].append(result.row_id)
    executed = sorted(result.row_id for result in results)
    return Coverage(
        selected=sorted(selected),
        executed=executed,
        passed=sorted(by_state[ResultState.PASS]),
        failed=sorted(by_state[ResultState.FAIL]),
        not_applicable=sorted(by_state[ResultState.NOT_APPLICABLE]),
        incomplete=sorted(by_state[ResultState.INCOMPLETE]),
        deferred=sorted(by_state[ResultState.DEFERRED]),
        harness_error=sorted(by_state[ResultState.HARNESS_ERROR]),
        blocked=sorted(by_state[ResultState.BLOCKED]),
    )


def reduce_verdict(
    selected: List[MatrixRow],
    results: List[MatrixRowResult],
    mode: str,
    provisions: Optional[List[CertificationProvision]] = None,
) -> CertificationVerdict:
    provisions = provisions or []
    if mode != "certification":
        return CertificationVerdict(
            False,
            "non_certification_mode",
            "Non-certification mode",
            f"mode {mode} cannot certify",
        )
    selected_ids = {row.row_id for row in selected}
    result_ids = {result.row_id for result in results}
    if selected_ids != result_ids:
        missing = sorted(selected_ids - result_ids)
        extra = sorted(result_ids - selected_ids)
        return CertificationVerdict(
            False,
            "incomplete",
            "Incomplete",
            f"coverage mismatch; missing={missing}, extra={extra}",
            provisions,
        )
    canapp_results = [
        result for result in results if result.owner == RequirementOwner.CANAPP
    ]
    nonpass = [
        result
        for result in canapp_results
        if result.state not in {ResultState.PASS, ResultState.NOT_APPLICABLE}
    ]
    if nonpass:
        return CertificationVerdict(
            False,
            "not_certified",
            "Not certified",
            "applicable CanApp rows did not pass: "
            + ", ".join(f"{item.row_id}={item.state.value}" for item in nonpass),
            provisions,
        )
    if not canapp_results:
        return CertificationVerdict(
            False,
            "incomplete",
            "Incomplete",
            "profile selected no CanApp-owned rows",
            provisions,
        )
    if provisions:
        return CertificationVerdict(
            False,
            "provisional",
            provisional_display(provisions),
            (
                "all applicable CanApp-owned rows passed; "
                f"{len(provisions)} certification provision(s) remain"
            ),
            provisions,
        )
    return CertificationVerdict(
        True,
        "certified",
        "Certified",
        "all applicable CanApp-owned rows passed",
    )


def execute(
    matrix: CompatibilityMatrix,
    target: CanAppTarget,
    profile_value: str,
    mode: str,
    registry: ExecutorRegistry,
    run_seed: Optional[str] = None,
    selected_row_ids: Optional[List[str]] = None,
) -> SuiteRun:
    profile = matrix.resolve_profile(profile_value)
    selected = matrix.selected_rows(profile.profile_id)
    if selected_row_ids is not None:
        if mode == "certification":
            raise ValueError("partial Matrix-row execution cannot certify")
        requested = set(selected_row_ids)
        available = {row.row_id for row in selected}
        unknown = sorted(requested - available)
        if unknown:
            raise ValueError(
                f"rows are not selected by profile {profile.profile_id}: {unknown}"
            )
        selected = [row for row in selected if row.row_id in requested]
    effective_seed = run_seed or secrets.token_hex(32)
    run_id = hashlib.sha256(
        f"{effective_seed}:{matrix.semantic_hash}:{profile.profile_id}:{target.digest}:{mode}".encode("utf-8")
    ).hexdigest()[:24]
    nonce = hashlib.sha256(f"{run_id}:scenario".encode("utf-8")).hexdigest()[:24]
    context = ExecutionContext(
        matrix=matrix,
        target=target,
        profile_id=profile.profile_id,
        mode=mode,
        run_id=run_id,
        scenario_nonce=nonce,
    )
    results: List[MatrixRowResult] = []
    for row in selected:
        executor = registry.executor_for(row.row_id)
        if executor is None:
            evidence = [
                context.evidence(
                    row,
                    "executor_registry",
                    "suite",
                    {"registered": False, "row_id": row.row_id},
                )
            ]
            results.append(
                context.result(
                    row,
                    ResultState.INCOMPLETE,
                    "no registered executor",
                    "The Test Suite has no executor for this selected Matrix row.",
                    evidence,
                )
            )
            continue
        try:
            result = executor(context, row)
        except Exception as error:
            evidence = [
                context.evidence(
                    row,
                    "exception",
                    "suite",
                    {"type": type(error).__name__, "message": str(error)},
                )
            ]
            result = context.result(
                row,
                ResultState.HARNESS_ERROR,
                type(error).__name__,
                "The row executor raised an exception.",
                evidence,
            )
        if not result.evidence or any(
            item.target_digest != target.digest or item.scenario_nonce != nonce
            for item in result.evidence
        ):
            result = context.result(
                row,
                ResultState.INCOMPLETE,
                "unattributed evidence",
                "The row result lacked target-attributed scenario evidence.",
                [],
            )
        results.append(result)
    publication_prerequisites = target.metadata.setdefault(
        "_publication_prerequisites", {}
    )
    if isinstance(publication_prerequisites, dict):
        result_by_id = {item.row_id: item for item in results}
        for row_id, key in (
            ("PUBLISH-001", "authorization"),
            ("PUBLISH-002", "immutable_artifact"),
            ("PUBLISH-003", "certification_key"),
        ):
            result = result_by_id.get(row_id)
            if result is not None:
                publication_prerequisites.setdefault(
                    key,
                    {
                        "status": (
                            "valid"
                            if result.state == ResultState.PASS
                            else result.state.value
                        )
                    },
                )
    coverage = _coverage([row.row_id for row in selected], results)
    evidence_environment = classify_evidence_environment(target)
    provisions = derive_provisions(selected, evidence_environment, results)
    verdict = reduce_verdict(selected, results, mode, provisions)
    return SuiteRun(
        suite_version=SUITE_VERSION,
        run_id=run_id,
        matrix_id=matrix.matrix_id,
        matrix_version=matrix.matrix_version,
        matrix_semantic_hash=matrix.semantic_hash,
        profile_id=profile.profile_id,
        mode=mode,
        target_uri=target.uri,
        target_adapter=target.adapter,
        target_digest=target.digest,
        scenario_nonce=nonce,
        results=sorted(results, key=lambda item: item.row_id),
        coverage=coverage,
        verdict=verdict,
        actor_health=context.actors,
        capabilities=sorted(target.capabilities),
        evidence_environment=evidence_environment,
    )
