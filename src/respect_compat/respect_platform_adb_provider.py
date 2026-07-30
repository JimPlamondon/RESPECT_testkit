# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Suite-shipped action runner for RESPECT Platform emulator observations."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


def _template(value: str, environment: Mapping[str, str]) -> str:
    pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name not in environment:
            raise ValueError(f"undefined provider environment value: {name}")
        return environment[name]

    return pattern.sub(replace, value)


def _path_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            raise ValueError(f"capture path does not exist: {path}")
    return current


def _project(
    value: Any,
    captures: Mapping[str, Any],
    environment: Mapping[str, str],
) -> Any:
    if isinstance(value, dict) and set(value) == {"capture"}:
        reference = value["capture"]
        if not isinstance(reference, str) or not reference:
            raise ValueError("capture reference must be a nonempty string")
        name, _, path = reference.partition(".")
        if name not in captures:
            raise ValueError(f"unknown provider capture: {name}")
        return (
            _path_value(captures[name], path)
            if path
            else captures[name]
        )
    if isinstance(value, dict):
        return {
            key: _project(item, captures, environment)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _project(item, captures, environment) for item in value
        ]
    if isinstance(value, str):
        return _template(value, environment)
    return value


def _run_command(
    action: Mapping[str, Any],
    *,
    root: Path,
    environment: Mapping[str, str],
) -> Any:
    argv = action.get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise ValueError("provider command action requires an argv array")
    completed = subprocess.run(
        [_template(item, environment) for item in argv],
        cwd=root,
        env=dict(environment),
        check=False,
        capture_output=True,
        text=True,
        timeout=int(action.get("timeout_seconds", 120)),
    )
    if completed.returncode != int(action.get("expected_exit", 0)):
        raise RuntimeError(
            f"provider action failed ({argv[0]}): "
            f"exit={completed.returncode}, stderr={completed.stderr.strip()}"
        )
    output: Any = completed.stdout
    if action.get("parse") == "json":
        output = json.loads(completed.stdout)
    return {
        "stdout": output,
        "stderr": completed.stderr,
        "exit": completed.returncode,
    }


def _run_http(
    action: Mapping[str, Any],
    *,
    environment: Mapping[str, str],
) -> Dict[str, Any]:
    url = action.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("provider HTTP action requires url")
    headers = action.get("headers", {})
    if not isinstance(headers, dict):
        raise ValueError("provider HTTP headers must be an object")
    body = action.get("body")
    data = None
    if body is not None:
        rendered = _project(body, {}, environment)
        data = (
            json.dumps(rendered).encode("utf-8")
            if not isinstance(rendered, str)
            else rendered.encode("utf-8")
        )
    request = urllib.request.Request(
        _template(url, environment),
        data=data,
        method=str(action.get("method", "GET")).upper(),
        headers={
            str(key): _template(str(value), environment)
            for key, value in headers.items()
        },
    )
    try:
        response = urllib.request.urlopen(
            request,
            timeout=float(action.get("timeout_seconds", 30)),
        )
    except urllib.error.HTTPError as error:
        response = error
    response_body = response.read()
    text = response_body.decode("utf-8", errors="replace")
    parsed_json = None
    if action.get("parse") == "json":
        parsed_json = json.loads(text)
    return {
        "status": response.status,
        "headers": dict(response.headers.items()),
        "body": text,
        "body_sha256": hashlib.sha256(response_body).hexdigest(),
        "json": parsed_json,
    }


def _run_read_json(
    action: Mapping[str, Any],
    *,
    root: Path,
    environment: Mapping[str, str],
) -> Any:
    path_value = action.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise ValueError("provider read_json action requires path")
    path = Path(_template(path_value, environment))
    if not path.is_absolute():
        path = root / path
    return json.loads(path.read_text(encoding="utf-8"))


def _run_regex(
    action: Mapping[str, Any],
    captures: Mapping[str, Any],
) -> Dict[str, str]:
    source = action.get("source")
    pattern = action.get("pattern")
    if not isinstance(source, str) or not isinstance(pattern, str):
        raise ValueError("provider regex action requires source and pattern")
    name, _, path = source.partition(".")
    if name not in captures:
        raise ValueError(f"unknown regex source capture: {name}")
    value = _path_value(captures[name], path) if path else captures[name]
    if not isinstance(value, str):
        raise ValueError("provider regex source must be text")
    match = re.search(pattern, value, re.MULTILINE)
    if match is None:
        raise ValueError(f"provider regex did not match: {pattern}")
    if match.groupdict():
        return match.groupdict()
    return {
        str(index): item
        for index, item in enumerate(match.groups(), start=1)
    }


