# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import argparse
import hashlib
import json
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from respect_compat.cli import main as suite_main
from respect_compat.android_apk import inspect_apk, probe_android_device
from respect_compat.android_runtime_runner import (
    SCENARIO_ACTION_TYPES,
    run_native_android_runtime,
)
from respect_compat.handoff import canonical_hash
from respect_compat.execution_log import (
    ExecutionLog,
    execution_log_path_from_argv,
)
from respect_compat.matrix_runtime import load_matrix
from respect_compat.target import (
    CanAppTarget,
    attach_publication_inputs,
    load_apk_target,
    load_fixture_target,
    load_server_target,
    load_url_target,
)

from .ledger import append_event, read_ledger
from .lesson_modeler import (
    build_coverage,
    build_modeling_packet,
    compile_run_plan,
    read_artifact as read_lesson_artifact,
    run_lesson_batch,
    validate_artifact as validate_lesson_artifact,
    write_artifact as write_lesson_artifact,
    write_modeling_handback,
)
from .planner import build_work_plan, validate_work_plan
from .prep import generate_prep, write_prep
from .publication_pack import (
    build_publication_manifest_from_adapter,
    build_publication_pack,
    build_verification_receipt,
    verify_deployed_publication,
    verify_publication_pack,
)
from .publication_authorization import (
    SpixPublicationClient,
    ensure_publication_authorization,
)
from .publication_server import serve_publication_pack
from .repair_adapter import write_repair_adapter
from .truth_audit import build_matrix_truth_audit
from .verifier import run_narrow_verifier


class KitArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage()
        self.exit(64, f"{self.prog}: error: {message}\n")


