# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import mimetypes
import os
import posixpath
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from respect_compat.handoff import canonical_hash
from respect_compat.matrix_runtime import load_matrix

from .truth_audit import build_matrix_truth_audit, select_truth_contracts


_IGNORED_PARTS = {
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
_SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".dart",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
_BUILD_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "Package.swift",
    "package.json",
    "pom.xml",
    "pubspec.yaml",
    "pyproject.toml",
    "settings.gradle",
    "settings.gradle.kts",
}
_MANIFEST_NAMES = {
    "AndroidManifest.xml",
    "Info.plist",
    "app.json",
    "manifest.json",
    "webmanifest",
}
_STRING_LITERAL = re.compile(r"""["']([^"'\r\n]{1,240})["']""")
_GENERIC_REFERENCE_NAMES = {
    "cache.json",
    "config.json",
    "index.json",
    "metadata.json",
    "settings.json",
}
_CONTENT_WORDS = {
    "activity",
    "activities",
    "chapter",
    "chapters",
    "content",
    "course",
    "courses",
    "exercise",
    "exercises",
    "lesson",
    "lessons",
    "module",
    "modules",
    "song",
    "songs",
    "unit",
    "units",
}
_SIGNALS = {
    "launch": (
        "onNewIntent",
        "intent.data",
        "deepLink",
        "app link",
        "universal link",
        "activity_id",
    ),
    "lifecycle": (
        "onDestroy",
        "onStop",
        "onPause",
        "dispose",
        "unbindService",
        "background",
    ),
    "selection": (
        "openLesson",
        "selectLesson",
        "lessonId",
        "courseId",
        "moduleId",
        "navigate",
    ),
    "completion": (
        "complete",
        "completed",
        "completion",
        "result",
        "score",
        "progress",
    ),
    "xapi": (
        "xapi",
        "Experience API",
        "statementId",
        "voidedStatementId",
        "Messenger",
        "bindService",
    ),
    "storage_or_loading": (
        "assets.open",
        "getResource",
        "readBytes",
        "readText",
        "FileInputStream",
        "fetch(",
        "URL(",
        "database",
        "query(",
        "download",
    ),
    "embedded_packaging": (
        "assets.srcDir",
        "src/main/assets",
        "copy bundle resources",
        "Bundle.main",
        "includeAssets",
        "embeddedResource",
    ),
    "embedded_loading": (
        "assets.open",
        "AssetManager",
        "Bundle.main",
        "getResource",
        "classpath:",
    ),
    "remote_acquisition": (
        "HttpURLConnection",
        "HttpClient",
        "URLSession",
        "fetch(",
        "download",
        "ktor.client",
        "OkHttpClient",
    ),
    "bounded_cache": (
        "cacheDir",
        "cachesDirectory",
        "CacheStorage",
        "IndexedDB",
        "LruCache",
        "maximumSize",
        "maxCache",
        "evict",
    ),
    "catalog_discovery": (
        "application/opds+json",
        "application/webpub+json",
        "learningUnits",
        "catalog",
        "publication manifest",
    ),
}


def _files(root: Path) -> Iterable[Path]:
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories if name not in _IGNORED_PARTS
        )
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(root)
            if any(part in _IGNORED_PARTS for part in relative.parts):
                continue
            if path.is_symlink():
                continue
            yield path


