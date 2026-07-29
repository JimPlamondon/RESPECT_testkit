# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Tuple

from .matrix_runtime import load_matrix
from .models import SuiteRun


def canonical_hash(data: Any, excluded_keys: Tuple[str, ...] = ()) -> str:
    candidate = copy.deepcopy(data)
    if isinstance(candidate, dict):
        for key in excluded_keys:
            candidate.pop(key, None)
    encoded = json.dumps(
        candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _shared(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": report["run_id"],
        "suite_version": report["suite_version"],
        "matrix_id": report["matrix_id"],
        "matrix_version": report["matrix_version"],
        "matrix_semantic_hash": report["matrix_semantic_hash"],
        "profile_id": report["profile_id"],
        "target_id": report["target_id"],
        "target_digest": report["target_digest"],
        "challenge": report["challenge"],
        "evidence_environment": copy.deepcopy(report["evidence_environment"]),
    }


def _safe_locator(value: str) -> bool:
    path_text = value.split("#", 1)[0]
    path = PurePosixPath(path_text)
    return (
        bool(path_text)
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in path_text
        and "://" not in path_text
    )


def build_handoff(
    run: SuiteRun,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    from .report import suite_json_payload, verify_suite_payload

    report = suite_json_payload(run)
    verification_errors = verify_suite_payload(report)
    report["independent_verification"] = {
        "passed": not verification_errors,
        "errors": verification_errors,
    }
    shared = _shared(report)
    evidence_items = []
    for result in report["results"]:
        for item in result["evidence"]:
            evidence_items.append(
                {
                    **copy.deepcopy(item),
                    "row_id": result["row_id"],
                    "feature_id": result["feature_id"],
                }
            )
    evidence_items.sort(key=lambda item: (item["row_id"], item["evidence_id"]))
    evidence_manifest = {
        "artifact_type": "respect_evidence_manifest",
        "format_version": "2.0.0",
        **shared,
        "evidence": evidence_items,
    }
    matrix = load_matrix()
    tasks = []
    for result in report["results"]:
        if "kit_task" not in result.get("artifacts", []):
            continue
        task_id = f"repair:{result['row_id']}"
        tasks.append(
            {
                "task_id": task_id,
                "row_id": result["row_id"],
                "feature_id": result["feature_id"],
                "test_case_ids": copy.deepcopy(result["test_case_ids"]),
                "state": result["state"],
                "expected": copy.deepcopy(result["expected"]),
                "observed": copy.deepcopy(result["observed"]),
                "message": result["message"],
                "failure_domain": result["failure_domain"],
                "observed_result": result["observed_result"],
                "workflow_disposition": result["workflow_disposition"],
                "responsible_party": result["responsible_party"],
                "evidence_ids": [
                    item["evidence_id"] for item in result["evidence"]
                ],
                "evidence_locators": [
                    f"respect-evidence-manifest.json#evidence/{item['evidence_id']}"
                    for item in result["evidence"]
                ],
                "required_resources": copy.deepcopy(
                    matrix.rows[result["row_id"]].required_tooling
                ),
                "dependency_task_ids": [],
                "narrow_verifier_id": f"matrix-row:{result['row_id']}",
                "nonnormative_repair_guidance": result.get("repair_guidance")
                or "Inspect the Matrix expectation and target-attributed evidence.",
                "completion_oracle": (
                    f"The suite-owned narrow verifier for {result['row_id']} passes; "
                    "a full selected-profile Test Suite run remains required."
                ),
            }
        )
    tasks.sort(key=lambda item: item["task_id"])
    task_packet = {
        "artifact_type": "respect_ification_task_packet",
        "format_version": "2.0.0",
        **shared,
        "summary": {
            "actionable_task_count": len(tasks),
            "states": {
                state: sum(task["state"] == state for task in tasks)
                for state in sorted({task["state"] for task in tasks})
            },
        },
        "tasks": tasks,
    }
    task_packet["graph_hash"] = canonical_hash(tasks)
    report_core = canonical_hash(report, ("core_hash", "artifact_set"))
    evidence_core = canonical_hash(
        evidence_manifest, ("core_hash", "artifact_set")
    )
    task_core = canonical_hash(task_packet, ("core_hash", "artifact_set"))
    artifact_set = {
        "report_core_hash": report_core,
        "evidence_manifest_core_hash": evidence_core,
        "task_packet_core_hash": task_core,
    }
    artifact_set["handoff_id"] = canonical_hash(artifact_set)
    for artifact, core_hash in (
        (report, report_core),
        (evidence_manifest, evidence_core),
        (task_packet, task_core),
    ):
        artifact["core_hash"] = core_hash
        artifact["artifact_set"] = copy.deepcopy(artifact_set)
    return report, evidence_manifest, task_packet


def validate_handoff(
    report: Dict[str, Any],
    evidence_manifest: Dict[str, Any],
    task_packet: Dict[str, Any],
) -> List[str]:
    from .report import verify_suite_payload

    errors = list(verify_suite_payload(report))
    artifacts = [report, evidence_manifest, task_packet]
    for artifact in artifacts:
        if artifact.get("format_version") != "2.0.0":
            errors.append(
                f"{artifact.get('artifact_type', 'report')} is not v2"
            )
    try:
        shared = _shared(report)
    except KeyError as error:
        return sorted(set(errors + [f"report missing binding field {error}"]))
    for artifact in artifacts[1:]:
        for key, expected in shared.items():
            if artifact.get(key) != expected:
                errors.append(f"{artifact.get('artifact_type')} {key} binding mismatch")
    expected_cores = {
        "report_core_hash": canonical_hash(
            report, ("core_hash", "artifact_set")
        ),
        "evidence_manifest_core_hash": canonical_hash(
            evidence_manifest, ("core_hash", "artifact_set")
        ),
        "task_packet_core_hash": canonical_hash(
            task_packet, ("core_hash", "artifact_set")
        ),
    }
    expected_cores["handoff_id"] = canonical_hash(expected_cores)
    for artifact in artifacts:
        if artifact.get("artifact_set") != expected_cores:
            errors.append(f"{artifact.get('artifact_type', 'report')} artifact binding mismatch")
    if evidence_manifest.get("core_hash") != expected_cores[
        "evidence_manifest_core_hash"
    ]:
        errors.append("evidence manifest core hash mismatch")
    if task_packet.get("core_hash") != expected_cores["task_packet_core_hash"]:
        errors.append("task packet core hash mismatch")
    evidence_ids = {
        item.get("evidence_id") for item in evidence_manifest.get("evidence", [])
    }
    expected_evidence = []
    report_results = {
        item.get("row_id"): item for item in report.get("results", [])
    }
    for result in report_results.values():
        for item in result.get("evidence", []):
            expected_evidence.append(
                {
                    **copy.deepcopy(item),
                    "row_id": result.get("row_id"),
                    "feature_id": result.get("feature_id"),
                }
            )
    expected_evidence.sort(
        key=lambda item: (item.get("row_id"), item.get("evidence_id"))
    )
    if evidence_manifest.get("evidence") != expected_evidence:
        errors.append("evidence manifest is not an exact report projection")
    matrix = load_matrix()
    tasks = task_packet.get("tasks", [])
    task_ids = [item.get("task_id") for item in tasks]
    if len(task_ids) != len(set(task_ids)):
        errors.append("duplicate task identifier")
    task_id_set = set(task_ids)
    for task in tasks:
        result = report_results.get(task.get("row_id"), {})
        matrix_row = matrix.rows.get(task.get("row_id"))
        expected_fields = {
            "task_id": f"repair:{task.get('row_id')}",
            "feature_id": result.get("feature_id"),
            "test_case_ids": result.get("test_case_ids"),
            "state": result.get("state"),
            "expected": result.get("expected"),
            "observed": result.get("observed"),
            "message": result.get("message"),
            "failure_domain": result.get("failure_domain"),
            "observed_result": result.get("observed_result"),
            "workflow_disposition": result.get("workflow_disposition"),
            "responsible_party": result.get("responsible_party"),
            "evidence_ids": [
                item.get("evidence_id") for item in result.get("evidence", [])
            ],
            "required_resources": (
                matrix_row.required_tooling if matrix_row is not None else None
            ),
            "narrow_verifier_id": f"matrix-row:{task.get('row_id')}",
        }
        for field, expected in expected_fields.items():
            if task.get(field) != expected:
                errors.append(
                    f"task {task.get('task_id')} {field} is not an exact report/Matrix projection"
                )
        if not set(task.get("evidence_ids", [])).issubset(evidence_ids):
            errors.append(f"task {task.get('task_id')} has unknown evidence")
        if not set(task.get("dependency_task_ids", [])).issubset(task_id_set):
            errors.append(f"task {task.get('task_id')} has unknown dependency")
        if any(
            not _safe_locator(locator)
            for locator in task.get("evidence_locators", [])
        ):
            errors.append(f"task {task.get('task_id')} has unsafe evidence locator")
    dependencies = {
        item.get("task_id"): item.get("dependency_task_ids", []) for item in tasks
    }
    visiting = set()
    visited = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            errors.append("task graph contains a dependency cycle")
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies.get(task_id, []):
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id)
    if task_packet.get("graph_hash") != canonical_hash(tasks):
        errors.append("task graph hash mismatch")
    actionable = {
        item["row_id"]
        for item in report.get("results", [])
        if "kit_task" in item.get("artifacts", [])
    }
    if {item.get("row_id") for item in tasks} != actionable:
        errors.append("task packet does not exactly map actionable CanApp rows")
    if task_packet.get("summary", {}).get("actionable_task_count") != len(tasks):
        errors.append("task packet count mismatch")
    if shared["matrix_semantic_hash"] != matrix.semantic_hash:
        errors.append("handoff Matrix hash does not match canonical Matrix")
    return sorted(set(errors))


def write_handoff(
    report: Dict[str, Any],
    evidence_manifest: Dict[str, Any],
    task_packet: Dict[str, Any],
    output_dir: Path,
) -> None:
    errors = validate_handoff(report, evidence_manifest, task_packet)
    if errors:
        raise ValueError(f"invalid Test Suite handoff: {errors}")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "respect-report.json": report,
        "respect-evidence-manifest.json": evidence_manifest,
        "respect-ification-task-packet.json": task_packet,
    }
    for name, payload in artifacts.items():
        temporary = output_dir / f".{name}.tmp"
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output_dir / name)
