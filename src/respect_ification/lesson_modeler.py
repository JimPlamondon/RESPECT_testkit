# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Owner-local lesson-system modeling and deterministic scenario compilation."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set

import jsonschema

from respect_compat.android_runtime_runner import (
    SCENARIO_ACTION_TYPES,
    validate_runtime_scenario,
)
from respect_compat.handoff import canonical_hash

from .resources import resource


FORMAT_VERSION = "1.0.0"
_HEX64 = set("0123456789abcdef")
_SCHEMAS = {
    "inventory": "data/schemas/canapp_lesson_inventory.schema.json",
    "model": "data/schemas/canapp_lesson_model.schema.json",
    "selection": "data/schemas/canapp_lesson_selection.schema.json",
    "run_plan": "data/schemas/canapp_lesson_run_plan.schema.json",
    "coverage": "data/schemas/canapp_lesson_coverage.schema.json",
    "capability_gaps": (
        "data/schemas/canapp_lesson_capability_gaps.schema.json"
    ),
    "modeling_packet": (
        "data/schemas/canapp_lesson_modeling_packet.schema.json"
    ),
}
_ARTIFACT_KINDS = {
    "respect_canapp_lesson_inventory": "inventory",
    "respect_canapp_lesson_model": "model",
    "respect_canapp_lesson_selection": "selection",
    "respect_canapp_lesson_run_plan": "run_plan",
    "respect_canapp_lesson_coverage": "coverage",
    "respect_canapp_lesson_capability_gaps": "capability_gaps",
    "respect_canapp_lesson_modeling_packet": "modeling_packet",
}
_TYPE_CHECKS = {
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: type(value) is int,
    "boolean": lambda value: type(value) is bool,
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "number": lambda value: type(value) in {int, float},
}
_IGNORED_SOURCE_PARTS = {
    ".git",
    ".gradle",
    ".idea",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
_MAX_SOURCE_FILE = 2_000_000


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and not (set(value) - _HEX64)
    )


def _duplicate_rejector(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_artifact(
    path: Path, expected_kind: Optional[str] = None
) -> Dict[str, Any]:
    if path.is_symlink():
        raise ValueError("artifact path must not be a symlink")
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("artifact exceeds the 64 MiB safety limit")
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_duplicate_rejector,
    )
    if not isinstance(value, dict):
        raise ValueError("lesson-model artifact must be a JSON object")
    validate_artifact(value, expected_kind)
    return value


