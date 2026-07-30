# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Build and operate a local RESPECT school compatibility lab."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from .android_apk import inspect_apk, probe_android_device
from .respect_platform_emulator import (
    PLATFORM_ROW_IDS,
    evaluate_platform_observation,
)
from .respect_platform_receipt import build_receipt


SCHOOL_ROW_ORDER = (
    "AUTH-002",
    "LAUNCH-001",
    "LAUNCH-002",
    "OFFLINE-001",
    "OFFLINE-002",
    "REG-001",
    "REG-004",
    "REG-002",
    "REG-003",
    "REG-005",
    "XAPI-012",
    "XAPI-020",
    "LAUNCH-009",
)
API29_ROWS = ("LAUNCH-009",)
API30_PLUS_ROWS = tuple(
    row_id for row_id in SCHOOL_ROW_ORDER if row_id not in API29_ROWS
)
EVIDENCE_FILES = (
    "run-manifest.json",
    "source-revisions.json",
    "artifact-receipts.json",
    "scenario.json",
    "seed-manifest.json",
    "raw-provider-observations.json",
    "row-results.json",
    "database-exports.json",
    "service-config.json",
    "http-log.jsonl",
    "ui-hierarchies/",
    "activity-state/",
    "logcat/",
    "commands.jsonl",
    "timestamps.json",
)
SET_FIELDS = {
    "LAUNCH-009": ("resolved_packages",),
    "OFFLINE-001": ("declared_urls", "requested_urls"),
    "REG-001": (
        "listed_object_urls",
        "displayed_urls",
        "statement_ids",
    ),
    "REG-002": (
        "active_statement_ids",
        "displayed_statement_ids",
    ),
    "REG-003": ("active_urls_after",),
    "REG-004": ("listing_statement_ids",),
    "XAPI-012": ("stored_grouping_ids",),
    "XAPI-020": (
        "submitted_statement_ids",
        "returned_statement_ids",
    ),
}
DEFAULT_RESPECT_PACKAGE = "world.respect.app"
DEFAULT_CANAPP_PACKAGE = "org.jims.mobilekb"
DEFAULT_RESPECT_ACTIVITY = "world.respect.MainActivity"
DEFAULT_WEBVIEW_ACTIVITY = "world.respect.WebViewActivity"
DEFAULT_API29_AVD = "RESPECT_API_29_ARM64"
DEFAULT_API30_PLUS_AVD = "JiMS_API_36_1_ARM64_Clean"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, value: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == rendered:
        return
    path.write_text(rendered, encoding="utf-8")
    if private:
        path.chmod(0o600)


def _read_object(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _git_revision(source: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    revision = completed.stdout.strip()
    if completed.returncode or not revision:
        raise ValueError(f"could not determine source revision: {source}")
    return revision


def _git_status(source: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode:
        raise ValueError(f"could not determine source status: {source}")
    return completed.stdout


def _respect_gradle_command(
    respect_source: Path,
    ca_certificate: Path,
) -> List[str]:
    return [
        str(respect_source / "gradlew"),
        ":respect-server:shadowJar",
        ":app-android:assembleDebug",
        f"-PrespectTestkitCa={ca_certificate}",
        "--no-daemon",
        "--console=plain",
    ]


class RunState:
    """Small idempotent state authority for one ephemeral lab run."""

    def __init__(self, path: Path, run_id: Optional[str] = None):
        self.path = path
        if path.is_file():
            self.value = _read_object(path)
            existing = self.value.get("run_id")
            if run_id and existing and existing != run_id:
                raise ValueError(
                    "state run ID does not match requested run ID"
                )
        else:
            self.value = {
                "artifact_type": "respect_school_harness_state",
                "format_version": "1.0.0",
                "run_id": run_id,
                "operations": {},
            }
        if run_id and not self.value.get("run_id"):
            self.value["run_id"] = run_id

    def completed(self, operation: str) -> bool:
        return (
            self.value.get("operations", {})
            .get(operation, {})
            .get("status")
            == "complete"
        )

    def operation(self, operation: str) -> Dict[str, Any]:
        value = self.value.get("operations", {}).get(operation, {})
        return value if isinstance(value, dict) else {}

    def mark_complete(
        self,
        operation: str,
        result: Mapping[str, Any],
    ) -> None:
        operations = self.value.setdefault("operations", {})
        record = {"status": "complete", "result": dict(result)}
        if operations.get(operation) == record:
            return
        operations[operation] = record
        _write_json(self.path, self.value, private=True)

    def update_runtime(self, values: Mapping[str, Any]) -> None:
        runtime = self.value.setdefault("runtime", {})
        changed = False
        for key, value in values.items():
            if runtime.get(key) != value:
                runtime[key] = value
                changed = True
        if changed:
            _write_json(self.path, self.value, private=True)


class CommandRecorder:
    """Run commands while preserving exact, attributable receipts."""

    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self.path = evidence_dir / "commands.jsonl"
        self.last_command_id: Optional[str] = None
        evidence_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: int = 900,
        check: bool = True,
        input_text: Optional[str] = None,
        recorded_argv: Optional[Sequence[str]] = None,
    ) -> subprocess.CompletedProcess:
        started = _utc_now()
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            input=input_text,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        self.last_command_id = secrets.token_hex(12)
        record = {
            "command_id": self.last_command_id,
            "argv": list(recorded_argv or argv),
            "cwd": str(cwd.resolve()) if cwd else None,
            "started_at": started,
            "completed_at": _utc_now(),
            "exit_status": completed.returncode,
            "stdout_sha256": hashlib.sha256(
                completed.stdout.encode("utf-8")
            ).hexdigest(),
            "stderr_sha256": hashlib.sha256(
                completed.stderr.encode("utf-8")
            ).hexdigest(),
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        if check and completed.returncode:
            raise RuntimeError(
                f"command failed with exit {completed.returncode}: "
                f"{argv[0]}: {completed.stderr.strip()}"
            )
        return completed

    def start(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[Path] = None,
        env: Optional[Mapping[str, str]] = None,
        stdout_path: Path,
        stderr_path: Path,
    ) -> subprocess.Popen:
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_stream = stdout_path.open("ab")
        stderr_stream = stderr_path.open("ab")
        process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            stdout=stdout_stream,
            stderr=stderr_stream,
            start_new_session=True,
        )
        self.last_command_id = secrets.token_hex(12)
        record = {
            "command_id": self.last_command_id,
            "argv": list(argv),
            "cwd": str(cwd.resolve()) if cwd else None,
            "started_at": _utc_now(),
            "pid": process.pid,
            "status": "started",
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        return process


def validate_observation_sets(
    row_id: str,
    observed: Mapping[str, Any],
) -> None:
    for field in SET_FIELDS.get(row_id, ()):
        value = observed.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip()
            for item in value
        ):
            raise ValueError(
                f"{row_id} observation {field} must contain only "
                "nonempty strings"
            )


def validate_scenario_routing(
    scenario: Mapping[str, Any],
    probes: Mapping[str, Mapping[str, Any]],
) -> None:
    selected_rows = scenario.get("selected_rows")
    row_devices = scenario.get("row_devices")
    if (
        not isinstance(selected_rows, list)
        or set(selected_rows) != PLATFORM_ROW_IDS
        or not isinstance(row_devices, dict)
        or set(row_devices) != PLATFORM_ROW_IDS
    ):
        raise ValueError(
            "scenario must route every RESPECT school harness row"
        )
    for row_id in selected_rows:
        device_id = row_devices[row_id]
        probe = probes.get(device_id)
        if (
            not isinstance(probe, Mapping)
            or probe.get("healthy") is not True
            or probe.get("emulator") is not True
        ):
            raise ValueError(
                f"{row_id} is not routed to a healthy emulator"
            )
        api_level = probe.get("api_level")
        if row_id == "LAUNCH-009" and not (
            isinstance(api_level, int) and 0 < api_level < 30
        ):
            raise ValueError(
                "LAUNCH-009 must be routed to an API-below-30 emulator"
            )
        if row_id == "LAUNCH-001" and not (
            isinstance(api_level, int) and api_level >= 30
        ):
            raise ValueError(
                "LAUNCH-001 must be routed to an API-30-or-newer emulator"
            )


def validate_row_record(
    record: Mapping[str, Any],
    *,
    run_nonce: str,
    expected_device: str,
    expected_package: str,
) -> None:
    row_id = record.get("row_id")
    if row_id not in PLATFORM_ROW_IDS:
        raise ValueError("row record has an unsupported row ID")
    positive = record.get("positive")
    negative = record.get("isolated_negative")
    if not isinstance(positive, Mapping) or not isinstance(
        negative, Mapping
    ):
        raise ValueError(f"{row_id} requires positive and negative cases")
    validate_observation_sets(str(row_id), positive)
    validate_observation_sets(str(row_id), negative)
    if not evaluate_platform_observation(str(row_id), positive)[0]:
        raise ValueError(f"{row_id} positive case failed its Testkit oracle")
    if evaluate_platform_observation(str(row_id), negative)[0]:
        raise ValueError(
            f"{row_id} isolated negative passed its Testkit oracle"
        )
    health = record.get("harness_health")
    if (
        not isinstance(health, Mapping)
        or health.get("before") != "healthy"
        or health.get("after") != "healthy"
    ):
        raise ValueError(f"{row_id} lacks a live harness-health control")
    attribution = record.get("target_attribution")
    if not isinstance(attribution, Mapping) or attribution != {
        "device_id": expected_device,
        "package_id": expected_package,
        "row_id": row_id,
    }:
        raise ValueError(f"{row_id} target attribution does not match")
    anti_replay = record.get("anti_replay")
    if (
        not isinstance(anti_replay, Mapping)
        or anti_replay.get("nonce") != run_nonce
        or not anti_replay.get("capture_sha256")
        or anti_replay.get("capture_sha256")
        == anti_replay.get("prior_capture_sha256")
    ):
        raise ValueError(f"{row_id} anti-replay evidence is invalid")
    if not record.get("regression_lock"):
        raise ValueError(f"{row_id} lacks a regression lock")
    sources = record.get("capture_sources")
    if (
        not isinstance(sources, list)
        or not sources
        or any(
            not isinstance(source, Mapping)
            or source.get("kind") != "production"
            or not source.get("command_id")
            for source in sources
        )
    ):
        raise ValueError(
            f"{row_id} requires attributable production capture sources"
        )


def build_run_manifest(
    *,
    run_id: str,
    nonce: str,
    evidence_dir: Path,
    respect_revision: str,
    mobile_kb_revision: str,
    respect_apk_sha256: str,
    mobile_kb_apk_sha256: str,
    scenario_sha256: str,
    emulator_probes: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        "artifact_type": "respect_school_harness_run_manifest",
        "format_version": "1.0.0",
        "run_id": run_id,
        "nonce": nonce,
        "created_at": _utc_now(),
        "evidence_dir": str(evidence_dir.resolve()),
        "source_revisions": {
            "respect": respect_revision,
            "mobile_kb": mobile_kb_revision,
        },
        "artifact_digests": {
            "respect_apk_sha256": respect_apk_sha256,
            "mobile_kb_apk_sha256": mobile_kb_apk_sha256,
            "scenario_sha256": scenario_sha256,
        },
        "packages": {
            "respect": DEFAULT_RESPECT_PACKAGE,
            "canapp": DEFAULT_CANAPP_PACKAGE,
        },
        "emulators": dict(emulator_probes),
        "rows": list(SCHOOL_ROW_ORDER),
        "evidence_files": list(EVIDENCE_FILES),
    }


def _add_path_argument(
    parser: argparse.ArgumentParser,
    name: str,
    *,
    env_name: Optional[str] = None,
) -> None:
    default = os.environ.get(env_name) if env_name else None
    parser.add_argument(name, type=Path, default=default)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and operate the local two-emulator RESPECT school lab."
        )
    )
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--provision", action="store_true")
    operation.add_argument("--build", action="store_true")
    operation.add_argument("--seed", action="store_true")
    operation.add_argument("--run-row", choices=SCHOOL_ROW_ORDER)
    operation.add_argument("--run-all", action="store_true")
    operation.add_argument("--collect-evidence", action="store_true")
    operation.add_argument("--diagnose", action="store_true")
    operation.add_argument("--stop", action="store_true")
    operation.add_argument(
        "--clean-ephemeral-state",
        action="store_true",
    )
    parser.add_argument("--run-id")
    _add_path_argument(parser, "--state-dir")
    _add_path_argument(parser, "--respect-source")
    _add_path_argument(parser, "--mobile-kb-source")
    _add_path_argument(parser, "--respect-apk")
    _add_path_argument(parser, "--mobile-kb-apk")
    _add_path_argument(parser, "--build-receipt")
    _add_path_argument(parser, "--scenario")
    _add_path_argument(parser, "--evidence-dir")
    _add_path_argument(
        parser,
        "--android-sdk",
        env_name="ANDROID_SDK_ROOT",
    )
    _add_path_argument(parser, "--java-home", env_name="JAVA_HOME")
    parser.add_argument("--api29-serial", default="emulator-5556")
    parser.add_argument(
        "--api30-plus-serial",
        default="emulator-5554",
    )
    parser.add_argument("--api29-avd", default=DEFAULT_API29_AVD)
    parser.add_argument(
        "--api30-plus-avd",
        default=DEFAULT_API30_PLUS_AVD,
    )
    parser.add_argument("--server-port", type=int, default=18098)
    parser.add_argument("--publisher-port", type=int, default=18443)
    parser.add_argument("--respect-package", default=DEFAULT_RESPECT_PACKAGE)
    parser.add_argument("--canapp-package", default=DEFAULT_CANAPP_PACKAGE)
    return parser


