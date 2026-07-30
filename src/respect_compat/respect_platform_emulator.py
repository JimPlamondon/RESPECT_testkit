# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Emulator-hosted RESPECT Platform observation provider."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from .android_apk import inspect_apk, probe_android_device
from .target import CanAppTarget


PLATFORM_ROW_IDS = {
    "AUTH-002",
    "LAUNCH-001",
    "LAUNCH-002",
    "LAUNCH-009",
    "OFFLINE-001",
    "OFFLINE-002",
    "REG-001",
    "REG-002",
    "REG-003",
    "REG-004",
    "REG-005",
    "XAPI-012",
    "XAPI-020",
}

KNOWN_BROWSER_PACKAGES = {
    "com.android.chrome",
    "com.mi.globalbrowser",
    "com.sec.android.app.sbrowser",
    "org.chromium.webview_shell",
    "org.mozilla.firefox",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def load_platform_scenario(path: Path) -> Dict[str, Any]:
    value = _read_object(path)
    if value.get("artifact_type") != "respect_platform_emulator_scenario":
        raise ValueError("not a RESPECT Platform emulator scenario")
    if value.get("format_version") != "1.0.0":
        raise ValueError("unsupported RESPECT Platform scenario version")
    for field in ("respect_package", "canapp_package"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f"platform scenario requires {field}")
    command = value.get("provider_command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(item, str) or not item for item in command)
    ):
        raise ValueError("provider_command must be a nonempty argument array")
    selected_rows = value.get("selected_rows")
    if (
        not isinstance(selected_rows, list)
        or not selected_rows
        or any(row_id not in PLATFORM_ROW_IDS for row_id in selected_rows)
        or len(selected_rows) != len(set(selected_rows))
    ):
        raise ValueError("selected_rows contains an unsupported or duplicate row")
    row_devices = value.get("row_devices", {})
    if not isinstance(row_devices, dict) or any(
        row_id not in selected_rows
        or not isinstance(mapped_device, str)
        or not mapped_device
        for row_id, mapped_device in row_devices.items()
    ):
        raise ValueError(
            "row_devices must map selected row IDs to nonempty device IDs"
        )
    return value


def load_platform_build_receipt(
    path: Path,
    *,
    respect_apk: Path,
    package_id: str,
) -> Dict[str, Any]:
    value = _read_object(path)
    if value.get("artifact_type") != "respect_platform_build_receipt":
        raise ValueError("not a RESPECT Platform build receipt")
    if value.get("format_version") != "1.0.0":
        raise ValueError("unsupported RESPECT Platform receipt version")
    if value.get("apk_sha256") != _sha256(respect_apk):
        raise ValueError("RESPECT Platform APK digest does not match receipt")
    if value.get("package_id") != package_id:
        raise ValueError("RESPECT Platform package does not match receipt")
    for field in ("build_id", "respect_revision"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise ValueError(f"RESPECT Platform receipt requires {field}")
    return value


def _same_nonempty(left: Any, right: Any) -> bool:
    return isinstance(left, str) and bool(left) and left == right


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str) and item}


def _evaluate_auth(observed: Mapping[str, Any]) -> bool:
    return (
        200 <= observed.get("valid_status", 0) < 300
        and observed.get("missing_status") == 403
        and observed.get("altered_status") == 403
        and _same_nonempty(
            observed.get("effect_digest_before"),
            observed.get("effect_digest_after"),
        )
    )


def _evaluate_launch_001(observed: Mapping[str, Any]) -> bool:
    selected = observed.get("selected_package")
    return (
        observed.get("api_level", 0) >= 30
        and observed.get("native_attempted") is True
        and isinstance(selected, str)
        and bool(selected)
        and selected not in KNOWN_BROWSER_PACKAGES
        and observed.get("activity_package") == selected
        and _same_nonempty(
            observed.get("launch_url"),
            observed.get("expected_launch_url"),
        )
    )


def _evaluate_launch_002(observed: Mapping[str, Any]) -> bool:
    return (
        isinstance(observed.get("native_failure"), str)
        and bool(observed["native_failure"])
        and observed.get("selected_activity")
        == "world.respect.WebViewActivity"
        and observed.get("page_loaded") is True
        and _same_nonempty(
            observed.get("webview_url"),
            observed.get("expected_launch_url"),
        )
    )


