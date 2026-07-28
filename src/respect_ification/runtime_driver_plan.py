# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


DRIVER_GATED_ROW_IDS = frozenset(
    {
        "ANDROID-001",
        "ANDROID-002",
        "AUTH-001",
        "AUTH-003",
        "LAUNCH-003",
        "LAUNCH-004",
        "LAUNCH-005",
        "LAUNCH-006",
        "LAUNCH-007",
        "LIFECYCLE-001",
        "XAPI-003",
        "XAPI-004",
        "XAPI-005",
        "XAPI-006",
        "XAPI-007",
        "XAPI-008",
        "XAPI-009",
        "XAPI-010",
        "XAPI-011",
        "XAPI-013",
        "XAPI-014",
        "XAPI-015",
        "XAPI-016",
        "XAPI-017",
        "XAPI-018",
        "XAPI-019",
    }
)

_TEXT_SUFFIXES = {
    ".gradle",
    ".html",
    ".java",
    ".jimsong",
    ".js",
    ".json",
    ".kts",
    ".kt",
    ".xml",
}
_IGNORED_PARTS = {
    ".git",
    ".gradle",
    ".idea",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

_SIGNALS = {
    "manifest_files": ("AndroidManifest.xml",),
    "build_files": ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
    "launch_files": (
        "onCreate",
        "onNewIntent",
        "intent.data",
        "activity_id",
        "xapiIpcPackage",
    ),
    "lifecycle_files": ("onDestroy", "onStop", "unbindService", "DisposableEffect"),
    "lesson_fact_files": (
        "LessonSnapshot",
        "LessonPhase",
        "hits",
        "total",
        "score",
        "Results",
    ),
    "xapi_files": (
        "xapi",
        "Xapi",
        "Messenger",
        "bindService",
        "statementId",
        "voidedStatementId",
    ),
    "test_files": (
        "androidTest",
        "androidInstrumentedTest",
        "androidUnitTest",
        "Test.kt",
        "Test.java",
    ),
}


def _candidate_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        yield path


def analyze_canapp_source(source_root: Path) -> Dict[str, List[str]]:
    root = source_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("CanApp source root must be a directory")
    analysis: Dict[str, Set[str]] = {key: set() for key in _SIGNALS}
    analysis["lesson_content_files"] = set()
    for path in _candidate_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for category, signals in _SIGNALS.items():
            if any(signal in path.name or signal in relative or signal in text for signal in signals):
                analysis[category].add(relative)
        content_path = relative.lower()
        if path.suffix == ".jimsong" or (
            path.suffix in {".html", ".json"}
            and any(
                signal in content_path
                for signal in ("lesson", "course", "song")
            )
        ):
            analysis["lesson_content_files"].add(relative)
    return {key: sorted(values) for key, values in analysis.items()}


def _task_rows(work_plan: Dict[str, Any]) -> Set[str]:
    if work_plan.get("artifact_type") != "respect_ification_local_work_plan":
        raise ValueError("runtime-driver planning requires a local work plan")
    if work_plan.get("profile_id") != "PROFILE-NATIVE_ANDROID":
        raise ValueError("runtime-driver planning requires PROFILE-NATIVE_ANDROID")
    return {
        item.get("row_id")
        for item in work_plan.get("tasks", [])
        if item.get("row_id") in DRIVER_GATED_ROW_IDS
    }


def _paths(values: List[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "(none discovered)"


def render_runtime_driver_prompt(
    work_plan: Dict[str, Any],
    source_root: Path,
    *,
    testkit_commit: str,
) -> str:
    observed_rows = _task_rows(work_plan)
    if observed_rows != DRIVER_GATED_ROW_IDS:
        missing = sorted(DRIVER_GATED_ROW_IDS - observed_rows)
        extra = sorted(observed_rows - DRIVER_GATED_ROW_IDS)
        raise ValueError(
            "driver-gated task set mismatch: "
            f"missing={missing}, extra={extra}"
        )
    analysis = analyze_canapp_source(source_root)
    tasks = {
        item["row_id"]: item["normative_task"]
        for item in work_plan["tasks"]
        if item["row_id"] in DRIVER_GATED_ROW_IDS
    }
    lines = [
        "# Implement the source-aware native Android runtime driver",
        "",
        f"Implement and verify the Test Suite-owned runtime driver for the 26 runtime-driver-gated rows in the RESPECT-ification work plan bound to target digest `{work_plan.get('target_digest')}` and Matrix semantic hash `{work_plan.get('matrix_semantic_hash')}`. Base Testkit work on immutable commit `{testkit_commit}`.",
        "",
        "## Authority and outcome",
        "",
        "The Test Suite remains the only compatibility-verdict authority. The RESPECT-ification Kit may inspect owner-local Candidate App source and generate this implementation prompt, but only the Test Suite controller may convert directly observed device behavior into row outcomes. CanApp test code may trigger operations; it must never submit trusted row states or bypass controller validation.",
        "",
        "Implement a suite-owned companion Android application plus a Python Android Debug Bridge controller. The companion provides the `org.openeel.action.xapioveripc` Messenger service, records bind/request/reply/flow/lifecycle observations, returns controlled Experience API responses, and exposes sanitized evidence to the Python controller. The controller installs the submitted Android Package Kit and companion application, launches the submitted production HTTPS App Link, drives source-mapped CanApp scenarios, verifies package resolution and domain association, and supplies attributable observations directly to the Matrix executors.",
        "",
        "## Discovered CanApp seams",
        "",
        f"- Android manifests: {_paths(analysis['manifest_files'])}",
        f"- Gradle build entry points: {_paths(analysis['build_files'])}",
        f"- launch and intent handling: {_paths(analysis['launch_files'])}",
        f"- lifecycle handling: {_paths(analysis['lifecycle_files'])}",
        f"- lesson facts and completion: {_paths(analysis['lesson_fact_files'])}",
        f"- lesson content candidates: {_paths(analysis['lesson_content_files'])}",
        f"- Experience API or Messenger integration: {_paths(analysis['xapi_files'])}",
        f"- existing test source sets: {_paths(analysis['test_files'])}",
        "",
        "Treat these paths as nonnormative implementation hints. Re-read the live files before editing, preserve production behavior, and keep target-specific trigger code in test source sets. Do not place secrets, private actors, credentials, device identifiers, or generated evidence in source control.",
        "",
        "## Truthfulness and content binding",
        "",
        "Build a one-to-one inventory of real lessons that the production CanApp actually packages, loads, downloads, or otherwise makes selectable. Derive the default lesson catalog and Readium publication wrappers from that inventory. Do not invent a generic lesson, placeholder title, placeholder image, marker script, or publication solely to satisfy structural validators. If the source format cannot be wrapped losslessly, report the missing adapter as a repair task.",
        "",
        "Each catalog publication must identify one real lesson or a documented real grouping, and its acquisition URL must launch that exact lesson. The Test Suite controller must derive the launch URL from the selected catalog publication, append only the standard reserved launch parameters, and require the launch `activity_id` to equal that publication's identifier. Reject owner-selected launch URLs, hidden control parameters, and disconnected activity identifiers.",
        "",
        "Experience API evidence must result from the selected lesson's actual launch and lifecycle. A debug-only trigger, manufactured lesson snapshot, canned completion, or test-only query parameter is diagnostic evidence only and cannot satisfy a CanApp conformance row. Bind statement activity, score, completion, and success fields to facts observed from the selected real lesson.",
        "",
        "## Required rows",
        "",
    ]
    for row_id in sorted(DRIVER_GATED_ROW_IDS):
        task = tasks[row_id]
        lines.append(
            f"- `{row_id}` — {task.get('expected', 'Use the live Matrix expectation.')} Narrow verifier: `{task.get('narrow_verifier_id')}`."
        )
    lines.extend(
        [
            "",
            "## Driver contract",
            "",
            "Use red/green Test-Driven Development. Add negative controls proving that owner-authored fixture assertions, owner-authored result files, unhealthy devices, wrong packages, wrong endpoints, wrong authorization, wrong actors, malformed statements, missing correlation identifiers, stale replies, and incomplete flows cannot produce passes. The Test Suite itself must set controlled-runtime provenance only after its controller has completed health checks and bound every observation to the submitted target digest, Android Package Kit digest, companion digest, device, scenario nonce, and Matrix row.",
            "",
            "Expose the driver through documented `respect-compat` and `respect-ification verify`/`full-test` command-line options. The interface must accept the selected device, submitted Android Package Kit, suite-built companion package and source-bound build receipt, production launch URL, and a source-aware scenario artifact generated from this prompt. Certification mode must reject deterministic seeds, untrusted observation imports, emulator-only completion when physical hardware is required, and missing or stale evidence.",
            "",
            "The suite-owned companion must implement clean-room protocol behavior from the canonical Matrix and public Android Messenger contract: explicit package binding with action `org.openeel.action.xapioveripc`; correlated request and reply identifiers; statement POST; statement GET; GET flow emissions and completion; endpoint and authorization preservation; controlled statement storage, retrieval, voiding, filtering, bounds, and representation selection. Do not copy or translate code from incompatible upstream implementations.",
            "",
            "Finish with a complete selected-profile Test Suite run. Report exact commands and exit codes, the 26 row outcomes, controller and target hashes, device evidence, negative-control results, and remaining blockers. A fixture, imported observation file, owner-authored pass flag, or static Android Package Kit inspection alone must never satisfy a runtime row.",
            "",
        ]
    )
    return "\n".join(lines)


def write_runtime_driver_prompt(
    work_plan: Dict[str, Any],
    source_root: Path,
    output: Path,
    *,
    testkit_commit: str,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_runtime_driver_prompt(
            work_plan,
            source_root,
            testkit_commit=testkit_commit,
        ),
        encoding="utf-8",
    )
