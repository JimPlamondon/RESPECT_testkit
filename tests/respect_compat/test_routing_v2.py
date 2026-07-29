# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from respect_compat.resources import resource
from respect_compat.matrix_runtime import load_matrix

from respect_compat.routing import (
    ArtifactKind,
    AtomicResult,
    ClassificationInput,
    ControlOwner,
    ObservedResult,
    RequirementOwner,
    ResponsibleParty,
    RoutingClassificationError,
    RoutingEvidence,
    SubstituteFidelity,
    VerificationMode,
    WorkflowDisposition,
    certification_summary,
    classify_result,
    ensure_work_generation_allowed,
    validate_routing_artifact_set,
    verify_legacy_routing_artifact,
)


def _input(
    observed_result,
    *,
    requirement_owner=RequirementOwner.CANAPP,
    control_owner=ControlOwner.CANAPP_ARTIFACT,
    verification_mode=VerificationMode.REAL,
    evidence=None,
    responsible_party=None,
):
    return ClassificationInput(
        requirement_owner=requirement_owner,
        control_owner=control_owner,
        responsible_party=responsible_party,
        verification_mode=verification_mode,
        observed_result=observed_result,
        evidence=evidence or RoutingEvidence(attributable=True),
    )


def test_classifier_round_trips_all_six_dimensions():
    result = classify_result(
        "ROW-1",
        _input(ObservedResult.CANAPP_IMPLEMENTATION_FAIL),
    )

    payload = result.to_json_dict()
    assert AtomicResult.from_json_dict(payload) == result
    assert {
        "requirement_owner",
        "control_owner",
        "responsible_party",
        "verification_mode",
        "observed_result",
        "workflow_disposition",
    }.issubset(payload)

    for field in (
        "requirement_owner",
        "control_owner",
        "responsible_party",
        "verification_mode",
        "observed_result",
        "workflow_disposition",
    ):
        broken = dict(payload)
        broken.pop(field)
        with pytest.raises(ValueError, match=field):
            AtomicResult.from_json_dict(broken)

        broken = dict(payload)
        broken[field] = "unknown-enum-value"
        with pytest.raises(ValueError):
            AtomicResult.from_json_dict(broken)


def test_owner_vocabulary_is_schema_constrained():
    valid = {
        party.value
        for party in ResponsibleParty
    }
    assert {
        "canapp_artifact_owner",
        "appdev_harness",
        "appdev_provisioning",
        "appdev_publication",
        "respect_platform_team",
        "publisher",
        "spix_foundation",
        "testkit_team",
        "certification_authority",
        "specification_authority",
    }.issubset(valid)
    with pytest.raises(ValueError):
        ResponsibleParty("whoever-is-nearby")


