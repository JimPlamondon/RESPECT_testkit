# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import base64
import copy
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

from respect_compat.models import RequirementOwner
from respect_compat.routing import (
    ClassificationInput,
    ControlOwner,
    ObservedResult,
    RoutingEvidence,
    VerificationMode,
    classify_result,
)
from respect_compat.routing_artifacts import (
    ArtifactBindings,
    build_platform_gap_packet,
)
from respect_upgrade_dossier.generator import generate_dossier
from respect_upgrade_dossier.ledger import append_event, verify_ledger
from respect_upgrade_dossier.lifecycle import DossierState, transition
from respect_upgrade_dossier.observations import (
    collect_environment_observations,
)
from respect_upgrade_dossier.resources import load_schema
from respect_upgrade_dossier.trust import (
    Ed25519TrustPolicy,
    FailClosedTrustPolicy,
)
from respect_upgrade_dossier.verifier import verify_dossier


def _result(observed=ObservedResult.RESPECT_PLATFORM_GAP):
    return classify_result(
        "REG-001",
        ClassificationInput(
            requirement_owner=RequirementOwner.RESPECT_SERVICE,
            control_owner=ControlOwner.RESPECT_PLATFORM,
            verification_mode=VerificationMode.REAL,
            observed_result=observed,
            evidence=RoutingEvidence(
                attributable=True,
                signed=True,
                real_platform=True,
                independently_attributed=True,
                real_build_id="synthetic-fake-build",
                respect_revision="d" * 40,
                first_applicable_version="1.0.0",
                last_applicable_version="2.0.0",
            ),
        ),
    )


def _bindings():
    return ArtifactBindings(
        target_id="urn:synthetic:canapp",
        target_digest="a" * 64,
        matrix_id="respect-matrix",
        matrix_version="1.1.0",
        matrix_semantic_hash="b" * 64,
        challenge="synthetic-challenge-0001",
        evidence_ids=("synthetic-evidence-1",),
        artifact_set_hash="c" * 64,
        real_build_id="synthetic-fake-build",
        respect_revision="d" * 40,
        first_applicable_version="1.0.0",
        last_applicable_version="2.0.0",
    )


def _issued_packet():
    private_key = Ed25519PrivateKey.generate()
    packet = build_platform_gap_packet(_result(), _bindings())
    packet["suite_issuance"] = {
        "algorithm": "Ed25519",
        "key_id": "synthetic-suite-test-key",
        "signature": base64.b64encode(
            private_key.sign(packet["core_hash"].encode("ascii"))
        ).decode("ascii"),
    }
    policy = Ed25519TrustPolicy(
        {"synthetic-suite-test-key": private_key.public_key()}
    )
    return packet, policy


def _details():
    return {
        "affected_features": ["REGISTRATION"],
        "affected_profiles": ["PROFILE-WEB"],
        "normative_source": "RESPECT requirement REG-001",
        "applicability": "Applicable to the pinned synthetic build.",
        "independently_attributable_behavior": "Synthetic response omitted field.",
        "upgrade_guidance": "Implement the required response field.",
        "security_implications": "Preserve authenticated response handling.",
        "privacy_implications": "Do not add learner identifiers.",
        "compatibility_considerations": "Retain the prior response fields.",
        "migration_considerations": "No stored-data migration.",
        "deployment_considerations": "Deploy behind the existing endpoint.",
        "rollback_considerations": "Restore the prior endpoint build.",
        "acceptance_contract": {
            "test_ids": ["REG-001"],
            "required_result": "pass",
        },
        "dependencies": [],
    }


def test_dossier_generation_requires_verified_suite_platform_packet():
    packet, policy = _issued_packet()
    dossier = generate_dossier(packet, _details(), policy)

    assert dossier["state"] == "identified"
    assert dossier["pinned_respect"]["real_build_id"] == "synthetic-fake-build"
    assert dossier["evidence_bindings"]["challenge"] == packet["challenge"]
    assert verify_dossier(dossier)["valid"] is True
    Draft202012Validator(
        load_schema("upgrade_dossier_v2.schema.json")
    ).validate(dossier)

    with pytest.raises(ValueError, match="approved Suite key"):
        generate_dossier(packet, _details(), FailClosedTrustPolicy())
    with pytest.raises(ValueError, match="invalid platform-gap packet"):
        generate_dossier(
            {"artifact_type": "respect_suite_report", "format_version": "2.0.0"},
            _details(),
            policy,
        )


