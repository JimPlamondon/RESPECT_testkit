# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from respect_compat.cli import main as suite_main
from respect_compat.android_apk import probe_android_device
from respect_compat.handoff import canonical_hash
from respect_compat.target import (
    CanAppTarget,
    load_fixture_target,
    load_server_target,
    load_url_target,
)

from .ledger import append_event, read_ledger
from .planner import build_work_plan, validate_work_plan
from .prep import generate_prep, write_prep
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


def _add_target(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture-dir", type=Path)
    group.add_argument("--manifest-url")
    group.add_argument("--server-base-url")
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--device-id")


def _load_target(args: argparse.Namespace) -> CanAppTarget:
    if args.fixture_dir:
        target = load_fixture_target(args.fixture_dir, apk=args.apk)
    elif args.manifest_url:
        target = load_url_target(args.manifest_url, apk=args.apk)
    else:
        target = load_server_target(args.server_base_url, apk=args.apk)
    if args.device_id:
        probe = probe_android_device(args.device_id)
        target.metadata["device_id"] = args.device_id
        target.metadata["device_probe"] = probe
        if probe["healthy"]:
            target.capabilities.add("android_device")
    return target


def _suite_target_args(args: argparse.Namespace) -> List[str]:
    if args.fixture_dir:
        values = ["--fixture-dir", str(args.fixture_dir)]
    elif args.manifest_url:
        values = ["--manifest-url", args.manifest_url]
    else:
        values = ["--server-base-url", args.server_base_url]
    if args.apk:
        values.extend(["--apk", str(args.apk)])
    if args.device_id:
        values.extend(["--device-id", args.device_id])
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
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            public, private = generate_prep(
                args.source_root,
                args.target_digest,
                args.profile,
                include_private=args.private_output is not None,
            )
            write_prep(
                public, args.public_output, private, args.private_output
            )
            print(
                f"Prepared public packet"
                f"{' and owner-local private packet' if private else ''}."
            )
            return 0
        if args.command == "plan":
            report = _read(args.report)
            evidence = _read(args.evidence_manifest)
            tasks = _read(args.task_packet)
            private = _read(args.private_prep) if args.private_prep else None
            work_plan = build_work_plan(report, evidence, tasks, private)
            errors = validate_work_plan(work_plan, tasks)
            if errors:
                raise ValueError(f"invalid generated work plan: {errors}")
            _write(args.output, work_plan)
            print(f"Planned {len(work_plan['tasks'])} actionable repair tasks.")
            return 0
        if args.command == "status":
            plan = _read(args.work_plan)
            if plan.get("semantic_hash") != canonical_hash(
                plan, ("semantic_hash",)
            ):
                raise ValueError("work plan semantic hash mismatch")
            print(json.dumps(read_ledger(args.ledger, plan), indent=2, sort_keys=True))
            return 0
        if args.command == "record":
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
            return 0
        if args.command == "verify":
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
            target = _load_target(args)
            result = run_narrow_verifier(
                task["normative_task"]["narrow_verifier_id"],
                task["row_id"],
                target,
                plan["profile_id"],
                predecessor_target_digest=plan["target_digest"],
            )
            _write(args.output, result)
            print(f"{result['row_id']}: {result['state']} (non-certifying)")
            return 0 if result["state"] == "pass" else 2
        if args.command == "full-test":
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
            return suite_main(suite_args)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as error:
        parser.error(str(error))
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
