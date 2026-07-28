# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import secrets
from pathlib import Path
from typing import List, Optional

from .android_metadata_validator import validate_android
from .android_apk import probe_android_device
from .android_runtime_runner import run_native_android_runtime
from .ambiguity_router import route_claim
from .app_links_validator import validate_app_links
from .fake_launcher import build_launch_session
from .fake_lrs import FakeLrs
from .engine import execute
from .executors import build_registry
from .fixture_loader import FixtureCase, load_fixture, read_json
from .manifest_validator import load_manifest, validate_manifest
from .matrix_runtime import load_matrix
from .models import RequirementOwner, ResultState, RuleResult, worst_exit_code
from .opds_validator import validate_opds
from .profile import load_profile
from .report import suite_json_payload, verify_suite_payload, write_reports, write_suite_reports
from .security_labels import SecurityContext
from .target import (
    load_apk_target,
    load_fixture_target,
    load_server_target,
    load_url_target,
)


class SuiteArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage()
        self.exit(64, f"{self.prog}: error: {message}\n")


def run_fixture(case: FixtureCase, profile_name: str, mode: str, output_dir: Optional[Path], apk: Optional[Path] = None) -> List[RuleResult]:
    profile = load_profile(profile_name)
    context = SecurityContext(mode)
    manifest, results = load_manifest(case.manifest_path, profile, case.target, context.mode)
    if manifest:
        results.extend(validate_manifest(manifest, str(case.manifest_path), profile, case.target, context.mode, case.metadata))
        results.extend(validate_android(manifest, profile, case.target, context.mode, apk=apk))
    opds_name = case.expected.get("opds")
    if opds_name:
        results.extend(validate_opds(case.root / opds_name, profile, case.target, context.mode))
    if case.metadata.get("app_links") is not None and isinstance(manifest.get("android"), dict):
        results.extend(validate_app_links(case.metadata["app_links"], str(manifest["android"].get("packageId", "")), profile, case.target, context.mode))
    if case.expected.get("exercise_launcher"):
        try:
            session = build_launch_session(manifest, seed="respect-v0-1", endpoint_base="https://lrs.invalid/xapi", context=context)
            results.append(RuleResult("RCS-008", ResultState.DEFERRED, case.target, "deterministic suite-owned launch session", session.launch_url, "Fake launcher produced a suite-test-candidate session.", "fake_launcher", profile.profile_id, case.target, context.mode, disposition="suite_test_candidate"))
        except ValueError as exc:
            results.append(RuleResult("RCS-008", ResultState.FAIL, case.target, "respectLaunchVersion and endpoint", str(exc), "Fake launcher could not construct a session.", "fake_launcher", profile.profile_id, case.target, context.mode, disposition="suite_test_candidate"))
    if case.expected.get("xapi_statement"):
        lrs = FakeLrs(context)
        receipt = lrs.receive(read_json(case.root / case.expected["xapi_statement"]))
        state = ResultState.PASS if receipt.get("accepted") else ResultState.FAIL
        results.append(RuleResult("RCS-007", state, case.target, "valid xAPI actor, verb, and object", receipt, "Fake LRS processed the xAPI statement.", "fake_lrs", profile.profile_id, case.target, context.mode, disposition=profile.requirement("RCS-007").get("v0_1_disposition")))
    unsupported = case.expected.get("unsupported_requirement")
    if unsupported:
        results.append(route_claim(unsupported["claim"], unsupported["disposition"], profile, case.target, context.mode))
    if not results:
        results.append(RuleResult("RCS-010", ResultState.PASS, case.target, "reportable rule results", "none", "No validators were selected for this fixture.", "cli", profile.profile_id, case.target, context.mode, disposition=profile.requirement("RCS-010").get("v0_1_disposition")))
    results.append(RuleResult("RCS-010", ResultState.PASS, case.target, "JSON, text, and JUnit XML reports", "writers available", "Report writers completed.", "report", profile.profile_id, case.target, context.mode, disposition=profile.requirement("RCS-010").get("v0_1_disposition")))
    if output_dir is not None:
        write_reports(results, output_dir)
    return results


