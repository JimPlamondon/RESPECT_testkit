# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json

from respect_compat.handoff import canonical_hash
from respect_ification.cli import main
from respect_compat.resources import resource
from respect_ification.runtime_driver_plan import DRIVER_GATED_ROW_IDS


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


def test_driver_plan_cli_inspects_source_and_writes_complete_prompt(tmp_path):
    source = tmp_path / "source"
    manifest = source / "app" / "src" / "main" / "AndroidManifest.xml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("<manifest />")
    tasks = [
        {
            "task_id": f"repair:{row_id}",
            "row_id": row_id,
            "initial_state": "pending",
            "source_hints": [],
            "normative_task": {
                "task_id": f"repair:{row_id}",
                "row_id": row_id,
                "expected": f"Expected {row_id}",
                "narrow_verifier_id": f"matrix-row:{row_id}",
                "dependency_task_ids": [],
            },
        }
        for row_id in sorted(DRIVER_GATED_ROW_IDS)
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
    output = tmp_path / "driver-prompt.md"

    assert (
        main(
            [
                "driver-plan",
                "--work-plan",
                str(plan_path),
                "--source-root",
                str(source),
                "--testkit-commit",
                "abc123",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    prompt = output.read_text()
    assert "26 runtime-driver-gated rows" in prompt
    assert "app/src/main/AndroidManifest.xml" in prompt
