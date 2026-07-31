# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import pytest

from respect_compat.android_runtime_runner import validate_runtime_scenario
from respect_compat.execution_log import ExecutionLog
from respect_compat.handoff import canonical_hash
from respect_ification.cli import (
    _lesson_child_outcome,
    build_parser,
    main,
)
from respect_ification.lesson_modeler import (
    build_coverage,
    build_modeling_packet,
    compile_run_plan,
    finalize_artifact,
    read_artifact,
    resolve_selection,
    run_lesson_batch,
    validate_artifact,
    write_artifact,
    write_modeling_handback,
)


DIGEST = "a" * 64


def _inventory(count=3):
    lessons = []
    for index in range(count):
        lessons.append(
            {
                "lesson_id": f"lesson-{index:04d}",
                "course_id": f"course-{index // 1000}",
                "source": {
                    "path": f"lessons/{index:04d}.json",
                    "sha256": f"{index:064x}",
                },
                "owner_metadata": {"example:locale": "en"},
            }
        )
    return finalize_artifact(
        {
            "artifact_type": "respect_canapp_lesson_inventory",
            "format_version": "1.0.0",
            "source_digest": DIGEST,
            "lessons": lessons,
        }
    )


def _scenario_template():
    return {
        "artifact_type": "respect_native_android_runtime_scenario",
        "format_version": "1.0.0",
        "canapp_package": {"$binding": "canapp_package"},
        "driver_package": "org.respect.testkit.runtime",
        "launch_url": {"$binding": "launch_url"},
        "endpoint": {"$binding": "endpoint"},
        "auth": {"$binding": "auth"},
        "actor": {"$binding": "actor"},
        "activity_id": {"$binding": "activity_id"},
        "actions": [{"type": "wait", "milliseconds": 1}],
    }


def _binding(index):
    return {
        "canapp_package": "org.example.canapp",
        "launch_url": f"https://owner.example/lesson/{index}",
        "endpoint": "https://lrs.example/xapi",
        "auth": f"secret-auth-{index}",
        "actor": {"account": {"name": f"synthetic-{index}", "homePage": "https://example.invalid"}},
        "activity_id": f"https://lesson.example/activity/{index}",
    }


def _model(inventory, count=3, *, unclassified=()):
    classifications = []
    bindings = []
    for index in range(count):
        lesson_id = f"lesson-{index:04d}"
        if index in unclassified:
            classifications.append(
                {
                    "lesson_id": lesson_id,
                    "status": "unclassified",
                    "reason": "owner evidence is incomplete",
                    "evidence": [{"kind": "source_hash", "sha256": f"{index:064x}"}],
                }
            )
        else:
            family_id = f"family-{index % 3}"
            classifications.append(
                {
                    "lesson_id": lesson_id,
                    "status": "classified",
                    "family_id": family_id,
                    "evidence": [{"kind": "source_hash", "sha256": f"{index:064x}"}],
                }
            )
            bindings.append({"lesson_id": lesson_id, "values": _binding(index)})
    parameter_types = {
        "canapp_package": {"type": "string"},
        "launch_url": {"type": "string"},
        "endpoint": {"type": "string"},
        "auth": {"type": "string", "sensitive": True},
        "actor": {"type": "object", "sensitive": True},
        "activity_id": {"type": "string"},
    }
    families = [
        {
            "family_id": f"family-{index}",
            "required_capabilities": ["wait"],
            "parameters": parameter_types,
            "scenario_template": _scenario_template(),
        }
        for index in range(3)
    ]
    return finalize_artifact(
        {
            "artifact_type": "respect_canapp_lesson_model",
            "format_version": "1.0.0",
            "inventory_semantic_hash": inventory["semantic_hash"],
            "families": families,
            "classifications": classifications,
            "lesson_bindings": bindings,
        }
    )


