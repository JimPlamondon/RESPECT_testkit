# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json

from respect_ification.runtime_driver_plan import (
    DRIVER_GATED_ROW_IDS,
    analyze_canapp_source,
    render_runtime_driver_prompt,
)


def _work_plan():
    tasks = []
    for row_id in sorted(DRIVER_GATED_ROW_IDS):
        tasks.append(
            {
                "task_id": f"repair:{row_id}",
                "row_id": row_id,
                "initial_state": "pending",
                "source_hints": [],
                "normative_task": {
                    "task_id": f"repair:{row_id}",
                    "row_id": row_id,
                    "expected": f"Expected behavior for {row_id}",
                    "narrow_verifier_id": f"matrix-row:{row_id}",
                    "dependency_task_ids": [],
                },
            }
        )
    return {
        "artifact_type": "respect_ification_local_work_plan",
        "profile_id": "PROFILE-NATIVE_ANDROID",
        "matrix_semantic_hash": "matrix-hash",
        "target_digest": "target-digest",
        "semantic_hash": "plan-hash",
        "tasks": tasks,
    }


def test_source_analysis_maps_mobile_seams_without_copying_source(tmp_path):
    manifest = tmp_path / "app" / "src" / "androidMain" / "AndroidManifest.xml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '<manifest><application><activity android:name=".MainActivity" /></application></manifest>'
    )
    activity = (
        tmp_path
        / "app"
        / "src"
        / "androidMain"
        / "kotlin"
        / "org"
        / "example"
        / "MainActivity.kt"
    )
    activity.parent.mkdir(parents=True)
    activity.write_text(
        "class MainActivity { fun onNewIntent() {} val endpoint = intent.data }"
    )
    lesson = activity.parent / "LessonCore.kt"
    lesson.write_text("data class LessonSnapshot(val hits: Int, val total: Int)")
    song = tmp_path / "JiMS_Songs" / "Real_Lesson.jimsong"
    song.parent.mkdir()
    song.write_text('{"title":"Real Lesson","format_version":2}')

    analysis = analyze_canapp_source(tmp_path)

    assert "app/src/androidMain/AndroidManifest.xml" in analysis["manifest_files"]
    assert "app/src/androidMain/kotlin/org/example/MainActivity.kt" in analysis[
        "launch_files"
    ]
    assert "app/src/androidMain/kotlin/org/example/LessonCore.kt" in analysis[
        "lesson_fact_files"
    ]
    assert "JiMS_Songs/Real_Lesson.jimsong" in analysis[
        "lesson_content_files"
    ]
    assert "class MainActivity" not in json.dumps(analysis)


def test_runtime_driver_prompt_covers_all_gated_rows_and_discovered_paths(tmp_path):
    manifest = tmp_path / "app" / "src" / "main" / "AndroidManifest.xml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("<manifest />")
    plan = _work_plan()

    prompt = render_runtime_driver_prompt(
        plan,
        tmp_path,
        testkit_commit="abc123",
    )

    for row_id in DRIVER_GATED_ROW_IDS:
        assert row_id in prompt
    assert "app/src/main/AndroidManifest.xml" in prompt
    assert "abc123" in prompt
    assert "26 runtime-driver-gated rows" in prompt
    assert "derive the launch URL from the selected catalog publication" in prompt
    assert "one-to-one inventory of real lessons" in prompt
    assert "debug-only trigger" in prompt
    assert "_trusted_reference" not in prompt
    assert "_controlled_runtime" not in prompt


def test_runtime_driver_prompt_rejects_missing_gated_row(tmp_path):
    plan = _work_plan()
    plan["tasks"].pop()

    try:
        render_runtime_driver_prompt(plan, tmp_path, testkit_commit="abc123")
    except ValueError as error:
        assert "driver-gated task set" in str(error)
    else:
        raise AssertionError("missing runtime-driver row was accepted")
