# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import json
from importlib.resources import files

import pytest
from jsonschema import Draft202012Validator

from respect_compat.models import RequirementOwner, ResponsibleParty
from respect_compat.routing import (
    ArtifactKind,
    ClassificationInput,
    ControlOwner,
    ObservedResult,
    RoutingEvidence,
    SubstituteFidelity,
    VerificationMode,
    classify_result,
)
from respect_compat.routing_artifacts import (
    ArtifactBindings,
    build_promotion_packet,
    project_destination_evidence,
    project_kit_tasks,
    verify_promotion_packet,
)


def _bindings():
    return ArtifactBindings(
        target_id="urn:canapp:example",
        target_digest="a" * 64,
        matrix_id="respect-matrix",
        matrix_version="1.2.0",
        matrix_semantic_hash="b" * 64,
        challenge="challenge-value-1234567890",
        evidence_ids=("evidence-1",),
        artifact_set_hash="c" * 64,
    )


def _fidelity():
    return SubstituteFidelity(
        substitute_id="local-https",
        substitute_version="1",
        owner=ResponsibleParty.APPDEV_PUBLICATION,
        covered_semantics=("descriptor", "catalog", "conditional-http"),
        excluded_semantics=("stable-owner-origin", "public-routing"),
        fidelity_guarantees=("same publication bytes and HTTP validators",),
        evidence_schema="respect-substitute-evidence-v2",
        real_dependency="owner-controlled HTTPS publication",
        clearance="deploy unchanged publication",
        promotion_test="rerun affected rows against declared origin",
        rerun_scope="affected_rows",
    )


def test_canapp_defect_projects_exactly_one_kit_task():
    result = classify_result(
        "DESC-001",
        ClassificationInput(
            requirement_owner=RequirementOwner.CANAPP,
            control_owner=ControlOwner.CANAPP_ARTIFACT,
            verification_mode=VerificationMode.REAL,
            observed_result=ObservedResult.CANAPP_IMPLEMENTATION_FAIL,
            evidence=RoutingEvidence(attributable=True),
        ),
    )
    tasks = project_kit_tasks([result])

    assert tasks == [
        {
            "task_id": "repair:DESC-001",
            "row_id": "DESC-001",
            "responsible_party": "canapp_artifact_owner",
            "workflow_disposition": "kit_repair",
        }
    ]
    assert ArtifactKind.PROMOTION_PACKET not in result.artifacts


def test_local_https_positive_evidence_yields_provisional_and_promotion_only():
    fidelity = _fidelity()
    result = classify_result(
        "HTTP-001",
        ClassificationInput(
            requirement_owner=RequirementOwner.CANAPP,
            control_owner=ControlOwner.APPDEV_PUBLICATION,
            responsible_party=ResponsibleParty.APPDEV_PUBLICATION,
            verification_mode=VerificationMode.SUBSTITUTE,
            observed_result=ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE,
            evidence=RoutingEvidence(
                attributable=True,
                positive_substitute=True,
                claimed_semantics=fidelity.covered_semantics,
                substitute_fidelity=fidelity,
            ),
        ),
    )
    packet = build_promotion_packet(result, _bindings(), fidelity)

    assert packet["artifact_type"] == "respect_promotion_packet"
    assert packet["format_version"] == "2.0.0"
    assert packet["covered_semantics"] == list(fidelity.covered_semantics)
    assert packet["excluded_semantics"] == list(fidelity.excluded_semantics)
    assert verify_promotion_packet(packet, _bindings()) == []
    assert project_kit_tasks([result]) == []


def test_promotion_binding_rejects_every_independent_tamper():
    fidelity = _fidelity()
    result = classify_result(
        "HTTP-001",
        ClassificationInput(
            requirement_owner=RequirementOwner.CANAPP,
            control_owner=ControlOwner.APPDEV_PUBLICATION,
            responsible_party=ResponsibleParty.APPDEV_PUBLICATION,
            verification_mode=VerificationMode.SUBSTITUTE,
            observed_result=ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE,
            evidence=RoutingEvidence(
                attributable=True,
                positive_substitute=True,
                claimed_semantics=fidelity.covered_semantics,
                substitute_fidelity=fidelity,
            ),
        ),
    )
    packet = build_promotion_packet(result, _bindings(), fidelity)
    for field in (
        "target_id",
        "target_digest",
        "matrix_id",
        "matrix_version",
        "matrix_semantic_hash",
        "challenge",
        "evidence_ids",
        "artifact_set_hash",
    ):
        tampered = copy.deepcopy(packet)
        tampered[field] = ["other"] if field == "evidence_ids" else "other"
        assert verify_promotion_packet(tampered, _bindings())


def test_signed_synthetic_real_build_evidence_is_neutrally_attributed():
    result = classify_result(
        "REG-001",
        ClassificationInput(
            requirement_owner=RequirementOwner.RESPECT_SERVICE,
            control_owner=ControlOwner.RESPECT_PLATFORM,
            verification_mode=VerificationMode.REAL,
            observed_result=ObservedResult.RESPECT_PLATFORM_GAP,
            evidence=RoutingEvidence(
                attributable=True,
                signed=True,
                real_platform=True,
                independently_attributed=True,
                real_build_id="synthetic-build",
                respect_revision="d" * 40,
                first_applicable_version="1.0.0",
                last_applicable_version="2.0.0",
            ),
        ),
    )
    assert result.observed_result == ObservedResult.RESPECT_PLATFORM_GAP
    assert result.workflow_disposition.value == "platform_observation_recorded"
    assert result.artifacts == ()
    assert project_kit_tasks([result]) == []


def test_v2_promotion_packet_validates_against_schema():
    promotion_result = classify_result(
        "HTTP-001",
        ClassificationInput(
            requirement_owner=RequirementOwner.CANAPP,
            control_owner=ControlOwner.APPDEV_PUBLICATION,
            responsible_party=ResponsibleParty.APPDEV_PUBLICATION,
            verification_mode=VerificationMode.SUBSTITUTE,
            observed_result=ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE,
            evidence=RoutingEvidence(
                attributable=True,
                positive_substitute=True,
                claimed_semantics=_fidelity().covered_semantics,
                substitute_fidelity=_fidelity(),
            ),
        ),
    )
    schema_root = files("respect_compat").joinpath("data/schemas")
    promotion_schema = json.loads(
        schema_root.joinpath("promotion_packet_v2.schema.json").read_text()
    )
    Draft202012Validator.check_schema(promotion_schema)
    Draft202012Validator(promotion_schema).validate(
        build_promotion_packet(promotion_result, _bindings(), _fidelity())
    )


def test_destination_projection_excludes_cross_owned_and_unsafe_evidence():
    evidence = {
        "canapp": {
            "evidence_id": "canapp",
            "destination": "kit",
            "source": "suite",
        },
        "platform": {
            "evidence_id": "platform",
            "destination": "public",
            "source": "suite",
        },
    }
    assert [
        item["evidence_id"]
        for item in project_destination_evidence(evidence, "kit")
    ] == ["canapp"]
    assert [
        item["evidence_id"]
        for item in project_destination_evidence(evidence, "public")
    ] == ["platform"]

    unsafe = dict(evidence)
    unsafe["bad"] = {
        "evidence_id": "bad",
        "destination": "public",
        "source": "file:///private/local",
    }
    with pytest.raises(ValueError, match="unsafe"):
        project_destination_evidence(unsafe, "public")
    with pytest.raises(ValueError, match="unknown evidence destination"):
        project_destination_evidence(evidence, "dossier")
