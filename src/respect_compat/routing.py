# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Typed responsibility routing for TestKit v2 artifacts.

This module is the single normative authority for converting an independently
typed observation into a workflow disposition and artifact set. Consumers may
format these values but must not derive their own mappings.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from .models import RequirementOwner, ResponsibleParty, ResultState


class ControlOwner(str, Enum):
    CANAPP_ARTIFACT = "canapp_artifact"
    APPDEV_HARNESS = "appdev_harness"
    APPDEV_PROVISIONING = "appdev_provisioning"
    APPDEV_PUBLICATION = "appdev_publication"
    RESPECT_PLATFORM = "respect_platform"
    PUBLISHER = "publisher"
    SPIX_FOUNDATION = "spix_foundation"
    TESTKIT = "testkit"
    CERTIFICATION_AUTHORITY = "certification_authority"
    SPECIFICATION_AUTHORITY = "specification_authority"
    NONE = "none"


class VerificationMode(str, Enum):
    REAL = "real"
    SUBSTITUTE = "substitute"
    FIXTURE = "fixture"
    STATIC = "static"
    UNAVAILABLE = "unavailable"
    PRODUCTION_META_TEST = "production_meta_test"


class ObservedResult(str, Enum):
    PASS = "pass"
    CANAPP_IMPLEMENTATION_FAIL = "canapp_implementation_fail"
    CODE_COMPATIBLE_THROUGH_SUBSTITUTE = "code_compatible_through_substitute"
    UNMEASURED_EXTERNAL_DEPENDENCY = "unmeasured_external_dependency"
    TESTKIT_CAPABILITY_GAP = "testkit_capability_gap"
    HARNESS_ERROR = "harness_error"
    RESPECT_PLATFORM_GAP = "respect_platform_gap"
    SPECIFICATION_BLOCKED = "specification_blocked"
    NOT_APPLICABLE = "not_applicable"


class WorkflowDisposition(str, Enum):
    NONE = "none"
    KIT_REPAIR = "kit_repair"
    PROVISIONAL_PROMOTION_REQUIRED = "provisional_promotion_required"
    PROVISION_OR_CAPABILITY_WORK = "provision_or_capability_work"
    TESTKIT_ENGINEERING = "testkit_engineering"
    DIAGNOSTIC_INCIDENT = "diagnostic_incident"
    PLATFORM_OBSERVATION_RECORDED = "platform_observation_recorded"
    SPECIFICATION_DECISION = "specification_decision"


class ArtifactKind(str, Enum):
    KIT_TASK = "kit_task"
    PROMOTION_PACKET = "promotion_packet"
    TESTKIT_ENGINEERING_ITEM = "testkit_engineering_item"
    DIAGNOSTIC_INCIDENT = "diagnostic_incident"
    SPECIFICATION_ITEM = "specification_item"


@dataclass(frozen=True)
class SubstituteFidelity:
    substitute_id: str
    substitute_version: str
    owner: ResponsibleParty
    covered_semantics: Tuple[str, ...]
    excluded_semantics: Tuple[str, ...]
    fidelity_guarantees: Tuple[str, ...]
    evidence_schema: str
    real_dependency: str
    clearance: str
    promotion_test: str
    rerun_scope: str

    def __post_init__(self) -> None:
        if not self.substitute_id or not self.substitute_version:
            raise ValueError("substitute identity and version are required")
        if not self.covered_semantics:
            raise ValueError("substitute covered semantics are required")
        if not self.excluded_semantics:
            raise ValueError("substitute excluded semantics are required")
        if not self.fidelity_guarantees or not self.evidence_schema:
            raise ValueError("substitute fidelity and evidence schema are required")


@dataclass(frozen=True)
class RoutingEvidence:
    attributable: bool = False
    signed: bool = False
    real_platform: bool = False
    independently_attributed: bool = False
    observer_present: bool = True
    actor_malfunction: bool = False
    target_blame: bool = False
    positive_substitute: bool = False
    claimed_semantics: Tuple[str, ...] = ()
    substitute_fidelity: Optional[SubstituteFidelity] = None
    real_build_id: Optional[str] = None
    respect_revision: Optional[str] = None
    first_applicable_version: Optional[str] = None
    last_applicable_version: Optional[str] = None


@dataclass(frozen=True)
class ClassificationInput:
    requirement_owner: RequirementOwner
    control_owner: ControlOwner
    verification_mode: VerificationMode
    observed_result: ObservedResult
    evidence: RoutingEvidence = field(default_factory=RoutingEvidence)
    responsible_party: Optional[ResponsibleParty] = None
    policy_required: bool = True