def _selection(inventory, model, **selectors):
    return finalize_artifact(
        {
            "artifact_type": "respect_canapp_lesson_selection",
            "format_version": "1.0.0",
            "inventory_semantic_hash": inventory["semantic_hash"],
            "model_semantic_hash": model["semantic_hash"],
            "selectors": {
                "all": False,
                "lesson_ids": [],
                "course_ids": [],
                "family_ids": [],
                **selectors,
            },
            "exclude_lesson_ids": [],
        }
    )


def test_three_course_family_and_all_selections_preserve_inventory_order():
    inventory = _inventory(3000)
    model = _model(inventory, 3000)
    explicit = _selection(
        inventory,
        model,
        lesson_ids=["lesson-2000", "lesson-0002", "lesson-1001"],
    )
    assert resolve_selection(inventory, model, explicit) == [
        "lesson-0002",
        "lesson-1001",
        "lesson-2000",
    ]
    course = _selection(inventory, model, course_ids=["course-1"])
    assert len(resolve_selection(inventory, model, course)) == 1000
    family = _selection(inventory, model, family_ids=["family-2"])
    assert len(resolve_selection(inventory, model, family)) == 1000
    all_lessons = _selection(inventory, model, all=True)
    assert len(resolve_selection(inventory, model, all_lessons)) == 3000


def test_unknown_duplicate_and_accidentally_empty_selection_fail():
    inventory = _inventory()
    model = _model(inventory)
    with pytest.raises(ValueError, match="unknown lesson"):
        resolve_selection(
            inventory,
            model,
            _selection(inventory, model, lesson_ids=["missing"]),
        )
    with pytest.raises(ValueError, match="duplicate"):
        resolve_selection(
            inventory,
            model,
            _selection(
                inventory,
                model,
                lesson_ids=["lesson-0000", "lesson-0000"],
            ),
        )
    with pytest.raises(ValueError, match="empty"):
        resolve_selection(inventory, model, _selection(inventory, model))


def test_compile_uses_typed_bindings_and_existing_scenario_validator():
    inventory = _inventory()
    model = _model(inventory)
    selection = _selection(
        inventory,
        model,
        lesson_ids=["lesson-0000", "lesson-0002"],
    )
    plan = compile_run_plan(
        inventory,
        model,
        selection,
        testkit_commit="b" * 40,
        target_id="synthetic-target",
        target_digest=DIGEST,
        profile_id="PROFILE-NATIVE_ANDROID",
        available_capabilities={"wait", "tap", "keyevent", "stroke", "webview_tap"},
    )
    assert [entry["lesson_id"] for entry in plan["entries"]] == [
        "lesson-0000",
        "lesson-0002",
    ]
    assert all(entry["status"] == "compiled" for entry in plan["entries"])
    for entry in plan["entries"]:
        validate_runtime_scenario(entry["scenario"])


def test_unclassified_and_missing_capability_fail_closed_but_remain_visible():
    inventory = _inventory()
    model = _model(inventory, unclassified=(1,))
    model["families"][0]["required_capabilities"] = ["future_action"]
    model = finalize_artifact(model)
    selection = _selection(inventory, model, all=True)
    plan = compile_run_plan(
        inventory,
        model,
        selection,
        testkit_commit="b" * 40,
        target_id="synthetic-target",
        target_digest=DIGEST,
        profile_id="PROFILE-NATIVE_ANDROID",
        available_capabilities={"wait"},
    )
    by_id = {entry["lesson_id"]: entry for entry in plan["entries"]}
    assert by_id["lesson-0000"]["status"] == "blocked"
    assert by_id["lesson-0000"]["reason"] == "missing_testkit_capability"
    assert by_id["lesson-0001"]["status"] == "blocked"
    assert by_id["lesson-0001"]["reason"] == "unclassified"
    assert plan["capability_gaps"][0]["capability"] == "future_action"
    assert "lesson-0000" not in json.dumps(plan["capability_gaps"])