def run_provider_scenario(
    scenario: Mapping[str, Any],
    *,
    root: Path,
    environment: Mapping[str, str],
) -> Dict[str, Any]:
    selected_rows = scenario.get("selected_rows")
    workflows = scenario.get("row_workflows")
    if not isinstance(selected_rows, list) or not isinstance(
        workflows, dict
    ):
        raise ValueError(
            "ADB provider scenario requires selected_rows and row_workflows"
        )
    if set(workflows) != set(selected_rows):
        raise ValueError(
            "row_workflows must exactly match selected_rows"
        )
    observations: Dict[str, Any] = {}
    row_devices = scenario.get("row_devices", {})
    if not isinstance(row_devices, dict):
        raise ValueError("row_devices must be an object")
    for row_id in selected_rows:
        workflow = workflows[row_id]
        if not isinstance(workflow, dict):
            raise ValueError(f"{row_id} workflow must be an object")
        actions = workflow.get("actions")
        projection = workflow.get("observation")
        if not isinstance(actions, list) or not isinstance(
            projection, dict
        ):
            raise ValueError(
                f"{row_id} workflow requires actions and observation"
            )
        row_environment = dict(environment)
        row_environment.update(
            {
                "RESPECT_TESTKIT_ROW_ID": row_id,
                "RESPECT_TESTKIT_ROW_DEVICE_ID": row_devices.get(
                    row_id,
                    environment.get("RESPECT_TESTKIT_DEVICE_ID", ""),
                ),
            }
        )
        captures: Dict[str, Any] = {}
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError(f"{row_id} action must be an object")
            action_type = action.get("type")
            capture = action.get("capture")
            if not isinstance(capture, str) or not capture:
                raise ValueError(
                    f"{row_id} action requires a capture name"
                )
            if capture in captures:
                raise ValueError(f"duplicate provider capture: {capture}")
            if action_type == "command":
                result = _run_command(
                    action,
                    root=root,
                    environment=row_environment,
                )
            elif action_type == "http":
                result = _run_http(
                    action,
                    environment=row_environment,
                )
            elif action_type == "read_json":
                result = _run_read_json(
                    action,
                    root=root,
                    environment=row_environment,
                )
            elif action_type == "regex":
                result = _run_regex(action, captures)
            else:
                raise ValueError(
                    f"unsupported provider action type: {action_type}"
                )
            captures[capture] = result
        observations[row_id] = _project(
            projection,
            captures,
            row_environment,
        )
    return observations


def main(argv: Optional[List[str]] = None) -> int:
    del argv
    environment = os.environ.copy()
    required = (
        "RESPECT_TESTKIT_CHALLENGE",
        "RESPECT_TESTKIT_TARGET_DIGEST",
        "RESPECT_TESTKIT_DEVICE_ID",
        "RESPECT_TESTKIT_RESPECT_APK_SHA256",
        "RESPECT_TESTKIT_RESPECT_PACKAGE",
        "RESPECT_TESTKIT_CANAPP_PACKAGE",
        "RESPECT_TESTKIT_SCENARIO",
        "RESPECT_TESTKIT_ROW_DEVICES",
    )
    missing = [name for name in required if not environment.get(name)]
    if missing:
        raise SystemExit(
            f"missing provider environment: {', '.join(missing)}"
        )
    scenario_path = Path(
        environment["RESPECT_TESTKIT_SCENARIO"]
    ).resolve()
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    observations = run_provider_scenario(
        scenario,
        root=scenario_path.parent,
        environment=environment,
    )
    bundle = {
        "artifact_type": "respect_platform_raw_observations",
        "format_version": "1.0.0",
        "challenge": environment["RESPECT_TESTKIT_CHALLENGE"],
        "target_digest": environment["RESPECT_TESTKIT_TARGET_DIGEST"],
        "device_id": environment["RESPECT_TESTKIT_DEVICE_ID"],
        "respect_apk_sha256": environment[
            "RESPECT_TESTKIT_RESPECT_APK_SHA256"
        ],
        "respect_package": environment[
            "RESPECT_TESTKIT_RESPECT_PACKAGE"
        ],
        "canapp_package": environment[
            "RESPECT_TESTKIT_CANAPP_PACKAGE"
        ],
        "observations": observations,
    }
    print(json.dumps(bundle, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