def _read_text(path: Path) -> Optional[str]:
    if path.stat().st_size > 2_000_000:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _metadata_hint(text: Optional[str]) -> Dict[str, str]:
    if text is None:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(value, dict):
        return {}
    hints = {}
    for key in ("identifier", "id", "name", "title"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            hints[key] = item.strip()
    return hints


def _path_words(path: str) -> Set[str]:
    return {
        word
        for word in re.split(r"[^a-z0-9]+", path.lower())
        if word
    }


def _source_references(
    source_text: Dict[str, str],
    inventory_paths: Set[str],
) -> Dict[str, List[str]]:
    by_name: Dict[str, List[str]] = {}
    for path in inventory_paths:
        by_name.setdefault(Path(path).name, []).append(path)
    references: Dict[str, Set[str]] = {}
    for source_path, text in source_text.items():
        for literal in _STRING_LITERAL.findall(text):
            normalized = literal.replace("\\", "/").lstrip("./")
            resolved = {
                normalized,
                posixpath.normpath(
                    posixpath.join(
                        posixpath.dirname(source_path),
                        literal.replace("\\", "/"),
                    )
                ),
            }
            candidates = []
            for target in resolved:
                if target in inventory_paths:
                    candidates.append(target)
                prefix = target.rstrip("/") + "/"
                candidates.extend(
                    path for path in inventory_paths if path.startswith(prefix)
                )
            basename_matches = by_name.get(Path(normalized).name, [])
            if (
                len(basename_matches) == 1
                and Path(normalized).name.lower()
                not in _GENERIC_REFERENCE_NAMES
            ):
                candidates.extend(basename_matches)
            for candidate in candidates:
                if candidate == source_path:
                    continue
                references.setdefault(candidate, set()).add(source_path)
    return {
        path: sorted(referrers)
        for path, referrers in sorted(references.items())
    }


def _reaches_any_referrer(
    path: str,
    references: Dict[str, List[str]],
    targets: Set[str],
    visited: Optional[Set[str]] = None,
) -> bool:
    seen = set() if visited is None else visited
    if path in seen:
        return False
    seen.add(path)
    for referrer in references.get(path, []):
        if referrer in targets:
            return True
        if _reaches_any_referrer(referrer, references, targets, seen):
            return True
    return False


def analyze_canapp_source(
    source_root: Path,
    canapp_root: Optional[Path] = None,
) -> Dict[str, Any]:
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("CanApp source root must be a directory")
    scope = (root / (canapp_root or Path("."))).resolve(strict=True)
    if not scope.is_dir() or (scope != root and root not in scope.parents):
        raise ValueError("CanApp root must be a directory within the source root")
    scope_prefix = (
        ""
        if scope == root
        else scope.relative_to(root).as_posix().rstrip("/") + "/"
    )
    inventory = []
    source_text: Dict[str, str] = {}
    reference_text: Dict[str, str] = {}
    text_by_path: Dict[str, Optional[str]] = {}
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        body = path.read_bytes()
        text = _read_text(path)
        text_by_path[relative] = text
        if (
            relative.startswith(scope_prefix)
            and path.suffix.lower() in _SOURCE_SUFFIXES
            and text is not None
        ):
            source_text[relative] = text
        if relative.startswith(scope_prefix) and text is not None:
            reference_text[relative] = text
        inventory.append(
            {
                "path": relative,
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    inventory_paths = {item["path"] for item in inventory}
    references = _source_references(reference_text, inventory_paths)
    seams: Dict[str, List[str]] = {
        "build": [],
        "manifest": [],
        "existing_respect": [],
        **{key: [] for key in _SIGNALS},
    }
    for path, text in text_by_path.items():
        if not path.startswith(scope_prefix):
            continue
        name = Path(path).name
        if name in _BUILD_NAMES:
            seams["build"].append(path)
        if name in _MANIFEST_NAMES:
            seams["manifest"].append(path)
        if any(part.lower().startswith("respect") for part in Path(path).parts):
            seams["existing_respect"].append(path)
        if text is None:
            continue
        for category, signals in _SIGNALS.items():
            if any(signal.lower() in text.lower() for signal in signals):
                seams[category].append(path)
    candidates = []
    product_sources = set(source_text) - set(seams["build"])
    embedded_build_files = set(seams["build"]) & set(
        seams["embedded_packaging"]
    )
    for item in inventory:
        path = item["path"]
        suffix = Path(path).suffix.lower()
        if suffix in _SOURCE_SUFFIXES or Path(path).name in _BUILD_NAMES:
            continue
        if any(part.lower().startswith("respect") for part in Path(path).parts):
            continue
        words = _path_words(path)
        referrers = references.get(path, [])
        content_named = path.startswith(scope_prefix) and bool(
            words & _CONTENT_WORDS
        )
        referenced_by_product = _reaches_any_referrer(
            path,
            references,
            product_sources,
        )
        embedded_by_build = _reaches_any_referrer(
            path,
            references,
            embedded_build_files,
        )
        build_content_named = embedded_by_build and bool(words & _CONTENT_WORDS)
        if not content_named and not referenced_by_product and not build_content_named:
            continue
        delivery_evidence = []
        if embedded_by_build:
            delivery_evidence.append("embedded_by_build")
        if referenced_by_product:
            delivery_evidence.append("referenced_by_product_source")
        candidates.append(
            {
                **item,
                "media_type_hint": (
                    mimetypes.guess_type(path)[0]
                    or "application/octet-stream"
                ),
                "metadata_hint": _metadata_hint(text_by_path[path]),
                "referenced_by": referrers,
                "delivery_evidence": delivery_evidence,
                "reasons": sorted(
                    reason
                    for reason, present in (
                        ("content-oriented path", content_named),
                        ("referenced by product source", referenced_by_product),
                        ("included by build configuration", embedded_by_build),
                    )
                    if present
                ),
            }
        )
    embedded_content = bool(seams["embedded_packaging"]) or any(
        "embedded_by_build" in item["delivery_evidence"]
        for item in candidates
    )
    return {
        "source_root_name": root.name,
        "canapp_root": (
            "."
            if scope == root
            else scope.relative_to(root).as_posix()
        ),
        "source_tree_digest": canonical_hash(inventory),
        "file_count": len(inventory),
        "seams": {
            key: sorted(set(values))
            for key, values in seams.items()
        },
        "content_candidates": candidates,
        "content_delivery": {
            "embedded_content": embedded_content,
            "on_demand_acquisition": bool(seams["remote_acquisition"]),
            "bounded_cache": bool(seams["bounded_cache"]),
            "catalog_discovery": bool(seams["catalog_discovery"]),
        },
    }


def build_repair_adapter(
    work_plan: Dict[str, Any],
    source_root: Path,
    *,
    testkit_commit: str,
    canapp_root: Optional[Path] = None,
) -> Dict[str, Any]:
    if work_plan.get("artifact_type") != "respect_ification_local_work_plan":
        raise ValueError("repair adaptation requires a local work plan")
    if work_plan.get("format_version") != "2.0.0":
        raise ValueError("legacy work plans are read-only and cannot generate work")
    if work_plan.get("semantic_hash") != canonical_hash(
        work_plan, ("semantic_hash",)
    ):
        raise ValueError("work plan semantic hash mismatch")
    matrix = load_matrix()
    if work_plan.get("matrix_semantic_hash") != matrix.semantic_hash:
        raise ValueError("work plan Matrix hash does not match the canonical Matrix")
    profile = matrix.resolve_profile(str(work_plan.get("profile_id")))
    selected_row_ids = {
        row.row_id for row in matrix.selected_rows(profile.profile_id)
    }
    planned_row_ids = [
        str(item.get("row_id")) for item in work_plan.get("tasks", [])
    ]
    outside_profile = sorted(set(planned_row_ids) - selected_row_ids)
    if outside_profile:
        raise ValueError(
            f"repair rows are outside the selected profile: {outside_profile}"
        )
    truth_audit = build_matrix_truth_audit(matrix)
    truth_contracts = select_truth_contracts(truth_audit, planned_row_ids)
    analysis = analyze_canapp_source(source_root, canapp_root)
    delivery = analysis["content_delivery"]
    acquisition_required = bool(
        analysis["content_candidates"]
        and (
            delivery["embedded_content"]
            or not delivery["on_demand_acquisition"]
            or not delivery["bounded_cache"]
            or not delivery["catalog_discovery"]
        )
    )
    if delivery["embedded_content"]:
        source_delivery_state = "embedded"
    elif delivery["on_demand_acquisition"] and not delivery["bounded_cache"]:
        source_delivery_state = "remote_unbounded"
    elif (
        delivery["on_demand_acquisition"]
        and delivery["bounded_cache"]
        and delivery["catalog_discovery"]
    ):
        source_delivery_state = "external_on_demand"
    else:
        source_delivery_state = "external_or_unknown"
    tasks = [
        {
            "task_id": item.get("task_id"),
            "row_id": item.get("row_id"),
            "expected": item.get("normative_task", {}).get("expected"),
            "source_hints": item.get("source_hints", []),
            "truth_contract": truth_contracts[str(item.get("row_id"))],
        }
        for item in work_plan.get("tasks", [])
    ]
    core = {
        "artifact_type": "respect_ification_generated_repair_adapter",
        "format_version": "2.0.0",
        "adapter_scope": "kit_time_only",
        "testkit_commit": testkit_commit,
        "matrix_semantic_hash": work_plan.get("matrix_semantic_hash"),
        "work_plan_semantic_hash": work_plan.get("semantic_hash"),
        "target_digest": work_plan.get("target_digest"),
        "profile_id": work_plan.get("profile_id"),
        "source_analysis": analysis,
        "tasks": tasks,
        "matrix_truth_audit": truth_audit,
        "content_acquisition_contract": {
            "required": acquisition_required,
            "source_delivery_state": source_delivery_state,
            "requirements": [
                "Keep ordinary lesson payloads outside the installable CanApp artifact.",
                "Discover lightweight catalog and publication metadata before acquiring lesson payloads.",
                "Acquire only the selected lesson through its declared publication resource.",
                "Validate response status, media type, publication identity, and declared integrity before parsing.",
                "Use a bounded persistent cache with offline reuse and deterministic eviction.",
                "Keep proprietary lesson parsing and runtime integration in normal CanApp-owned code.",
            ],
        },
        "publication_pack_contract": {
            "kit_owned_workflow": [
                "publication-manifest",
                "publication-pack",
                "publication-serve",
                "publication-verify",
            ],
            "owner_facts_required": [
                "stable CanApp identifier and localized title",
                "application package identifier",
                "public path and acquisition launch path",
                "stable lesson identifier namespace",
                "native lesson media type",
                "selected HTTPS origin",
                "real signing-certificate SHA-256 fingerprint",
                "provisional or production provision classification",
            ],
            "emitted_surface": [
                "CanApp descriptor",
                "OPDS catalog",
                "Readium publication manifests",
                "acquisition pages",
                "exact native lesson resources",
                "reachable covers",
                "Android Digital Asset Links association",
                "media-type and cache-validator deployment contract",
                "portable reference server and container recipe",
                "content and validation receipt",
            ],
        },
        "required_invariants": [
            "Trace the production content inventory through real build, storage, selection, loading, and completion paths before generating descriptions.",
            "Generate one truthful OPDS publication and Readium wrapper per real selectable lesson, or document and verify a real grouping represented by one publication.",
            "Externalize ordinary lesson payloads and make the CanApp acquire only the selected publication resource on demand through a bounded, integrity-checked cache.",
            "Make every acquisition launch the exact selected lesson through the CanApp production entry path.",
            "Bind runtime activity and Experience API statements to the selected publication and actual lesson facts.",
            "Keep provisional external services outside the CanApp while serving source-derived, correctly formatted artifacts.",
            "Integrate durable product behavior into the CanApp; do not retain a test-recognizing runtime adapter.",
        ],
    }
    return {
        **core,
        "semantic_hash": canonical_hash(core),
    }


def _paths(values: List[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "(none discovered)"


def render_repair_prompt(adapter: Dict[str, Any]) -> str:
    if adapter.get("artifact_type") != "respect_ification_generated_repair_adapter":
        raise ValueError("repair prompt requires a generated repair adapter")
    if adapter.get("semantic_hash") != canonical_hash(
        adapter, ("semantic_hash",)
    ):
        raise ValueError("repair adapter semantic hash mismatch")
    analysis = adapter["source_analysis"]
    seams = analysis["seams"]
    candidates = analysis["content_candidates"]
    lines = [
        "# Implement the source-derived RESPECT repair",
        "",
        "Use this prompt inside the Candidate App owner's source environment. The generated adapter is Kit-time scaffolding only. Its valid outputs are durable production changes in the Candidate App, its build, its tests, and any genuinely external service required by RESPECT.",
        "",
        "## Bindings",
        "",
        f"- profile: `{adapter.get('profile_id')}`",
        f"- target digest: `{adapter.get('target_digest')}`",
        f"- Matrix semantic hash: `{adapter.get('matrix_semantic_hash')}`",
        f"- work-plan semantic hash: `{adapter.get('work_plan_semantic_hash')}`",
        f"- source-tree digest: `{analysis.get('source_tree_digest')}`",
        f"- Testkit commit: `{adapter.get('testkit_commit')}`",
        "",
        "## Discovered implementation seams",
        "",
    ]
    for label in (
        "build",
        "manifest",
        "existing_respect",
        "storage_or_loading",
        "embedded_packaging",
        "embedded_loading",
        "remote_acquisition",
        "bounded_cache",
        "catalog_discovery",
        "selection",
        "completion",
        "launch",
        "lifecycle",
        "xapi",
    ):
        lines.append(f"- {label.replace('_', ' ')}: {_paths(seams[label])}")
    lines.extend(["", "## Candidate lesson/content artifacts", ""])
    if candidates:
        for item in candidates:
            metadata = item.get("metadata_hint") or {}
            title = metadata.get("title") or metadata.get("name")
            description = f"; title/name hint: {title}" if title else ""
            lines.append(
                f"- `{item['path']}`; SHA-256 `{item['sha256']}`; reasons: {', '.join(item['reasons'])}{description}"
            )
    else:
        lines.append("- No content artifact was safely inferred. Trace the production selector and loader before editing; do not invent a lesson.")
    lines.extend(
        [
            "",
            "These are evidence-derived candidates, not a declared lesson inventory. Determine the real inventory by tracing what the production CanApp actually packages, downloads, queries, presents, selects, loads, and completes. The proprietary content format belongs to the CanApp-specific repair, never to the generic Test Suite or permanent Kit logic.",
            "",
            "## Required repair behavior",
            "",
            "- Add or revise normal production code so an acquisition launch selects the exact catalog publication's real lesson.",
            "- Remove ordinary lesson payloads from the installable application package. Retain only an explicitly justified bootstrap lesson when the product has a real offline-first requirement for it.",
            "- Discover lightweight descriptor, catalog, and publication metadata first; download only the selected lesson when the learner selects or launches it.",
            "- Validate the selected response status, media type, publication identity, and declared integrity before the proprietary lesson parser receives any bytes.",
            "- Store acquired lessons in a bounded local cache that supports offline reuse, atomic replacement, and deterministic eviction without turning cached content into a second catalog authority.",
            "- Keep the transport, catalog, publication, cache, and acquisition contracts content-format agnostic. The proprietary lesson parser remains CanApp-owned and is invoked only after generic acquisition validation succeeds.",
            "- Generate the default OPDS catalog and Readium publication wrappers from the verified real inventory. Preserve each native lesson artifact losslessly as a declared resource when applicable.",
            "- After tracing the production selector and loader, explicitly confirm that every selected analyzer candidate is a real selectable lesson, then use the Kit's `publication-manifest` workflow to combine that confirmed inventory with owner-supplied identity facts. Never fill an unknown fact with a placeholder.",
            "- Use `publication-pack` to emit the complete RESPECT Publication Pack: descriptor, OPDS catalog, Readium wrappers, acquisition pages, exact lesson bytes, covers, Android association, deployment contract, reference server, container recipe, and receipt.",
            "- Use `publication-serve` for provisional HTTPS hosting and `publication-verify` to validate both the pack and its deployed origin, including media types, byte identity, lengths, validators, and conditional responses.",
            "- Derive identifiers, titles, media types, images, and other descriptions from real source facts. Do not invent a lesson, generic wrapper, marker resource, placeholder image, or disconnected activity.",
            "- Emit Experience API statements from the selected lesson's actual runtime lifecycle and completion facts. Do not use a hidden query parameter, debug-only completion route, canned snapshot, or Test Suite recognition.",
            "- Put legitimate reusable runtime functionality into the CanApp as supported product code. Keep this generated adapter and any source-analysis data out of the production runtime.",
            "- Use a provisional local service only for functionality that is genuinely external to the CanApp. It must serve the real generated artifacts and must not simulate CanApp behavior.",
            "- Add production-owned tests proving inventory-to-catalog, catalog-to-launch, launch-to-selection, selection-to-runtime, and runtime-to-statement continuity.",
            "- Run the unchanged, format-agnostic Test Suite after the product repair. Do not change Matrix requirements, applicability, result classification, fixtures, or trust metadata.",
            "",
            "## Matrix-addressed repair tasks",
            "",
        ]
    )
    for task in adapter["tasks"]:
        contract = task["truth_contract"]
        lines.extend(
            [
                f"### `{task['row_id']}` — {contract['title']}",
                "",
                f"- Matrix expectation: {task.get('expected') or contract['test_action']}",
                f"- Required behavior: {contract['canapp_behavior']}",
                f"- Positive case: {contract['positive_case']}",
                f"- Negative case: {contract['negative_case']}",
                f"- Required observation: {contract['test_action']}",
                f"- Implement in: {', '.join(contract['implementation_targets'])}",
                f"- Inspect source seams: {', '.join(contract['source_seams'])}",
                f"- Evidence class: {contract['required_evidence_class']}",
                "- Forbidden substitutes: "
                + "; ".join(contract["forbidden_substitutes"]),
                "",
            ]
        )
    lines.extend(
        [
            "",
            "If proprietary-format interpretation cannot be established from source and runtime evidence, stop that repair task with the exact missing fact. Do not substitute structurally valid but semantically false content.",
            "",
        ]
    )
    return "\n".join(lines)


def write_repair_adapter(
    work_plan: Dict[str, Any],
    source_root: Path,
    adapter_output: Path,
    prompt_output: Path,
    *,
    testkit_commit: str,
    canapp_root: Optional[Path] = None,
) -> None:
    adapter = build_repair_adapter(
        work_plan,
        source_root,
        testkit_commit=testkit_commit,
        canapp_root=canapp_root,
    )
    adapter_output.parent.mkdir(parents=True, exist_ok=True)
    prompt_output.parent.mkdir(parents=True, exist_ok=True)
    adapter_output.write_text(
        json.dumps(adapter, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prompt_output.write_text(render_repair_prompt(adapter), encoding="utf-8")