@pytest.mark.parametrize(
    "bad_value,error",
    [
        ({"$binding": "auth", "extra": "code"}, "binding reference"),
        ({"$binding": "unknown"}, "undeclared binding"),
    ],
)
def test_template_expressions_and_unknown_bindings_are_rejected(bad_value, error):
    inventory = _inventory(1)
    model = _model(inventory, 1)
    model["families"][0]["scenario_template"]["auth"] = bad_value
    model = finalize_artifact(model)
    selection = _selection(inventory, model, all=True)
    with pytest.raises(ValueError, match=error):
        compile_run_plan(
            inventory,
            model,
            selection,
            testkit_commit="b" * 40,
            target_id="synthetic-target",
            target_digest=DIGEST,
            profile_id="PROFILE-NATIVE_ANDROID",
            available_capabilities={"wait"},
        )


def test_schema_hash_and_duplicate_json_keys_are_rejected(tmp_path):
    inventory = _inventory()
    validate_artifact(inventory, "inventory")
    altered = json.loads(json.dumps(inventory))
    altered["lessons"][0]["lesson_id"] = "changed"
    with pytest.raises(ValueError, match="semantic hash"):
        validate_artifact(altered, "inventory")
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"artifact_type":"x","artifact_type":"y"}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        read_artifact(duplicate)


def test_coverage_never_turns_sample_into_inventory_execution():
    inventory = _inventory(3000)
    model = _model(inventory, 3000)
    selection = _selection(
        inventory,
        model,
        lesson_ids=["lesson-0000", "lesson-0001", "lesson-0002"],
    )
    plan = compile_run_plan(
        inventory,
        model,
        selection,
        testkit_commit="b" * 40,
        target_id="synthetic-target",
        target_digest=DIGEST,
        profile_id="PROFILE-NATIVE_ANDROID",
        available_capabilities={"wait"},
    )
    coverage = build_coverage(inventory, model, selection, plan, {})
    assert coverage["counts"]["inventoried"] == 3000
    assert coverage["counts"]["selected"] == 3
    assert coverage["counts"]["executed"] == 0
    assert coverage["full_inventory_executed"] is False


def test_modeling_packet_is_source_bound_without_copying_source(tmp_path):
    source = tmp_path / "owner-source"
    source.mkdir()
    (source / "lesson-loader.js").write_text(
        'function openLesson(id) { return fetch("lessons/" + id); }'
    )
    inventory = _inventory(1)
    packet = build_modeling_packet(source, inventory)
    encoded = json.dumps(packet)
    assert packet["source_tree_digest"]
    assert "openLesson" not in encoded
    assert "function " not in encoded
    prompt = tmp_path / "modeling-prompt.md"
    todo = tmp_path / "Human_ToDo.md"
    write_modeling_handback(packet, prompt, todo)
    assert packet["semantic_hash"] in prompt.read_text()
    assert str(prompt) in todo.read_text()


