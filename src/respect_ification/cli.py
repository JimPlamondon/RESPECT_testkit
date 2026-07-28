# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import argparse
import hashlib
import json
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from respect_compat.cli import main as suite_main
from respect_compat.android_apk import inspect_apk, probe_android_device
from respect_compat.android_runtime_runner import run_native_android_runtime
from respect_compat.handoff import canonical_hash
from respect_compat.matrix_runtime import load_matrix
from respect_compat.target import (
    CanAppTarget,
    load_fixture_target,
    load_server_target,
    load_url_target,
)

from .ledger import append_event, read_ledger
from .planner import build_work_plan, validate_work_plan
from .prep import generate_prep, write_prep
from .publication_pack import (
    build_publication_manifest_from_adapter,
    build_publication_pack,
    build_verification_receipt,
    verify_deployed_publication,
    verify_publication_pack,
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


def _add_target(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fixture-dir", type=Path)
    group.add_argument("--manifest-url")
    group.add_argument("--server-base-url")
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--device-id")
    parser.add_argument("--runtime-driver-apk", type=Path)
    parser.add_argument("--runtime-driver-receipt", type=Path)
    parser.add_argument("--runtime-scenario", type=Path)


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
            scenario_path=args.runtime_scenario,
            scenario_nonce=secrets.token_hex(12),
        )
        target.capabilities.add("controlled_android_runtime")
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
    if args.runtime_driver_apk:
        values.extend(["--runtime-driver-apk", str(args.runtime_driver_apk)])
    if args.runtime_driver_receipt:
        values.extend(
            ["--runtime-driver-receipt", str(args.runtime_driver_receipt)]
        )
    if args.runtime_scenario:
        values.extend(["--runtime-scenario", str(args.runtime_scenario)])
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

    truth_audit = subparsers.add_parser("truth-audit")
    truth_audit.add_argument("--output", type=Path, required=True)

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
        if args.command == "repair-plan":
            plan = _read(args.work_plan)
            write_repair_adapter(
                plan,
                args.source_root,
                args.adapter_output,
                args.prompt_output,
                testkit_commit=args.testkit_commit,
                canapp_root=args.canapp_root,
            )
            print(
                "Wrote the Kit-time repair adapter and source-derived "
                "implementation prompt."
            )
            return 0
        if args.command == "truth-audit":
            audit = build_matrix_truth_audit(load_matrix())
            audit["semantic_hash"] = canonical_hash(
                audit,
                ("semantic_hash",),
            )
            _write(args.output, audit)
            print(
                "Audited "
                f"{audit['summary']['row_count']} Matrix rows: "
                f"{audit['summary']['canapp_repair_row_count']} require "
                "durable CanApp repair and "
                f"{audit['summary']['protected_non_canapp_row_count']} "
                "retain their non-CanApp owner."
            )
            return 0
        if args.command == "publication-pack":
            manifest = _read(args.manifest)
            signing_fingerprint = args.signing_fingerprint
            apk_binding = None
            if args.provision == "production" and not args.apk:
                raise ValueError(
                    "production publication requires a submitted APK"
                )
            if args.apk:
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
            receipt = build_publication_pack(
                manifest,
                args.source_root,
                args.origin,
                signing_fingerprint,
                args.output,
                provision=args.provision,
                signer_kind=args.signer_kind,
                apk_binding=apk_binding,
            )
            print(
                f"Wrote a {receipt['provision']} RESPECT Publication Pack "
                f"for {receipt['lesson_count']} real lessons."
            )
            return 0
        if args.command == "publication-manifest":
            adapter = _read(args.repair_adapter)
            confirmed_inventory = _read(args.lesson_inventory)
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
            _write(args.output, manifest)
            print(
                f"Wrote a truthful publication manifest for "
                f"{len(manifest['lessons'])} source-derived lessons."
            )
            return 0
        if args.command == "publication-verify":
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
            return 0 if not errors else 2
        if args.command == "publication-serve":
            serve_publication_pack(
                args.pack,
                bind=args.bind,
                port=args.port,
                certfile=args.certfile,
                keyfile=args.keyfile,
            )
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
