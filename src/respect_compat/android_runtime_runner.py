# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import re
import shlex
import shutil
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .android_apk import inspect_apk, probe_android_device
from .android_runtime_driver import (
    RuntimeBinding,
    project_runtime_observations,
)
from .resources import resource_path
from .target import CanAppTarget


DRIVER_PACKAGE = "org.respect.testkit.runtime"
DRIVER_PROTOCOL_VERSION = "1.0.0"
_PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
_KEY_EVENTS = {"BACK", "ENTER", "HOME"}


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _tree_hash(root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def runtime_driver_source_hash() -> str:
    with resource_path("data/android/native-runtime-driver") as source:
        return _tree_hash(source)


def verify_runtime_driver_receipt(
    driver_apk: Path,
    receipt_path: Path,
) -> Dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("runtime driver receipt must be a JSON object")
    expected = {
        "artifact_type": "respect_native_android_runtime_driver_build_receipt",
        "format_version": DRIVER_PROTOCOL_VERSION,
        "driver_package": DRIVER_PACKAGE,
        "source_tree_sha256": runtime_driver_source_hash(),
        "apk_sha256": _sha256(driver_apk),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("runtime driver build receipt does not match suite source and APK")
    return receipt


def _absolute_https(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def domain_is_verified(association: str, host: str) -> bool:
    return bool(
        re.search(
            rf"(?im)^\s*{re.escape(host)}:\s*(?:verified|1024)\s*$",
            association,
        )
    )


def load_runtime_scenario(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime scenario must be a JSON object")
    if value.get("artifact_type") != "respect_native_android_runtime_scenario":
        raise ValueError("runtime scenario artifact type is invalid")
    if value.get("format_version") != DRIVER_PROTOCOL_VERSION:
        raise ValueError("runtime scenario version is unsupported")
    if not _PACKAGE.fullmatch(str(value.get("canapp_package", ""))):
        raise ValueError("runtime scenario CanApp package is invalid")
    if value.get("driver_package") != DRIVER_PACKAGE:
        raise ValueError("runtime scenario driver package is invalid")
    if not _absolute_https(value.get("launch_url")):
        raise ValueError("runtime scenario launch URL must use HTTPS")
    if not _absolute_https(value.get("endpoint")):
        raise ValueError("runtime scenario endpoint must use HTTPS")
    if not isinstance(value.get("auth"), str) or not value["auth"]:
        raise ValueError("runtime scenario authorization is missing")
    if not isinstance(value.get("actor"), dict):
        raise ValueError("runtime scenario actor must be an object")
    if not _absolute_https(value.get("activity_id")):
        raise ValueError("runtime scenario activity identifier must use HTTPS")
    actions = value.get("actions", [])
    if not isinstance(actions, list) or len(actions) > 100:
        raise ValueError("runtime scenario actions are invalid")
    wait_total = 0
    normalized = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("runtime scenario action must be an object")
        action_type = action.get("type")
        if action_type == "wait":
            milliseconds = action.get("milliseconds")
            if (
                not isinstance(milliseconds, int)
                or milliseconds < 0
                or milliseconds > 10_000
            ):
                raise ValueError("runtime scenario wait action is invalid")
            wait_total += milliseconds
            normalized.append({"type": "wait", "milliseconds": milliseconds})
        elif action_type == "tap":
            x = action.get("x")
            y = action.get("y")
            if (
                not isinstance(x, int)
                or not isinstance(y, int)
                or not 0 <= x <= 10_000
                or not 0 <= y <= 10_000
            ):
                raise ValueError("runtime scenario tap action is invalid")
            normalized.append({"type": "tap", "x": x, "y": y})
        elif action_type == "keyevent":
            key = action.get("key")
            if key not in _KEY_EVENTS:
                raise ValueError("runtime scenario key action is invalid")
            normalized.append({"type": "keyevent", "key": key})
        else:
            raise ValueError("runtime scenario action type is unsupported")
    if wait_total > 60_000:
        raise ValueError("runtime scenario waits exceed the bounded total")
    return {**value, "actions": normalized}


def parse_driver_events(text: str) -> List[Dict[str, Any]]:
    events = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"invalid runtime driver event at line {line_number}: {error}"
            )
        if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
            raise ValueError("runtime driver event is not an object with a kind")
        events.append(value)
    health = [
        item
        for item in events
        if item.get("kind") == "driver_health"
        and item.get("protocol_version") == DRIVER_PROTOCOL_VERSION
        and item.get("package") == DRIVER_PACKAGE
    ]
    if not health:
        raise ValueError("runtime driver health control is missing")
    return events


def _completed(
    runner: Callable[..., subprocess.CompletedProcess],
    command: List[str],
    *,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    result = runner(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"runtime driver command failed ({command[0]}): "
            f"exit={result.returncode}, stderr={result.stderr.strip()}"
        )
    return result


def run_native_android_runtime(
    target: CanAppTarget,
    *,
    device_id: str,
    driver_apk: Path,
    driver_receipt: Path,
    scenario_path: Path,
    scenario_nonce: str,
    certification_mode: bool = False,
    adb: Optional[Path] = None,
    command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> Dict[str, Dict[str, Any]]:
    if target.apk is None or not target.apk.is_file():
        raise ValueError("native Android runtime requires the submitted CanApp APK")
    if not driver_apk.is_file():
        raise ValueError("native Android runtime driver APK is missing")
    verify_runtime_driver_receipt(driver_apk, driver_receipt)
    scenario = load_runtime_scenario(scenario_path)
    target_inspection = inspect_apk(target.apk)
    driver_inspection = inspect_apk(driver_apk)
    if target_inspection.get("package_id") != scenario["canapp_package"]:
        raise ValueError("runtime scenario CanApp package does not match the submitted APK")
    if driver_inspection.get("package_id") != DRIVER_PACKAGE:
        raise ValueError("runtime driver APK package is not suite-owned")
    service_valid = any(
        item.get("exported") is True
        and "org.openeel.action.xapioveripc" in item.get("actions", [])
        for item in driver_inspection.get("services", [])
    )
    if not service_valid:
        raise ValueError("runtime driver APK lacks the suite-owned xAPI IPC service")
    probe = probe_android_device(device_id, adb=adb)
    if not probe.get("healthy"):
        raise ValueError("selected Android Debug Bridge device is unhealthy")
    if certification_mode and probe.get("emulator") is not False:
        raise ValueError(
            "certification mode requires an attributable physical Android device"
        )
    tool = adb
    if tool is None:
        located = shutil.which("adb")
        if not located:
            raise FileNotFoundError("adb")
        tool = Path(located)

    def device(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
        return _completed(
            command_runner,
            [str(tool), "-s", device_id, *args],
            timeout=timeout,
        )

    device("install", "-r", str(driver_apk), timeout=120)
    device("install", "-r", str(target.apk), timeout=120)
    device("shell", "pm", "clear", DRIVER_PACKAGE)
    device("shell", "am", "force-stop", scenario["canapp_package"])
    device(
        "shell",
        "pm",
        "verify-app-links",
        "--re-verify",
        scenario["canapp_package"],
    )
    host = urllib.parse.urlparse(scenario["launch_url"]).hostname or ""
    association = ""
    for _attempt in range(10):
        association = device(
            "shell",
            "pm",
            "get-app-links",
            scenario["canapp_package"],
        ).stdout
        if domain_is_verified(association, host):
            break
        sleeper(1)
    if not domain_is_verified(association, host):
        raise ValueError("Android domain association did not become verified")
    device(
        "shell",
        "pm",
        "set-app-links-user-selection",
        "--user",
        "0",
        "--package",
        scenario["canapp_package"],
        "true",
        host,
    )
    resolution = device(
        "shell",
        "cmd",
        "package",
        "resolve-activity",
        "--brief",
        "-a",
        "android.intent.action.VIEW",
        "-c",
        "android.intent.category.BROWSABLE",
        "-d",
        shlex.quote(scenario["launch_url"]),
    ).stdout.strip()
    launch = device(
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-c",
        "android.intent.category.BROWSABLE",
        "-d",
        shlex.quote(scenario["launch_url"]),
    ).stdout
    for action in scenario["actions"]:
        if action["type"] == "wait":
            sleeper(action["milliseconds"] / 1000)
        elif action["type"] == "tap":
            device(
                "shell",
                "input",
                "tap",
                str(action["x"]),
                str(action["y"]),
            )
        elif action["type"] == "keyevent":
            device("shell", "input", "keyevent", action["key"])
    device("shell", "am", "force-stop", scenario["canapp_package"])
    sleeper(0.25)
    event_text = device(
        "shell",
        "run-as",
        DRIVER_PACKAGE,
        "cat",
        "files/events.jsonl",
    ).stdout
    raw_events = parse_driver_events(event_text)

    apk_sha256 = _sha256(target.apk)
    driver_sha256 = _sha256(driver_apk)
    envelope = {
        "target_digest": target.digest,
        "apk_sha256": apk_sha256,
        "driver_sha256": driver_sha256,
        "device_id": device_id,
        "scenario_nonce": scenario_nonce,
    }
    domain_verified = domain_is_verified(association, host)
    events = [
        {
            "kind": "app_link_resolved",
            "resolved_package": (
                scenario["canapp_package"]
                if scenario["canapp_package"] in f"{resolution}\n{launch}"
                else resolution
            ),
            "domain_verified": domain_verified,
            **envelope,
        },
        *[
            {**event, **envelope}
            for event in raw_events
            if event.get("kind") != "driver_health"
        ],
    ]
    binding = RuntimeBinding(
        target_digest=target.digest,
        apk_sha256=apk_sha256,
        driver_sha256=driver_sha256,
        device_id=device_id,
        scenario_nonce=scenario_nonce,
        canapp_package=scenario["canapp_package"],
        driver_package=DRIVER_PACKAGE,
        endpoint=scenario["endpoint"],
        auth=scenario["auth"],
        actor=scenario["actor"],
        activity_id=scenario["activity_id"],
    )
    observations = project_runtime_observations(events, binding)
    target.metadata["row_observations"] = observations
    target.metadata["_controlled_runtime"] = True
    target.metadata["runtime_driver_receipt"] = {
        "protocol_version": DRIVER_PROTOCOL_VERSION,
        "target_digest": target.digest,
        "apk_sha256": apk_sha256,
        "driver_sha256": driver_sha256,
        "device_id": device_id,
        "scenario_nonce": scenario_nonce,
        "event_count": len(events),
    }
    return observations
