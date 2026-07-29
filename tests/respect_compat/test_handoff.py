# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import json

import pytest

from respect_compat.engine import ExecutorRegistry, execute
from respect_compat.handoff import (
    build_handoff,
    validate_handoff,
    write_handoff,
)
from respect_compat.matrix_runtime import load_matrix
from respect_compat.models import ResultState
from respect_compat.target import CanAppTarget


def _target():
    return CanAppTarget(
        uri="https://canapp.invalid/descriptor.json",
        adapter="test",
        digest="target-digest",
        document={"metadata": {}, "links": []},
        capabilities={"descriptor"},
    )


def _result(context, row):
    state = ResultState.FAIL if row.owner == "canapp" else ResultState.PASS
    evidence = [context.evidence(row, "controlled", context.target.uri, state.value)]
    return context.result(row, state, state.value, "controlled result", evidence)


def _run():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, _result)
    return execute(
        matrix,
        _target(),
        "PROFILE-WEB",
        "test",
        registry,
        run_seed="handoff-test",
    )


def test_handoff_maps_actionable_canapp_rows_exactly():
    report, evidence, tasks = build_handoff(_run())
    actionable = {
        item["row_id"]
        for item in report["results"]
        if "kit_task" in item["artifacts"]
    }
    assert {item["row_id"] for item in tasks["tasks"]} == actionable
    assert tasks["summary"]["actionable_task_count"] == len(actionable)
    assert validate_handoff(report, evidence, tasks) == []
    assert {
        report["format_version"],
        evidence["format_version"],
        tasks["format_version"],
    } == {"2.0.0"}
    assert report["challenge"] == evidence["challenge"] == tasks["challenge"]


def test_handoff_does_not_turn_canapp_observation_gap_into_kit_work():
    matrix = load_matrix()
    registry = ExecutorRegistry()

    def blocked(context, row):
        evidence = [
            context.evidence(row, "controlled", context.target.uri, "blocked")
        ]
        return context.result(
            row,
            ResultState.BLOCKED,
            None,
            "dependency absent",
            evidence,
        )

    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, blocked)
    run = execute(matrix, _target(), "PROFILE-WEB", "test", registry)
    _, _, tasks = build_handoff(run)
    assert tasks["tasks"] == []


def test_handoff_writes_three_bound_artifacts(tmp_path):
    report, evidence, tasks = build_handoff(_run())
    write_handoff(report, evidence, tasks, tmp_path)
    assert json.loads((tmp_path / "respect-report.json").read_text()) == report
    assert (tmp_path / "respect-evidence-manifest.json").is_file()
    assert (tmp_path / "respect-ification-task-packet.json").is_file()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda report, evidence, tasks: report.update(
            {"matrix_semantic_hash": "0" * 64}
        ),
        lambda report, evidence, tasks: evidence["evidence"][0].update(
            {"target_digest": "other"}
        ),
        lambda report, evidence, tasks: tasks["tasks"][0].update(
            {"evidence_ids": ["missing"]}
        ),
        lambda report, evidence, tasks: tasks["tasks"][0].update(
            {"dependency_task_ids": ["missing"]}
        ),
        lambda report, evidence, tasks: tasks["tasks"][0].update(
            {"evidence_locators": ["../private"]}
        ),
    ],
)
def test_handoff_rejects_tampering(mutator):
    artifacts = [copy.deepcopy(item) for item in build_handoff(_run())]
    mutator(*artifacts)
    assert validate_handoff(*artifacts)