def _evaluate_launch_009(observed: Mapping[str, Any]) -> bool:
    resolved = _string_set(observed.get("resolved_packages"))
    selected = observed.get("selected_package")
    return (
        0 < observed.get("api_level", 0) < 30
        and isinstance(selected, str)
        and selected in resolved
        and selected not in KNOWN_BROWSER_PACKAGES
        and observed.get("activity_package") == selected
        and _same_nonempty(
            observed.get("launch_url"),
            observed.get("expected_launch_url"),
        )
    )


def _evaluate_offline_001(observed: Mapping[str, Any]) -> bool:
    declared = _string_set(observed.get("declared_urls"))
    requested = _string_set(observed.get("requested_urls"))
    unrelated = observed.get("unrelated_url")
    return (
        bool(declared)
        and declared.issubset(requested)
        and unrelated not in requested
        and observed.get("pin_state") == "complete"
    )


def _evaluate_offline_002(observed: Mapping[str, Any]) -> bool:
    return (
        observed.get("remote_unavailable") is True
        and observed.get("offline_usable") is True
        and observed.get("never_fetched_available") is False
        and _same_nonempty(
            observed.get("online_digest"),
            observed.get("offline_digest"),
        )
    )


def _evaluate_reg_001(observed: Mapping[str, Any]) -> bool:
    descriptor = observed.get("descriptor_url")
    return (
        isinstance(descriptor, str)
        and descriptor in _string_set(observed.get("listed_object_urls"))
        and descriptor in _string_set(observed.get("displayed_urls"))
        and bool(_string_set(observed.get("statement_ids")))
    )


def _evaluate_reg_002(observed: Mapping[str, Any]) -> bool:
    active = _string_set(observed.get("active_statement_ids"))
    displayed = _string_set(observed.get("displayed_statement_ids"))
    return (
        bool(active)
        and active == displayed
        and _same_nonempty(
            observed.get("opened_descriptor_url"),
            observed.get("expected_descriptor_url"),
        )
    )


def _evaluate_reg_003(observed: Mapping[str, Any]) -> bool:
    removed = observed.get("removed_descriptor_url")
    active_after = _string_set(observed.get("active_urls_after"))
    unrelated = observed.get("unrelated_url")
    return (
        _same_nonempty(
            observed.get("voided_listing_id"),
            observed.get("latest_listing_id"),
        )
        and isinstance(removed, str)
        and removed not in active_after
        and isinstance(unrelated, str)
        and unrelated in active_after
    )


def _evaluate_reg_004(observed: Mapping[str, Any]) -> bool:
    identifiers = observed.get("listing_statement_ids")
    return (
        isinstance(observed.get("descriptor_url"), str)
        and isinstance(identifiers, list)
        and len(identifiers) >= 2
        and len(identifiers) == len(_string_set(identifiers))
    )


def _evaluate_reg_005(observed: Mapping[str, Any]) -> bool:
    return (
        observed.get("active_actor") is False
        and observed.get("requested_action") in {"add", "remove"}
        and observed.get("warning_observed") is True
        and _same_nonempty(
            observed.get("statement_digest_before"),
            observed.get("statement_digest_after"),
        )
    )


def _evaluate_xapi_012(observed: Mapping[str, Any]) -> bool:
    assignment_id = observed.get("assignment_id")
    return (
        isinstance(assignment_id, str)
        and assignment_id
        in _string_set(observed.get("stored_grouping_ids"))
        and observed.get("storage_succeeded") is True
        and isinstance(observed.get("original_statement_digest"), str)
        and bool(observed["original_statement_digest"])
        and isinstance(observed.get("stored_statement_digest"), str)
        and bool(observed["stored_statement_digest"])
    )


def _evaluate_xapi_020(observed: Mapping[str, Any]) -> bool:
    headers = observed.get("headers")
    if not isinstance(headers, dict):
        return False
    normalized_headers = {
        str(key).lower(): value for key, value in headers.items()
    }
    required_headers = {
        "last-modified",
        "x-experience-api-version",
        "x-experience-api-consistent-through",
    }
    submitted = _string_set(observed.get("submitted_statement_ids"))
    returned = _string_set(observed.get("returned_statement_ids"))
    return (
        observed.get("status") == 200
        and required_headers.issubset(normalized_headers)
        and all(normalized_headers[key] for key in required_headers)
        and bool(submitted)
        and submitted == returned
        and observed.get("nonmatching_statement_id") not in returned
    )