def test_classifier_covers_every_normative_route_and_rejects_impossible_combinations():
    fidelity = SubstituteFidelity(
        substitute_id="local-https",
        substitute_version="1",
        owner=ResponsibleParty.APPDEV_PUBLICATION,
        covered_semantics=("descriptor", "catalog", "conditional-http"),
        excluded_semantics=("stable-owner-origin",),
        fidelity_guarantees=("same-byte publication graph",),
        evidence_schema="respect-substitute-evidence-v2",
        real_dependency="owner-controlled HTTPS origin",
        clearance="deploy unchanged bytes",
        promotion_test="rerun affected rows at declared origin",
        rerun_scope="affected_rows",
    )
    cases = [
        (
            _input(ObservedResult.CANAPP_IMPLEMENTATION_FAIL),
            WorkflowDisposition.KIT_REPAIR,
            {ArtifactKind.KIT_TASK},
        ),
        (
            _input(
                ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE,
                verification_mode=VerificationMode.SUBSTITUTE,
                evidence=RoutingEvidence(
                    attributable=True,
                    positive_substitute=True,
                    claimed_semantics=(
                        "descriptor",
                        "catalog",
                        "conditional-http",
                    ),
                    substitute_fidelity=fidelity,
                ),
            ),
            WorkflowDisposition.PROVISIONAL_PROMOTION_REQUIRED,
            {ArtifactKind.PROMOTION_PACKET},
        ),
        (
            _input(
                ObservedResult.UNMEASURED_EXTERNAL_DEPENDENCY,
                control_owner=ControlOwner.APPDEV_PROVISIONING,
                verification_mode=VerificationMode.UNAVAILABLE,
            ),
            WorkflowDisposition.PROVISION_OR_CAPABILITY_WORK,
            set(),
        ),
        (
            _input(
                ObservedResult.TESTKIT_CAPABILITY_GAP,
                requirement_owner=RequirementOwner.RESPECT_SERVICE,
                control_owner=ControlOwner.TESTKIT,
                verification_mode=VerificationMode.UNAVAILABLE,
                evidence=RoutingEvidence(observer_present=False),
            ),
            WorkflowDisposition.TESTKIT_ENGINEERING,
            {ArtifactKind.TESTKIT_ENGINEERING_ITEM},
        ),
        (
            _input(
                ObservedResult.HARNESS_ERROR,
                control_owner=ControlOwner.TESTKIT,
                evidence=RoutingEvidence(actor_malfunction=True),
            ),
            WorkflowDisposition.DIAGNOSTIC_INCIDENT,
            {ArtifactKind.DIAGNOSTIC_INCIDENT},
        ),
        (
            _input(
                ObservedResult.RESPECT_PLATFORM_GAP,
                requirement_owner=RequirementOwner.RESPECT_SERVICE,
                control_owner=ControlOwner.RESPECT_PLATFORM,
                evidence=RoutingEvidence(
                    attributable=True,
                    signed=True,
                    real_platform=True,
                    independently_attributed=True,
                    real_build_id="fake-build",
                    respect_revision="f" * 40,
                    first_applicable_version="1.0.0",
                    last_applicable_version="2.0.0",
                ),
            ),
            WorkflowDisposition.DOSSIER_ELIGIBLE,
            {ArtifactKind.PLATFORM_GAP_PACKET},
        ),
        (
            _input(
                ObservedResult.SPECIFICATION_BLOCKED,
                requirement_owner=RequirementOwner.PROFILE_OWNER,
                control_owner=ControlOwner.SPECIFICATION_AUTHORITY,
            ),
            WorkflowDisposition.SPECIFICATION_DECISION,
            {ArtifactKind.SPECIFICATION_ITEM},
        ),
        (
            _input(
                ObservedResult.NOT_APPLICABLE,
                verification_mode=VerificationMode.UNAVAILABLE,
            ),
            WorkflowDisposition.NONE,
            set(),
        ),
        (
            _input(ObservedResult.PASS),
            WorkflowDisposition.NONE,
            set(),
        ),
    ]

    for index, (classification_input, disposition, artifacts) in enumerate(cases):
        result = classify_result(f"ROW-{index}", classification_input)
        assert result.workflow_disposition is disposition
        assert set(result.artifacts) == artifacts

    with pytest.raises(RoutingClassificationError, match="positive substitute"):
        classify_result(
            "BAD-SUBSTITUTE",
            _input(
                ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE,
                verification_mode=VerificationMode.SUBSTITUTE,
            ),
        )
    with pytest.raises(RoutingClassificationError, match="covered semantics"):
        classify_result(
            "BAD-FIDELITY",
            _input(
                ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE,
                verification_mode=VerificationMode.SUBSTITUTE,
                evidence=RoutingEvidence(
                    positive_substitute=True,
                    claimed_semantics=("not-covered",),
                    substitute_fidelity=fidelity,
                ),
            ),
        )
    with pytest.raises(RoutingClassificationError, match="CanApp"):
        classify_result(
            "BAD-KIT",
            _input(
                ObservedResult.CANAPP_IMPLEMENTATION_FAIL,
                requirement_owner=RequirementOwner.RESPECT_SERVICE,
                control_owner=ControlOwner.RESPECT_PLATFORM,
            ),
        )
    with pytest.raises(RoutingClassificationError, match="qualifying real"):
        classify_result(
            "BAD-DOSSIER",
            _input(
                ObservedResult.RESPECT_PLATFORM_GAP,
                requirement_owner=RequirementOwner.RESPECT_SERVICE,
                control_owner=ControlOwner.RESPECT_PLATFORM,
                verification_mode=VerificationMode.FIXTURE,
            ),
        )
    with pytest.raises(RoutingClassificationError, match="target blame"):
        classify_result(
            "BAD-GAP",
            _input(
                ObservedResult.TESTKIT_CAPABILITY_GAP,
                control_owner=ControlOwner.TESTKIT,
                evidence=RoutingEvidence(target_blame=True),
            ),
        )


def test_certified_requires_every_required_dimension_final():
    passing = [
        classify_result("PASS", _input(ObservedResult.PASS)),
        classify_result(
            "NA",
            _input(
                ObservedResult.NOT_APPLICABLE,
                verification_mode=VerificationMode.UNAVAILABLE,
            ),
        ),
    ]
    assert certification_summary(passing).certified is True
    assert certification_summary(passing).display == "Certified"

    nonfinal_inputs = [
        _input(ObservedResult.CANAPP_IMPLEMENTATION_FAIL),
        _input(
            ObservedResult.UNMEASURED_EXTERNAL_DEPENDENCY,
            control_owner=ControlOwner.APPDEV_PROVISIONING,
            verification_mode=VerificationMode.UNAVAILABLE,
        ),
        _input(
            ObservedResult.TESTKIT_CAPABILITY_GAP,
            control_owner=ControlOwner.TESTKIT,
            verification_mode=VerificationMode.UNAVAILABLE,
        ),
        _input(
            ObservedResult.HARNESS_ERROR,
            control_owner=ControlOwner.TESTKIT,
            evidence=RoutingEvidence(actor_malfunction=True),
        ),
        _input(
            ObservedResult.SPECIFICATION_BLOCKED,
            control_owner=ControlOwner.SPECIFICATION_AUTHORITY,
        ),
    ]
    for index, classification_input in enumerate(nonfinal_inputs):
        result = classify_result(f"NONFINAL-{index}", classification_input)
        summary = certification_summary(passing + [result])
        assert summary.certified is False
        assert summary.display != "Certified"


