# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import pytest

from respect_compat import executors
from respect_compat.engine import execute
from respect_compat.matrix_runtime import load_matrix
from respect_compat.models import ResultState
from respect_compat.routing import ObservedResult, WorkflowDisposition
from respect_compat.target import CanAppTarget


def _target():
    return CanAppTarget(
        uri="https://canapp.invalid/descriptor.json",
        adapter="test",
        digest="a" * 64,
        document={"metadata": {}, "links": []},
        capabilities=set(),
    )


@pytest.mark.parametrize(
    ("row_id", "contract"),
    [
        ("SUITE-003", "suite_selected_coverage_contract"),
        ("SUITE-004", "suite_nonfinal_cannot_certify_contract"),
        ("SUITE-005", "suite_independent_oracle_contract"),
    ],
)
def test_suite_meta_test_fails_when_production_contract_is_removed(
    monkeypatch, row_id, contract
):
    matrix = load_matrix()
    monkeypatch.setattr(executors, contract, lambda *args: False)

    run = execute(
        matrix,
        _target(),
        "PROFILE-SUITE_QUALITY",
        "test",
        executors.build_registry(matrix),
        run_seed="suite-assurance-negative-control",
        selected_row_ids=[row_id],
    )

    assert run.results[0].state == ResultState.FAIL
    assert run.results[0].atomic_result.final_affirmative is False


def test_real_signed_platform_observation_is_neutral_and_generates_no_work():
    matrix = load_matrix()
    row = next(
        item
        for item in matrix.selected_rows("PROFILE-WEB")
        if item.owner == "respect_service"
    )
    target = _target()
    target.metadata["_trusted_reference"] = True
    target.metadata["environment_observations"] = {
        row.row_id: {
            "state": "fail",
            "observed": {"synthetic": "platform behavior"},
            "source": "synthetic-platform-provider",
            "platform_evidence": {
                "signed": True,
                "real_platform": True,
                "independently_attributed": True,
                "real_build_id": "synthetic-fake-build",
                "respect_revision": "d" * 40,
                "first_applicable_version": "1.0.0",
                "last_applicable_version": "2.0.0",
            },
        }
    }
    run = execute(
        matrix,
        target,
        "PROFILE-WEB",
        "test",
        executors.build_registry(matrix),
        run_seed="synthetic-platform-route",
        selected_row_ids=[row.row_id],
    )
    atomic = run.results[0].atomic_result
    assert atomic.observed_result == ObservedResult.RESPECT_PLATFORM_GAP
    assert (
        atomic.workflow_disposition
        == WorkflowDisposition.PLATFORM_OBSERVATION_RECORDED
    )
    assert atomic.artifacts == ()

    target.metadata["environment_observations"] = {}
    missing = execute(
        matrix,
        target,
        "PROFILE-WEB",
        "test",
        executors.build_registry(matrix),
        run_seed="synthetic-platform-route-missing",
        selected_row_ids=[row.row_id],
    ).results[0].atomic_result
    assert missing.observed_result == ObservedResult.TESTKIT_CAPABILITY_GAP