_ORACLES: Dict[str, Callable[[Mapping[str, Any]], bool]] = {
    "AUTH-002": _evaluate_auth,
    "LAUNCH-001": _evaluate_launch_001,
    "LAUNCH-002": _evaluate_launch_002,
    "LAUNCH-009": _evaluate_launch_009,
    "OFFLINE-001": _evaluate_offline_001,
    "OFFLINE-002": _evaluate_offline_002,
    "REG-001": _evaluate_reg_001,
    "REG-002": _evaluate_reg_002,
    "REG-003": _evaluate_reg_003,
    "REG-004": _evaluate_reg_004,
    "REG-005": _evaluate_reg_005,
    "XAPI-012": _evaluate_xapi_012,
    "XAPI-020": _evaluate_xapi_020,
}


def evaluate_platform_observation(
    row_id: str,
    observed: Mapping[str, Any],
) -> Tuple[bool, str]:
    oracle = _ORACLES.get(row_id)
    if oracle is None:
        raise ValueError(f"no emulator platform oracle for {row_id}")
    passed = oracle(observed)
    return (
        passed,
        (
            "Suite-controlled emulator observation satisfied the "
            f"{row_id} production-path oracle."
            if passed
            else (
                "Suite-controlled emulator observation violated the "
                f"{row_id} production-path oracle."
            )
        ),
    )


