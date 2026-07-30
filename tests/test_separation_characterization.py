# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from respect_compat.models import RequirementOwner
from respect_compat.routing import (
    ClassificationInput,
    ControlOwner,
    ObservedResult,
    ResponsibleParty,
    RoutingEvidence,
    SubstituteFidelity,
    VerificationMode,
    classify_result,
)
from respect_compat.school_harness import _respect_gradle_command


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads(
    (ROOT / "tests/fixtures/separation_characterization_v1.json").read_text(
        encoding="utf-8"
    )
)


def _logical_result(result):
    value = result.to_json_dict()
    value.pop("policy_required")
    value.pop("row_id")
    value.pop("verification_mode")
    return value


def test_canapp_facing_routing_characterization():
    fidelity = SubstituteFidelity(
        substitute_id="local-https",
        substitute_version="1",
        owner=ResponsibleParty.APPDEV_PUBLICATION,
        covered_semantics=("descriptor",),
        excluded_semantics=("stable-owner-origin",),
        fidelity_guarantees=("same-byte publication",),
        evidence_schema="respect-substitute-evidence-v2",
        real_dependency="owner-controlled HTTPS origin",
        clearance="deploy unchanged bytes",
        promotion_test="rerun affected rows",
        rerun_scope="affected_rows",
    )
    cases = {
        "canapp_pass": ClassificationInput(
            requirement_owner=RequirementOwner.CANAPP,
            control_owner=ControlOwner.CANAPP_ARTIFACT,
            verification_mode=VerificationMode.REAL,
            observed_result=ObservedResult.PASS,
        ),
        "canapp_failure": ClassificationInput(
            requirement_owner=RequirementOwner.CANAPP,
            control_owner=ControlOwner.CANAPP_ARTIFACT,
            verification_mode=VerificationMode.REAL,
            observed_result=ObservedResult.CANAPP_IMPLEMENTATION_FAIL,
            evidence=RoutingEvidence(attributable=True),
        ),
        "provisional_substitute": ClassificationInput(
            requirement_owner=RequirementOwner.CANAPP,
            control_owner=ControlOwner.APPDEV_PUBLICATION,
            verification_mode=VerificationMode.SUBSTITUTE,
            observed_result=ObservedResult.CODE_COMPATIBLE_THROUGH_SUBSTITUTE,
            evidence=RoutingEvidence(
                attributable=True,
                positive_substitute=True,
                claimed_semantics=("descriptor",),
                substitute_fidelity=fidelity,
            ),
        ),
        "missing_observer": ClassificationInput(
            requirement_owner=RequirementOwner.RESPECT_SERVICE,
            control_owner=ControlOwner.RESPECT_PLATFORM,
            verification_mode=VerificationMode.UNAVAILABLE,
            observed_result=ObservedResult.UNMEASURED_EXTERNAL_DEPENDENCY,
            evidence=RoutingEvidence(observer_present=False),
        ),
        "harness_error": ClassificationInput(
            requirement_owner=RequirementOwner.TEST_SUITE,
            control_owner=ControlOwner.TESTKIT,
            verification_mode=VerificationMode.REAL,
            observed_result=ObservedResult.HARNESS_ERROR,
            evidence=RoutingEvidence(actor_malfunction=True),
        ),
    }
    assert {
        name: _logical_result(classify_result(name, value))
        for name, value in cases.items()
    } == {name: GOLDEN[name] for name in cases}


def test_school_harness_gradle_ca_handoff_characterization():
    assert _respect_gradle_command(
        Path("/checkout/respect"),
        Path("/run/tls/ca.pem"),
    ) == GOLDEN["respect_gradle_command"]


def test_retained_console_script_characterization():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    scripts = sorted(
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if line.startswith("respect-")
        and not line.startswith("respect-upgrade-dossier")
    )
    assert scripts == GOLDEN["retained_console_scripts"]
