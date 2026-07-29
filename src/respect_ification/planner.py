# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

from respect_compat.handoff import canonical_hash, validate_handoff
from respect_compat.routing import ensure_work_generation_allowed


def build_work_plan(
    report: Dict[str, Any],
    evidence_manifest: Dict[str, Any],
    task_packet: Dict[str, Any],
    private_prep: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_work_generation_allowed([report, evidence_manifest, task_packet])
    errors = validate_handoff(report, evidence_manifest, task_packet)
    if errors:
        raise ValueError(f"invalid Test Suite handoff: {errors}")
    if private_prep is not None:
        if private_prep.get("semantic_hash") != canonical_hash(
            private_prep, ("semantic_hash",)
        ):
            raise ValueError("private Prep semantic hash mismatch")
        if private_prep.get("target_digest") != report["target_digest"]:
            raise ValueError("private Prep target does not match Test Suite target")
        if private_prep.get("profile_id") != report["profile_id"]:
            raise ValueError("private Prep profile does not match Test Suite profile")
    planned = []
    mappings = private_prep.get("row_mappings", {}) if private_prep else {}
    inventory = {
        item["path"] for item in private_prep.get("source_inventory", [])
    } if private_prep else set()
    for task in task_packet["tasks"]:
        hints = []
        for path_text in mappings.get(task["row_id"], []):
            path = Path(path_text)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe private source path: {path_text}")
            if path_text not in inventory:
                raise ValueError(f"private source path is not inventoried: {path_text}")
            hints.append(
                {
                    "path": path_text,
                    "authority": "nonnormative_private_prep",
                    "confidence": "owner_supplied_mapping",
                }
            )
        planned.append(
            {
                "task_id": task["task_id"],
                "row_id": task["row_id"],
                "normative_task": copy.deepcopy(task),
                "source_hints": hints,
                "initial_state": "pending",
            }
        )
    plan = {
        "artifact_type": "respect_ification_local_work_plan",
        "format_version": "2.0.0",
        "matrix_id": report["matrix_id"],
        "matrix_version": report["matrix_version"],
        "matrix_semantic_hash": report["matrix_semantic_hash"],
        "profile_id": report["profile_id"],
        "target_id": report["target_id"],
        "target_digest": report["target_digest"],
        "run_id": report["run_id"],
        "challenge": report["challenge"],
        "handoff_id": task_packet["artifact_set"]["handoff_id"],
        "task_packet_core_hash": task_packet["core_hash"],
        "private_prep_semantic_hash": (
            private_prep.get("semantic_hash") if private_prep else None
        ),
        "authority_notice": (
            "This work plan is nonnormative. Only a full RESPECT Compatible "
            "Test Suite run can establish compatibility."
        ),
        "tasks": planned,
    }
    plan["semantic_hash"] = canonical_hash(plan, ("semantic_hash",))
    return plan


def validate_work_plan(
    plan: Dict[str, Any], task_packet: Dict[str, Any]
) -> List[str]:
    errors = []
    if plan.get("semantic_hash") != canonical_hash(plan, ("semantic_hash",)):
        errors.append("work plan semantic hash mismatch")
    if plan.get("task_packet_core_hash") != task_packet.get("core_hash"):
        errors.append("work plan task-packet binding mismatch")
    source_tasks = {
        item["task_id"]: item for item in task_packet.get("tasks", [])
    }
    planned = plan.get("tasks", [])
    if {item.get("task_id") for item in planned} != set(source_tasks):
        errors.append("work plan task set mismatch")
    for item in planned:
        if item.get("normative_task") != source_tasks.get(item.get("task_id")):
            errors.append(
                f"work plan changed normative task {item.get('task_id')}"
            )
    return sorted(set(errors))
