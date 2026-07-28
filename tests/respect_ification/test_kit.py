# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import json
from pathlib import Path

import pytest

from respect_compat.engine import ExecutorRegistry, execute
from respect_compat.handoff import build_handoff
from respect_compat.handoff import canonical_hash
from respect_compat.matrix_runtime import load_matrix
from respect_compat.models import ResultState
from respect_compat.target import CanAppTarget
from respect_ification.ledger import append_event, read_ledger
from respect_ification.planner import build_work_plan, validate_work_plan
from respect_ification.prep import generate_prep, validate_prep_pair
from respect_ification.verifier import run_narrow_verifier


def _target():
    return CanAppTarget(
        uri="https://canapp.invalid/descriptor.json",
        adapter="test",
        digest="target-digest",
        document={"metadata": {}, "links": []},
        capabilities={"descriptor"},
    )


def _executor(context, row):
    state = ResultState.FAIL if row.owner == "canapp" else ResultState.PASS
    evidence = [context.evidence(row, "controlled", context.target.uri, state.value)]
    return context.result(row, state, state.value, "controlled result", evidence)


def _handoff():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, _executor)
    run = execute(
        matrix, _target(), "PROFILE-WEB", "test", registry, run_seed="kit-test"
    )
    return build_handoff(run)


def test_prep_public_private_separation_and_determinism(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')\n")
    (tmp_path / "pyproject.toml").write_text("[build-system]\n")
    first = generate_prep(
        tmp_path, "target-digest", "PROFILE-WEB", include_private=True
    )
    second = generate_prep(
        tmp_path, "target-digest", "PROFILE-WEB", include_private=True
    )
    assert first == second
    public, private = first
    assert "source_inventory" not in json.dumps(public)
    assert private["public_semantic_hash"] == public["semantic_hash"]
    assert validate_prep_pair(public, private) == []


def test_prep_rejects_secret_and_symlink_escape(tmp_path):
    secret_path = tmp_path / ("." + "env")
    secret_path.write_text("API_TOKEN=secret-value\n")
    with pytest.raises(ValueError, match="secret"):
        generate_prep(tmp_path, "target-digest", "PROFILE-WEB")
    secret_path.unlink()
    (tmp_path / "escape").symlink_to(Path("/tmp"))
    with pytest.raises(ValueError, match="symlink"):
        generate_prep(tmp_path, "target-digest", "PROFILE-WEB")


def test_planner_works_without_private_prep():
    report, evidence, tasks = _handoff()
    plan = build_work_plan(report, evidence, tasks)
    assert plan["tasks"]
    assert all(item["source_hints"] == [] for item in plan["tasks"])
    assert validate_work_plan(plan, tasks) == []


def test_private_prep_adds_only_nonnormative_source_hints(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('ok')\n")
    public, private = generate_prep(
        tmp_path, "target-digest", "PROFILE-WEB", include_private=True
    )
    report, evidence, tasks = _handoff()
    row_id = tasks["tasks"][0]["row_id"]
    private["row_mappings"] = {row_id: ["src/main.py"]}
    private["semantic_hash"] = canonical_hash(private, ("semantic_hash",))
    plan = build_work_plan(report, evidence, tasks, private_prep=private)
    planned = next(item for item in plan["tasks"] if item["row_id"] == row_id)
    assert planned["normative_task"] == tasks["tasks"][0]
    assert planned["source_hints"][0]["path"] == "src/main.py"
    assert planned["source_hints"][0]["authority"] == "nonnormative_private_prep"
    assert public["target_digest"] == report["target_digest"]


def test_planner_rejects_mismatched_private_prep(tmp_path):
    (tmp_path / "main.py").write_text("print('ok')\n")
    _, private = generate_prep(
        tmp_path, "another-target", "PROFILE-WEB", include_private=True
    )
    with pytest.raises(ValueError, match="target"):
        build_work_plan(*_handoff(), private_prep=private)


def test_ledger_is_append_only_and_rejects_invalid_transition(tmp_path):
    report, evidence, tasks = _handoff()
    plan = build_work_plan(report, evidence, tasks)
    task_id = plan["tasks"][0]["task_id"]
    ledger = tmp_path / "ledger.jsonl"
    append_event(ledger, plan, task_id, "diagnosing", "inspect evidence")
    append_event(ledger, plan, task_id, "implementing", "repair locally")
    state = read_ledger(ledger, plan)
    assert state["tasks"][task_id]["state"] == "implementing"
    with pytest.raises(ValueError, match="transition"):
        append_event(ledger, plan, task_id, "locally_verified", "skip verification")


def test_ledger_detects_history_tampering(tmp_path):
    report, evidence, tasks = _handoff()
    plan = build_work_plan(report, evidence, tasks)
    task_id = plan["tasks"][0]["task_id"]
    ledger = tmp_path / "ledger.jsonl"
    append_event(ledger, plan, task_id, "diagnosing", "inspect")
    item = json.loads(ledger.read_text())
    item["note"] = "tampered"
    ledger.write_text(json.dumps(item) + "\n")
    with pytest.raises(ValueError, match="hash"):
        read_ledger(ledger, plan)


def test_ledger_rejects_unsafe_verifier_reference(tmp_path):
    report, evidence, tasks = _handoff()
    plan = build_work_plan(report, evidence, tasks)
    task_id = plan["tasks"][0]["task_id"]
    ledger = tmp_path / "ledger.jsonl"
    append_event(ledger, plan, task_id, "diagnosing", "inspect")
    append_event(ledger, plan, task_id, "implementing", "repair")
    append_event(ledger, plan, task_id, "verifying", "verify")
    with pytest.raises(ValueError, match="unsafe"):
        append_event(
            ledger,
            plan,
            task_id,
            "locally_verified",
            "narrow verifier passed",
            "../outside.json",
        )


def test_narrow_verifier_is_non_certifying():
    report, evidence, tasks = _handoff()
    plan = build_work_plan(report, evidence, tasks)
    task = plan["tasks"][0]
    result = run_narrow_verifier(
        task["normative_task"]["narrow_verifier_id"],
        task["row_id"],
        _target(),
        "PROFILE-WEB",
        predecessor_target_digest="prior-target",
    )
    assert result["mode"] == "narrow_non_certifying"
    assert result["certified"] is False
    assert result["row_id"] == task["row_id"]
    assert result["predecessor_target_digest"] == "prior-target"
    assert result["target_lineage"] == "owner_supplied_repaired_successor"


def test_unknown_or_packet_command_verifier_is_rejected():
    with pytest.raises(ValueError, match="unknown verifier"):
        run_narrow_verifier(
            "sh -c 'touch /tmp/forbidden'",
            "DESC-001",
            _target(),
            "PROFILE-WEB",
        )