def write_artifact(path: Path, value: Dict[str, Any]) -> None:
    validate_artifact(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def finalize_artifact(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop("semantic_hash", None)
    result["semantic_hash"] = canonical_hash(result)
    return result


def validate_artifact(
    value: Mapping[str, Any], expected_kind: Optional[str] = None
) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("lesson-model artifact must be an object")
    artifact_type = value.get("artifact_type")
    kind = _ARTIFACT_KINDS.get(str(artifact_type))
    if kind is None:
        raise ValueError(f"unknown lesson-model artifact type: {artifact_type}")
    if expected_kind is not None and kind != expected_kind:
        raise ValueError(
            f"expected {expected_kind} artifact, received {kind}"
        )
    schema = json.loads(resource(_SCHEMAS[kind]).read_text(encoding="utf-8"))
    try:
        jsonschema.Draft202012Validator(schema).validate(value)
    except jsonschema.ValidationError as error:
        raise ValueError(
            f"invalid {kind} artifact: {error.message}"
        ) from error
    if value.get("semantic_hash") != canonical_hash(
        value, ("semantic_hash",)
    ):
        raise ValueError(f"{kind} semantic hash mismatch")
    if kind == "inventory":
        _validate_inventory_semantics(value)
    elif kind == "model":
        _validate_model_semantics(value)
    elif kind == "selection":
        _validate_selection_semantics(value)


def _validate_inventory_semantics(value: Mapping[str, Any]) -> None:
    lesson_ids = set()
    for lesson in value["lessons"]:
        lesson_id = lesson["lesson_id"]
        if lesson_id in lesson_ids:
            raise ValueError("duplicate lesson identifier")
        lesson_ids.add(lesson_id)
        source = lesson.get("source")
        if source:
            path = Path(source["path"])
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("lesson source path is unsafe")
            if not _is_sha256(source["sha256"]):
                raise ValueError("lesson source SHA-256 is invalid")


def _validate_model_semantics(value: Mapping[str, Any]) -> None:
    families = {}
    for family in value["families"]:
        family_id = family["family_id"]
        if family_id in families:
            raise ValueError("duplicate interaction family")
        families[family_id] = family
        for name, declaration in family["parameters"].items():
            if declaration["type"] not in _TYPE_CHECKS:
                raise ValueError("unsupported lesson binding type")
    classified = set()
    for item in value["classifications"]:
        lesson_id = item["lesson_id"]
        if lesson_id in classified:
            raise ValueError("duplicate lesson classification")
        classified.add(lesson_id)
        if item["status"] == "classified":
            if item.get("family_id") not in families:
                raise ValueError("classification references unknown family")
        elif "family_id" in item:
            raise ValueError(
                "non-classified lesson must not name a family"
            )
        if not item.get("evidence") and item["status"] != "excluded":
            raise ValueError("lesson classification lacks evidence")
    bound = set()
    for binding in value["lesson_bindings"]:
        lesson_id = binding["lesson_id"]
        if lesson_id in bound:
            raise ValueError("duplicate lesson binding")
        bound.add(lesson_id)


def _validate_selection_semantics(value: Mapping[str, Any]) -> None:
    selectors = value["selectors"]
    for name in ("lesson_ids", "course_ids", "family_ids"):
        items = selectors[name]
        if len(items) != len(set(items)):
            raise ValueError(f"duplicate {name} selection")
    exclusions = value["exclude_lesson_ids"]
    if len(exclusions) != len(set(exclusions)):
        raise ValueError("duplicate lesson exclusion")


def _check_bound_artifacts(
    inventory: Mapping[str, Any],
    model: Mapping[str, Any],
    selection: Optional[Mapping[str, Any]] = None,
) -> None:
    validate_artifact(inventory, "inventory")
    validate_artifact(model, "model")
    if model["inventory_semantic_hash"] != inventory["semantic_hash"]:
        raise ValueError("lesson model is bound to another inventory")
    inventory_ids = {item["lesson_id"] for item in inventory["lessons"]}
    classification_ids = {
        item["lesson_id"] for item in model["classifications"]
    }
    unknown = classification_ids - inventory_ids
    if unknown:
        raise ValueError("model classifies unknown lessons")
    if selection is not None:
        validate_artifact(selection, "selection")
        if (
            selection["inventory_semantic_hash"]
            != inventory["semantic_hash"]
            or selection["model_semantic_hash"] != model["semantic_hash"]
        ):
            raise ValueError("lesson selection artifact binding mismatch")


def resolve_selection(
    inventory: Mapping[str, Any],
    model: Mapping[str, Any],
    selection: Mapping[str, Any],
) -> List[str]:
    _check_bound_artifacts(inventory, model, selection)
    lessons = inventory["lessons"]
    inventory_ids = {item["lesson_id"] for item in lessons}
    classifications = {
        item["lesson_id"]: item for item in model["classifications"]
    }
    selectors = selection["selectors"]
    requested_ids = set(selectors["lesson_ids"])
    unknown = requested_ids - inventory_ids
    if unknown:
        raise ValueError("unknown lesson identifiers")
    known_courses = {
        item.get("course_id")
        for item in lessons
        if item.get("course_id") is not None
    }
    unknown_courses = set(selectors["course_ids"]) - known_courses
    if unknown_courses:
        raise ValueError("unknown course identifiers")
    known_families = {item["family_id"] for item in model["families"]}
    unknown_families = set(selectors["family_ids"]) - known_families
    if unknown_families:
        raise ValueError("unknown interaction families")
    exclusions = set(selection["exclude_lesson_ids"])
    unknown_exclusions = exclusions - inventory_ids
    if unknown_exclusions:
        raise ValueError("unknown excluded lessons")
    selected = []
    for lesson in lessons:
        lesson_id = lesson["lesson_id"]
        classification = classifications.get(lesson_id, {})
        matches = (
            selectors["all"]
            or lesson_id in requested_ids
            or lesson.get("course_id") in selectors["course_ids"]
            or classification.get("family_id") in selectors["family_ids"]
        )
        if matches and lesson_id not in exclusions:
            selected.append(lesson_id)
    if not selected:
        raise ValueError("lesson selection resolved to an empty set")
    return selected


def _binding_value_valid(value: Any, declaration: Mapping[str, Any]) -> bool:
    checker = _TYPE_CHECKS[declaration["type"]]
    return checker(value)


def _substitute(
    value: Any,
    declarations: Mapping[str, Any],
    bindings: Mapping[str, Any],
) -> Any:
    if isinstance(value, dict):
        if "$binding" in value:
            if set(value) != {"$binding"}:
                raise ValueError(
                    "binding reference must be the only object member"
                )
            name = value["$binding"]
            if name not in declarations:
                raise ValueError("undeclared binding reference")
            if name not in bindings:
                raise ValueError("missing lesson binding")
            if not _binding_value_valid(bindings[name], declarations[name]):
                raise ValueError("lesson binding has wrong type")
            return copy.deepcopy(bindings[name])
        return {
            key: _substitute(item, declarations, bindings)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_substitute(item, declarations, bindings) for item in value]
    return copy.deepcopy(value)


def compile_run_plan(
    inventory: Mapping[str, Any],
    model: Mapping[str, Any],
    selection: Mapping[str, Any],
    *,
    testkit_commit: str,
    target_id: str,
    target_digest: str,
    profile_id: str,
    available_capabilities: Iterable[str],
    event: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    selected = resolve_selection(inventory, model, selection)
    if event:
        event(
            "lesson_selection",
            "completed",
            {
                "selected_count": len(selected),
                "selection_hash": selection["semantic_hash"],
            },
        )
    families = {item["family_id"]: item for item in model["families"]}
    classifications = {
        item["lesson_id"]: item for item in model["classifications"]
    }
    bindings = {
        item["lesson_id"]: item["values"]
        for item in model["lesson_bindings"]
    }
    capabilities = set(available_capabilities)
    unsupported_claims = capabilities - SCENARIO_ACTION_TYPES
    if unsupported_claims:
        raise ValueError(
            "available capabilities contain an unsupported TestKit action"
        )
    gaps = {}
    entries = []
    for lesson_id in selected:
        classification = classifications.get(lesson_id)
        if not classification or classification["status"] != "classified":
            entries.append(
                {
                    "lesson_id": lesson_id,
                    "status": "blocked",
                    "reason": (
                        classification["status"]
                        if classification
                        else "unclassified"
                    ),
                }
            )
            continue
        family = families[classification["family_id"]]
        missing = sorted(
            set(family["required_capabilities"]) - capabilities
        )
        if missing:
            for capability in missing:
                gaps.setdefault(
                    capability,
                    {
                        "capability": capability,
                        "mechanism_hash": canonical_hash(
                            {
                                "capability": capability,
                                "template": family["scenario_template"],
                            }
                        ),
                    },
                )
            entries.append(
                {
                    "lesson_id": lesson_id,
                    "status": "blocked",
                    "reason": "missing_testkit_capability",
                    "missing_capabilities": missing,
                }
            )
            continue
        lesson_bindings = bindings.get(lesson_id)
        if lesson_bindings is None:
            entries.append(
                {
                    "lesson_id": lesson_id,
                    "status": "blocked",
                    "reason": "missing_bindings",
                }
            )
            continue
        surplus = set(lesson_bindings) - set(family["parameters"])
        if surplus:
            raise ValueError("lesson bindings contain surplus values")
        scenario = _substitute(
            family["scenario_template"],
            family["parameters"],
            lesson_bindings,
        )
        scenario = validate_runtime_scenario(scenario)
        entries.append(
            {
                "lesson_id": lesson_id,
                "status": "compiled",
                "scenario": scenario,
                "scenario_sha256": canonical_hash(scenario),
            }
        )
    result = finalize_artifact(
        {
            "artifact_type": "respect_canapp_lesson_run_plan",
            "format_version": FORMAT_VERSION,
            "testkit_commit": testkit_commit,
            "target_id": target_id,
            "target_digest": target_digest,
            "profile_id": profile_id,
            "inventory_semantic_hash": inventory["semantic_hash"],
            "model_semantic_hash": model["semantic_hash"],
            "selection_semantic_hash": selection["semantic_hash"],
            "selected_lesson_ids": selected,
            "entries": entries,
            "capability_gaps": sorted(
                gaps.values(), key=lambda item: item["capability"]
            ),
        }
    )
    validate_artifact(result, "run_plan")
    if event:
        event(
            "scenario_compilation",
            "completed",
            {
                "compiled_count": sum(
                    item["status"] == "compiled" for item in entries
                ),
                "blocked_count": sum(
                    item["status"] == "blocked" for item in entries
                ),
                "run_plan_hash": result["semantic_hash"],
            },
        )
    return result


def build_coverage(
    inventory: Mapping[str, Any],
    model: Mapping[str, Any],
    selection: Mapping[str, Any],
    run_plan: Mapping[str, Any],
    outcomes: Mapping[str, str],
) -> Dict[str, Any]:
    _check_bound_artifacts(inventory, model, selection)
    validate_artifact(run_plan, "run_plan")
    classifications = model["classifications"]
    counts = {
        "inventoried": len(inventory["lessons"]),
        "classified": sum(
            item["status"] == "classified" for item in classifications
        ),
        "unclassified": sum(
            item["status"] == "unclassified" for item in classifications
        ),
        "excluded": sum(
            item["status"] == "excluded" for item in classifications
        ),
        "selected": len(run_plan["selected_lesson_ids"]),
        "compiled": sum(
            item["status"] == "compiled" for item in run_plan["entries"]
        ),
        "executed": len(outcomes),
        "passed": sum(value == "passed" for value in outcomes.values()),
        "failed": sum(value == "failed" for value in outcomes.values()),
        "blocked": sum(value == "blocked" for value in outcomes.values()),
        "incomplete": sum(
            value == "incomplete" for value in outcomes.values()
        ),
    }
    return finalize_artifact(
        {
            "artifact_type": "respect_canapp_lesson_coverage",
            "format_version": FORMAT_VERSION,
            "inventory_semantic_hash": inventory["semantic_hash"],
            "model_semantic_hash": model["semantic_hash"],
            "selection_semantic_hash": selection["semantic_hash"],
            "run_plan_semantic_hash": run_plan["semantic_hash"],
            "counts": counts,
            "full_inventory_selected": counts["selected"]
            == counts["inventoried"],
            "full_inventory_executed": (
                counts["executed"] == counts["inventoried"]
                and counts["selected"] == counts["inventoried"]
            ),
            "lesson_outcomes": [
                {"lesson_id": lesson_id, "outcome": outcome}
                for lesson_id, outcome in outcomes.items()
            ],
        }
    )


def _source_files(root: Path) -> List[Dict[str, Any]]:
    result = []
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories if name not in _IGNORED_SOURCE_PARTS
        )
        for name in sorted(names):
            path = current_path / name
            if path.is_symlink():
                raise ValueError("source analysis rejects symlinks")
            relative = path.relative_to(root)
            if any(part in _IGNORED_SOURCE_PARTS for part in relative.parts):
                continue
            size = path.stat().st_size
            if size > _MAX_SOURCE_FILE:
                continue
            body = path.read_bytes()
            result.append(
                {
                    "path": relative.as_posix(),
                    "size": size,
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
    return result


def build_modeling_packet(
    source_root: Path, inventory: Mapping[str, Any]
) -> Dict[str, Any]:
    validate_artifact(inventory, "inventory")
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("modeling source root must be a directory")
    files = _source_files(root)
    source_tree_digest = canonical_hash(files)
    return finalize_artifact(
        {
            "artifact_type": "respect_canapp_lesson_modeling_packet",
            "format_version": FORMAT_VERSION,
            "inventory_semantic_hash": inventory["semantic_hash"],
            "source_tree_digest": source_tree_digest,
            "source_files": files,
            "questions": [
                "Identify distinct technical lesson interaction families.",
                "Bind every classification to source or runtime evidence.",
                "Declare only existing TestKit scenario capabilities.",
                "Leave ambiguous lessons unclassified.",
            ],
            "authority_notice": (
                "This private packet supports owner-local modeling and cannot "
                "establish Test Suite evidence or a certification verdict."
            ),
        }
    )


def write_modeling_handback(
    packet: Mapping[str, Any], prompt_path: Path, human_todo_path: Path
) -> None:
    validate_artifact(packet, "modeling_packet")
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = (
        "# Model the CanApp lesson system\n\n"
        f"Modeling-packet semantic hash: `{packet['semantic_hash']}`\n\n"
        "Read the private packet and the owner source it binds. Identify "
        "technical interaction families, classify lessons only with evidence, "
        "declare typed owner-local bindings, and use only existing TestKit "
        "scenario actions. Leave uncertainty unclassified. Do not invent "
        "lesson meaning, learner data, answers, or certification evidence.\n"
    )
    temporary_prompt = prompt_path.with_name(f".{prompt_path.name}.tmp")
    temporary_prompt.write_text(prompt, encoding="utf-8")
    os.replace(temporary_prompt, prompt_path)
    todo = (
        "# Human ToDo — CanApp Lesson Modeler\n\n"
        f"- [ ] Execute the modeling prompt at `{prompt_path}`.\n"
        f"- [ ] Preserve packet binding `{packet['semantic_hash']}`.\n"
        "- [ ] Confirm every classification and owner-local binding.\n"
        "- [ ] Leave unknown or ambiguous lessons unclassified.\n"
        "- [ ] Rerun Modeler validation and selected TestKit execution.\n"
    )
    temporary_todo = human_todo_path.with_name(
        f".{human_todo_path.name}.tmp"
    )
    temporary_todo.write_text(todo, encoding="utf-8")
    os.replace(temporary_todo, human_todo_path)


def _child_directory(root: Path, index: int, lesson_id: str) -> Path:
    digest = hashlib.sha256(lesson_id.encode("utf-8")).hexdigest()[:16]
    return root / "children" / f"{index:06d}-{digest}"


def run_lesson_batch(
    run_plan: Mapping[str, Any],
    output_dir: Path,
    runner: Callable[
        [Mapping[str, Any], Path, Callable[[str, str, Dict[str, Any]], Any]],
        Mapping[str, Any],
    ],
    *,
    resume: bool = False,
    event: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    validate_artifact(run_plan, "run_plan")
    emit = event or (lambda *_args, **_kwargs: None)
    index_path = output_dir / "canapp-lesson-batch-index.json"
    plan_path = output_dir / "canapp-lesson-run-plan.json"
    if resume:
        if not index_path.is_file() or not plan_path.is_file():
            raise ValueError("resume requires an existing bound lesson batch")
        prior_plan = read_artifact(plan_path, "run_plan")
        if prior_plan["semantic_hash"] != run_plan["semantic_hash"]:
            raise ValueError("run plan does not match resumable batch")
        prior = json.loads(index_path.read_text(encoding="utf-8"))
        if prior.get("semantic_hash") != canonical_hash(
            prior, ("semantic_hash",)
        ):
            raise ValueError("lesson batch index semantic hash mismatch")
        children = prior.get("children", [])
        if len(children) != len(run_plan["entries"]):
            raise ValueError("resumable batch child count mismatch")
        for child, entry in zip(children, run_plan["entries"]):
            if (
                child.get("lesson_id") != entry["lesson_id"]
                or child.get("scenario_sha256")
                != entry.get("scenario_sha256")
            ):
                raise ValueError("resumable child binding mismatch")
            report_reference = child.get("report")
            report_hash = child.get("report_sha256")
            if not isinstance(report_reference, str) or not _is_sha256(
                report_hash
            ):
                raise ValueError("resumable child report binding is missing")
            report_path = output_dir / report_reference
            if (
                not report_path.is_file()
                or hashlib.sha256(report_path.read_bytes()).hexdigest()
                != report_hash
            ):
                raise ValueError("resumable child report binding mismatch")
            child["resumed"] = True
        result = finalize_artifact(
            {
            "artifact_type": "respect_canapp_lesson_batch_index",
            "format_version": FORMAT_VERSION,
            "authority_notice": (
                "Non-authoritative index; child TestKit reports retain "
                "their individual authority."
            ),
            "run_plan_semantic_hash": run_plan["semantic_hash"],
            "children": children,
            "exit_code": prior["exit_code"],
            }
        )
        emit(
            "lesson_batch_resume",
            "completed",
            {"child_count": len(children), "run_plan_hash": run_plan["semantic_hash"]},
        )
        return result
    if output_dir.exists():
        existing = [
            item
            for item in output_dir.iterdir()
            if item.name != "respect-execution-log.jsonl"
        ]
        if existing:
            raise ValueError("lesson batch output directory is not empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_artifact(plan_path, dict(run_plan))
    children = []
    for index, entry in enumerate(run_plan["entries"]):
        child_dir = _child_directory(
            output_dir, index, entry["lesson_id"]
        )
        child_dir.mkdir(parents=True, exist_ok=False)
        emit(
            "child_test",
            "started",
            {
                "lesson_id_hash": hashlib.sha256(
                    entry["lesson_id"].encode("utf-8")
                ).hexdigest(),
                "scenario_hash": entry.get("scenario_sha256"),
            },
        )
        if entry["status"] != "compiled":
            report = {
                "lesson_id": entry["lesson_id"],
                "scenario_sha256": None,
                "exit_code": 2,
                "outcome": "blocked",
                "reason": entry["reason"],
            }
            report_path = child_dir / "modeler-blocked.json"
            report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        else:
            try:
                report = dict(runner(entry, child_dir, emit))
            except Exception as error:
                report = {
                    "lesson_id": entry["lesson_id"],
                    "scenario_sha256": entry["scenario_sha256"],
                    "exit_code": 64,
                    "outcome": "failed",
                    "error_type": type(error).__name__,
                }
                report_path = child_dir / "modeler-error.json"
                report_path.write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                emit(
                    "child_test",
                    "failed",
                    {
                        "scenario_hash": entry.get("scenario_sha256"),
                        "error_type": type(error).__name__,
                    },
                )
            if (
                report.get("lesson_id") != entry["lesson_id"]
                or report.get("scenario_sha256")
                != entry["scenario_sha256"]
            ):
                raise ValueError("child TestKit report binding mismatch")
            if "report_path" not in locals():
                report_path = child_dir / "respect-report.json"
        report_reference = str(report_path.relative_to(output_dir))
        report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
        child = {
            "lesson_id": entry["lesson_id"],
            "scenario_sha256": entry.get("scenario_sha256"),
            "report": report_reference,
            "report_sha256": report_sha256,
            "exit_code": int(report["exit_code"]),
            "outcome": report["outcome"],
            "resumed": False,
        }
        children.append(child)
        if "report_path" in locals():
            del report_path
        emit(
            "child_test",
            "completed",
            {
                "scenario_hash": entry.get("scenario_sha256"),
                "exit_code": child["exit_code"],
                "outcome": child["outcome"],
            },
        )
    exit_code = 0 if all(
        child["exit_code"] == 0 and child["outcome"] == "passed"
        for child in children
    ) else 2
    result = finalize_artifact(
        {
        "artifact_type": "respect_canapp_lesson_batch_index",
        "format_version": FORMAT_VERSION,
        "authority_notice": (
            "Non-authoritative index; child TestKit reports retain their "
            "individual authority."
        ),
        "run_plan_semantic_hash": run_plan["semantic_hash"],
        "children": children,
        "exit_code": exit_code,
        }
    )
    temporary = index_path.with_name(f".{index_path.name}.tmp")
    temporary.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, index_path)
    return result
