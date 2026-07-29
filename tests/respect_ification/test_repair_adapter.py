# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from respect_compat.handoff import canonical_hash
from respect_compat.matrix_runtime import load_matrix
from respect_ification.repair_adapter import (
    analyze_canapp_source,
    build_repair_adapter,
    render_repair_prompt,
)
from respect_ification.truth_audit import build_matrix_truth_audit


def _work_plan(profile_id="PROFILE-NATIVE_ANDROID"):
    matrix = load_matrix()
    core = {
        "artifact_type": "respect_ification_local_work_plan",
        "format_version": "2.0.0",
        "challenge": "synthetic-repair-challenge",
        "profile_id": profile_id,
        "matrix_semantic_hash": matrix.semantic_hash,
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


def test_truth_audit_covers_every_matrix_row_without_owner_substitution():
    matrix = load_matrix()

    audit = build_matrix_truth_audit(matrix)

    assert audit["summary"] == {
        "row_count": 87,
        "canapp_repair_row_count": 57,
        "protected_non_canapp_row_count": 30,
        "uncovered_row_count": 0,
    }
    assert {item["row_id"] for item in audit["rows"]} == set(matrix.rows)
    canapp = [item for item in audit["rows"] if item["owner"] == "canapp"]
    protected = [item for item in audit["rows"] if item["owner"] != "canapp"]
    assert all(
        item["kit_disposition"] == "durable_canapp_repair_required"
        and item["durable_product_change_required"] is True
        and item["implementation_targets"]
        and item["required_evidence_class"]
        and item["forbidden_substitutes"]
        for item in canapp
    )
    assert all(
        item["kit_disposition"] == "protected_non_canapp_requirement"
        and item["durable_product_change_required"] is False
        for item in protected
    )


def test_each_adapter_task_contains_its_complete_row_truth_contract(tmp_path):
    (tmp_path / "lesson.unit").write_text('{"title":"Real lesson"}')

    adapter = build_repair_adapter(
        _work_plan(),
        tmp_path,
        testkit_commit="abc123",
    )

    task = adapter["tasks"][0]
    contract = task["truth_contract"]
    assert contract["row_id"] == "OPDS-003"
    assert contract["durable_product_change_required"] is True
    assert "source-derived OPDS" in contract["implementation_targets"][0]
    assert "owner-authored pass flag" in contract["forbidden_substitutes"][0]
    assert adapter["matrix_truth_audit"]["summary"]["row_count"] == 87


def test_repair_adapter_rejects_non_canapp_repair_task(tmp_path):
    matrix = load_matrix()
    plan = _work_plan()
    plan["tasks"][0]["task_id"] = "repair:AUTH-002"
    plan["tasks"][0]["row_id"] = "AUTH-002"
    plan["tasks"][0]["normative_task"]["task_id"] = "repair:AUTH-002"
    plan["tasks"][0]["normative_task"]["row_id"] = "AUTH-002"
    plan["tasks"][0]["normative_task"]["narrow_verifier_id"] = (
        "matrix-row:AUTH-002"
    )
    plan["semantic_hash"] = canonical_hash(plan, ("semantic_hash",))
    assert "AUTH-002" in {
        row.row_id for row in matrix.selected_rows(plan["profile_id"])
    }

    try:
        build_repair_adapter(plan, tmp_path, testkit_commit="abc123")
    except ValueError as error:
        assert "owned by respect_service" in str(error)
    else:
        raise AssertionError("non-CanApp Matrix row became a CanApp repair")


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


def test_source_analysis_distinguishes_packaged_content_from_on_demand_acquisition(
    tmp_path,
):
    app = tmp_path / "app"
    app.mkdir()
    (app / "build.gradle.kts").write_text(
        'sourceSets["main"].assets.srcDir("../lesson-library")'
    )
    (app / "LessonLoader.kt").write_text(
        'fun load(name: String) = context.assets.open(name)'
    )
    lessons = tmp_path / "lesson-library"
    lessons.mkdir()
    (lessons / "one.proprietary").write_text('{"title":"One"}')

    analysis = analyze_canapp_source(tmp_path, canapp_root=Path("app"))

    candidate = next(
        item
        for item in analysis["content_candidates"]
        if item["path"] == "lesson-library/one.proprietary"
    )
    assert candidate["delivery_evidence"] == ["embedded_by_build"]
    assert analysis["content_delivery"]["embedded_content"] is True
    assert analysis["content_delivery"]["on_demand_acquisition"] is False
    assert analysis["content_delivery"]["bounded_cache"] is False


def test_source_analysis_does_not_mistake_publication_generation_for_packaging(
    tmp_path,
):
    app = tmp_path / "app"
    app.mkdir()
    (app / "build.gradle.kts").write_text(
        'tasks.register("catalog") { commandLine("python", "generate.py") }'
    )
    (app / "generate.py").write_text(
        'MODEL = "publication.json"\n'
        'def generate(): return MODEL\n'
    )
    (app / "publication.json").write_text(
        '{"lesson_source_root":"../lesson-library"}'
    )
    lessons = tmp_path / "lesson-library"
    lessons.mkdir()
    (lessons / "one.proprietary").write_text('{"title":"One"}')
    (app / "Acquisition.kt").write_text(
        'HttpURLConnection(URL("https://example.test/catalog.json"))\n'
        'val index = root.resolve("index.json")\n'
        'fun evict() = Unit\n'
        'const val catalog = "application/opds+json"\n'
    )
    unrelated = tmp_path / "unrelated-library"
    unrelated.mkdir()
    (unrelated / "index.json").write_text('{"not":"a lesson"}')

    analysis = analyze_canapp_source(tmp_path, canapp_root=Path("app"))

    candidate_paths = {
        item["path"] for item in analysis["content_candidates"]
    }
    assert "lesson-library/one.proprietary" in candidate_paths
    assert "unrelated-library/index.json" not in candidate_paths
    candidate = next(
        item
        for item in analysis["content_candidates"]
        if item["path"] == "lesson-library/one.proprietary"
    )
    assert candidate["delivery_evidence"] == ["referenced_by_product_source"]
    assert analysis["content_delivery"] == {
        "embedded_content": False,
        "on_demand_acquisition": True,
        "bounded_cache": True,
        "catalog_discovery": True,
    }
    adapter = build_repair_adapter(
        _work_plan(),
        tmp_path,
        testkit_commit="abc123",
        canapp_root=Path("app"),
    )
    assert adapter["content_acquisition_contract"]["required"] is False
    assert (
        adapter["content_acquisition_contract"]["source_delivery_state"]
        == "external_on_demand"
    )


def test_repair_prompt_requires_generic_external_on_demand_lesson_delivery(
    tmp_path,
):
    app = tmp_path / "native"
    app.mkdir()
    (app / "build.gradle.kts").write_text(
        'sourceSets["main"].assets.srcDir("../course-library")'
    )
    (app / "Loader.kt").write_text(
        'fun open(name: String) = assets.open(name)'
    )
    courses = tmp_path / "course-library"
    courses.mkdir()
    (courses / "unit.blob").write_bytes(b"real lesson bytes")

    adapter = build_repair_adapter(
        _work_plan(),
        tmp_path,
        testkit_commit="abc123",
        canapp_root=Path("native"),
    )
    prompt = render_repair_prompt(adapter)

    contract = adapter["content_acquisition_contract"]
    assert contract["required"] is True
    assert contract["source_delivery_state"] == "embedded"
    assert "Remove ordinary lesson payloads from the installable application package" in prompt
    assert "download only the selected lesson" in prompt
    assert "bounded local cache" in prompt
    assert "offline reuse" in prompt
    assert "media type, publication identity, and declared integrity" in prompt
    assert "proprietary lesson parser remains CanApp-owned" in prompt
    assert "RESPECT Publication Pack" in prompt
    assert "publication-manifest" in prompt
    assert "publication-pack" in prompt
    assert "publication-verify" in prompt


def test_repair_adapter_requires_catalog_discovery_for_external_content(
    tmp_path,
):
    app = tmp_path / "web"
    app.mkdir()
    (app / "loader.ts").write_text(
        'fetch("remote.lesson"); function evict() {}'
    )
    (app / "remote.lesson").write_bytes(b"real lesson bytes")

    adapter = build_repair_adapter(
        _work_plan("PROFILE-WEB"),
        tmp_path,
        testkit_commit="abc123",
    )

    assert adapter["source_analysis"]["content_delivery"] == {
        "embedded_content": False,
        "on_demand_acquisition": True,
        "bounded_cache": True,
        "catalog_discovery": False,
    }
    assert adapter["content_acquisition_contract"]["required"] is True


def test_repair_adapter_rejects_modified_work_plan(tmp_path):
    plan = _work_plan()
    plan["tasks"][0]["row_id"] = "OPDS-004"

    try:
        build_repair_adapter(plan, tmp_path, testkit_commit="abc123")
    except ValueError as error:
        assert "semantic hash mismatch" in str(error)
    else:
        raise AssertionError("modified work plan was accepted")