@dataclass(frozen=True)
class RoutingRule:
    disposition: WorkflowDisposition
    artifacts: Tuple[ArtifactKind, ...]
    default_party: Optional[ResponsibleParty]
    final_affirmative: bool


# The sole normative result-to-workflow mapping.
ROUTING_TABLE: Mapping[ObservedResult, RoutingRule] = {
    ObservedResult.PASS: RoutingRule(
        WorkflowDisposition.NONE, (), ResponsibleParty.NONE, True
    ),
    ObservedResult.CANAPP_IMPLEMENTATION_FAIL: RoutingRule(
        WorkflowDisposition.KIT_REPAIR,
        (ArtifactKind.KIT_TASK,),
        ResponsibleParty.CANAPP_ARTIFACT_OWNER,
        False,
    ),
    ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE: RoutingRule(
        WorkflowDisposition.PROVISIONAL_PROMOTION_REQUIRED,
        (ArtifactKind.PROMOTION_PACKET,),
        None,
        False,
    ),
    ObservedResult.UNMEASURED_EXTERNAL_DEPENDENCY: RoutingRule(
        WorkflowDisposition.PROVISION_OR_CAPABILITY_WORK, (), None, False
    ),
    ObservedResult.TESTKIT_CAPABILITY_GAP: RoutingRule(
        WorkflowDisposition.TESTKIT_ENGINEERING,
        (ArtifactKind.TESTKIT_ENGINEERING_ITEM,),
        ResponsibleParty.TESTKIT_TEAM,
        False,
    ),
    ObservedResult.HARNESS_ERROR: RoutingRule(
        WorkflowDisposition.DIAGNOSTIC_INCIDENT,
        (ArtifactKind.DIAGNOSTIC_INCIDENT,),
        ResponsibleParty.TESTKIT_OPERATOR,
        False,
    ),
    ObservedResult.RESPECT_PLATFORM_GAP: RoutingRule(
        WorkflowDisposition.PLATFORM_OBSERVATION_RECORDED,
        (),
        ResponsibleParty.RESPECT_PLATFORM_TEAM,
        False,
    ),
    ObservedResult.SPECIFICATION_BLOCKED: RoutingRule(
        WorkflowDisposition.SPECIFICATION_DECISION,
        (ArtifactKind.SPECIFICATION_ITEM,),
        ResponsibleParty.SPECIFICATION_AUTHORITY,
        False,
    ),
    ObservedResult.NOT_APPLICABLE: RoutingRule(
        WorkflowDisposition.NONE, (), ResponsibleParty.NONE, True
    ),
}


_PARTY_FOR_CONTROL: Mapping[ControlOwner, ResponsibleParty] = {
    ControlOwner.CANAPP_ARTIFACT: ResponsibleParty.CANAPP_ARTIFACT_OWNER,
    ControlOwner.APPDEV_HARNESS: ResponsibleParty.APPDEV_HARNESS,
    ControlOwner.APPDEV_PROVISIONING: ResponsibleParty.APPDEV_PROVISIONING,
    ControlOwner.APPDEV_PUBLICATION: ResponsibleParty.APPDEV_PUBLICATION,
    ControlOwner.RESPECT_PLATFORM: ResponsibleParty.RESPECT_PLATFORM_TEAM,
    ControlOwner.PUBLISHER: ResponsibleParty.PUBLISHER,
    ControlOwner.SPIX_FOUNDATION: ResponsibleParty.SPIX_FOUNDATION,
    ControlOwner.TESTKIT: ResponsibleParty.TESTKIT_TEAM,
    ControlOwner.CERTIFICATION_AUTHORITY: (
        ResponsibleParty.CERTIFICATION_AUTHORITY
    ),
    ControlOwner.SPECIFICATION_AUTHORITY: (
        ResponsibleParty.SPECIFICATION_AUTHORITY
    ),
    ControlOwner.NONE: ResponsibleParty.NONE,
}


class RoutingClassificationError(ValueError):
    """Raised when independently typed inputs form an impossible route."""


