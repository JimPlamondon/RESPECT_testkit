# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from respect_compat.handoff import canonical_hash
from respect_ification.repair_adapter import (
    analyze_canapp_source,
    build_repair_adapter,
    render_repair_prompt,
)


def _work_plan(profile_id="PROFILE-NATIVE_ANDROID"):
    core = {
        "artifact_type": "respect_ification_local_work_plan",
        "format_version": "1.0.0",
        "profile_id": profile_id,
        "matrix_semantic_hash": "matrix-hash",
        "target_digest": "target-digest",
        "tasks": [
            {
                "task_id": "repair:OPDS-003",
                "row_id": "OPDS-003",
                "initial_state": "pending",
                "source_hints": [],
                "normative_task": {
                    "task_id": "repair:OPDS-003",
                    "row_id": "OPDS-003",
                    "expected": "Describe the selected publication truthfully.",
                    "narrow_verifier_id": "matrix-row:OPDS-003",
                    "dependency_task_ids": [],
                },
            }
        ],
    }
    return {**core, "semantic_hash": canonical_hash(core)}


def test_source_analysis_discovers_proprietary_content_from_product_references(
    tmp_path,
):
    activity = tmp_path / "app" / "MainActivity.kt"
    activity.parent.mkdir()
    activity.write_text(
        'fun openLesson() = assets.open("Opaque_One.lessonpack")'
    )
    content = tmp_path / "private-content" / "Opaque_One.lessonpack"
    content.parent.mkdir()
    content.write_text('{"title":"Opaque One","private_format":17}')

    analysis = analyze_canapp_source(tmp_path)

    candidate = next(
        item
        for item in analysis["content_candidates"]
        if item["path"] == "private-content/Opaque_One.lessonpack"
    )
    assert candidate["metadata_hint"]["title"] == "Opaque One"
    assert candidate["media_type_hint"] == "application/octet-stream"
    assert candidate["referenced_by"] == ["app/MainActivity.kt"]
    assert "referenced by product source" in candidate["reasons"]


def test_repair_adapter_is_kit_time_and_profile_agnostic(tmp_path):
    loader = tmp_path / "web" / "loader.ts"
    loader.parent.mkdir()
    loader.write_text('fetch("unit-42.blob"); const completion = "complete"')
    content = loader.parent / "unit-42.blob"
    content.write_bytes(b"\x00\x01proprietary")

    adapter = build_repair_adapter(
        _work_plan("PROFILE-WEB"),
        tmp_path,
        testkit_commit="abc123",
    )
    prompt = render_repair_prompt(adapter)

    assert adapter["adapter_scope"] == "kit_time_only"
    assert adapter["profile_id"] == "PROFILE-WEB"
    assert adapter["semantic_hash"] == canonical_hash(
        adapter, ("semantic_hash",)
    )
    assert "web/unit-42.blob" in prompt
    assert "proprietary content format belongs to the CanApp-specific repair" in prompt
    assert "normal production code" in prompt
    assert "hidden query parameter" in prompt
    assert "Test Suite recognition" in prompt
    assert "suite-owned companion" not in prompt


def test_source_analysis_scopes_product_code_but_follows_external_content(tmp_path):
    app = tmp_path / "apps" / "candidate"
    app.mkdir(parents=True)
    (app / "loader.ts").write_text('fetch("real.unit")')
    external = tmp_path / "shared-lessons" / "real.unit"
    external.parent.mkdir()
    external.write_text('{"title":"Real Unit"}')
    unrelated = tmp_path / "other" / "loader.ts"
    unrelated.parent.mkdir()
    unrelated.write_text('fetch("unrelated.unit")')
    (unrelated.parent / "unrelated.unit").write_text('{"title":"Unrelated"}')

    analysis = analyze_canapp_source(
        tmp_path,
        canapp_root=Path("apps/candidate"),
    )

    paths = {
        item["path"]
        for item in analysis["content_candidates"]
    }
    assert analysis["canapp_root"] == "apps/candidate"
    assert "shared-lessons/real.unit" in paths
    assert "other/unrelated.unit" not in paths


def test_repair_adapter_rejects_modified_work_plan(tmp_path):
    plan = _work_plan()
    plan["tasks"][0]["row_id"] = "OPDS-004"

    try:
        build_repair_adapter(plan, tmp_path, testkit_commit="abc123")
    except ValueError as error:
        assert "semantic hash mismatch" in str(error)
    else:
        raise AssertionError("modified work plan was accepted")
