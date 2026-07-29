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
from .routing import (
    ClassificationInput,
    ControlOwner,
    ObservedResult,
    RoutingEvidence,
    SubstituteFidelity,
    VerificationMode,
    classify_result,
)
from .models import ResponsibleParty
from .target import CanAppTarget


SUITE_VERSION = "2.0.0"
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

    @property
    def challenge(self) -> str:
        return self.scenario_nonce

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
        atomic_result = self._classify(row, state, observed, evidence)
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
            atomic_result=atomic_result,
            repair_guidance=repair,
        )

    def _classify(
        self,
        row: MatrixRow,
        state: ResultState,
        observed: object,
        evidence: List[EvidenceRecord],
    ):
        owner = RequirementOwner(row.owner)
        control_owner = ControlOwner(row.control_owner)
        responsible_party = ResponsibleParty(row.responsible_party)
        verification_mode = (
            VerificationMode.PRODUCTION_META_TEST
            if owner == RequirementOwner.TEST_SUITE
            else VerificationMode.REAL
        )
        routing_evidence = RoutingEvidence(attributable=bool(evidence))
        observed_result = ObservedResult.PASS

        publication_kind = classify_evidence_environment(self.target)[
            "publication"
        ]["kind"]
        if state == ResultState.NOT_APPLICABLE:
            observed_result = ObservedResult.NOT_APPLICABLE
            verification_mode = VerificationMode.UNAVAILABLE
            control_owner = ControlOwner.NONE
            responsible_party = ResponsibleParty.NONE
        elif state == ResultState.HARNESS_ERROR:
            observed_result = ObservedResult.HARNESS_ERROR
            control_owner = ControlOwner.TESTKIT
            responsible_party = ResponsibleParty.TESTKIT_OPERATOR
            routing_evidence = RoutingEvidence(
                attributable=bool(evidence), actor_malfunction=True
            )
        elif state in {
            ResultState.BLOCKED,
            ResultState.INCOMPLETE,
            ResultState.DEFERRED,
        }:
            verification_mode = VerificationMode.UNAVAILABLE
            if owner in {
                RequirementOwner.RESPECT_LAUNCHER,
                RequirementOwner.RESPECT_SERVICE,
                RequirementOwner.TEST_SUITE,
            }:
                observed_result = ObservedResult.TESTKIT_CAPABILITY_GAP
                control_owner = ControlOwner.TESTKIT
                responsible_party = ResponsibleParty.TESTKIT_TEAM
                routing_evidence = RoutingEvidence(
                    attributable=bool(evidence), observer_present=False
                )
            else:
                observed_result = (
                    ObservedResult.UNMEASURED_EXTERNAL_DEPENDENCY
                )
        elif state == ResultState.FAIL:
            platform_evidence = (
                observed.get("platform_evidence")
                if isinstance(observed, dict)
                else None
            )
            if (
                owner
                in {
                    RequirementOwner.RESPECT_LAUNCHER,
                    RequirementOwner.RESPECT_SERVICE,
                }
                and isinstance(platform_evidence, dict)
            ):
                observed_result = ObservedResult.RESPECT_PLATFORM_GAP
                control_owner = ControlOwner.RESPECT_PLATFORM
                responsible_party = ResponsibleParty.RESPECT_PLATFORM_TEAM
                verification_mode = VerificationMode.REAL
                routing_evidence = RoutingEvidence(
                    attributable=bool(evidence),
                    signed=platform_evidence.get("signed") is True,
                    real_platform=platform_evidence.get("real_platform") is True,
                    independently_attributed=(
                        platform_evidence.get("independently_attributed") is True
                    ),
                    real_build_id=platform_evidence.get("real_build_id"),
                    respect_revision=platform_evidence.get("respect_revision"),
                    first_applicable_version=platform_evidence.get(
                        "first_applicable_version"
                    ),
                    last_applicable_version=platform_evidence.get(
                        "last_applicable_version"
                    ),
                )
            elif (
                owner == RequirementOwner.CANAPP
                and control_owner == ControlOwner.CANAPP_ARTIFACT
            ):
                observed_result = ObservedResult.CANAPP_IMPLEMENTATION_FAIL
            elif owner == RequirementOwner.TEST_SUITE:
                observed_result = ObservedResult.TESTKIT_CAPABILITY_GAP
                control_owner = ControlOwner.TESTKIT
                responsible_party = ResponsibleParty.TESTKIT_TEAM
            else:
                observed_result = (
                    ObservedResult.UNMEASURED_EXTERNAL_DEPENDENCY
                )
        elif (
            state == ResultState.PASS
            and owner == RequirementOwner.CANAPP
            and publication_kind == "local_https"
            and row.substitute_fidelity_contract is not None
        ):
            contract = row.substitute_fidelity_contract
            fidelity = SubstituteFidelity(
                substitute_id=contract["substitute_id"],
                substitute_version=contract["substitute_version"],
                owner=ResponsibleParty(contract["owner"]),
                covered_semantics=tuple(contract["covered_semantics"]),
                excluded_semantics=tuple(contract["excluded_semantics"]),
                fidelity_guarantees=tuple(contract["fidelity_guarantees"]),
                evidence_schema=contract["evidence_schema"],
                real_dependency=contract["real_dependency"],
                clearance=contract["clearance"],
                promotion_test=contract["promotion_test"],
                rerun_scope=contract["rerun_scope"],
            )
            observed_result = (
                ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE
            )
            verification_mode = VerificationMode.SUBSTITUTE
            routing_evidence = RoutingEvidence(
                attributable=True,
                positive_substitute=True,
                claimed_semantics=fidelity.covered_semantics,
                substitute_fidelity=fidelity,
            )
        elif (
            state == ResultState.PASS
            and owner == RequirementOwner.CANAPP
            and self.target.adapter == "fixture"
        ):
            observed_result = (
                ObservedResult.UNMEASURED_EXTERNAL_DEPENDENCY
            )
            verification_mode = VerificationMode.FIXTURE

        return classify_result(
            row.row_id,
            ClassificationInput(
                requirement_owner=owner,
                control_owner=control_owner,
                responsible_party=(
                    None
                    if observed_result == ObservedResult.PASS
                    else responsible_party
                ),
                verification_mode=verification_mode,
                observed_result=observed_result,
                evidence=routing_evidence,
            ),
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
    required = [
        result.atomic_result
        for result in results
        if result.atomic_result.policy_required
    ]
    nonfinal = [result for result in required if not result.final_affirmative]
    if nonfinal and not (
        provisions
        and all(
            result.observed_result
            == ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE
            for result in nonfinal
        )
    ):
        return CertificationVerdict(
            False,
            "not_certified",
            "Not certified",
            "policy-required dimensions are non-final: "
            + ", ".join(
                f"{item.row_id}={item.observed_result.value}"
                for item in nonfinal
            ),
            provisions,
        )
    if not required:
        return CertificationVerdict(
            False,
            "incomplete",
            "Incomplete",
            "profile selected no policy-required dimensions",
            provisions,
        )
    if provisions:
        return CertificationVerdict(
            False,
            "provisional",
            provisional_display(provisions),
            (
                "all remaining non-final dimensions are qualified substitutes; "
                f"{len(provisions)} certification provision(s) remain"
            ),
            provisions,
        )
    return CertificationVerdict(
        True,
        "certified",
        "Certified",
        "every policy-required dimension is final and affirmative",
    )


def execute(
    matrix: CompatibilityMatrix,
    target: CanAppTarget,
    profile_value: str,
    mode: str,
    registry: ExecutorRegistry,
    run_seed: Optional[str] = None,
    selected_row_ids: Optional[List[str]] = None,
    challenge: Optional[str] = None,
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
    nonce = challenge or hashlib.sha256(
        f"{run_id}:challenge".encode("utf-8")
    ).hexdigest()[:24]
    if len(nonce) < 16:
        raise ValueError("challenge must contain at least 16 characters")
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