def test_routing_family_legacy_is_read_only_and_mixed_versions_fail():
    v2 = {
        "artifact_type": "respect_suite_report",
        "format_version": "2.0.0",
    }
    v1 = {
        "artifact_type": "respect_evidence_manifest",
        "format_version": "1.0.0",
    }
    unversioned = {"suite_version": "1.0.0", "results": []}

    assert validate_routing_artifact_set([v2]) == "v2"
    assert validate_routing_artifact_set([v1]) == "legacy_v1"
    assert validate_routing_artifact_set([unversioned]) == "legacy_unversioned"
    with pytest.raises(ValueError, match="mixed"):
        validate_routing_artifact_set([v2, v1])
    with pytest.raises(ValueError, match="read-only"):
        ensure_work_generation_allowed([v1])
    with pytest.raises(ValueError, match="read-only"):
        ensure_work_generation_allowed([unversioned])


def test_frozen_legacy_golden_artifacts_verify_but_cannot_generate_work():
    fixture_root = Path(__file__).parents[1] / "fixtures" / "routing"
    artifacts = [
        json.loads(path.read_text())
        for path in (
            fixture_root / "legacy_task_packet_v1.json",
            fixture_root / "legacy_suite_report_unversioned.json",
        )
    ]
    for artifact in artifacts:
        assert verify_legacy_routing_artifact(artifact) == ()
        with pytest.raises(ValueError, match="read-only"):
            ensure_work_generation_allowed([artifact])
    with pytest.raises(ValueError, match="mixed"):
        validate_routing_artifact_set(artifacts)


def test_v2_atomic_result_and_suite_schemas_reject_unknown_dimensions():
    atomic_schema = json.loads(
        resource("data/schemas/atomic_result_v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    suite_schema = json.loads(
        resource("data/schemas/suite_report_v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(atomic_schema)
    Draft202012Validator.check_schema(suite_schema)

    payload = classify_result(
        "ROW-1",
        _input(ObservedResult.CANAPP_IMPLEMENTATION_FAIL),
    ).to_json_dict()
    Draft202012Validator(atomic_schema).validate(payload)

    broken = dict(payload)
    broken["responsible_party"] = "untyped-owner"
    assert list(Draft202012Validator(atomic_schema).iter_errors(broken))

    suite = {
        "artifact_type": "respect_suite_report",
        "format_version": "2.0.0",
        "suite_version": "2.0.0",
        "run_id": "run",
        "matrix_id": "matrix",
        "matrix_version": "1.0.0",
        "matrix_semantic_hash": "a" * 64,
        "profile_id": "profile",
        "target_id": "urn:sha256:" + "c" * 64,
        "target_digest": "b" * 64,
        "challenge": "challenge-challenge-value",
        "results": [payload],
    }
    Draft202012Validator(suite_schema).validate(suite)


def test_matrix_exposes_executable_routing_and_dossier_bindings():
    matrix = load_matrix()
    raw_rows = {item["row_id"]: item for item in matrix.raw["rows"]}
    raw_features = {
        item["feature_id"]: item for item in matrix.raw["features"]
    }
    respect_owners = {"respect_launcher", "respect_service"}

    for row in matrix.rows.values():
        raw = raw_rows[row.row_id]
        assert row.control_owner == raw["control_owner"]
        assert row.responsible_party == raw["responsible_party"]
        assert row.applicability_evaluator == raw[
            "applicability_evaluator"
        ]
        assert row.routing_contract == "respect_compat.routing.ROUTING_TABLE"
        assert raw["verification_modes"]
        if row.owner in respect_owners:
            assert row.platform_gap_eligible is True
            assert row.dossier_acceptance_test == (
                f"matrix-row:{row.row_id}"
            )
        else:
            assert row.platform_gap_eligible is False
        if (
            row.owner == "canapp"
            and row.row_id.split("-", 1)[0]
            in {"DESC", "HTTP", "OPDS"}
        ):
            contract = raw["substitute_fidelity_contract"]
            assert contract["substitute_id"] == "local_https_publication"
            assert contract["covered_semantics"]
            assert contract["excluded_semantics"]

    rowless_upstream = [
        item
        for item in raw_features.values()
        if (
            item["requirement_status"] == "upstream_gap"
            or item["conformance_disposition"] == "upstream_gap"
        )
        and not item["row_ids"]
    ]
    assert len(rowless_upstream) == 13
    for feature in raw_features.values():
        assert feature["respect_upgrade_guidance"]
    for feature in rowless_upstream:
        assert feature["feature_work_unit"]["feature_id"] == feature[
            "feature_id"
        ]
        assert feature["feature_work_unit"]["closure_requires_executable_acceptance"]