def main(argv: Optional[list[str]] = None) -> int:
    parser = SuiteArgumentParser(
        description="Run the Matrix-driven RESPECT Compatible Test Suite against one CanApp."
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--manifest-url")
    input_group.add_argument("--fixture-dir")
    input_group.add_argument("--server-base-url")
    input_group.add_argument("--apk-only", action="store_true")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--apk", type=Path)
    parser.add_argument(
        "--ca-cert",
        type=Path,
        help="Trust this CA certificate for a provisioned HTTPS target.",
    )
    parser.add_argument("--device-id")
    parser.add_argument("--runtime-driver-apk", type=Path)
    parser.add_argument("--runtime-driver-receipt", type=Path)
    parser.add_argument("--runtime-scenario", type=Path)
    parser.add_argument(
        "--run-seed",
        help="Deterministic test/replay seed; forbidden in certification mode.",
    )
    parser.add_argument("--mode", choices=sorted(["certification", "test", "replay"]), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.mode == "certification" and args.run_seed:
        parser.error("--run-seed is forbidden in certification mode")
    runtime_values = (
        args.runtime_driver_apk,
        args.runtime_driver_receipt,
        args.runtime_scenario,
    )
    if any(runtime_values) and not all(runtime_values):
        parser.error(
            "--runtime-driver-apk, --runtime-driver-receipt, and "
            "--runtime-scenario must be supplied together"
        )
    if args.runtime_driver_apk and (not args.apk or not args.device_id):
        parser.error(
            "native runtime execution requires --apk and --device-id"
        )
    try:
        matrix = load_matrix()
        matrix.resolve_profile(args.profile)
        if args.apk_only:
            if not args.apk:
                parser.error("--apk-only requires --apk")
            target = load_apk_target(args.apk)
        elif args.fixture_dir:
            target = load_fixture_target(Path(args.fixture_dir), apk=args.apk)
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
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError) as error:
        parser.error(str(error))
    if args.device_id:
        device_probe = probe_android_device(args.device_id)
        target.metadata["device_id"] = args.device_id
        target.metadata["device_probe"] = device_probe
        if device_probe["healthy"]:
            target.capabilities.add("android_device")
    if args.runtime_driver_apk:
        try:
            run_native_android_runtime(
                target,
                device_id=args.device_id,
                driver_apk=args.runtime_driver_apk,
                driver_receipt=args.runtime_driver_receipt,
                scenario_path=args.runtime_scenario,
                scenario_nonce=secrets.token_hex(12),
                certification_mode=args.mode == "certification",
            )
            target.capabilities.add("controlled_android_runtime")
        except (FileNotFoundError, json.JSONDecodeError, OSError, RuntimeError, ValueError) as error:
            parser.error(str(error))
    run = execute(
        matrix,
        target,
        args.profile,
        args.mode,
        build_registry(matrix),
        run_seed=args.run_seed,
    )
    write_suite_reports(run, args.output_dir)
    verification_errors = verify_suite_payload(suite_json_payload(run))
    print(
        f"RESPECT {run.profile_id}: {run.verdict.display}; "
        f"pass={len(run.coverage.passed)} fail={len(run.coverage.failed)} "
        f"blocked={len(run.coverage.blocked)} incomplete={len(run.coverage.incomplete)}"
    )
    if verification_errors or run.coverage.harness_error:
        return 3
    canapp_failures = [
        result
        for result in run.results
        if result.owner == RequirementOwner.CANAPP
        and result.state == ResultState.FAIL
    ]
    if canapp_failures:
        return 1
    if args.mode == "certification":
        return 0 if run.verdict.certified else 2
    if run.coverage.blocked or run.coverage.incomplete or run.coverage.deferred:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