@dataclass(frozen=True)
class AtomicResult:
    row_id: str
    requirement_owner: RequirementOwner
    control_owner: ControlOwner
    responsible_party: ResponsibleParty
    verification_mode: VerificationMode
    observed_result: ObservedResult
    workflow_disposition: WorkflowDisposition
    artifacts: Tuple[ArtifactKind, ...]
    policy_required: bool
    final_affirmative: bool

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "row_id": self.row_id,
            "requirement_owner": self.requirement_owner.value,
            "control_owner": self.control_owner.value,
            "responsible_party": self.responsible_party.value,
            "verification_mode": self.verification_mode.value,
            "observed_result": self.observed_result.value,
            "workflow_disposition": self.workflow_disposition.value,
            "artifacts": [item.value for item in self.artifacts],
            "policy_required": self.policy_required,
            "final_affirmative": self.final_affirmative,
        }

    @classmethod
    def from_json_dict(cls, payload: Dict[str, Any]) -> "AtomicResult":
        required = (
            "row_id",
            "requirement_owner",
            "control_owner",
            "responsible_party",
            "verification_mode",
            "observed_result",
            "workflow_disposition",
            "artifacts",
            "policy_required",
            "final_affirmative",
        )
        for field_name in required:
            if field_name not in payload:
                raise ValueError(f"atomic result missing {field_name}")
        for field_name in ("policy_required", "final_affirmative"):
            if type(payload[field_name]) is not bool:
                raise ValueError(f"atomic result {field_name} must be boolean")
        try:
            return cls(
                row_id=str(payload["row_id"]),
                requirement_owner=RequirementOwner(
                    payload["requirement_owner"]
                ),
                control_owner=ControlOwner(payload["control_owner"]),
                responsible_party=ResponsibleParty(
                    payload["responsible_party"]
                ),
                verification_mode=VerificationMode(
                    payload["verification_mode"]
                ),
                observed_result=ObservedResult(payload["observed_result"]),
                workflow_disposition=WorkflowDisposition(
                    payload["workflow_disposition"]
                ),
                artifacts=tuple(
                    ArtifactKind(item) for item in payload["artifacts"]
                ),
                policy_required=payload["policy_required"],
                final_affirmative=payload["final_affirmative"],
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid atomic result: {error}") from error


@dataclass(frozen=True)
class CertificationSummary:
    certified: bool
    state: str
    display: str
    reason: str


def is_provisional_nonfinal(
    result: AtomicResult,
    state: Any,
) -> bool:
    state_value = getattr(state, "value", state)
    if (
        result.observed_result
        == ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE
    ):
        return True
    return (
        result.requirement_owner != RequirementOwner.CANAPP
        and state_value
        in {
            ResultState.BLOCKED.value,
            ResultState.INCOMPLETE.value,
            ResultState.DEFERRED.value,
        }
    )


def _validate(classification_input: ClassificationInput) -> None:
    observed = classification_input.observed_result
    evidence = classification_input.evidence
    if observed == ObservedResult.CANAPP_IMPLEMENTATION_FAIL:
        if (
            classification_input.requirement_owner
            != RequirementOwner.CANAPP
            or classification_input.control_owner
            != ControlOwner.CANAPP_ARTIFACT
        ):
            raise RoutingClassificationError(
                "Kit repair requires CanApp requirement and control ownership"
            )
        if not evidence.attributable:
            raise RoutingClassificationError(
                "CanApp implementation failure requires attributable evidence"
            )
    if observed == ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE:
        fidelity = evidence.substitute_fidelity
        if (
            classification_input.verification_mode
            != VerificationMode.SUBSTITUTE
            or not evidence.positive_substitute
            or fidelity is None
        ):
            raise RoutingClassificationError(
                "Provisional requires positive substitute evidence and fidelity"
            )
        if not set(evidence.claimed_semantics).issubset(
            fidelity.covered_semantics
        ):
            raise RoutingClassificationError(
                "claimed semantics exceed covered semantics"
            )
    if observed == ObservedResult.TESTKIT_CAPABILITY_GAP:
        if evidence.target_blame:
            raise RoutingClassificationError(
                "TestKit Capability Gap cannot carry target blame"
            )
        if classification_input.control_owner != ControlOwner.TESTKIT:
            raise RoutingClassificationError(
                "TestKit Capability Gap must be controlled by TestKit"
            )
    if observed == ObservedResult.HARNESS_ERROR:
        if (
            classification_input.control_owner != ControlOwner.TESTKIT
            or not evidence.actor_malfunction
        ):
            raise RoutingClassificationError(
                "Harness Error requires an attributable TestKit actor malfunction"
            )
    if observed == ObservedResult.RESPECT_PLATFORM_GAP:
        qualifying = (
            classification_input.control_owner
            == ControlOwner.RESPECT_PLATFORM
            and classification_input.verification_mode
            == VerificationMode.REAL
            and evidence.attributable
            and evidence.signed
            and evidence.real_platform
            and evidence.independently_attributed
            and evidence.real_build_id
            and evidence.respect_revision
            and evidence.first_applicable_version
        )
        if not qualifying:
            raise RoutingClassificationError(
                "platform attribution requires qualifying real, signed, "
                "independently attributable platform evidence with pinned build "
                "and version bounds"
            )
    if observed == ObservedResult.SPECIFICATION_BLOCKED:
        if (
            classification_input.control_owner
            != ControlOwner.SPECIFICATION_AUTHORITY
        ):
            raise RoutingClassificationError(
                "Specification Blocked requires specification authority control"
            )
    if observed == ObservedResult.NOT_APPLICABLE:
        if (
            classification_input.verification_mode
            != VerificationMode.UNAVAILABLE
        ):
            raise RoutingClassificationError(
                "Not Applicable must not claim an executed verification mode"
            )


def classify_result(
    row_id: str, classification_input: ClassificationInput
) -> AtomicResult:
    """Classify one atomic result through the sole normative routing table."""

    if not row_id:
        raise RoutingClassificationError("row_id is required")
    _validate(classification_input)
    rule = ROUTING_TABLE[classification_input.observed_result]
    party = (
        classification_input.responsible_party
        or rule.default_party
        or _PARTY_FOR_CONTROL[classification_input.control_owner]
    )
    if (
        rule.default_party is not None
        and classification_input.responsible_party is not None
        and classification_input.responsible_party != rule.default_party
    ):
        raise RoutingClassificationError(
            "responsible party contradicts the normative route"
        )
    return AtomicResult(
        row_id=row_id,
        requirement_owner=classification_input.requirement_owner,
        control_owner=classification_input.control_owner,
        responsible_party=party,
        verification_mode=classification_input.verification_mode,
        observed_result=classification_input.observed_result,
        workflow_disposition=rule.disposition,
        artifacts=rule.artifacts,
        policy_required=classification_input.policy_required,
        final_affirmative=rule.final_affirmative,
    )


def certification_summary(
    results: Iterable[AtomicResult],
) -> CertificationSummary:
    values = list(results)
    required = [item for item in values if item.policy_required]
    nonfinal = [item for item in required if not item.final_affirmative]
    if not required:
        return CertificationSummary(
            False,
            "incomplete",
            "Incomplete",
            "no policy-required dimensions were evaluated",
        )
    if nonfinal:
        return CertificationSummary(
            False,
            "not_certified",
            "Not certified",
            "policy-required dimensions are non-final: "
            + ", ".join(
                f"{item.row_id}={item.observed_result.value}"
                for item in nonfinal
            ),
        )
    return CertificationSummary(
        True,
        "certified",
        "Certified",
        "every policy-required dimension is final and affirmative",
    )


def _artifact_generation(value: Dict[str, Any]) -> str:
    version = value.get("format_version")
    if version == "2.0.0":
        return "v2"
    if version == "1.0.0":
        return "legacy_v1"
    if version is None and "suite_version" in value:
        return "legacy_unversioned"
    raise ValueError(
        f"unsupported routing artifact version: {version!r}"
    )


def validate_routing_artifact_set(
    artifacts: Iterable[Dict[str, Any]],
) -> str:
    generations = {_artifact_generation(item) for item in artifacts}
    if not generations:
        raise ValueError("routing artifact set is empty")
    if len(generations) != 1:
        raise ValueError(
            f"mixed routing artifact versions are forbidden: {sorted(generations)}"
        )
    return next(iter(generations))


def ensure_work_generation_allowed(
    artifacts: Iterable[Dict[str, Any]],
) -> None:
    generation = validate_routing_artifact_set(artifacts)
    if generation != "v2":
        raise ValueError(
            f"{generation} routing artifacts are read-only and cannot generate work"
        )


def verify_legacy_routing_artifact(value: Dict[str, Any]) -> Tuple[str, ...]:
    """Perform frozen structural verification without interpreting old routes."""

    generation = _artifact_generation(value)
    errors = []
    if generation == "v2":
        errors.append("artifact is not legacy")
    elif generation == "legacy_v1":
        if not value.get("artifact_type"):
            errors.append("legacy v1 artifact type is missing")
    elif generation == "legacy_unversioned":
        if not isinstance(value.get("results"), list):
            errors.append("legacy unversioned Suite results are missing")
    return tuple(sorted(errors))