def _read(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return data


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _lesson_child_outcome(
    report: Dict[str, Any], exit_code: int
) -> str:
    if exit_code == 0:
        return "passed"
    states = {
        result.get("state")
        for result in report.get("results", [])
        if isinstance(result, dict)
    }
    if "fail" in states:
        return "failed"
    if "incomplete" in states:
        return "incomplete"
    return "blocked"


def _add_target(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture-dir", type=Path)
    group.add_argument("--manifest-url")
    group.add_argument("--server-base-url")
    group.add_argument("--apk-only", action="store_true")
    parser.add_argument("--apk", type=Path)
    parser.add_argument(
        "--ca-cert",
        type=Path,
        help="Trust this CA certificate for a provisioned HTTPS target.",
    )
    parser.add_argument("--device-id")
    parser.add_argument("--runtime-driver-apk", type=Path)
    parser.add_argument("--runtime-gesture-apk", type=Path)
    parser.add_argument("--runtime-driver-receipt", type=Path)
    parser.add_argument("--runtime-scenario", type=Path)
    parser.add_argument("--respect-platform-apk", type=Path)
    parser.add_argument("--respect-platform-build-receipt", type=Path)
    parser.add_argument("--respect-platform-scenario", type=Path)
    parser.add_argument("--publication-artifact", type=Path)
    parser.add_argument("--immutable-artifact-url")
    parser.add_argument("--publication-authorization-token", type=Path)
    parser.add_argument(
        "--spix-public-key",
        type=Path,
        help=(
            "Forward a submission-supplied key for negative verification; "
            "it cannot establish Spix certification trust."
        ),
    )
    parser.add_argument("--certification-key-state-dir", type=Path)


def _add_lesson_model_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)


def _load_target(
    args: argparse.Namespace,
    execution_event=None,
) -> CanAppTarget:
    if args.apk_only:
        if not args.apk:
            raise ValueError("--apk-only requires --apk")
        target = load_apk_target(args.apk)
    elif args.fixture_dir:
        target = load_fixture_target(args.fixture_dir, apk=args.apk)
    elif args.manifest_url:
        target = load_url_target(
            args.manifest_url,
            apk=args.apk,
            ca_cert=args.ca_cert,
        )
    else:
        target = load_server_target(
            args.server_base_url,
            apk=args.apk,
            ca_cert=args.ca_cert,
        )
    attach_publication_inputs(
        target,
        artifact=args.publication_artifact,
        immutable_artifact_url=args.immutable_artifact_url,
        authorization_token=args.publication_authorization_token,
        spix_public_key=args.spix_public_key,
    )
    if args.device_id:
        probe = probe_android_device(args.device_id)
        target.metadata["device_id"] = args.device_id
        target.metadata["device_probe"] = probe
        if probe["healthy"]:
            target.capabilities.add("android_device")
    runtime_values = (
        args.runtime_driver_apk,
        args.runtime_driver_receipt,
        args.runtime_scenario,
    )
    if any(runtime_values) and not all(runtime_values):
        raise ValueError(
            "--runtime-driver-apk, --runtime-driver-receipt, and "
            "--runtime-scenario must be supplied together"
        )
    if args.runtime_gesture_apk and not all(runtime_values):
        raise ValueError(
            "--runtime-gesture-apk requires the complete native runtime group"
        )
    if args.runtime_driver_apk:
        if not args.apk or not args.device_id:
            raise ValueError(
                "native runtime execution requires --apk and --device-id"
            )
        run_native_android_runtime(
            target,
            device_id=args.device_id,
            driver_apk=args.runtime_driver_apk,
            driver_receipt=args.runtime_driver_receipt,
            gesture_apk=args.runtime_gesture_apk,
            scenario_path=args.runtime_scenario,
            scenario_nonce=secrets.token_hex(12),
            execution_event=execution_event,
        )
        target.capabilities.add("controlled_android_runtime")
    platform_values = (
        args.respect_platform_apk,
        args.respect_platform_build_receipt,
        args.respect_platform_scenario,
    )
    if any(platform_values) and not all(platform_values):
        raise ValueError(
            "--respect-platform-apk, "
            "--respect-platform-build-receipt, and "
            "--respect-platform-scenario must be supplied together"
        )
    return target


def _suite_target_args(args: argparse.Namespace) -> List[str]:
    if args.apk_only:
        values = ["--apk-only"]
    elif args.fixture_dir:
        values = ["--fixture-dir", str(args.fixture_dir)]
    elif args.manifest_url:
        values = ["--manifest-url", args.manifest_url]
    else:
        values = ["--server-base-url", args.server_base_url]
    if args.apk:
        values.extend(["--apk", str(args.apk)])
    if args.ca_cert:
        values.extend(["--ca-cert", str(args.ca_cert)])
    if args.device_id:
        values.extend(["--device-id", args.device_id])
    if args.runtime_driver_apk:
        values.extend(["--runtime-driver-apk", str(args.runtime_driver_apk)])
    if args.runtime_gesture_apk:
        values.extend(["--runtime-gesture-apk", str(args.runtime_gesture_apk)])
    if args.runtime_driver_receipt:
        values.extend(
            ["--runtime-driver-receipt", str(args.runtime_driver_receipt)]
        )
    if args.runtime_scenario:
        values.extend(["--runtime-scenario", str(args.runtime_scenario)])
    if args.respect_platform_apk:
        values.extend(
            ["--respect-platform-apk", str(args.respect_platform_apk)]
        )
    if args.respect_platform_build_receipt:
        values.extend(
            [
                "--respect-platform-build-receipt",
                str(args.respect_platform_build_receipt),
            ]
        )
    if args.respect_platform_scenario:
        values.extend(
            [
                "--respect-platform-scenario",
                str(args.respect_platform_scenario),
            ]
        )
    if args.publication_artifact:
        values.extend(
            ["--publication-artifact", str(args.publication_artifact)]
        )
    if args.immutable_artifact_url:
        values.extend(
            ["--immutable-artifact-url", args.immutable_artifact_url]
        )
    if args.publication_authorization_token:
        values.extend(
            [
                "--publication-authorization-token",
                str(args.publication_authorization_token),
            ]
        )
    if args.spix_public_key:
        values.extend(["--spix-public-key", str(args.spix_public_key)])
    if args.certification_key_state_dir:
        values.extend(
            [
                "--certification-key-state-dir",
                str(args.certification_key_state_dir),
            ]
        )
    return values


def build_parser() -> KitArgumentParser:
    parser = KitArgumentParser(
        description=(
            "Turn immutable RESPECT Test Suite failures into local repair work "
            "without changing conformance semantics."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--source-root", type=Path, required=True)
    prepare.add_argument("--target-digest", required=True)
    prepare.add_argument("--profile", required=True)
    prepare.add_argument("--public-output", type=Path, required=True)
    prepare.add_argument("--private-output", type=Path)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--report", type=Path, required=True)
    plan.add_argument("--evidence-manifest", type=Path, required=True)
    plan.add_argument("--task-packet", type=Path, required=True)
    plan.add_argument("--private-prep", type=Path)
    plan.add_argument("--output", type=Path, required=True)

    repair_plan = subparsers.add_parser("repair-plan")
    repair_plan.add_argument("--work-plan", type=Path, required=True)
    repair_plan.add_argument("--source-root", type=Path, required=True)
    repair_plan.add_argument("--canapp-root", type=Path)
    repair_plan.add_argument("--testkit-commit", required=True)
    repair_plan.add_argument("--adapter-output", type=Path, required=True)
    repair_plan.add_argument("--prompt-output", type=Path, required=True)
    repair_plan.add_argument(
        "--human-todo-output",
        type=Path,
        help=(
            "Write the human delegation checklist here "
            "(default: Human_ToDo.md beside --prompt-output)."
        ),
    )

    truth_audit = subparsers.add_parser("truth-audit")
    truth_audit.add_argument("--output", type=Path, required=True)

    lesson_model = subparsers.add_parser(
        "lesson-model",
        help=(
            "Run the CanApp Lesson Modeler without adding CanApp facts "
            "to the TestKit."
        ),
    )
    lesson_actions = lesson_model.add_subparsers(
        dest="lesson_model_action", required=True
    )

    lesson_analyze = lesson_actions.add_parser("analyze")
    lesson_analyze.add_argument("--source-root", type=Path, required=True)
    lesson_analyze.add_argument("--inventory", type=Path, required=True)
    lesson_analyze.add_argument("--output-dir", type=Path, required=True)

    lesson_validate = lesson_actions.add_parser("validate")
    lesson_validate.add_argument(
        "--artifact", type=Path, action="append", required=True
    )
    lesson_validate.add_argument("--output-dir", type=Path, required=True)

    lesson_compile = lesson_actions.add_parser("compile")
    _add_lesson_model_inputs(lesson_compile)
    lesson_compile.add_argument("--testkit-commit", required=True)
    lesson_compile.add_argument("--target-id", required=True)
    lesson_compile.add_argument("--target-digest", required=True)
    lesson_compile.add_argument("--profile", required=True)
    lesson_compile.add_argument(
        "--available-capability",
        action="append",
        choices=sorted(SCENARIO_ACTION_TYPES),
    )
    lesson_compile.add_argument("--output-dir", type=Path, required=True)

    lesson_execute = lesson_actions.add_parser("execute")
    lesson_execute.add_argument("--run-plan", type=Path, required=True)
    lesson_execute.add_argument("--resume", action="store_true")
    lesson_execute.add_argument("--output-dir", type=Path, required=True)
    _add_target(lesson_execute)

    lesson_status = lesson_actions.add_parser("status")
    _add_lesson_model_inputs(lesson_status)
    lesson_status.add_argument("--run-plan", type=Path, required=True)
    lesson_status.add_argument("--batch-index", type=Path)
    lesson_status.add_argument("--output-dir", type=Path, required=True)

    publication_pack = subparsers.add_parser("publication-pack")
    publication_pack.add_argument("--manifest", type=Path, required=True)
    publication_pack.add_argument("--source-root", type=Path, required=True)
    publication_pack.add_argument("--origin", required=True)
    publication_signer = publication_pack.add_mutually_exclusive_group(
        required=True
    )
    publication_signer.add_argument(
        "--signing-fingerprint",
    )
    publication_signer.add_argument("--apk", type=Path)
    publication_pack.add_argument(
        "--provision",
        choices=("provisional", "production"),
        required=True,
    )
    publication_pack.add_argument(
        "--signer-kind",
        choices=("debug", "release"),
    )
    publication_pack.add_argument(
        "--publication-authorization-token", type=Path
    )
    publication_pack.add_argument("--output", type=Path, required=True)

    publication_manifest = subparsers.add_parser(
        "publication-manifest"
    )
    publication_manifest.add_argument(
        "--repair-adapter",
        type=Path,
        required=True,
    )
    publication_manifest.add_argument(
        "--source-root",
        type=Path,
        required=True,
    )
    publication_manifest.add_argument(
        "--canapp-identifier",
        required=True,
    )
    publication_manifest.add_argument("--canapp-title", required=True)
    publication_manifest.add_argument("--application-id", required=True)
    publication_manifest.add_argument("--public-path", required=True)
    publication_manifest.add_argument(
        "--launch-path-prefix",
        required=True,
    )
    publication_manifest.add_argument(
        "--lesson-identifier-root",
        required=True,
    )
    publication_manifest.add_argument(
        "--lesson-media-type",
        required=True,
    )
    publication_manifest.add_argument("--language", default="en")
    publication_manifest.add_argument(
        "--lesson-inventory",
        type=Path,
        required=True,
    )
    publication_manifest.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    publication_verify = subparsers.add_parser("publication-verify")
    publication_verify.add_argument("--pack", type=Path, required=True)
    publication_verify.add_argument(
        "--receipt-output",
        type=Path,
        required=True,
    )
    publication_verify.add_argument("--deployed-origin")
    publication_verify.add_argument("--ca-cert", type=Path)

    publication_serve = subparsers.add_parser("publication-serve")
    publication_serve.add_argument("--pack", type=Path, required=True)
    publication_serve.add_argument("--bind", default="127.0.0.1")
    publication_serve.add_argument("--port", type=int, default=8765)
    publication_serve.add_argument("--certfile", type=Path)
    publication_serve.add_argument("--keyfile", type=Path)

    publication_authorization = subparsers.add_parser(
        "publication-authorization"
    )
    publication_authorization.add_argument(
        "--spix-service-url", required=True
    )
    publication_authorization.add_argument("--publisher-id", required=True)
    publication_authorization.add_argument(
        "--agreement-version", required=True
    )
    publication_authorization.add_argument("--app-id", required=True)
    publication_authorization.add_argument(
        "--artifact", type=Path, required=True
    )
    publication_authorization.add_argument(
        "--immutable-artifact-url", required=True
    )
    publication_authorization.add_argument(
        "--state", type=Path, required=True
    )
    publication_authorization.add_argument(
        "--token-output", type=Path, required=True
    )
    publication_authorization.add_argument(
        "--open-signing", action="store_true"
    )
    publication_authorization.add_argument(
        "--replace-terminal-request", action="store_true"
    )

    status = subparsers.add_parser("status")
    status.add_argument("--work-plan", type=Path, required=True)
    status.add_argument("--ledger", type=Path, required=True)

    record = subparsers.add_parser("record")
    record.add_argument("--work-plan", type=Path, required=True)
    record.add_argument("--ledger", type=Path, required=True)
    record.add_argument("--task-id", required=True)
    record.add_argument("--state", required=True)
    record.add_argument("--note", required=True)
    record.add_argument("--verifier-result-ref")

    verify = subparsers.add_parser("verify")
    verify.add_argument("--work-plan", type=Path, required=True)
    verify.add_argument("--task-id", required=True)
    verify.add_argument("--output", type=Path, required=True)
    _add_target(verify)

    full_test = subparsers.add_parser("full-test")
    full_test.add_argument("--profile", required=True)
    full_test.add_argument("--output-dir", type=Path, required=True)
    _add_target(full_test)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    raw_argv = list(argv if argv is not None else sys.argv[1:])
    command = (
        raw_argv[0]
        if raw_argv and not raw_argv[0].startswith("-")
        else "cli"
    )
    event_log = ExecutionLog(
        execution_log_path_from_argv(
            raw_argv,
            command=command,
        ),
        program="respect-ification",
        command=command,
        argv=raw_argv,
    )
    print(f"Execution log: {event_log.path}", file=sys.stderr)
    parser = build_parser()
    try:
        args = parser.parse_args(raw_argv)
    except SystemExit as error:
        event_log.emit(
            "argument_parsing",
            "failed" if error.code else "completed",
            {"exit_code": error.code},
        )
        event_log.finish(int(error.code or 0))
        raise
    event_log.emit("arguments", "validated")

    def finish(exit_code: int) -> int:
        event_log.finish(exit_code)
        return exit_code

    try:
        if args.command == "prepare":
            with event_log.step("generate_prep"):
                public, private = generate_prep(
                    args.source_root,
                    args.target_digest,
                    args.profile,
                    include_private=args.private_output is not None,
                )
            with event_log.step("write_prep"):
                write_prep(
                    public, args.public_output, private, args.private_output
                )
            print(
                f"Prepared public packet"
                f"{' and owner-local private packet' if private else ''}."
            )
            return finish(0)
        if args.command == "plan":
            with event_log.step("read_handoff"):
                report = _read(args.report)
                evidence = _read(args.evidence_manifest)
                tasks = _read(args.task_packet)
                private = _read(args.private_prep) if args.private_prep else None
            with event_log.step("build_work_plan"):
                work_plan = build_work_plan(report, evidence, tasks, private)
                errors = validate_work_plan(work_plan, tasks)
            if errors:
                raise ValueError(f"invalid generated work plan: {errors}")
            with event_log.step("write_work_plan"):
                _write(args.output, work_plan)
            print(f"Planned {len(work_plan['tasks'])} actionable repair tasks.")
            return finish(0)
        if args.command == "repair-plan":
            with event_log.step("read_work_plan"):
                plan = _read(args.work_plan)
            with event_log.step("write_repair_package"):
                write_repair_adapter(
                    plan,
                    args.source_root,
                    args.adapter_output,
                    args.prompt_output,
                    testkit_commit=args.testkit_commit,
                    canapp_root=args.canapp_root,
                    human_todo_output=args.human_todo_output,
                )
            print(
                "Wrote the Kit-time repair adapter and source-derived "
                "implementation prompt, plus its synchronized Human_ToDo.md."
            )
            return finish(0)
        if args.command == "truth-audit":
            with event_log.step("build_truth_audit"):
                audit = build_matrix_truth_audit(load_matrix())
                audit["semantic_hash"] = canonical_hash(
                    audit,
                    ("semantic_hash",),
                )
            with event_log.step("write_truth_audit"):
                _write(args.output, audit)
            print(
                "Audited "
                f"{audit['summary']['row_count']} Matrix rows: "
                f"{audit['summary']['canapp_repair_row_count']} require "
                "durable CanApp repair and "
                f"{audit['summary']['protected_non_canapp_row_count']} "
                "retain their non-CanApp owner."
            )
            return finish(0)
        if args.command == "lesson-model":
            if args.lesson_model_action == "analyze":
                with event_log.step("read_lesson_inventory"):
                    inventory = read_lesson_artifact(
                        args.inventory, "inventory"
                    )
                with event_log.step("build_lesson_modeling_packet"):
                    packet = build_modeling_packet(
                        args.source_root, inventory
                    )
                with event_log.step("write_lesson_modeling_handback"):
                    write_lesson_artifact(
                        args.output_dir
                        / "canapp-lesson-modeling-packet.json",
                        packet,
                    )
                    write_modeling_handback(
                        packet,
                        args.output_dir
                        / "canapp-lesson-modeling-prompt.md",
                        args.output_dir / "Human_ToDo.md",
                    )
                print(
                    "Wrote the private, source-bound CanApp Lesson "
                    "Modeler packet and handback."
                )
                return finish(0)
            if args.lesson_model_action == "validate":
                with event_log.step("validate_lesson_model_artifacts"):
                    artifacts = [
                        read_lesson_artifact(path)
                        for path in args.artifact
                    ]
                receipt = {
                    "artifact_type": (
                        "respect_canapp_lesson_model_validation_receipt"
                    ),
                    "format_version": "1.0.0",
                    "artifacts": [
                        {
                            "artifact_type": item["artifact_type"],
                            "semantic_hash": item["semantic_hash"],
                        }
                        for item in artifacts
                    ],
                    "valid": True,
                }
                with event_log.step("write_lesson_validation_receipt"):
                    _write(
                        args.output_dir
                        / "canapp-lesson-model-validation.json",
                        receipt,
                    )
                print(f"Validated {len(artifacts)} lesson-model artifacts.")
                return finish(0)
            if args.lesson_model_action == "compile":
                with event_log.step("read_lesson_model_inputs"):
                    inventory = read_lesson_artifact(
                        args.inventory, "inventory"
                    )
                    model = read_lesson_artifact(args.model, "model")
                    selection = read_lesson_artifact(
                        args.selection, "selection"
                    )
                with event_log.step("compile_lesson_run_plan"):
                    run_plan = compile_run_plan(
                        inventory,
                        model,
                        selection,
                        testkit_commit=args.testkit_commit,
                        target_id=args.target_id,
                        target_digest=args.target_digest,
                        profile_id=args.profile,
                        available_capabilities=set(
                            args.available_capability
                            or SCENARIO_ACTION_TYPES
                        ),
                        event=event_log.emit,
                    )
                with event_log.step("write_lesson_run_plan"):
                    write_lesson_artifact(
                        args.output_dir / "canapp-lesson-run-plan.json",
                        run_plan,
                    )
                    gap_artifact = {
                        "artifact_type": (
                            "respect_canapp_lesson_capability_gaps"
                        ),
                        "format_version": "1.0.0",
                        "run_plan_semantic_hash": (
                            run_plan["semantic_hash"]
                        ),
                        "gaps": run_plan["capability_gaps"],
                        "authority_notice": (
                            "Generic capability gaps require separate "
                            "TestKit review and do not modify the TestKit."
                        ),
                    }
                    gap_artifact["semantic_hash"] = canonical_hash(
                        gap_artifact
                    )
                    write_lesson_artifact(
                        args.output_dir
                        / "canapp-lesson-capability-gaps.json",
                        gap_artifact,
                    )
                    for index, entry in enumerate(run_plan["entries"]):
                        if entry["status"] != "compiled":
                            continue
                        digest = hashlib.sha256(
                            entry["lesson_id"].encode("utf-8")
                        ).hexdigest()[:16]
                        _write(
                            args.output_dir
                            / "compiled-scenarios"
                            / f"{index:06d}-{digest}.json",
                            entry["scenario"],
                        )
                blocked = sum(
                    entry["status"] != "compiled"
                    for entry in run_plan["entries"]
                )
                print(
                    f"Compiled {len(run_plan['entries']) - blocked} "
                    f"of {len(run_plan['entries'])} selected lessons."
                )
                return finish(0 if blocked == 0 else 2)
            if args.lesson_model_action == "execute":
                with event_log.step("read_lesson_run_plan"):
                    run_plan = read_lesson_artifact(
                        args.run_plan, "run_plan"
                    )
                if (
                    not args.apk
                    or not args.device_id
                    or not args.runtime_driver_apk
                    or not args.runtime_driver_receipt
                ):
                    raise ValueError(
                        "lesson execution requires --apk, --device-id, "
                        "--runtime-driver-apk, and "
                        "--runtime-driver-receipt"
                    )
                if args.runtime_scenario:
                    raise ValueError(
                        "--runtime-scenario is generated by the lesson "
                        "run plan and must not be supplied"
                    )

                def child_runner(entry, child_dir, child_event):
                    scenario_path = child_dir / "runtime-scenario.json"
                    _write(scenario_path, entry["scenario"])
                    suite_args = _suite_target_args(args)
                    suite_args.extend(
                        [
                            "--runtime-scenario",
                            str(scenario_path),
                            "--profile",
                            run_plan["profile_id"],
                            "--mode",
                            "certification",
                            "--output-dir",
                            str(child_dir),
                        ]
                    )
                    exit_code = suite_main(suite_args)
                    report_path = child_dir / "respect-report.json"
                    if not report_path.is_file():
                        raise ValueError(
                            "child TestKit did not write its report"
                        )
                    report = _read(report_path)
                    outcome = _lesson_child_outcome(report, exit_code)
                    child_event(
                        "child_testkit_report",
                        "observed",
                        {
                            "report_core_hash": report.get("core_hash"),
                            "exit_code": exit_code,
                            "outcome": outcome,
                        },
                    )
                    return {
                        "lesson_id": entry["lesson_id"],
                        "scenario_sha256": entry["scenario_sha256"],
                        "exit_code": exit_code,
                        "outcome": outcome,
                    }

                with event_log.step("execute_lesson_batch"):
                    batch = run_lesson_batch(
                        run_plan,
                        args.output_dir,
                        child_runner,
                        resume=args.resume,
                        event=event_log.emit,
                    )
                print(
                    f"Indexed {len(batch['children'])} per-lesson TestKit "
                    "runs; the batch index is non-authoritative."
                )
                return finish(batch["exit_code"])
            if args.lesson_model_action == "status":
                with event_log.step("read_lesson_status_inputs"):
                    inventory = read_lesson_artifact(
                        args.inventory, "inventory"
                    )
                    model = read_lesson_artifact(args.model, "model")
                    selection = read_lesson_artifact(
                        args.selection, "selection"
                    )
                    run_plan = read_lesson_artifact(
                        args.run_plan, "run_plan"
                    )
                outcomes = {}
                if args.batch_index:
                    batch = _read(args.batch_index)
                    if (
                        batch.get("run_plan_semantic_hash")
                        != run_plan["semantic_hash"]
                    ):
                        raise ValueError(
                            "batch index does not match the lesson run plan"
                        )
                    outcomes = {
                        child["lesson_id"]: child["outcome"]
                        for child in batch["children"]
                    }
                with event_log.step("build_lesson_coverage"):
                    coverage = build_coverage(
                        inventory,
                        model,
                        selection,
                        run_plan,
                        outcomes,
                    )
                with event_log.step("write_lesson_coverage"):
                    write_lesson_artifact(
                        args.output_dir / "canapp-lesson-coverage.json",
                        coverage,
                    )
                print(json.dumps(coverage["counts"], sort_keys=True))
                return finish(0)
        if args.command == "publication-pack":
            with event_log.step("read_publication_manifest"):
                manifest = _read(args.manifest)
            signing_fingerprint = args.signing_fingerprint
            apk_binding = None
            if args.provision == "production" and not args.apk:
                raise ValueError(
                    "production publication requires a submitted APK"
                )
            if args.apk:
                with event_log.step("inspect_apk"):
                    inspection = inspect_apk(args.apk)
                expected_package = manifest.get("canapp", {}).get(
                    "application_id"
                )
                if inspection.get("package_id") != expected_package:
                    raise ValueError(
                        "APK package identifier does not match the "
                        "publication manifest"
                    )
                signer = inspection.get("signer_sha256")
                if not isinstance(signer, str):
                    raise ValueError(
                        "APK signing certificate could not be determined"
                    )
                signing_fingerprint = ":".join(
                    signer[index : index + 2]
                    for index in range(0, len(signer), 2)
                )
                apk_binding = {
                    "package_id": str(inspection.get("package_id")),
                    "signer_sha256": signer.upper(),
                    "apk_sha256": hashlib.sha256(
                        args.apk.read_bytes()
                    ).hexdigest(),
                }
            with event_log.step("build_publication_pack"):
                receipt = build_publication_pack(
                    manifest,
                    args.source_root,
                    args.origin,
                    signing_fingerprint,
                    args.output,
                    provision=args.provision,
                    signer_kind=args.signer_kind,
                    apk_binding=apk_binding,
                    certified_artifact=args.apk,
                    publication_authorization_token=(
                        args.publication_authorization_token
                    ),
                )
            print(
                f"Wrote a {receipt['provision']} RESPECT Publication Pack "
                f"for {receipt['lesson_count']} real lessons."
            )
            return finish(0)
        if args.command == "publication-manifest":
            with event_log.step("read_publication_inputs"):
                adapter = _read(args.repair_adapter)
                confirmed_inventory = _read(args.lesson_inventory)
            with event_log.step("build_publication_manifest"):
                manifest = build_publication_manifest_from_adapter(
                    adapter,
                    args.source_root,
                    canapp_identifier=args.canapp_identifier,
                    canapp_title=args.canapp_title,
                    application_id=args.application_id,
                    public_path=args.public_path,
                    launch_path_prefix=args.launch_path_prefix,
                    lesson_identifier_root=args.lesson_identifier_root,
                    lesson_media_type=args.lesson_media_type,
                    confirmed_inventory=confirmed_inventory,
                    language=args.language,
                )
            with event_log.step("write_publication_manifest"):
                _write(args.output, manifest)
            print(
                f"Wrote a truthful publication manifest for "
                f"{len(manifest['lessons'])} source-derived lessons."
            )
            return finish(0)
        if args.command == "publication-verify":
            with event_log.step("verify_publication_pack"):
                errors = verify_publication_pack(args.pack)
                deployment = _read(args.pack / "deployment.json")
            if (
                deployment.get("provision") == "production"
                and not args.deployed_origin
            ):
                errors.append(
                    "PRODUCTION_DEPLOYMENT_NOT_VERIFIED: "
                    "production verification requires --deployed-origin"
                )
            if args.deployed_origin:
                with event_log.step("verify_deployed_publication"):
                    errors.extend(
                        verify_deployed_publication(
                            args.pack,
                            deployed_origin=args.deployed_origin,
                            ca_cert=args.ca_cert,
                        )
                    )
            elif args.ca_cert:
                raise ValueError(
                    "--ca-cert requires --deployed-origin"
                )
            errors = sorted(set(errors))
            with event_log.step("write_verification_receipt"):
                receipt = build_verification_receipt(
                    args.pack,
                    errors,
                    deployed_origin=args.deployed_origin,
                )
                _write(args.receipt_output, receipt)
            print(
                "Publication Pack valid."
                if not errors
                else f"Publication Pack invalid: {errors}"
            )
            return finish(0 if not errors else 2)
        if args.command == "publication-serve":
            with event_log.step(
                "serve_publication_pack",
                {"bind": args.bind, "port": args.port},
            ):
                serve_publication_pack(
                    args.pack,
                    bind=args.bind,
                    port=args.port,
                    certfile=args.certfile,
                    keyfile=args.keyfile,
                )
            return finish(0)
        if args.command == "publication-authorization":
            with event_log.step("inspect_publication_artifact"):
                artifact = args.artifact.resolve(strict=True)
            if not artifact.is_file():
                raise ValueError("--artifact must name a file")
            with event_log.step("publication_authorization"):
                state = ensure_publication_authorization(
                    args.state,
                    args.token_output,
                    {
                        "publisher_id": args.publisher_id,
                        "agreement_version": args.agreement_version,
                        "app_id": args.app_id,
                        "artifact_sha256": hashlib.sha256(
                            artifact.read_bytes()
                        ).hexdigest(),
                        "immutable_artifact_url": (
                            args.immutable_artifact_url
                        ),
                    },
                    SpixPublicationClient(args.spix_service_url),
                    open_signing=args.open_signing,
                    replace_terminal_request=args.replace_terminal_request,
                )
            print(
                "Publication authorization: "
                f"{state['status']} "
                f"(envelope {state.get('docusign_envelope_id') or 'pending'})."
            )
            return finish(0 if state["status"] == "authorized" else 2)
        if args.command == "status":
            with event_log.step("read_work_status"):
                plan = _read(args.work_plan)
            if plan.get("semantic_hash") != canonical_hash(
                plan, ("semantic_hash",)
            ):
                raise ValueError("work plan semantic hash mismatch")
            print(json.dumps(read_ledger(args.ledger, plan), indent=2, sort_keys=True))
            return finish(0)
        if args.command == "record":
            with event_log.step("append_repair_ledger_event"):
                plan = _read(args.work_plan)
                event = append_event(
                    args.ledger,
                    plan,
                    args.task_id,
                    args.state,
                    args.note,
                    args.verifier_result_ref,
                )
            print(event["event_id"])
            return finish(0)
        if args.command == "verify":
            with event_log.step("read_verification_task"):
                plan = _read(args.work_plan)
            if plan.get("semantic_hash") != canonical_hash(
                plan, ("semantic_hash",)
            ):
                raise ValueError("work plan semantic hash mismatch")
            task = next(
                (
                    item
                    for item in plan["tasks"]
                    if item["task_id"] == args.task_id
                ),
                None,
            )
            if task is None:
                raise ValueError(f"unknown work-plan task: {args.task_id}")
            with event_log.step("load_target"):
                target = _load_target(
                    args,
                    execution_event=event_log.emit,
                )
            with event_log.step(
                f"matrix_row:{task['row_id']}",
                {"row_id": task["row_id"]},
            ):
                result = run_narrow_verifier(
                    task["normative_task"]["narrow_verifier_id"],
                    task["row_id"],
                    target,
                    plan["profile_id"],
                    predecessor_target_digest=plan["target_digest"],
                )
            with event_log.step("write_verifier_result"):
                _write(args.output, result)
            print(f"{result['row_id']}: {result['state']} (non-certifying)")
            return finish(0 if result["state"] == "pass" else 2)
        if args.command == "full-test":
            event_log.emit("test_suite", "started")
            suite_args = _suite_target_args(args)
            suite_args.extend(
                [
                    "--profile",
                    args.profile,
                    "--mode",
                    "certification",
                    "--output-dir",
                    str(args.output_dir),
                ]
            )
            exit_code = suite_main(suite_args, execution_log=event_log)
            event_log.emit(
                "test_suite",
                "completed",
                {"exit_code": exit_code},
            )
            return finish(exit_code)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as error:
        event_log.emit(
            "command",
            "failed",
            {"error_type": type(error).__name__, "error": str(error)},
        )
        event_log.finish(64)
        parser.error(str(error))
    return finish(64)


if __name__ == "__main__":
    raise SystemExit(main())