def validate_raw_observation_bundle(
    value: Mapping[str, Any],
    *,
    challenge: str,
    target_digest: str,
    device_id: str,
    respect_apk_sha256: str,
    respect_package: str,
    canapp_package: str,
    selected_rows: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    expected = {
        "artifact_type": "respect_platform_raw_observations",
        "format_version": "1.0.0",
        "challenge": challenge,
        "target_digest": target_digest,
        "device_id": device_id,
        "respect_apk_sha256": respect_apk_sha256,
        "respect_package": respect_package,
        "canapp_package": canapp_package,
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise ValueError(
                f"RESPECT Platform observation {field} does not match run"
            )
    observations = value.get("observations")
    if not isinstance(observations, dict):
        raise ValueError("RESPECT Platform observations must be an object")
    selected = set(selected_rows)
    if set(observations) != selected:
        raise ValueError(
            "RESPECT Platform observations do not match selected rows"
        )
    if any(not isinstance(item, dict) for item in observations.values()):
        raise ValueError("each RESPECT Platform observation must be an object")
    return observations


def run_respect_platform_emulator(
    target: CanAppTarget,
    *,
    device_id: str,
    respect_apk: Path,
    build_receipt: Path,
    scenario_path: Path,
    challenge: str,
    adb: Optional[Path] = None,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Dict[str, Dict[str, Any]]:
    if not respect_apk.is_file():
        raise ValueError("RESPECT Platform APK is missing")
    scenario = load_platform_scenario(scenario_path)
    inspection = inspect_apk(respect_apk)
    respect_package = scenario["respect_package"]
    if inspection.get("package_id") != respect_package:
        raise ValueError("scenario RESPECT package does not match APK")
    receipt = load_platform_build_receipt(
        build_receipt,
        respect_apk=respect_apk,
        package_id=respect_package,
    )
    row_devices = {
        row_id: scenario.get("row_devices", {}).get(row_id, device_id)
        for row_id in scenario["selected_rows"]
    }
    device_ids = sorted({device_id, *row_devices.values()})
    probes = {}
    for platform_device_id in device_ids:
        platform_probe = probe_android_device(platform_device_id, adb=adb)
        api_level = platform_probe.get("api_level")
        if isinstance(api_level, str) and api_level.isdigit():
            platform_probe["api_level"] = int(api_level)
        if (
            not platform_probe.get("healthy")
            or platform_probe.get("emulator") is not True
        ):
            raise ValueError(
                "RESPECT Platform provider requires every row device to be "
                f"a healthy Android emulator: {platform_device_id}"
            )
        probes[platform_device_id] = platform_probe
    probe = probes[device_id]
    target.metadata["device_id"] = device_id
    target.metadata["device_probe"] = probe
    apk_digest = _sha256(respect_apk)
    adb_tool = adb
    if adb_tool is None:
        located_adb = shutil.which("adb")
        if located_adb:
            adb_tool = Path(located_adb)
        else:
            android_home = os.environ.get(
                "ANDROID_HOME"
            ) or os.environ.get("ANDROID_SDK_ROOT")
            candidate = (
                Path(android_home).expanduser() / "platform-tools" / "adb"
                if android_home
                else None
            )
            if candidate is None or not candidate.is_file():
                raise FileNotFoundError("adb")
            adb_tool = candidate
    for platform_device_id in device_ids:
        install = command_runner(
            [
                str(adb_tool),
                "-s",
                platform_device_id,
                "install",
                "-r",
                "-t",
                str(respect_apk),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if install.returncode != 0:
            raise RuntimeError(
                "could not install the pinned RESPECT Platform APK on "
                f"{platform_device_id}: {install.stderr.strip()}"
            )
    environment = os.environ.copy()
    environment.update(
        {
            "RESPECT_TESTKIT_CHALLENGE": challenge,
            "RESPECT_TESTKIT_TARGET_DIGEST": target.digest,
            "RESPECT_TESTKIT_DEVICE_ID": device_id,
            "RESPECT_TESTKIT_RESPECT_APK": str(respect_apk.resolve()),
            "RESPECT_TESTKIT_RESPECT_APK_SHA256": apk_digest,
            "RESPECT_TESTKIT_RESPECT_PACKAGE": respect_package,
            "RESPECT_TESTKIT_CANAPP_PACKAGE": scenario["canapp_package"],
            "RESPECT_TESTKIT_SCENARIO": str(scenario_path.resolve()),
            "RESPECT_TESTKIT_ROW_DEVICES": json.dumps(
                row_devices,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
    )
    completed = command_runner(
        scenario["provider_command"],
        cwd=scenario_path.parent,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=int(scenario.get("timeout_seconds", 900)),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "RESPECT Platform observation provider failed: "
            f"exit={completed.returncode}, stderr={completed.stderr.strip()}"
        )
    try:
        raw_bundle = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(
            "RESPECT Platform provider did not emit one JSON object"
        ) from error
    if not isinstance(raw_bundle, dict):
        raise ValueError("RESPECT Platform provider output is not an object")
    raw_observations = validate_raw_observation_bundle(
        raw_bundle,
        challenge=challenge,
        target_digest=target.digest,
        device_id=device_id,
        respect_apk_sha256=apk_digest,
        respect_package=respect_package,
        canapp_package=scenario["canapp_package"],
        selected_rows=scenario["selected_rows"],
    )
    observations: Dict[str, Dict[str, Any]] = {}
    for row_id, observed in raw_observations.items():
        row_device_id = row_devices[row_id]
        row_probe = probes[row_device_id]
        observed = dict(observed)
        if row_id in {"LAUNCH-001", "LAUNCH-009"}:
            claimed_api_level = observed.get("api_level")
            actual_api_level = row_probe.get("api_level")
            if (
                claimed_api_level is not None
                and claimed_api_level != actual_api_level
            ):
                raise ValueError(
                    f"{row_id} claimed API level does not match its emulator"
                )
            observed["api_level"] = actual_api_level
        passed, message = evaluate_platform_observation(row_id, observed)
        observations[row_id] = {
            "state": "pass" if passed else "fail",
            "observed": observed,
            "message": message,
            "source": "suite-owned-respect-platform-emulator-provider",
            "platform_evidence": {
                "signed": False,
                "real_platform": True,
                "independently_attributed": True,
                "real_build_id": receipt["build_id"],
                "respect_revision": receipt["respect_revision"],
                "respect_apk_sha256": apk_digest,
                "respect_package": respect_package,
                "device_id": row_device_id,
                "device_environment": row_probe,
                "challenge": challenge,
            },
        }
    target.metadata["environment_observations"] = observations
    target.metadata["_controlled_respect_platform"] = True
    target.metadata["_controlled_runtime"] = True
    target.metadata["respect_platform_runtime_receipt"] = {
        "artifact_type": "respect_platform_runtime_receipt",
        "format_version": "1.0.0",
        "build_id": receipt["build_id"],
        "respect_revision": receipt["respect_revision"],
        "respect_apk_sha256": apk_digest,
        "respect_package": respect_package,
        "primary_device_id": device_id,
        "devices": probes,
        "row_devices": row_devices,
        "challenge": challenge,
        "rows": sorted(observations),
    }
    return observations