class SchoolHarness:
    """Concrete lifecycle implementation for the local school lab."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.run_id = args.run_id or datetime.now(timezone.utc).strftime(
            "respect-school-%Y%m%dT%H%M%SZ"
        )
        if args.state_dir is None:
            raise ValueError("--state-dir is required")
        self.state_dir = args.state_dir.resolve()
        self.evidence_dir = (
            args.evidence_dir.resolve()
            if args.evidence_dir
            else self.state_dir / "evidence"
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.state = RunState(
            self.state_dir / "state.json",
            run_id=self.run_id,
        )
        self.commands = CommandRecorder(self.evidence_dir)
        self.sdk = args.android_sdk.resolve() if args.android_sdk else None
        self.java_home = (
            args.java_home.resolve() if args.java_home else None
        )

    def _require_path(
        self,
        value: Optional[Path],
        flag: str,
        *,
        directory: bool = True,
    ) -> Path:
        if value is None:
            raise ValueError(f"{flag} is required")
        resolved = value.resolve()
        exists = resolved.is_dir() if directory else resolved.is_file()
        if not exists:
            raise ValueError(f"{flag} does not exist: {resolved}")
        return resolved

    def _tool(self, relative: str) -> Path:
        sdk = self._require_path(self.sdk, "--android-sdk")
        tool = sdk / relative
        if not tool.is_file():
            raise ValueError(f"Android tool is missing: {tool}")
        return tool

    def _java_env(self) -> Dict[str, str]:
        java_home = self._require_path(self.java_home, "--java-home")
        environment = os.environ.copy()
        environment.update(
            {
                "JAVA_HOME": str(java_home),
                "ANDROID_HOME": str(
                    self._require_path(self.sdk, "--android-sdk")
                ),
                "ANDROID_SDK_ROOT": str(
                    self._require_path(self.sdk, "--android-sdk")
                ),
            }
        )
        return environment

    def _probe_devices(self) -> Dict[str, Dict[str, Any]]:
        adb = self._tool("platform-tools/adb")
        probes = {
            self.args.api29_serial: probe_android_device(
                self.args.api29_serial,
                adb=adb,
            ),
            self.args.api30_plus_serial: probe_android_device(
                self.args.api30_plus_serial,
                adb=adb,
            ),
        }
        for probe in probes.values():
            api_level = probe.get("api_level")
            if isinstance(api_level, str) and api_level.isdigit():
                probe["api_level"] = int(api_level)
        return probes

    def _wait_for_device(self, serial: str, expected_api: str) -> None:
        adb = self._tool("platform-tools/adb")
        self.commands.run(
            [str(adb), "-s", serial, "wait-for-device"],
            timeout=180,
        )
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            completed = self.commands.run(
                [
                    str(adb),
                    "-s",
                    serial,
                    "shell",
                    "getprop",
                    "sys.boot_completed",
                ],
                check=False,
                timeout=30,
            )
            if completed.stdout.strip() == "1":
                probe = probe_android_device(serial, adb=adb)
                api_level = probe.get("api_level")
                if isinstance(api_level, str) and api_level.isdigit():
                    api_level = int(api_level)
                if expected_api == "api29" and api_level != 29:
                    raise ValueError(
                        f"{serial} must run API 29, found {api_level}"
                    )
                if expected_api == "api30plus" and (
                    not isinstance(api_level, int) or api_level < 30
                ):
                    raise ValueError(
                        f"{serial} must run API 30+, found {api_level}"
                    )
                return
            time.sleep(2)
        raise RuntimeError(f"emulator did not finish booting: {serial}")

    def provision(self) -> Dict[str, Any]:
        probes = self._probe_devices()
        requirements = (
            (
                self.args.api29_serial,
                self.args.api29_avd,
                "api29",
            ),
            (
                self.args.api30_plus_serial,
                self.args.api30_plus_avd,
                "api30plus",
            ),
        )
        emulator = self._tool("emulator/emulator")
        for serial, avd, expected_api in requirements:
            probe = probes[serial]
            healthy = probe.get("healthy") is True
            api_level = probe.get("api_level")
            correct = (
                api_level == 29
                if expected_api == "api29"
                else isinstance(api_level, int) and api_level >= 30
            )
            if healthy and correct:
                continue
            port = serial.rsplit("-", 1)[-1]
            log_root = self.evidence_dir / "emulators"
            process = self.commands.start(
                [
                    str(emulator),
                    "-avd",
                    avd,
                    "-port",
                    port,
                    "-no-snapshot-save",
                    "-no-boot-anim",
                ],
                stdout_path=log_root / f"{serial}.stdout.log",
                stderr_path=log_root / f"{serial}.stderr.log",
            )
            self.state.update_runtime(
                {f"{serial}_emulator_pid": process.pid}
            )
            self._wait_for_device(serial, expected_api)
        probes = self._probe_devices()
        scenario = {
            "selected_rows": list(SCHOOL_ROW_ORDER),
            "row_devices": {
                row_id: (
                    self.args.api29_serial
                    if row_id in API29_ROWS
                    else self.args.api30_plus_serial
                )
                for row_id in SCHOOL_ROW_ORDER
            },
        }
        validate_scenario_routing(scenario, probes)
        result = {"devices": probes}
        self.state.mark_complete("provision", result)
        return result

    def _ensure_tls(self) -> Dict[str, str]:
        tls = self.state_dir / "tls"
        tls.mkdir(parents=True, exist_ok=True)
        ca_key = tls / "ca.key.pem"
        ca_cert = tls / "ca.cert.pem"
        server_key = tls / "localhost.key.pem"
        server_csr = tls / "localhost.csr.pem"
        server_cert = tls / "localhost.cert.pem"
        config = tls / "openssl.cnf"
        if not config.is_file():
            config.write_text(
                "[req]\n"
                "distinguished_name = subject\n"
                "prompt = no\n"
                "[subject]\n"
                "CN = localhost\n"
                "[server_extensions]\n"
                "subjectAltName = @server_names\n"
                "basicConstraints = critical,CA:FALSE\n"
                "keyUsage = critical,digitalSignature,keyEncipherment\n"
                "extendedKeyUsage = serverAuth\n"
                "[server_names]\n"
                "DNS.1 = localhost\n"
                "IP.1 = 127.0.0.1\n",
                encoding="utf-8",
            )
        if not ca_cert.is_file():
            self.commands.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(ca_key),
                    "-out",
                    str(ca_cert),
                    "-days",
                    "30",
                    "-subj",
                    f"/CN=RESPECT-Testkit-{self.run_id}",
                ]
            )
            self.commands.run(
                [
                    "openssl",
                    "req",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-keyout",
                    str(server_key),
                    "-out",
                    str(server_csr),
                    "-config",
                    str(config),
                ]
            )
            self.commands.run(
                [
                    "openssl",
                    "x509",
                    "-req",
                    "-in",
                    str(server_csr),
                    "-CA",
                    str(ca_cert),
                    "-CAkey",
                    str(ca_key),
                    "-CAcreateserial",
                    "-out",
                    str(server_cert),
                    "-days",
                    "30",
                    "-extfile",
                    str(config),
                    "-extensions",
                    "server_extensions",
                ]
            )
            for private_path in (ca_key, server_key):
                private_path.chmod(0o600)
        return {
            "ca_key": str(ca_key),
            "ca_cert": str(ca_cert),
            "server_key": str(server_key),
            "server_cert": str(server_cert),
        }

    def build(self) -> Dict[str, Any]:
        respect_source = self._require_path(
            self.args.respect_source,
            "--respect-source",
        )
        mobile_source = self._require_path(
            self.args.mobile_kb_source,
            "--mobile-kb-source",
        )
        tls = self._ensure_tls()
        mobile_debug_ca = (
            mobile_source
            / "app"
            / "src"
            / "debug"
            / "res"
            / "raw"
            / "respect_testkit_ca.pem"
        )
        mobile_debug_ca.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tls["ca_cert"], mobile_debug_ca)
        publication_origin = (
            f"https://localhost:{self.args.publisher_port}"
        )
        self.commands.run(
            _respect_gradle_command(
                respect_source,
                Path(tls["ca_cert"]),
            ),
            cwd=respect_source,
            env=self._java_env(),
            timeout=3600,
        )
        self.commands.run(
            [
                str(mobile_source / "gradlew"),
                ":app:assembleDebug",
                f"-PrespectPublicationOrigin={publication_origin}",
                "--no-daemon",
                "--console=plain",
            ],
            cwd=mobile_source,
            env=self._java_env(),
            timeout=3600,
        )
        respect_apk_source = (
            respect_source
            / "app-android"
            / "build"
            / "outputs"
            / "apk"
            / "debug"
            / "app-android-debug.apk"
        )
        mobile_apk_source = (
            mobile_source
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "debug"
            / "app-debug.apk"
        )
        server_jar_source = (
            respect_source
            / "respect-server"
            / "build"
            / "libs"
            / "respect-server-all.jar"
        )
        for artifact in (
            respect_apk_source,
            mobile_apk_source,
            server_jar_source,
        ):
            if not artifact.is_file():
                raise ValueError(f"build did not create {artifact}")
        artifacts = self.state_dir / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        respect_apk = artifacts / "respect.apk"
        mobile_apk = artifacts / "mobile-kb.apk"
        server_jar = artifacts / "respect-server.jar"
        shutil.copy2(respect_apk_source, respect_apk)
        shutil.copy2(mobile_apk_source, mobile_apk)
        shutil.copy2(server_jar_source, server_jar)
        receipt = build_receipt(
            respect_apk,
            respect_revision=_git_revision(respect_source),
            apkanalyzer=self._tool(
                "cmdline-tools/latest/bin/apkanalyzer"
            ),
            java_home=self._require_path(
                self.java_home,
                "--java-home",
            ),
        )
        receipt_path = artifacts / "respect-build-receipt.json"
        _write_json(receipt_path, receipt)
        result = {
            "respect_apk": str(respect_apk),
            "mobile_kb_apk": str(mobile_apk),
            "server_jar": str(server_jar),
            "build_receipt": str(receipt_path),
            "respect_revision": _git_revision(respect_source),
            "respect_source_clean": not bool(
                _git_status(respect_source).strip()
            ),
            "mobile_kb_revision": _git_revision(mobile_source),
            "mobile_kb_source_status_sha256": hashlib.sha256(
                _git_status(mobile_source).encode("utf-8")
            ).hexdigest(),
            "respect_apk_sha256": _sha256(respect_apk),
            "mobile_kb_apk_sha256": _sha256(mobile_apk),
            "server_jar_sha256": _sha256(server_jar),
            "publication_origin": publication_origin,
            "tls": tls,
        }
        previous_build = self.state.operation("build").get("result", {})
        if isinstance(previous_build, Mapping) and any(
            previous_build.get(key) != result.get(key)
            for key in (
                "respect_apk_sha256",
                "mobile_kb_apk_sha256",
                "server_jar_sha256",
            )
        ):
            self.state.value.get("operations", {}).pop("seed", None)
        self.state.mark_complete("build", result)
        public_result = {
            key: value
            for key, value in result.items()
            if key != "tls"
        }
        public_result["ca_certificate_sha256"] = _sha256(
            Path(tls["ca_cert"])
        )
        public_result["respect_build_receipt"] = receipt
        _write_json(
            self.evidence_dir / "artifact-receipts.json",
            public_result,
        )
        return result

    def _artifact_path(
        self,
        explicit: Optional[Path],
        state_key: str,
        flag: str,
    ) -> Path:
        if explicit:
            return self._require_path(
                explicit,
                flag,
                directory=False,
            )
        value = self.state.operation("build").get("result", {}).get(
            state_key
        )
        if not isinstance(value, str):
            raise ValueError(f"{flag} is required or --build must run first")
        return self._require_path(Path(value), flag, directory=False)

    def _wait_port(self, port: int, timeout: int = 120) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with socket.socket() as connection:
                connection.settimeout(1)
                if connection.connect_ex(("127.0.0.1", port)) == 0:
                    return
            time.sleep(1)
        raise RuntimeError(f"local service did not listen on port {port}")

    def _http_json(
        self,
        url: str,
        *,
        method: str = "GET",
        body: Optional[Any] = None,
        headers: Optional[Mapping[str, str]] = None,
        context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        data = (
            json.dumps(body).encode("utf-8")
            if body is not None
            else None
        )
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=dict(headers or {}),
        )
        started = _utc_now()
        command_id = secrets.token_hex(12)
        try:
            response = urllib.request.urlopen(
                request,
                timeout=30,
                context=context,
            )
        except urllib.error.HTTPError as error:
            response = error
        content = response.read()
        record = {
            "command_id": command_id,
            "timestamp": started,
            "method": method,
            "url": url,
            "status": response.status,
            "request_body_sha256": (
                hashlib.sha256(data).hexdigest() if data else None
            ),
            "response_body_sha256": hashlib.sha256(content).hexdigest(),
            "response_headers": dict(response.headers.items()),
        }
        with (self.evidence_dir / "http-log.jsonl").open(
            "a",
            encoding="utf-8",
        ) as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        return {
            "status": response.status,
            "headers": dict(response.headers.items()),
            "body": content,
            "command_id": command_id,
        }

    def _school_database(self) -> Path:
        database = (
            self.state_dir
            / "server-data"
            / f"http___127_0_0_1_{self.args.server_port}_"
            / "school.db"
        )
        return self._require_path(
            database,
            "seeded school database",
            directory=False,
        )

    def _sqlite_query(self, query: str) -> List[str]:
        completed = self.commands.run(
            ["sqlite3", str(self._school_database()), query]
        )
        return [
            line
            for line in completed.stdout.splitlines()
            if line.strip()
        ]

    def _statement_jsons(self) -> List[Dict[str, Any]]:
        values: List[Dict[str, Any]] = []
        for line in self._sqlite_query(
            "SELECT fullStatement FROM XapiStatementEntityJson "
            "ORDER BY rowid"
        ):
            value = json.loads(line)
            if isinstance(value, dict):
                values.append(value)
        return values

    def _statement_digest(self) -> str:
        return _json_sha256(self._statement_jsons())

    def _bearer_token(self) -> str:
        tokens = self._sqlite_query(
            "SELECT atToken FROM AuthTokenEntity "
            "ORDER BY atUid DESC LIMIT 1"
        )
        if not tokens:
            raise RuntimeError("seeded school has no production auth token")
        return tokens[0]

    def _xapi_request(
        self,
        *,
        method: str = "GET",
        body: Optional[Any] = None,
        token: Optional[str] = None,
        query: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        endpoint = (
            f"http://127.0.0.1:{self.args.server_port}"
            "/api/school/xapi/statements"
        )
        if query:
            endpoint += "?" + urllib.parse.urlencode(query)
        headers = {
            "X-Experience-API-Version": "1.0.3",
            "Content-Type": "application/json",
        }
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return self._http_json(
            endpoint,
            method=method,
            body=body,
            headers=headers,
        )

    def _active_listings(self) -> List[Dict[str, Any]]:
        statements = self._statement_jsons()
        voided = {
            str(statement.get("object", {}).get("id"))
            for statement in statements
            if statement.get("verb", {}).get("id")
            == "http://adlnet.gov/expapi/verbs/voided"
            and isinstance(statement.get("object"), dict)
        }
        latest_by_url: Dict[str, Dict[str, Any]] = {}
        for statement in statements:
            if (
                statement.get("verb", {}).get("id")
                != "https://id.openeel.org/verb/listed-app"
            ):
                continue
            url = statement.get("object", {}).get("id")
            if isinstance(url, str):
                latest_by_url[url] = statement
        return [
            statement
            for statement in latest_by_url.values()
            if statement.get("id") not in voided
        ]

    def _adb(self, serial: str, *arguments: str, **kwargs) -> subprocess.CompletedProcess:
        return self.commands.run(
            [
                str(self._tool("platform-tools/adb")),
                "-s",
                serial,
                *arguments,
            ],
            **kwargs,
        )

    def _dump_ui(self, serial: str, label: str) -> ElementTree.Element:
        completed: Optional[subprocess.CompletedProcess] = None
        xml_text: Optional[str] = None
        end_marker = "</hierarchy>"
        for attempt in range(3):
            completed = self._adb(
                serial,
                "exec-out",
                "uiautomator",
                "dump",
                "/dev/tty",
                check=False,
                timeout=30,
            )
            combined = completed.stdout + completed.stderr
            start = combined.find("<?xml")
            end = combined.find(end_marker)
            if completed.returncode == 0 and start >= 0 and end >= 0:
                xml_text = combined[start : end + len(end_marker)]
                break
            if attempt < 2:
                time.sleep(1)
        if xml_text is None:
            detail = completed.stderr.strip() if completed else ""
            raise RuntimeError(
                f"could not capture UI hierarchy from {serial}: {detail}"
            )
        destination = (
            self.evidence_dir
            / "ui-hierarchies"
            / serial
            / f"{label}.xml"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(xml_text + "\n", encoding="utf-8")
        return ElementTree.fromstring(xml_text)

    def _node_matches(
        self,
        node: ElementTree.Element,
        *,
        text: Optional[str],
        resource_id: Optional[str],
        content_description: Optional[str],
        class_name: Optional[str],
    ) -> bool:
        if text is not None and node.attrib.get("text") != text:
            return False
        if resource_id is not None:
            actual = node.attrib.get("resource-id", "")
            if actual != resource_id and not actual.endswith(
                f":id/{resource_id}"
            ):
                return False
        if (
            content_description is not None
            and node.attrib.get("content-desc") != content_description
        ):
            return False
        if (
            class_name is not None
            and node.attrib.get("class") != class_name
        ):
            return False
        return True

    def _find_ui_node(
        self,
        root: ElementTree.Element,
        *,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        content_description: Optional[str] = None,
        class_name: Optional[str] = None,
    ) -> Optional[ElementTree.Element]:
        return next(
            (
                node
                for node in root.iter("node")
                if self._node_matches(
                    node,
                    text=text,
                    resource_id=resource_id,
                    content_description=content_description,
                    class_name=class_name,
                )
            ),
            None,
        )

    def _tap_node(
        self,
        serial: str,
        node: ElementTree.Element,
    ) -> None:
        bounds = node.attrib.get("bounds", "")
        numbers = [
            int(value)
            for value in bounds.replace("][", ",")
            .replace("[", "")
            .replace("]", "")
            .split(",")
            if value
        ]
        if len(numbers) != 4:
            raise ValueError(f"UI node has invalid bounds: {bounds}")
        x = (numbers[0] + numbers[2]) // 2
        y = (numbers[1] + numbers[3]) // 2
        self._adb(
            serial,
            "shell",
            "input",
            "tap",
            str(x),
            str(y),
        )

    def _tap_clickable_ancestor(
        self,
        serial: str,
        label: str,
        *,
        text: str,
        timeout: int = 60,
    ) -> None:
        deadline = time.monotonic() + timeout
        attempt = 0
        while time.monotonic() < deadline:
            root = self._dump_ui(serial, f"{label}-{attempt}")
            parent = {
                child: ancestor
                for ancestor in root.iter()
                for child in ancestor
            }
            node = self._find_ui_node(root, text=text)
            while node is not None:
                if node.attrib.get("clickable") == "true":
                    self._tap_node(serial, node)
                    return
                node = parent.get(node)
            attempt += 1
            time.sleep(1)
        raise RuntimeError(
            f"clickable ancestor for {text!r} did not appear on {serial}"
        )

    def _wait_ui_node(
        self,
        serial: str,
        label: str,
        *,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        content_description: Optional[str] = None,
        class_name: Optional[str] = None,
        timeout: int = 60,
    ) -> ElementTree.Element:
        deadline = time.monotonic() + timeout
        attempt = 0
        while time.monotonic() < deadline:
            root = self._dump_ui(serial, f"{label}-{attempt}")
            node = self._find_ui_node(
                root,
                text=text,
                resource_id=resource_id,
                content_description=content_description,
                class_name=class_name,
            )
            if node is not None:
                return node
            attempt += 1
            time.sleep(1)
        selector = text or resource_id or content_description or class_name
        raise RuntimeError(
            f"UI selector did not appear on {serial}: {selector}"
        )

    def _tap_ui(
        self,
        serial: str,
        label: str,
        *,
        text: Optional[str] = None,
        resource_id: Optional[str] = None,
        content_description: Optional[str] = None,
        class_name: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        node = self._wait_ui_node(
            serial,
            label,
            text=text,
            resource_id=resource_id,
            content_description=content_description,
            class_name=class_name,
            timeout=timeout,
        )
        # Re-resolve after transient Compose navigation animations so the
        # bounds used for the tap belong to the settled screen.
        time.sleep(1)
        settled = self._dump_ui(serial, f"{label}-settled")
        node = self._find_ui_node(
            settled,
            text=text,
            resource_id=resource_id,
            content_description=content_description,
            class_name=class_name,
        ) or node
        self._tap_node(serial, node)

    def _input_text(
        self,
        serial: str,
        value: str,
        *,
        sensitive: bool = False,
    ) -> None:
        # Compose focus propagation is asynchronous on the API 29 fixture.
        # A short settle avoids sending text to the previously focused field.
        time.sleep(1)
        encoded = value.replace(" ", "%s")
        self._adb(
            serial,
            "shell",
            "input",
            "text",
            encoded,
            recorded_argv=(
                [
                    str(self._tool("platform-tools/adb")),
                    "-s",
                    serial,
                    "shell",
                    "input",
                    "text",
                    "<redacted>",
                ]
                if sensitive
                else None
            ),
        )
        time.sleep(1)

    def _configure_respect_account(
        self,
        serial: str,
        *,
        school_password: str,
    ) -> None:
        server_base = f"http://127.0.0.1:{self.args.server_port}/"
        # Android 10's Autofill UI can take focus in a separate pop-up
        # window after the directory field is populated.  That window makes
        # the school-name input invisible to both `input text` and
        # uiautomator.  The ephemeral harness devices do not need Autofill,
        # so disable it before driving the login flow.
        self._adb(
            serial,
            "shell",
            "settings",
            "put",
            "secure",
            "autofill_service",
            "null",
        )
        self._adb(
            serial,
            "shell",
            "pm",
            "clear",
            self.args.respect_package,
        )
        self._adb(
            serial,
            "shell",
            "am",
            "start",
            "-n",
            (
                f"{self.args.respect_package}/"
                f"{DEFAULT_RESPECT_ACTIVITY}"
            ),
            "--es",
            "respect_directory",
            server_base,
        )
        self._tap_ui(
            serial,
            "onboarding",
            text="Get Started",
            timeout=90,
        )
        self._tap_ui(
            serial,
            "school-search",
            resource_id="school_name",
        )
        self._input_text(serial, "RESPECT Testkit")
        self._tap_ui(
            serial,
            "school-result",
            resource_id="school_list_item",
            timeout=60,
        )
        self._tap_ui(serial, "login-username", resource_id="username")
        self._input_text(serial, "admin")
        self._tap_ui(serial, "login-password", resource_id="password")
        self._input_text(serial, school_password, sensitive=True)
        self._tap_ui(serial, "login-submit", text="Login")
        self._wait_ui_node(
            serial,
            "apps-home",
            resource_id="app_title",
            text="Apps",
            timeout=90,
        )

    def _add_app_from_link(
        self,
        serial: str,
        descriptor_url: str,
    ) -> None:
        """Add an app through RESPECT's production Compose navigation."""
        self._return_to_apps_home(serial)
        self._tap_ui(
            serial,
            "apps-add",
            resource_id="floating_action_button",
        )
        self._tap_ui(
            serial,
            "apps-add-from-link",
            text="Add from Link",
        )
        self._tap_ui(
            serial,
            "apps-link-input",
            class_name="android.widget.EditText",
        )
        self._input_text(serial, descriptor_url)
        self._tap_ui(serial, "apps-link-next", text="Next")
        self._wait_ui_node(
            serial,
            "apps-link-detail",
            resource_id="app_title",
            text="App detail",
            timeout=90,
        )
        detail = self._dump_ui(serial, "apps-link-detail-settled")
        if self._find_ui_node(
            detail,
            text="Add to school apps",
        ) is None:
            if self._find_ui_node(detail, text="JiMS Mobile_KB") is not None:
                return
            raise RuntimeError(
                "app detail opened without an add action or app identity"
            )
        self._tap_ui(
            serial,
            "apps-link-confirm",
            text="Add to school apps",
        )
        self._wait_ui_node(
            serial,
            "apps-added-detail",
            text="JiMS Mobile_KB",
            timeout=90,
        )

    def _return_to_apps_home(self, serial: str) -> None:
        self._adb(
            serial,
            "shell",
            "am",
            "force-stop",
            self.args.respect_package,
        )
        self._adb(
            serial,
            "shell",
            "am",
            "start",
            "-n",
            (
                f"{self.args.respect_package}/"
                f"{DEFAULT_RESPECT_ACTIVITY}"
            ),
            "-f",
            "0x10008000",
        )
        for attempt in range(5):
            root = self._dump_ui(serial, f"return-apps-{attempt}")
            if self._find_ui_node(
                root,
                resource_id="app_title",
                text="Apps",
            ) is not None:
                return
            time.sleep(1)
        raise RuntimeError(f"could not return {serial} to the Apps screen")

    def _open_primary_lesson(self, serial: str) -> None:
        self._return_to_apps_home(serial)
        self._tap_clickable_ancestor(
            serial,
            "open-app-card",
            text="JiMS Mobile_KB",
            timeout=90,
        )
        self._wait_ui_node(
            serial,
            "app-detail-for-lesson",
            resource_id="app_title",
            text="App detail",
            timeout=90,
        )
        self._tap_clickable_ancestor(
            serial,
            "open-primary-lesson",
            text="C Major Scale Drill",
            timeout=90,
        )
        self._wait_ui_node(
            serial,
            "primary-lesson-detail",
            text="Open",
            timeout=90,
        )

    def _remove_app_from_home(
        self,
        serial: str,
        title: str = "JiMS Mobile_KB",
        descriptor_url: Optional[str] = None,
    ) -> None:
        self._return_to_apps_home(serial)
        root = self._dump_ui(serial, "remove-app-menu")
        parent = {
            child: ancestor
            for ancestor in root.iter()
            for child in ancestor
        }
        title_node = self._find_ui_node(root, text=title)
        if title_node is None:
            raise RuntimeError(f"app title is not displayed: {title}")
        card = title_node
        while (
            parent.get(card) is not None
            and parent[card].attrib.get("clickable") != "true"
        ):
            card = parent[card]
        card = parent.get(card, card)
        clickable = [
            node
            for node in card.iter("node")
            if node.attrib.get("clickable") == "true" and node is not card
        ]
        if not clickable:
            raise RuntimeError("app card has no semantic overflow action")

        def area(node: ElementTree.Element) -> int:
            values = [
                int(value)
                for value in node.attrib.get("bounds", "")
                .replace("][", ",")
                .replace("[", "")
                .replace("]", "")
                .split(",")
                if value
            ]
            return (
                (values[2] - values[0]) * (values[3] - values[1])
                if len(values) == 4
                else sys.maxsize
            )

        self._tap_node(serial, min(clickable, key=area))
        self._tap_ui(serial, "remove-app-confirm", text="Remove")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            active_urls = {
                statement.get("object", {}).get("id")
                for statement in self._active_listings()
            }
            target_absent = (
                descriptor_url not in active_urls
                if descriptor_url is not None
                else not any(
                    isinstance(url, str)
                    and "mobile-kb/descriptor" in url
                    for url in active_urls
                )
            )
            if target_absent:
                return
            time.sleep(1)
        raise RuntimeError("RESPECT did not persist the voiding statement")

    def _capture_launch(
        self,
        serial: str,
        *,
        choose_native: bool,
    ) -> Dict[str, Any]:
        source_ids: List[str] = []
        self._adb(serial, "logcat", "-c")
        if self.commands.last_command_id:
            source_ids.append(self.commands.last_command_id)
        self._open_primary_lesson(serial)
        self._tap_ui(serial, "launch-primary-lesson", text="Open")
        time.sleep(3)
        if choose_native:
            try:
                self._tap_clickable_ancestor(
                    serial,
                    "resolver-mobile-kb",
                    text="Mobile_KB",
                    timeout=3,
                )
            except RuntimeError:
                try:
                    self._tap_ui(
                        serial,
                        "resolver-mobile-kb-direct",
                        text="Mobile_KB",
                        timeout=5,
                    )
                except RuntimeError:
                    pass
            for button_text in ("Just once", "JUST ONCE"):
                try:
                    self._tap_ui(
                        serial,
                        "resolver-just-once",
                        text=button_text,
                        timeout=3,
                    )
                    break
                except RuntimeError:
                    continue
        deadline = time.monotonic() + 20
        activity: Optional[subprocess.CompletedProcess] = None
        while time.monotonic() < deadline:
            activity = self._adb(
                serial,
                "shell",
                "dumpsys",
                "activity",
                "activities",
            )
            expected_component = (
                f" {self.args.canapp_package}/"
                if choose_native
                else (
                    f" {self.args.respect_package}/"
                    f"{DEFAULT_WEBVIEW_ACTIVITY}"
                )
            )
            resumed_line = next(
                (
                    line
                    for line in activity.stdout.splitlines()
                    if "topResumedActivity=" in line
                    or "mResumedActivity=" in line
                ),
                "",
            )
            if expected_component in resumed_line:
                break
            time.sleep(1)
        if activity is None:
            raise RuntimeError("activity-state capture did not run")
        if self.commands.last_command_id:
            source_ids.append(self.commands.last_command_id)
        logcat = self._adb(
            serial,
            "logcat",
            "-d",
            "-v",
            "time",
        )
        if self.commands.last_command_id:
            source_ids.append(self.commands.last_command_id)
        activity_path = (
            self.evidence_dir
            / "activity-state"
            / f"{serial}-{secrets.token_hex(6)}.txt"
        )
        logcat_path = (
            self.evidence_dir
            / "logcat"
            / f"{serial}-{secrets.token_hex(6)}.txt"
        )
        activity_path.parent.mkdir(parents=True, exist_ok=True)
        logcat_path.parent.mkdir(parents=True, exist_ok=True)
        activity_path.write_text(activity.stdout, encoding="utf-8")
        logcat_path.write_text(logcat.stdout, encoding="utf-8")

        component_match = re.search(
            r"(?:topResumedActivity|mResumedActivity)[:=]"
            r"[^\n]*\s([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)",
            activity.stdout,
        )
        activity_package = (
            component_match.group(1) if component_match else ""
        )
        activity_name = (
            component_match.group(2) if component_match else ""
        )
        native_url_match = re.search(
            r"attempting to launch (\S+) with RequireNonBrowser",
            logcat.stdout,
        )
        fallback_url_match = re.search(
            r"(?:Launching URL:|launching) (https?://\S+)",
            logcat.stdout,
        )
        intent_url_match = re.search(
            r"\bdat=(https?://\S+?)(?:\s+(?:flg|xflg|cmp)=|\s+\})",
            activity.stdout,
        )
        return {
            "activity_package": activity_package,
            "activity_name": activity_name,
            "native_url": (
                native_url_match.group(1) if native_url_match else None
            ),
            "fallback_url": (
                fallback_url_match.group(1)
                if fallback_url_match
                else None
            ),
            "intent_url": (
                intent_url_match.group(1) if intent_url_match else None
            ),
            "logcat": logcat.stdout,
            "activity_state": activity.stdout,
            "activity_path": str(activity_path),
            "logcat_path": str(logcat_path),
            "source_ids": source_ids,
        }

    def _descriptor_url(self) -> str:
        seed = self.state.operation("seed").get("result", {})
        url = seed.get("descriptor_url")
        if not isinstance(url, str) or not url:
            raise RuntimeError("seed manifest has no descriptor URL")
        return url

    def _ensure_primary_app(self, serial: str) -> None:
        descriptor_url = self._descriptor_url()
        active_urls = {
            statement.get("object", {}).get("id")
            for statement in self._active_listings()
        }
        if descriptor_url not in active_urls:
            self._add_app_from_link(serial, descriptor_url)
            return
        self._return_to_apps_home(serial)
        self._wait_ui_node(
            serial,
            "primary-app-synchronized",
            text="JiMS Mobile_KB",
            timeout=90,
        )

    def _create_school(
        self,
        directory_password: str,
        school_password: str,
    ) -> Dict[str, Any]:
        server_base = f"http://127.0.0.1:{self.args.server_port}/"
        authorization = base64.b64encode(
            f"admin:{directory_password}".encode("utf-8")
        ).decode("ascii")
        timestamp = _utc_now()
        request = [
            {
                "school": {
                    "name": f"RESPECT Testkit {self.run_id}",
                    "self": server_base,
                    "xapi": f"{server_base}api/school/xapi",
                    "oneRoster": f"{server_base}api/school/oneroster",
                    "respectExt": f"{server_base}api/school/respect",
                    "rpId": None,
                    "lastModified": timestamp,
                    "stored": timestamp,
                },
                "dbUrl": "school.db",
                "adminUsername": "admin",
                "adminPassword": school_password,
            }
        ]
        response = self._http_json(
            f"{server_base}api/directory/school",
            method="POST",
            body=request,
            headers={
                "Authorization": f"Basic {authorization}",
                "Content-Type": "application/json",
            },
        )
        if not 200 <= response["status"] < 300:
            raise RuntimeError(
                f"school creation failed: status {response['status']}"
            )
        return {
            "school_name": request[0]["school"]["name"],
            "school_url": server_base,
            "admin_username": "admin",
            "created_at": timestamp,
            "response_sha256": hashlib.sha256(
                response["body"]
            ).hexdigest(),
        }

    def _publication_fingerprint(self, apk: Path) -> str:
        apksigner = self._tool("build-tools/36.0.0/apksigner")
        completed = self.commands.run(
            [str(apksigner), "verify", "--print-certs", str(apk)],
            env=self._java_env(),
        )
        for line in completed.stdout.splitlines():
            marker = "Signer #1 certificate SHA-256 digest:"
            if line.strip().startswith(marker):
                compact = line.split(":", 1)[1].strip().upper()
                return ":".join(
                    compact[index : index + 2]
                    for index in range(0, len(compact), 2)
                )
        raise ValueError("could not read Mobile_KB signing fingerprint")

    def seed(self) -> Dict[str, Any]:
        completed_seed = self.state.operation("seed")
        if completed_seed.get("status") == "complete":
            result = completed_seed.get("result")
            if isinstance(result, dict):
                return result
        if not self.state.completed("provision"):
            self.provision()
        # A failed seed can leave child services and a partially initialized
        # directory database behind.  Seed is transactional: stop any PIDs
        # recorded by an earlier attempt, then rebuild only seed-owned state.
        runtime = self.state.value.get("runtime", {})
        for key in ("server_pid", "publisher_pid"):
            pid = runtime.get(key)
            if isinstance(pid, int):
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass
        if any(
            isinstance(runtime.get(key), int)
            for key in ("server_pid", "publisher_pid")
        ):
            time.sleep(1)
        mobile_source = self._require_path(
            self.args.mobile_kb_source,
            "--mobile-kb-source",
        )
        respect_apk = self._artifact_path(
            self.args.respect_apk,
            "respect_apk",
            "--respect-apk",
        )
        mobile_apk = self._artifact_path(
            self.args.mobile_kb_apk,
            "mobile_kb_apk",
            "--mobile-kb-apk",
        )
        server_jar = self._artifact_path(
            None,
            "server_jar",
            "--build",
        )
        tls = self._ensure_tls()
        publication = self.state_dir / "publication"
        private_state = self.state_dir / "private"
        server_data = self.state_dir / "server-data"
        for seed_path in (publication, private_state, server_data):
            if seed_path.exists():
                shutil.rmtree(seed_path)
        fingerprint = self._publication_fingerprint(mobile_apk)
        self.commands.run(
            [
                sys.executable,
                str(mobile_source / "respect-public" / "generate.py"),
                "--origin",
                f"https://localhost:{self.args.publisher_port}",
                "--fingerprint",
                fingerprint,
                "--output",
                str(publication),
            ],
            cwd=mobile_source,
        )
        shutil.copy2(
            publication / "mobile-kb" / "descriptor.json",
            publication / "mobile-kb" / "descriptor-unrelated.json",
        )
        private_state.mkdir(parents=True, exist_ok=True)
        directory_password = secrets.token_hex(24)
        school_password = secrets.token_hex(24)
        (private_state / "directory-password").write_text(
            directory_password,
            encoding="utf-8",
        )
        (private_state / "school-password").write_text(
            school_password,
            encoding="utf-8",
        )
        for secret_file in private_state.iterdir():
            secret_file.chmod(0o600)
        server_data.mkdir(parents=True, exist_ok=True)
        (server_data / "dir-admin.txt").write_text(
            directory_password,
            encoding="utf-8",
        )
        (server_data / "dir-admin.txt").chmod(0o600)
        logs = self.evidence_dir / "services"
        server = self.commands.start(
            [
                str(
                    self._require_path(
                        self.java_home,
                        "--java-home",
                    )
                    / "bin"
                    / "java"
                ),
                "-jar",
                str(server_jar),
                "runserver",
                f"-P:ktor.deployment.port={self.args.server_port}",
                f"-P:ktor.respect.datadir={server_data}",
                "-P:ktor.e2eartifactupload.enabled=true",
            ],
            cwd=self.state_dir,
            env=self._java_env(),
            stdout_path=logs / "respect-server.stdout.log",
            stderr_path=logs / "respect-server.stderr.log",
        )
        publisher = self.commands.start(
            [
                sys.executable,
                str(mobile_source / "respect-public" / "serve.py"),
                "--directory",
                str(publication),
                "--port",
                str(self.args.publisher_port),
                "--bind",
                "127.0.0.1",
                "--certfile",
                tls["server_cert"],
                "--keyfile",
                tls["server_key"],
            ],
            cwd=self.state_dir,
            stdout_path=logs / "publisher.stdout.log",
            stderr_path=logs / "publisher.stderr.log",
        )
        self.state.update_runtime(
            {
                "server_pid": server.pid,
                "publisher_pid": publisher.pid,
            }
        )
        self._wait_port(self.args.server_port)
        self._wait_port(self.args.publisher_port)
        school = self._create_school(
            directory_password,
            school_password,
        )
        adb = self._tool("platform-tools/adb")
        for serial in (
            self.args.api30_plus_serial,
            self.args.api29_serial,
        ):
            for apk in (respect_apk, mobile_apk):
                self.commands.run(
                    [
                        str(adb),
                        "-s",
                        serial,
                        "install",
                        "-r",
                        "-t",
                        str(apk),
                    ],
                    timeout=300,
                )
            for port in (
                self.args.server_port,
                self.args.publisher_port,
            ):
                self.commands.run(
                    [
                        str(adb),
                        "-s",
                        serial,
                        "reverse",
                        f"tcp:{port}",
                        f"tcp:{port}",
                    ]
                )
            self._configure_respect_account(
                serial,
                school_password=school_password,
            )
        seed_manifest = {
            "artifact_type": "respect_school_seed_manifest",
            "format_version": "1.0.0",
            "run_id": self.run_id,
            "school": school,
            "publication_origin": (
                f"https://localhost:{self.args.publisher_port}"
            ),
            "descriptor_url": (
                f"https://localhost:{self.args.publisher_port}"
                "/mobile-kb/descriptor.json"
            ),
            "publication_tree_sha256": self._tree_digest(publication),
            "ca_certificate_sha256": _sha256(Path(tls["ca_cert"])),
            "server_pid": server.pid,
            "publisher_pid": publisher.pid,
            "devices": [
                self.args.api30_plus_serial,
                self.args.api29_serial,
            ],
            "created_at": _utc_now(),
        }
        self.state.mark_complete("seed", seed_manifest)
        _write_json(
            self.evidence_dir / "seed-manifest.json",
            seed_manifest,
        )
        return seed_manifest

    def _tree_digest(self, root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(_sha256(path).encode("ascii"))
        return digest.hexdigest()

    def _scenario(self) -> Dict[str, Any]:
        seed = self.state.operation("seed").get("result", {})
        scenario = {
            "artifact_type": "respect_platform_emulator_scenario",
            "format_version": "1.0.0",
            "respect_package": self.args.respect_package,
            "canapp_package": self.args.canapp_package,
            "provider_command": [
                "respect-school-harness",
                "--collect-evidence",
                "--run-id",
                self.run_id,
                "--state-dir",
                str(self.state_dir),
                "--evidence-dir",
                str(self.evidence_dir),
                "--android-sdk",
                str(self._require_path(self.sdk, "--android-sdk")),
                "--api29-serial",
                self.args.api29_serial,
                "--api30-plus-serial",
                self.args.api30_plus_serial,
                "--server-port",
                str(self.args.server_port),
                "--publisher-port",
                str(self.args.publisher_port),
            ],
            "selected_rows": list(SCHOOL_ROW_ORDER),
            "row_devices": {
                row_id: (
                    self.args.api29_serial
                    if row_id in API29_ROWS
                    else self.args.api30_plus_serial
                )
                for row_id in SCHOOL_ROW_ORDER
            },
            "school": {
                "url": seed.get("school", {}).get("school_url"),
            },
            "descriptor_url": seed.get("descriptor_url"),
            "timeout_seconds": 3600,
        }
        return scenario

    def _load_row_records(self) -> Dict[str, Any]:
        path = self.evidence_dir / "row-records.json"
        if not path.is_file():
            raise ValueError(
                "production row records are missing; run --run-row or "
                "--run-all before --collect-evidence"
            )
        value = _read_object(path)
        records = value.get("records")
        if not isinstance(records, dict):
            raise ValueError("row-records.json has no records object")
        return records

    def _health_control(self, serial: str) -> Dict[str, Any]:
        probe = probe_android_device(
            serial,
            adb=self._tool("platform-tools/adb"),
        )
        response = self._http_json(
            f"http://127.0.0.1:{self.args.server_port}/"
        )
        healthy = (
            probe.get("healthy") is True
            and 200 <= response["status"] < 500
            and self._port_open(self.args.publisher_port)
        )
        return {
            "status": "healthy" if healthy else "unhealthy",
            "probe": probe,
            "server_status": response["status"],
            "publisher_open": self._port_open(
                self.args.publisher_port
            ),
            "command_id": response["command_id"],
            "captured_at": _utc_now(),
        }

    def _persist_row_record(
        self,
        row_id: str,
        *,
        serial: str,
        positive: Mapping[str, Any],
        negative: Mapping[str, Any],
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        source_ids: Iterable[str],
    ) -> Dict[str, Any]:
        nonce = self.state.value.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            nonce = secrets.token_hex(24)
            self.state.value["nonce"] = nonce
        capture = {
            "row_id": row_id,
            "positive": positive,
            "negative": negative,
            "captured_at": _utc_now(),
            "device": serial,
        }
        capture_digest = _json_sha256(capture)
        prior_digest = _json_sha256(before)
        record = {
            "row_id": row_id,
            "positive": dict(positive),
            "isolated_negative": dict(negative),
            "harness_health": {
                "before": before["status"],
                "after": after["status"],
                "before_capture": dict(before),
                "after_capture": dict(after),
            },
            "target_attribution": {
                "device_id": serial,
                "package_id": self.args.canapp_package,
                "row_id": row_id,
            },
            "anti_replay": {
                "nonce": nonce,
                "capture_sha256": capture_digest,
                "prior_capture_sha256": prior_digest,
                "captured_at": capture["captured_at"],
            },
            "regression_lock": f"school-harness:{row_id}",
            "capture_sources": [
                {
                    "kind": "production",
                    "command_id": command_id,
                }
                for command_id in dict.fromkeys(source_ids)
                if command_id
            ],
        }
        if not record["capture_sources"]:
            raise RuntimeError(f"{row_id} produced no attributable sources")
        validate_row_record(
            record,
            run_nonce=nonce,
            expected_device=serial,
            expected_package=self.args.canapp_package,
        )
        path = self.evidence_dir / "row-records.json"
        container = (
            _read_object(path)
            if path.is_file()
            else {
                "artifact_type": "respect_school_row_records",
                "format_version": "1.0.0",
                "run_id": self.run_id,
                "records": {},
            }
        )
        container.setdefault("records", {})[row_id] = record
        _write_json(path, container)
        return record

    def _run_auth_002(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        token = self._bearer_token()
        before_digest = self._statement_digest()
        valid = self._xapi_request(token=token)
        missing = self._xapi_request(token=None)
        altered = self._xapi_request(token=f"{token}-altered")
        after_digest = self._statement_digest()
        positive = {
            "valid_status": valid["status"],
            "missing_status": missing["status"],
            "altered_status": altered["status"],
            "effect_digest_before": before_digest,
            "effect_digest_after": after_digest,
        }
        # The isolated fixture deliberately reuses the valid credential in
        # the "altered" slot.  The observed 2xx is real and demonstrates that
        # the oracle rejects a credential-negative that was not altered.
        unaltered = self._xapi_request(token=token)
        negative = dict(positive)
        negative["altered_status"] = unaltered["status"]
        return positive, negative, [
            valid["command_id"],
            missing["command_id"],
            altered["command_id"],
            unaltered["command_id"],
            self.commands.last_command_id or "",
        ]

    def _xapi_statement(
        self,
        *,
        statement_id: str,
        activity_id: str,
    ) -> Dict[str, Any]:
        return {
            "id": statement_id,
            "actor": {
                "name": "Admin Admin",
                "account": {
                    "homePage": (
                        f"http://127.0.0.1:{self.args.server_port}/"
                    ),
                    "name": "1",
                },
            },
            "verb": {
                "id": "http://adlnet.gov/expapi/verbs/experienced"
            },
            "object": {
                "objectType": "Activity",
                "id": activity_id,
            },
            "timestamp": _utc_now(),
            "version": "1.0.3",
        }

    def _run_xapi_020(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        token = self._bearer_token()
        retrieval_scope = uuid.uuid4()
        activity = (
            f"https://school-harness.invalid/{self.run_id}/"
            f"matching/{retrieval_scope}"
        )
        nonmatching_activity = (
            f"https://school-harness.invalid/{self.run_id}/"
            f"other/{retrieval_scope}"
        )
        submitted = [str(uuid.uuid4()), str(uuid.uuid4())]
        nonmatching = str(uuid.uuid4())
        post_match = self._xapi_request(
            method="POST",
            token=token,
            body=[
                self._xapi_statement(
                    statement_id=statement_id,
                    activity_id=activity,
                )
                for statement_id in submitted
            ],
        )
        post_other = self._xapi_request(
            method="POST",
            token=token,
            body=self._xapi_statement(
                statement_id=nonmatching,
                activity_id=nonmatching_activity,
            ),
        )
        if not 200 <= post_match["status"] < 300:
            raise RuntimeError("production xAPI statement POST failed")
        if not 200 <= post_other["status"] < 300:
            raise RuntimeError("production xAPI control POST failed")
        matching = self._xapi_request(
            token=token,
            query={
                "activity": activity,
                "related_activities": "false",
            },
        )
        value = json.loads(matching["body"])
        returned = [
            statement.get("id")
            for statement in value.get("statements", [])
            if isinstance(statement, dict)
            and isinstance(statement.get("id"), str)
        ]
        positive = {
            "status": matching["status"],
            "headers": matching["headers"],
            "submitted_statement_ids": submitted,
            "returned_statement_ids": returned,
            "nonmatching_statement_id": nonmatching,
        }
        unfiltered = self._xapi_request(token=token)
        unfiltered_value = json.loads(unfiltered["body"])
        unfiltered_ids = [
            statement.get("id")
            for statement in unfiltered_value.get("statements", [])
            if isinstance(statement, dict)
            and isinstance(statement.get("id"), str)
        ]
        negative = dict(positive)
        negative["returned_statement_ids"] = unfiltered_ids
        return positive, negative, [
            post_match["command_id"],
            post_other["command_id"],
            matching["command_id"],
            unfiltered["command_id"],
        ]

    def _resolved_packages(
        self,
        serial: str,
        launch_url: str,
    ) -> Tuple[List[str], str]:
        completed = self._adb(
            serial,
            "shell",
            "cmd",
            "package",
            "query-activities",
            "--brief",
            "-a",
            "android.intent.action.VIEW",
            "-c",
            "android.intent.category.BROWSABLE",
            "-d",
            launch_url.replace("&", r"\&"),
            check=False,
        )
        packages = []
        for line in completed.stdout.splitlines():
            package = line.strip().split("/", 1)[0]
            if package and "." in package and package not in packages:
                packages.append(package)
        return packages, self.commands.last_command_id or ""

    def _run_native_launch(
        self,
        serial: str,
        *,
        api_level: int,
        row_id: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        self._ensure_primary_app(serial)
        capture = self._capture_launch(serial, choose_native=True)
        launch_url = capture["intent_url"] or capture["native_url"]
        if not isinstance(launch_url, str) or not launch_url:
            raise RuntimeError(f"{row_id} did not produce a launch URL")
        packages, query_source = self._resolved_packages(
            serial,
            launch_url,
        )
        selected_package = capture["activity_package"]
        if selected_package != self.args.canapp_package:
            raise RuntimeError(
                f"{row_id} selected {selected_package!r}, not "
                f"{self.args.canapp_package!r}"
            )
        positive = {
            "api_level": api_level,
            "selected_package": selected_package,
            "activity_package": capture["activity_package"],
            "launch_url": launch_url,
            "expected_launch_url": capture["native_url"] or launch_url,
        }
        if row_id == "LAUNCH-001":
            positive["native_attempted"] = bool(capture["native_url"])
        else:
            positive["resolved_packages"] = packages

        altered_url = (
            launch_url
            + ("&" if "?" in launch_url else "?")
            + "school_harness_fault=altered"
        )
        self._adb(
            serial,
            "shell",
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.VIEW",
            "-c",
            "android.intent.category.BROWSABLE",
            "-d",
            altered_url.replace("&", r"\&"),
            "-p",
            self.args.canapp_package,
        )
        negative_source = self.commands.last_command_id or ""
        altered_state = self._adb(
            serial,
            "shell",
            "dumpsys",
            "activity",
            "activities",
        )
        altered_matches = re.findall(
            r"\bdat=(https?://\S+?)(?:\s+(?:flg|xflg|cmp)=|\s+\})",
            altered_state.stdout,
        )
        negative = dict(positive)
        negative["launch_url"] = next(
            (
                observed_url
                for observed_url in altered_matches
                if "school_harness_fault=altered" in observed_url
            ),
            altered_url,
        )
        return positive, negative, [
            *capture["source_ids"],
            query_source,
            negative_source,
            self.commands.last_command_id or "",
        ]

    def _run_launch_002(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        self._ensure_primary_app(serial)
        mobile_apk = self._artifact_path(
            self.args.mobile_kb_apk,
            "mobile_kb_apk",
            "--mobile-kb-apk",
        )
        publisher_log = (
            self.evidence_dir / "services" / "publisher.stderr.log"
        )
        log_before = (
            publisher_log.read_text(encoding="utf-8")
            if publisher_log.is_file()
            else ""
        )
        self._adb(
            serial,
            "uninstall",
            self.args.canapp_package,
            check=False,
        )
        uninstall_source = self.commands.last_command_id or ""
        try:
            fallback = self._capture_launch(
                serial,
                choose_native=False,
            )
            fallback_url = fallback["fallback_url"]
            if not isinstance(fallback_url, str) or not fallback_url:
                raise RuntimeError(
                    "absent-handler fixture did not reach WebView fallback"
                )
            log_after = (
                publisher_log.read_text(encoding="utf-8")
                if publisher_log.is_file()
                else ""
            )
            request_path = urllib.parse.urlsplit(
                fallback_url
            ).path
            page_loaded = (
                fallback["activity_package"] == self.args.respect_package
                and fallback["activity_name"].endswith(
                    "WebViewActivity"
                )
                and request_path in log_after[len(log_before) :]
            )
            positive = {
                "native_failure": "no installed non-browser handler",
                "selected_activity": DEFAULT_WEBVIEW_ACTIVITY,
                "page_loaded": page_loaded,
                "webview_url": fallback_url,
                "expected_launch_url": fallback_url,
            }
        finally:
            self._adb(
                serial,
                "install",
                "-r",
                "-t",
                str(mobile_apk),
                timeout=300,
            )
        install_source = self.commands.last_command_id or ""
        native = self._capture_launch(serial, choose_native=True)
        negative = dict(positive)
        negative.update(
            {
                "native_failure": "",
                "selected_activity": native["activity_name"],
                "page_loaded": False,
                "webview_url": native["intent_url"]
                or native["native_url"],
            }
        )
        return positive, negative, [
            uninstall_source,
            *fallback["source_ids"],
            install_source,
            *native["source_ids"],
        ]

    def _ui_semantic_texts(
        self,
        serial: str,
        label: str,
    ) -> Tuple[List[str], str]:
        root = self._dump_ui(serial, label)
        texts = [
            text
            for node in root.iter("node")
            if (text := node.attrib.get("text", "")).strip()
        ]
        return texts, self.commands.last_command_id or ""

    def _publisher_request_urls(self, text: str) -> List[str]:
        origin = f"https://localhost:{self.args.publisher_port}"
        return list(
            dict.fromkeys(
                urllib.parse.urljoin(origin, match)
                for match in re.findall(
                    r'"(?:GET|HEAD) ([^ ]+) HTTP/[0-9.]+"',
                    text,
                )
            )
        )

    def _declared_primary_urls(self) -> List[str]:
        publication_url = (
            f"https://localhost:{self.args.publisher_port}"
            "/mobile-kb/lessons/cmajor-scale-drill/publication.json"
        )
        path = (
            self.state_dir
            / "publication"
            / "mobile-kb"
            / "lessons"
            / "cmajor-scale-drill"
            / "publication.json"
        )
        publication = _read_object(path)
        links: List[Mapping[str, Any]] = []
        for key in ("links", "readingOrder", "resources"):
            values = publication.get(key, [])
            if isinstance(values, list):
                links.extend(
                    value
                    for value in values
                    if isinstance(value, Mapping)
                )
        declared = [publication_url]
        for link in links:
            href = link.get("href")
            if isinstance(href, str) and href:
                declared.append(
                    urllib.parse.urljoin(publication_url, href)
                )
        return list(dict.fromkeys(declared))

    def _run_offline_001(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        self._ensure_primary_app(serial)
        self._open_primary_lesson(serial)
        before_texts, before_source = self._ui_semantic_texts(
            serial,
            "offline-before-download",
        )
        publisher_log = (
            self.evidence_dir / "services" / "publisher.stderr.log"
        )
        before_log = (
            publisher_log.read_text(encoding="utf-8")
            if publisher_log.is_file()
            else ""
        )
        already_downloaded = "Downloaded" in before_texts
        if already_downloaded:
            after_texts = before_texts
            after_source = before_source
        else:
            self._tap_clickable_ancestor(
                serial,
                "download-primary-lesson",
                text="Download",
            )
            time.sleep(8)
            after_texts, after_source = self._ui_semantic_texts(
                serial,
                "offline-after-download",
            )
        after_log = publisher_log.read_text(encoding="utf-8")
        requested = self._publisher_request_urls(
            after_log if already_downloaded else after_log[len(before_log) :]
        )
        declared = self._declared_primary_urls()
        unrelated = (
            f"https://localhost:{self.args.publisher_port}"
            "/school-harness-unrelated"
        )
        complete = set(declared).issubset(requested)
        positive = {
            "declared_urls": declared,
            "requested_urls": requested,
            "unrelated_url": unrelated,
            "pin_state": "complete" if complete else "partial",
        }
        negative = {
            "declared_urls": declared,
            "requested_urls": (
                []
                if already_downloaded
                else self._publisher_request_urls(before_log)
            ),
            "unrelated_url": unrelated,
            "pin_state": "not-started",
        }
        online_semantics = {
            "texts": sorted(set(after_texts)),
            "declared_urls": declared,
        }
        self.state.value["offline_online_digest"] = _json_sha256(
            online_semantics
        )
        self.state.value["offline_online_texts"] = after_texts
        self.state.value["offline_before_texts"] = before_texts
        _write_json(self.state.path, self.state.value, private=True)
        return positive, negative, [
            before_source,
            after_source,
            self.commands.last_command_id or "",
        ]

    def _restart_publisher(self) -> str:
        mobile_source = self._require_path(
            self.args.mobile_kb_source,
            "--mobile-kb-source",
        )
        tls = self._ensure_tls()
        logs = self.evidence_dir / "services"
        publisher = self.commands.start(
            [
                sys.executable,
                str(mobile_source / "respect-public" / "serve.py"),
                "--directory",
                str(self.state_dir / "publication"),
                "--port",
                str(self.args.publisher_port),
                "--bind",
                "127.0.0.1",
                "--certfile",
                tls["server_cert"],
                "--keyfile",
                tls["server_key"],
            ],
            cwd=self.state_dir,
            stdout_path=logs / "publisher.stdout.log",
            stderr_path=logs / "publisher.stderr.log",
        )
        self.state.update_runtime({"publisher_pid": publisher.pid})
        self._wait_port(self.args.publisher_port)
        return self.commands.last_command_id or ""

    def _run_offline_002(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        online_digest = self.state.value.get("offline_online_digest")
        if not isinstance(online_digest, str) or not online_digest:
            raise RuntimeError("OFFLINE-001 must run before OFFLINE-002")
        publisher_pid = (
            self.state.value.get("runtime", {}).get("publisher_pid")
        )
        if not isinstance(publisher_pid, int):
            raise RuntimeError("publisher PID is missing")
        os.kill(publisher_pid, 15)
        deadline = time.monotonic() + 20
        while self._port_open(self.args.publisher_port):
            if time.monotonic() >= deadline:
                raise RuntimeError("publisher did not stop")
            time.sleep(0.25)
        remote_unavailable = not self._port_open(
            self.args.publisher_port
        )
        self._open_primary_lesson(serial)
        offline_texts, offline_source = self._ui_semantic_texts(
            serial,
            "offline-cached-primary",
        )
        expected_texts = self.state.value.get(
            "offline_online_texts",
            [],
        )
        stable_markers = {"C Major Scale Drill", "Open"}
        offline_usable = (
            stable_markers.issubset(set(offline_texts))
            and bool({"Download", "Downloaded"} & set(offline_texts))
        )
        offline_semantics = sorted(
            text
            for text in set(offline_texts)
            if text in stable_markers
        ) + ["download-control"]
        online_semantics = sorted(
            text
            for text in set(expected_texts)
            if text in stable_markers
        ) + ["download-control"]
        offline_digest = _json_sha256(
            {
                "texts": offline_semantics,
                "declared_urls": self._declared_primary_urls(),
            }
        )
        normalized_online_digest = _json_sha256(
            {
                "texts": online_semantics,
                "declared_urls": self._declared_primary_urls(),
            }
        )
        self._return_to_apps_home(serial)
        self._tap_clickable_ancestor(
            serial,
            "offline-open-app",
            text="JiMS Mobile_KB",
        )
        self._tap_clickable_ancestor(
            serial,
            "offline-never-fetched",
            text="Mary Had a Little Lamb",
        )
        time.sleep(4)
        never_texts, never_source = self._ui_semantic_texts(
            serial,
            "offline-never-fetched-result",
        )
        never_fetched_available = "Open" in never_texts
        restart_source = self._restart_publisher()
        positive = {
            "remote_unavailable": remote_unavailable,
            "offline_usable": offline_usable,
            "never_fetched_available": never_fetched_available,
            "online_digest": normalized_online_digest,
            "offline_digest": offline_digest,
        }
        # Actual online control: with the origin restored, the same
        # never-fetched item becomes available and must be rejected by the
        # offline oracle.
        self._return_to_apps_home(serial)
        self._tap_clickable_ancestor(
            serial,
            "online-control-open-app",
            text="JiMS Mobile_KB",
        )
        self._tap_clickable_ancestor(
            serial,
            "online-control-never-fetched",
            text="Mary Had a Little Lamb",
        )
        self._wait_ui_node(
            serial,
            "online-control-open",
            text="Open",
            timeout=60,
        )
        negative = dict(positive)
        negative.update(
            {
                "remote_unavailable": False,
                "never_fetched_available": True,
            }
        )
        return positive, negative, [
            offline_source,
            never_source,
            restart_source,
            self.commands.last_command_id or "",
        ]

    def _void_listing(self, listing_id: str) -> Dict[str, Any]:
        statement = {
            "id": str(uuid.uuid4()),
            "actor": {
                "name": "Admin Admin",
                "account": {
                    "homePage": (
                        f"http://127.0.0.1:{self.args.server_port}/"
                    ),
                    "name": "1",
                },
            },
            "verb": {
                "id": "http://adlnet.gov/expapi/verbs/voided"
            },
            "object": {
                "objectType": "StatementRef",
                "id": listing_id,
            },
            "timestamp": _utc_now(),
            "version": "1.0.3",
        }
        response = self._xapi_request(
            method="POST",
            token=self._bearer_token(),
            body=statement,
        )
        if not 200 <= response["status"] < 300:
            raise RuntimeError("production listing void failed")
        return response

    def _listing_statements(
        self,
        descriptor_url: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        values = [
            statement
            for statement in self._statement_jsons()
            if statement.get("verb", {}).get("id")
            == "https://id.openeel.org/verb/listed-app"
        ]
        if descriptor_url is None:
            return values
        return [
            statement
            for statement in values
            if statement.get("object", {}).get("id") == descriptor_url
        ]

    def _run_reg_001(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        descriptor = self._descriptor_url()
        active = [
            statement
            for statement in self._active_listings()
            if statement.get("object", {}).get("id") == descriptor
        ]
        sources: List[str] = []
        self._return_to_apps_home(serial)
        home_texts, home_source = self._ui_semantic_texts(
            serial,
            "reg001-existing-app",
        )
        sources.append(home_source)
        if "JiMS Mobile_KB" in home_texts:
            self._remove_app_from_home(
                serial,
                descriptor_url=descriptor,
            )
            time.sleep(3)
        negative_texts, negative_source = self._ui_semantic_texts(
            serial,
            "reg001-before-add",
        )
        before_ids = [
            statement["id"]
            for statement in self._active_listings()
            if statement.get("object", {}).get("id") == descriptor
        ]
        self._add_app_from_link(serial, descriptor)
        after = self._listing_statements(descriptor)
        displayed_texts, displayed_source = self._ui_semantic_texts(
            serial,
            "reg001-after-add",
        )
        positive = {
            "descriptor_url": descriptor,
            "listed_object_urls": [
                statement.get("object", {}).get("id")
                for statement in after
                if isinstance(statement.get("object", {}).get("id"), str)
            ],
            "displayed_urls": (
                [descriptor]
                if "JiMS Mobile_KB" in displayed_texts
                else []
            ),
            "statement_ids": [
                statement["id"]
                for statement in after
                if isinstance(statement.get("id"), str)
            ],
        }
        negative = {
            "descriptor_url": descriptor,
            "listed_object_urls": (
                [descriptor] if before_ids else []
            ),
            "displayed_urls": (
                [descriptor]
                if "JiMS Mobile_KB" in negative_texts
                else []
            ),
            "statement_ids": before_ids,
        }
        return positive, negative, [
            *sources,
            negative_source,
            displayed_source,
            self.commands.last_command_id or "",
        ]

    def _run_reg_004(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        descriptor = self._descriptor_url()
        existing = self._listing_statements(descriptor)
        if not existing:
            self._add_app_from_link(serial, descriptor)
            existing = self._listing_statements(descriptor)
        self._return_to_apps_home(serial)
        _, home_source = self._ui_semantic_texts(
            serial,
            "reg004-repeated-listings",
        )
        all_ids = [
            statement["id"]
            for statement in existing
            if isinstance(statement.get("id"), str)
        ]
        if len(set(all_ids)) < 2:
            raise RuntimeError(
                "REG-001 must create a repeated listing before REG-004"
            )
        positive = {
            "descriptor_url": descriptor,
            "listing_statement_ids": all_ids,
        }
        negative = {
            "descriptor_url": descriptor,
            "listing_statement_ids": all_ids[:1],
        }
        return positive, negative, [
            home_source,
            self.commands.last_command_id or "",
        ]

    def _run_reg_002(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        self._return_to_apps_home(serial)
        active = self._active_listings()
        texts, home_source = self._ui_semantic_texts(
            serial,
            "reg002-active-home",
        )
        active_ids = [
            statement["id"]
            for statement in active
            if isinstance(statement.get("id"), str)
        ]
        visible_cards = texts.count("JiMS Mobile_KB")
        displayed_ids = (
            active_ids if visible_cards >= len(active_ids) else []
        )
        self._tap_clickable_ancestor(
            serial,
            "reg002-open-descriptor",
            text="JiMS Mobile_KB",
        )
        detail_texts, detail_source = self._ui_semantic_texts(
            serial,
            "reg002-opened-detail",
        )
        descriptor = self._descriptor_url()
        positive = {
            "active_statement_ids": active_ids,
            "displayed_statement_ids": displayed_ids,
            "opened_descriptor_url": (
                descriptor if "JiMS Mobile_KB" in detail_texts else ""
            ),
            "expected_descriptor_url": descriptor,
        }
        negative = dict(positive)
        negative["displayed_statement_ids"] = []
        return positive, negative, [home_source, detail_source]

    def _run_reg_003(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        descriptor = self._descriptor_url()
        unrelated = (
            f"https://localhost:{self.args.publisher_port}"
            "/mobile-kb/descriptor-unrelated.json?reg003=control"
        )
        active = self._active_listings()
        if unrelated not in {
            statement.get("object", {}).get("id")
            for statement in active
        }:
            self._add_app_from_link(serial, unrelated)
            active = self._active_listings()
        target = [
            statement
            for statement in active
            if statement.get("object", {}).get("id") == descriptor
        ]
        if not target:
            self._add_app_from_link(serial, descriptor)
            target = [
                statement
                for statement in self._active_listings()
                if statement.get("object", {}).get("id")
                == descriptor
            ]
        latest = target[-1]
        before_void_ids = {
            statement.get("object", {}).get("id")
            for statement in self._statement_jsons()
            if statement.get("verb", {}).get("id")
            == "http://adlnet.gov/expapi/verbs/voided"
        }
        response = self._void_listing(latest["id"])
        time.sleep(2)
        active_after = self._active_listings()
        urls_after = [
            statement.get("object", {}).get("id")
            for statement in active_after
            if isinstance(statement.get("object", {}).get("id"), str)
        ]
        positive = {
            "voided_listing_id": latest["id"],
            "latest_listing_id": latest["id"],
            "removed_descriptor_url": descriptor,
            "active_urls_after": urls_after,
            "unrelated_url": unrelated,
        }
        negative = dict(positive)
        negative["voided_listing_id"] = next(
            iter(before_void_ids),
            "",
        )
        return positive, negative, [
            response["command_id"],
            self.commands.last_command_id or "",
        ]

    def _listed_app_statement(self, descriptor: str) -> Dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "actor": {
                "name": "Admin Admin",
                "account": {
                    "homePage": (
                        f"http://127.0.0.1:{self.args.server_port}/"
                    ),
                    "name": "1",
                },
            },
            "verb": {"id": "https://id.openeel.org/verb/listed-app"},
            "object": {
                "objectType": "Activity",
                "id": descriptor,
            },
            "context": {
                "contextActivities": {
                    "category": [
                        {
                            "objectType": "Activity",
                            "id": (
                                "https://id.openeel.org/recipes/"
                                "applisting"
                            ),
                        }
                    ]
                }
            },
            "timestamp": _utc_now(),
            "version": "1.0.3",
        }

    def _run_reg_005(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        descriptor = (
            f"https://school-harness.invalid/{self.run_id}/no-actor"
        )
        before = self._statement_digest()
        rejected = self._xapi_request(
            method="POST",
            token=None,
            body=self._listed_app_statement(descriptor),
        )
        after = self._statement_digest()
        positive = {
            "active_actor": False,
            "requested_action": "add",
            "warning_observed": rejected["status"] == 403,
            "statement_digest_before": before,
            "statement_digest_after": after,
        }
        accepted = self._xapi_request(
            method="POST",
            token=self._bearer_token(),
            body=self._listed_app_statement(
                descriptor + "-control"
            ),
        )
        changed = self._statement_digest()
        negative = {
            "active_actor": True,
            "requested_action": "add",
            "warning_observed": False,
            "statement_digest_before": after,
            "statement_digest_after": changed,
        }
        return positive, negative, [
            rejected["command_id"],
            accepted["command_id"],
            self.commands.last_command_id or "",
        ]

    def _run_xapi_012(
        self,
        serial: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
        self._return_to_apps_home(serial)
        self._wait_ui_node(
            serial,
            "assignment-app-synchronized",
            text="JiMS Mobile_KB",
            timeout=90,
        )
        mobile_apk = self._artifact_path(
            self.args.mobile_kb_apk,
            "mobile_kb_apk",
            "--mobile-kb-apk",
        )
        self._adb(
            serial,
            "uninstall",
            self.args.canapp_package,
            check=False,
        )
        uninstall_source = self.commands.last_command_id or ""
        try:
            fallback = self._capture_launch(
                serial,
                choose_native=False,
            )
        finally:
            self._adb(
                serial,
                "install",
                "-r",
                "-t",
                str(mobile_apk),
                timeout=300,
            )
        install_source = self.commands.last_command_id or ""
        launch_url = fallback.get("fallback_url")
        if not isinstance(launch_url, str):
            raise RuntimeError("xAPI assignment fixture lacks WebView URL")
        parameters = urllib.parse.parse_qs(
            urllib.parse.urlsplit(launch_url).query
        )
        endpoint = parameters.get("endpoint", [None])[0]
        authorization = parameters.get("auth", [None])[0]
        if not isinstance(endpoint, str) or not isinstance(
            authorization,
            str,
        ):
            raise RuntimeError("WebView launch omitted xAPI credentials")
        device_port = urllib.parse.urlsplit(endpoint).port
        if not isinstance(device_port, int):
            raise RuntimeError("WebView xAPI endpoint omitted local port")
        host_port = self.args.publisher_port + 1000
        self._adb(
            serial,
            "forward",
            f"tcp:{host_port}",
            f"tcp:{device_port}",
        )
        forward_source = self.commands.last_command_id or ""
        endpoint_parts = urllib.parse.urlsplit(endpoint)
        host_endpoint = urllib.parse.urlunsplit(
            (
                "http",
                f"127.0.0.1:{host_port}",
                endpoint_parts.path,
                "",
                "",
            )
        )
        assignment_id = (
            f"https://school-harness.invalid/{self.run_id}/assignment"
        )
        statement_id = str(uuid.uuid4())
        original = self._xapi_statement(
            statement_id=statement_id,
            activity_id=(
                f"https://school-harness.invalid/{self.run_id}/lesson"
            ),
        )
        assignment_endpoint = (
            host_endpoint.rstrip("/")
            + "/openeel_assignment/"
            + urllib.parse.quote(
                urllib.parse.quote(assignment_id, safe=""),
                safe="",
            )
            + "/statements"
        )
        stored_response = self._http_json(
            assignment_endpoint,
            method="POST",
            body=original,
            headers={
                "Authorization": authorization,
                "X-Experience-API-Version": "1.0.3",
                "Content-Type": "application/json",
                "Origin": (
                    f"https://localhost:{self.args.publisher_port}"
                ),
            },
        )
        stored = None
        deadline = time.monotonic() + 30
        while not isinstance(stored, dict) and time.monotonic() < deadline:
            stored = next(
                (
                    statement
                    for statement in self._statement_jsons()
                    if statement.get("id") == statement_id
                ),
                None,
            )
            if not isinstance(stored, dict):
                time.sleep(1)
        if not isinstance(stored, dict):
            raise RuntimeError("assignment-scoped statement was not stored")
        grouping = (
            stored.get("context", {})
            .get("contextActivities", {})
            .get("grouping", [])
        )
        grouping_ids = [
            item.get("id")
            for item in grouping
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
        ]
        positive = {
            "assignment_id": assignment_id,
            "stored_grouping_ids": grouping_ids,
            "storage_succeeded": (
                200 <= stored_response["status"] < 300
            ),
            "original_statement_digest": _json_sha256(original),
            "stored_statement_digest": _json_sha256(stored),
        }
        control_id = str(uuid.uuid4())
        control = self._xapi_statement(
            statement_id=control_id,
            activity_id=original["object"]["id"],
        )
        control_response = self._http_json(
            host_endpoint.rstrip("/") + "/statements",
            method="POST",
            body=control,
            headers={
                "Authorization": authorization,
                "X-Experience-API-Version": "1.0.3",
                "Content-Type": "application/json",
                "Origin": (
                    f"https://localhost:{self.args.publisher_port}"
                ),
            },
        )
        control_stored = next(
            (
                statement
                for statement in self._statement_jsons()
                if statement.get("id") == control_id
            ),
            {},
        )
        control_grouping = (
            control_stored.get("context", {})
            .get("contextActivities", {})
            .get("grouping", [])
        )
        negative = {
            "assignment_id": assignment_id,
            "stored_grouping_ids": [
                item.get("id")
                for item in control_grouping
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
            ],
            "storage_succeeded": (
                200 <= control_response["status"] < 300
            ),
            "original_statement_digest": _json_sha256(control),
            "stored_statement_digest": _json_sha256(control_stored),
        }
        return positive, negative, [
            uninstall_source,
            *fallback["source_ids"],
            install_source,
            forward_source,
            stored_response["command_id"],
            control_response["command_id"],
            self.commands.last_command_id or "",
        ]

    def _write_supporting_evidence(self) -> None:
        build = self.state.operation("build").get("result", {})
        if not isinstance(build, Mapping):
            raise RuntimeError("build result is unavailable")
        required_build_strings = (
            "respect_revision",
            "mobile_kb_revision",
            "respect_apk_sha256",
            "mobile_kb_apk_sha256",
        )
        if any(
            not isinstance(build.get(key), str) or not build.get(key)
            for key in required_build_strings
        ):
            raise RuntimeError("build result is incomplete")

        scenario = self._scenario()
        scenario_path = self.evidence_dir / "scenario.json"
        _write_json(scenario_path, scenario)
        probes = self._probe_devices()
        validate_scenario_routing(scenario, probes)

        source_revisions = {
            "artifact_type": "respect_school_source_revisions",
            "format_version": "1.0.0",
            "respect": {
                "revision": build["respect_revision"],
                "source_clean": build.get("respect_source_clean"),
            },
            "mobile_kb": {
                "revision": build["mobile_kb_revision"],
                "source_status_sha256": build.get(
                    "mobile_kb_source_status_sha256"
                ),
            },
        }
        _write_json(
            self.evidence_dir / "source-revisions.json",
            source_revisions,
        )

        receipt_path = Path(str(build.get("build_receipt", "")))
        receipt = (
            _read_object(receipt_path)
            if receipt_path.is_file()
            else {}
        )
        tls = build.get("tls", {})
        ca_cert = (
            Path(str(tls.get("ca_cert")))
            if isinstance(tls, Mapping) and tls.get("ca_cert")
            else None
        )
        public_build = {
            key: value
            for key, value in build.items()
            if key != "tls"
        }
        public_build["respect_build_receipt"] = receipt
        public_build["ca_certificate_sha256"] = (
            _sha256(ca_cert)
            if ca_cert is not None and ca_cert.is_file()
            else None
        )
        _write_json(
            self.evidence_dir / "artifact-receipts.json",
            public_build,
        )

        statements = self._statement_jsons()
        statement_ids = [
            statement["id"]
            for statement in statements
            if isinstance(statement.get("id"), str)
            and statement["id"].strip()
        ]
        _write_json(
            self.evidence_dir / "database-exports.json",
            {
                "artifact_type": "respect_school_database_digest_export",
                "format_version": "1.0.0",
                "statement_count": len(statements),
                "statement_ids": statement_ids,
                "statements_sha256": _json_sha256(statements),
                "captured_at": _utc_now(),
            },
        )
        seed = self.state.operation("seed").get("result", {})
        _write_json(
            self.evidence_dir / "service-config.json",
            {
                "artifact_type": "respect_school_service_configuration",
                "format_version": "1.0.0",
                "server": {
                    "base_url": (
                        f"http://127.0.0.1:{self.args.server_port}/"
                    ),
                    "port": self.args.server_port,
                },
                "publisher": {
                    "origin": (
                        f"https://localhost:{self.args.publisher_port}"
                    ),
                    "port": self.args.publisher_port,
                    "publication_tree_sha256": (
                        seed.get("publication_tree_sha256")
                        if isinstance(seed, Mapping)
                        else None
                    ),
                    "ca_certificate_sha256": (
                        seed.get("ca_certificate_sha256")
                        if isinstance(seed, Mapping)
                        else None
                    ),
                },
            },
        )

        command_records = []
        if self.commands.path.is_file():
            command_records = [
                json.loads(line)
                for line in self.commands.path.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
        row_results_path = self.evidence_dir / "row-results.json"
        row_results = (
            _read_object(row_results_path).get("results", {})
            if row_results_path.is_file()
            else {}
        )
        _write_json(
            self.evidence_dir / "timestamps.json",
            {
                "artifact_type": "respect_school_run_timestamps",
                "format_version": "1.0.0",
                "first_command_started_at": (
                    command_records[0].get("started_at")
                    if command_records
                    else None
                ),
                "last_command_completed_at": (
                    command_records[-1].get(
                        "completed_at",
                        command_records[-1].get("started_at"),
                    )
                    if command_records
                    else None
                ),
                "row_completed_at": {
                    row_id: result.get("completed_at")
                    for row_id, result in row_results.items()
                    if isinstance(result, Mapping)
                },
                "evidence_finalized_at": _utc_now(),
            },
        )

        nonce = self.state.value.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            raise RuntimeError("run nonce is unavailable")
        manifest = build_run_manifest(
            run_id=self.run_id,
            nonce=nonce,
            evidence_dir=self.evidence_dir,
            respect_revision=str(build["respect_revision"]),
            mobile_kb_revision=str(build["mobile_kb_revision"]),
            respect_apk_sha256=str(build["respect_apk_sha256"]),
            mobile_kb_apk_sha256=str(build["mobile_kb_apk_sha256"]),
            scenario_sha256=_sha256(scenario_path),
            emulator_probes=probes,
        )
        _write_json(self.evidence_dir / "run-manifest.json", manifest)

    def collect_evidence(self) -> Dict[str, Any]:
        records = self._load_row_records()
        challenge = os.environ.get("RESPECT_TESTKIT_CHALLENGE")
        target_digest = os.environ.get("RESPECT_TESTKIT_TARGET_DIGEST")
        external = bool(challenge and target_digest)
        nonce = (
            challenge
            if external
            else self.state.value.get("nonce")
        )
        if not isinstance(nonce, str) or not nonce:
            raise ValueError("run nonce is missing")
        observations: Dict[str, Any] = {}
        scenario = self._scenario()
        for row_id in scenario["selected_rows"]:
            record = records.get(row_id)
            if not isinstance(record, dict):
                raise ValueError(f"missing row record: {row_id}")
            validate_row_record(
                record,
                run_nonce=nonce,
                expected_device=scenario["row_devices"][row_id],
                expected_package=self.args.canapp_package,
            )
            observations[row_id] = record["positive"]
        bundle = {
            "artifact_type": "respect_platform_raw_observations",
            "format_version": "1.0.0",
            "challenge": (
                challenge if external else nonce
            ),
            "target_digest": (
                target_digest
                if external
                else self.state.value.get("target_digest")
            ),
            "device_id": (
                os.environ.get("RESPECT_TESTKIT_DEVICE_ID")
                if external
                else self.args.api30_plus_serial
            ),
            "respect_apk_sha256": (
                os.environ.get("RESPECT_TESTKIT_RESPECT_APK_SHA256")
                if external
                else self.state.operation("build")
                .get("result", {})
                .get("respect_apk_sha256")
            ),
            "respect_package": self.args.respect_package,
            "canapp_package": self.args.canapp_package,
            "observations": observations,
        }
        _write_json(
            self.evidence_dir / "raw-provider-observations.json",
            bundle,
        )
        self._write_supporting_evidence()
        if external:
            print(json.dumps(bundle, sort_keys=True))
        return bundle

    def run_row(self, row_id: str) -> Dict[str, Any]:
        if row_id not in PLATFORM_ROW_IDS:
            raise ValueError(f"unsupported row: {row_id}")
        if not self.state.completed("seed"):
            raise RuntimeError("--seed must complete before --run-row")
        scenario = self._scenario()
        probes = self._probe_devices()
        validate_scenario_routing(scenario, probes)
        serial = scenario["row_devices"][row_id]
        before = self._health_control(serial)
        if before["status"] != "healthy":
            raise RuntimeError(f"{row_id} preflight health control failed")
        if row_id == "AUTH-002":
            positive, negative, source_ids = self._run_auth_002()
        elif row_id == "LAUNCH-001":
            positive, negative, source_ids = self._run_native_launch(
                serial,
                api_level=probes[serial]["api_level"],
                row_id=row_id,
            )
        elif row_id == "LAUNCH-002":
            positive, negative, source_ids = self._run_launch_002(
                serial
            )
        elif row_id == "OFFLINE-001":
            positive, negative, source_ids = self._run_offline_001(
                serial
            )
        elif row_id == "OFFLINE-002":
            positive, negative, source_ids = self._run_offline_002(
                serial
            )
        elif row_id == "REG-001":
            positive, negative, source_ids = self._run_reg_001(serial)
        elif row_id == "REG-004":
            positive, negative, source_ids = self._run_reg_004(serial)
        elif row_id == "REG-002":
            positive, negative, source_ids = self._run_reg_002(serial)
        elif row_id == "REG-003":
            positive, negative, source_ids = self._run_reg_003(serial)
        elif row_id == "REG-005":
            positive, negative, source_ids = self._run_reg_005()
        elif row_id == "XAPI-012":
            positive, negative, source_ids = self._run_xapi_012(
                serial
            )
        elif row_id == "LAUNCH-009":
            positive, negative, source_ids = self._run_native_launch(
                serial,
                api_level=probes[serial]["api_level"],
                row_id=row_id,
            )
        elif row_id == "XAPI-020":
            positive, negative, source_ids = self._run_xapi_020()
        else:
            raise AssertionError(row_id)
        after = self._health_control(serial)
        record = self._persist_row_record(
            row_id,
            serial=serial,
            positive=positive,
            negative=negative,
            before=before,
            after=after,
            source_ids=[
                before["command_id"],
                *source_ids,
                after["command_id"],
            ],
        )
        results_path = self.evidence_dir / "row-results.json"
        results = (
            _read_object(results_path)
            if results_path.is_file()
            else {
                "artifact_type": "respect_school_row_results",
                "format_version": "1.0.0",
                "run_id": self.run_id,
                "results": {},
            }
        )
        passed, detail = evaluate_platform_observation(
            row_id,
            positive,
        )
        results.setdefault("results", {})[row_id] = {
            "passed": passed,
            "detail": detail,
            "completed_at": _utc_now(),
        }
        _write_json(results_path, results)
        _write_json(self.state.path, self.state.value, private=True)
        return record

    def run_all(self) -> Dict[str, Any]:
        self.provision()
        if not self.state.completed("build"):
            self.build()
        if not self.state.completed("seed"):
            self.seed()
        nonce = secrets.token_hex(24)
        self.state.value["nonce"] = nonce
        self.state.value["target_digest"] = _sha256(
            self._artifact_path(
                self.args.mobile_kb_apk,
                "mobile_kb_apk",
                "--mobile-kb-apk",
            )
        )
        _write_json(
            self.state.path,
            self.state.value,
            private=True,
        )
        results = {
            row_id: self.run_row(row_id)
            for row_id in SCHOOL_ROW_ORDER
        }
        observations = self.collect_evidence()
        return {
            "rows": results,
            "raw_provider_observations": observations,
            "evidence_dir": str(self.evidence_dir),
        }

    def diagnose(self) -> Dict[str, Any]:
        probes = self._probe_devices()
        scenario = self._scenario()
        validate_scenario_routing(scenario, probes)
        result = {
            "run_id": self.run_id,
            "state": self.state.value,
            "devices": probes,
            "scenario": scenario,
            "ports": {
                str(port): self._port_open(port)
                for port in (
                    self.args.server_port,
                    self.args.publisher_port,
                )
            },
        }
        _write_json(self.evidence_dir / "diagnosis.json", result)
        return result

    def _port_open(self, port: int) -> bool:
        with socket.socket() as connection:
            connection.settimeout(1)
            return connection.connect_ex(("127.0.0.1", port)) == 0

    def stop(self) -> Dict[str, Any]:
        stopped = []
        runtime = self.state.value.get("runtime", {})
        for name in ("server_pid", "publisher_pid"):
            pid = runtime.get(name)
            if isinstance(pid, int):
                completed = self.commands.run(
                    ["kill", "-TERM", str(pid)],
                    check=False,
                )
                stopped.append(
                    {"name": name, "pid": pid, "exit": completed.returncode}
                )
        adb = self._tool("platform-tools/adb")
        for serial in (
            self.args.api30_plus_serial,
            self.args.api29_serial,
        ):
            for package in (
                self.args.respect_package,
                self.args.canapp_package,
            ):
                self.commands.run(
                    [
                        str(adb),
                        "-s",
                        serial,
                        "shell",
                        "am",
                        "force-stop",
                        package,
                    ],
                    check=False,
                )
        return {"stopped": stopped}

    def clean(self) -> Dict[str, Any]:
        self.stop()
        protected = self.evidence_dir.resolve()
        for child in list(self.state_dir.iterdir()):
            if child.resolve() == protected:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        return {
            "cleaned": str(self.state_dir),
            "preserved_evidence": str(self.evidence_dir),
        }


def _operation_name(args: argparse.Namespace) -> str:
    for name in (
        "provision",
        "build",
        "seed",
        "run_row",
        "run_all",
        "collect_evidence",
        "diagnose",
        "stop",
        "clean_ephemeral_state",
    ):
        if getattr(args, name):
            return name
    raise ValueError("no operation selected")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        harness = SchoolHarness(args)
        operation = _operation_name(args)
        if operation == "provision":
            result = harness.provision()
        elif operation == "build":
            result = harness.build()
        elif operation == "seed":
            result = harness.seed()
        elif operation == "run_row":
            result = harness.run_row(args.run_row)
        elif operation == "run_all":
            result = harness.run_all()
        elif operation == "collect_evidence":
            result = harness.collect_evidence()
        elif operation == "diagnose":
            result = harness.diagnose()
        elif operation == "stop":
            result = harness.stop()
        else:
            result = harness.clean()
        if operation != "collect_evidence" or not os.environ.get(
            "RESPECT_TESTKIT_CHALLENGE"
        ):
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
