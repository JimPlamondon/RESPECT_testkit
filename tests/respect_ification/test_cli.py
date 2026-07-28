# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json

from respect_compat.handoff import canonical_hash
from respect_ification.cli import main
from respect_compat.resources import resource


def test_prepare_cli_writes_public_and_private_packets(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.py").write_text("print('ok')\n")
    public = tmp_path / "public.json"
    private = tmp_path / "private.json"
    assert (
        main(
            [
                "prepare",
                "--source-root",
                str(source),
                "--target-digest",
                "target-digest",
                "--profile",
                "PROFILE-WEB",
                "--public-output",
                str(public),
                "--private-output",
                str(private),
            ]
        )
        == 0
    )
    assert json.loads(public.read_text())["artifact_type"].endswith("public_prep")
    assert json.loads(private.read_text())["artifact_type"].endswith("private_prep")


def test_full_test_cli_preserves_test_suite_verdict(tmp_path):
    root = resource("data/fixtures/v1_0/positive/web_reference")
    output = tmp_path / "suite"
    assert (
        main(
            [
                "full-test",
                "--fixture-dir",
                str(root),
                "--profile",
                "PROFILE-WEB",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads((output / "respect-report.json").read_text())
    assert report["verdict"]["certified"] is True
    assert (output / "respect-evidence-manifest.json").is_file()
    assert (output / "respect-ification-task-packet.json").is_file()


def test_repair_plan_cli_writes_adapter_and_prompt(tmp_path):
    source = tmp_path / "source"
    loader = source / "app" / "loader.py"
    loader.parent.mkdir(parents=True)
    loader.write_text('open("lessons/real.unit")')
    lesson = source / "lessons" / "real.unit"
    lesson.parent.mkdir()
    lesson.write_text('{"title":"Real Unit"}')
    tasks = [
        {
            "task_id": "repair:OPDS-003",
            "row_id": "OPDS-003",
            "initial_state": "pending",
            "source_hints": [],
            "normative_task": {
                "task_id": "repair:OPDS-003",
                "row_id": "OPDS-003",
                "expected": "Truthful publication metadata",
                "narrow_verifier_id": "matrix-row:OPDS-003",
                "dependency_task_ids": [],
            },
        }
    ]
    plan = {
        "artifact_type": "respect_ification_local_work_plan",
        "profile_id": "PROFILE-NATIVE_ANDROID",
        "matrix_semantic_hash": "matrix-hash",
        "target_digest": "target-digest",
        "tasks": tasks,
    }
    plan["semantic_hash"] = canonical_hash(plan, ("semantic_hash",))
    plan_path = tmp_path / "work-plan.json"
    plan_path.write_text(json.dumps(plan))
    adapter_output = tmp_path / "repair-adapter.json"
    prompt_output = tmp_path / "repair-prompt.md"

    assert (
        main(
            [
                "repair-plan",
                "--work-plan",
                str(plan_path),
                "--source-root",
                str(source),
                "--canapp-root",
                ".",
                "--testkit-commit",
                "abc123",
                "--adapter-output",
                str(adapter_output),
                "--prompt-output",
                str(prompt_output),
            ]
        )
        == 0
    )
    adapter = json.loads(adapter_output.read_text())
    prompt = prompt_output.read_text()
    assert adapter["adapter_scope"] == "kit_time_only"
    assert "lessons/real.unit" in prompt
    assert "Truthful publication metadata" in prompt