def test_batch_preserves_child_results_and_resume_requires_exact_hashes(tmp_path):
    inventory = _inventory(2)
    model = _model(inventory, 2)
    selection = _selection(inventory, model, all=True)
    plan = compile_run_plan(
        inventory,
        model,
        selection,
        testkit_commit="b" * 40,
        target_id="synthetic-target",
        target_digest=DIGEST,
        profile_id="PROFILE-NATIVE_ANDROID",
        available_capabilities={"wait"},
    )

    def runner(entry, child_dir, event):
        report = {
            "lesson_id": entry["lesson_id"],
            "scenario_sha256": entry["scenario_sha256"],
            "exit_code": 0 if entry["lesson_id"].endswith("0") else 2,
            "outcome": "passed" if entry["lesson_id"].endswith("0") else "blocked",
        }
        (child_dir / "respect-report.json").write_text(json.dumps(report))
        event("child_test", "observed", {"lesson_id_hash": canonical_hash(entry)})
        return report

    output = tmp_path / "batch"
    log = ExecutionLog(
        output / "respect-execution-log.jsonl",
        program="test",
        command="lesson-model",
        argv=["lesson-model", "--execute"],
    )
    result = run_lesson_batch(plan, output, runner, event=log.emit)
    log.finish(result["exit_code"])
    assert result["exit_code"] == 2
    assert len(result["children"]) == 2
    assert result["children"][1]["outcome"] == "blocked"
    resumed = run_lesson_batch(plan, output, runner, resume=True)
    assert all(child["resumed"] for child in resumed["children"])
    first_report = output / result["children"][0]["report"]
    original_report = first_report.read_text()
    first_report.write_text('{"replayed":true}')
    with pytest.raises(ValueError, match="child report binding"):
        run_lesson_batch(plan, output, runner, resume=True)
    first_report.write_text(original_report)
    changed = json.loads(json.dumps(plan))
    changed["target_digest"] = "c" * 64
    changed = finalize_artifact(changed)
    with pytest.raises(ValueError, match="run plan"):
        run_lesson_batch(changed, output, runner, resume=True)


def test_execution_log_omits_sensitive_lesson_values(tmp_path):
    inventory = _inventory(1)
    model = _model(inventory, 1)
    selection = _selection(inventory, model, all=True)
    secret = model["lesson_bindings"][0]["values"]["auth"]
    log = ExecutionLog(
        tmp_path / "respect-execution-log.jsonl",
        program="test",
        command="lesson-model",
        argv=["lesson-model", "--auth", secret],
    )
    plan = compile_run_plan(
        inventory,
        model,
        selection,
        testkit_commit="b" * 40,
        target_id="synthetic-target",
        target_digest=DIGEST,
        profile_id="PROFILE-NATIVE_ANDROID",
        available_capabilities={"wait"},
        event=log.emit,
    )
    log.finish(0)
    assert plan["entries"][0]["status"] == "compiled"
    assert secret not in (tmp_path / "respect-execution-log.jsonl").read_text()


def test_cli_exposes_canapp_lesson_modeler_and_compiles(tmp_path):
    parser = build_parser()
    help_text = parser.format_help()
    assert "lesson-model" in help_text
    inventory = _inventory(2)
    model = _model(inventory, 2)
    selection = _selection(inventory, model, all=True)
    inventory_path = tmp_path / "inventory.json"
    model_path = tmp_path / "model.json"
    selection_path = tmp_path / "selection.json"
    write_artifact(inventory_path, inventory)
    write_artifact(model_path, model)
    write_artifact(selection_path, selection)
    output = tmp_path / "compiled"
    exit_code = main(
        [
            "lesson-model",
            "compile",
            "--inventory",
            str(inventory_path),
            "--model",
            str(model_path),
            "--selection",
            str(selection_path),
            "--testkit-commit",
            "b" * 40,
            "--target-id",
            "synthetic-target",
            "--target-digest",
            DIGEST,
            "--profile",
            "PROFILE-NATIVE_ANDROID",
            "--available-capability",
            "wait",
            "--output-dir",
            str(output),
        ]
    )
    assert exit_code == 0
    assert (output / "canapp-lesson-run-plan.json").is_file()
    assert (output / "canapp-lesson-capability-gaps.json").is_file()
    log = (output / "respect-execution-log.jsonl").read_text()
    assert '"step": "scenario_compilation"' in log


@pytest.mark.parametrize(
    ("states", "exit_code", "expected"),
    [
        (["pass"], 0, "passed"),
        (["pass", "fail", "blocked"], 1, "failed"),
        (["pass", "incomplete", "blocked"], 2, "incomplete"),
        (["pass", "blocked"], 2, "blocked"),
    ],
)
def test_lesson_child_outcome_uses_report_row_states(
    states, exit_code, expected
):
    report = {"results": [{"state": state} for state in states]}
    assert _lesson_child_outcome(report, exit_code) == expected