def test_dossier_binding_rejects_every_independent_tamper():
    packet, policy = _issued_packet()
    for field in (
        "target_id",
        "target_digest",
        "matrix_id",
        "matrix_version",
        "matrix_semantic_hash",
        "respect_revision",
        "first_applicable_version",
        "last_applicable_version",
        "challenge",
        "evidence_ids",
        "artifact_set_hash",
    ):
        tampered = copy.deepcopy(packet)
        tampered[field] = ["other"] if field == "evidence_ids" else "other"
        with pytest.raises(ValueError):
            generate_dossier(tampered, _details(), policy)


def test_dossier_rejects_unsafe_packet_reference_without_dereferencing():
    packet, policy = _issued_packet()
    packet["target_id"] = "file:/private/synthetic"
    with pytest.raises(ValueError, match="unsafe reference"):
        generate_dossier(packet, _details(), policy)


def test_dossier_lifecycle_accepts_only_normative_transitions():
    linear = [
        DossierState.IDENTIFIED,
        DossierState.TRIAGED,
        DossierState.ACCEPTED,
        DossierState.IN_IMPLEMENTATION,
        DossierState.CANDIDATE_READY,
        DossierState.INDEPENDENTLY_VERIFIED,
    ]
    for current, requested in zip(linear, linear[1:]):
        assert transition(current, requested) == requested
    for requested in (
        DossierState.SPECIFICATION_BLOCKED,
        DossierState.DUPLICATE,
        DossierState.SUPERSEDED,
        DossierState.REJECTED_WITH_EVIDENCE,
    ):
        assert transition(DossierState.TRIAGED, requested) == requested
        with pytest.raises(ValueError, match="terminal"):
            transition(requested, DossierState.ACCEPTED)
    with pytest.raises(ValueError, match="non-normative"):
        transition(DossierState.IDENTIFIED, DossierState.ACCEPTED)
    with pytest.raises(ValueError, match="closure requires"):
        transition(DossierState.INDEPENDENTLY_VERIFIED, DossierState.CLOSED)


@pytest.mark.parametrize(
    "closure_evidence",
    [
        {"commit_hash": "e" * 40},
        {"source_locator": "src/service.py"},
        {"internal_test": "unit_test_passed"},
        {"assertion": "fixed"},
        {"team_statement": "ready"},
    ],
)
def test_dossier_closure_rejects_nonqualifying_assertions(closure_evidence):
    packet, policy = _issued_packet()
    dossier = generate_dossier(packet, _details(), policy)
    with pytest.raises(ValueError, match="trusted independently-attributable"):
        transition(
            DossierState.INDEPENDENTLY_VERIFIED,
            DossierState.CLOSED,
            dossier=dossier,
            closure_evidence=closure_evidence,
        )


def test_dossier_closure_requires_pinned_real_build_acceptance():
    packet, policy = _issued_packet()
    dossier = generate_dossier(packet, _details(), policy)
    evidence = {
        "evidence_type": "real_platform_acceptance",
        "independently_attributable": True,
        "trust_approved": True,
        "real_build_id": "synthetic-fake-build",
        "respect_revision": "d" * 40,
        "acceptance_tests": [{"test_id": "REG-001", "result": "pass"}],
    }
    assert (
        transition(
            DossierState.INDEPENDENTLY_VERIFIED,
            DossierState.CLOSED,
            dossier=dossier,
            closure_evidence=evidence,
        )
        == DossierState.CLOSED
    )


def test_missing_observer_produces_no_platform_evidence_or_dossier():
    class SyntheticMissingObserver:
        provider_id = "synthetic-missing-observer"

        def observe(self):
            return []

    artifact = collect_environment_observations(SyntheticMissingObserver())
    Draft202012Validator(
        load_schema("environment_observations_v2.schema.json")
    ).validate(artifact)
    assert artifact["observations"] == []
    with pytest.raises(ValueError):
        generate_dossier(artifact, _details(), FailClosedTrustPolicy())


def test_append_only_ledger_detects_tampering(tmp_path):
    path = tmp_path / "dossier-ledger.jsonl"
    append_event(path, {"dossier_id": "d1", "state": "identified"})
    append_event(path, {"dossier_id": "d1", "state": "triaged"})
    assert verify_ledger(path)
    lines = path.read_text().splitlines()
    event = json.loads(lines[0])
    event["state"] = "closed"
    lines[0] = json.dumps(event)
    path.write_text("\n".join(lines) + "\n")
    assert not verify_ledger(path)


def test_narrow_verifier_is_non_certifying_and_cannot_transition():
    packet, policy = _issued_packet()
    result = verify_dossier(generate_dossier(packet, _details(), policy))
    assert result["non_certifying"] is True
    assert "certified" not in result
