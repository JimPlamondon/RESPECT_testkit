# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
import hashlib

import pytest

import respect_compat.android_runtime_runner as runtime_runner
from respect_compat.android_runtime_runner import (
    DRIVER_PACKAGE,
    load_runtime_scenario,
    parse_driver_events,
    runtime_driver_source_hash,
    verify_runtime_driver_receipt,
)


def _scenario():
    return {
        "artifact_type": "respect_native_android_runtime_scenario",
        "format_version": "1.0.0",
        "canapp_package": "org.example.canapp",
        "driver_package": DRIVER_PACKAGE,
        "launch_url": "https://canapp.example/launch",
        "endpoint": "https://lrs.example/xapi/",
        "auth": "Basic local-control",
        "actor": {
            "objectType": "Agent",
            "account": {
                "homePage": "https://example.invalid",
                "name": "control",
            },
        },
        "activity_id": "https://lesson.example/activity",
        "actions": [
            {"type": "wait", "milliseconds": 100},
            {"type": "tap", "x": 100, "y": 200},
            {"type": "keyevent", "key": "BACK"},
        ],
    }


def test_scenario_loader_accepts_bounded_non_shell_actions(tmp_path):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(_scenario()))

    scenario = load_runtime_scenario(path)

    assert scenario["driver_package"] == DRIVER_PACKAGE
    assert scenario["actions"][1] == {"type": "tap", "x": 100, "y": 200}


def test_scenario_loader_rejects_arbitrary_shell_action(tmp_path):
    value = _scenario()
    value["actions"] = [{"type": "shell", "command": "touch /data/local/tmp/pass"}]
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="action"):
        load_runtime_scenario(path)


def test_driver_event_parser_requires_health_control_and_valid_json_lines():
    text = "\n".join(
        [
            json.dumps(
                {
                    "kind": "driver_health",
                    "protocol_version": "1.0.0",
                    "package": DRIVER_PACKAGE,
                }
            ),
            json.dumps({"kind": "service_bound"}),
        ]
    )

    events = parse_driver_events(text)

    assert events[1]["kind"] == "service_bound"


def test_driver_event_parser_rejects_missing_health_control():
    with pytest.raises(ValueError, match="health"):
        parse_driver_events(json.dumps({"kind": "service_bound"}))


def test_driver_receipt_binds_suite_source_and_apk(tmp_path):
    apk = tmp_path / "driver.apk"
    apk.write_bytes(b"suite-driver")
    receipt = {
        "artifact_type": "respect_native_android_runtime_driver_build_receipt",
        "format_version": "1.0.0",
        "driver_package": DRIVER_PACKAGE,
        "source_tree_sha256": runtime_driver_source_hash(),
        "apk_sha256": hashlib.sha256(b"suite-driver").hexdigest(),
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))

    assert verify_runtime_driver_receipt(apk, path) == receipt

    receipt["apk_sha256"] = "owner-substituted"
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="does not match"):
        verify_runtime_driver_receipt(apk, path)


def test_certification_mode_rejects_an_emulator_before_device_mutation(
    tmp_path, monkeypatch
):
    target = type(
        "Target",
        (),
        {"apk": tmp_path / "canapp.apk", "metadata": {}, "digest": "target"},
    )()
    target.apk.write_bytes(b"canapp")
    driver = tmp_path / "driver.apk"
    driver.write_bytes(b"driver")
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps(_scenario()))
    monkeypatch.setattr(
        runtime_runner,
        "verify_runtime_driver_receipt",
        lambda *_args: {},
    )
    monkeypatch.setattr(
        runtime_runner,
        "inspect_apk",
        lambda path: {
            "package_id": (
                DRIVER_PACKAGE if path == driver else "org.example.canapp"
            ),
            "services": [
                {
                    "exported": True,
                    "actions": ["org.openeel.action.xapioveripc"],
                }
            ],
        },
    )
    monkeypatch.setattr(
        runtime_runner,
        "probe_android_device",
        lambda *_args, **_kwargs: {"healthy": True, "emulator": True},
    )

    with pytest.raises(ValueError, match="physical Android device"):
        runtime_runner.run_native_android_runtime(
            target,
            device_id="emulator-5554",
            driver_apk=driver,
            driver_receipt=tmp_path / "receipt.json",
            scenario_path=scenario,
            scenario_nonce="nonce",
            certification_mode=True,
            command_runner=lambda *_args, **_kwargs: pytest.fail(
                "device command should not run"
            ),
        )
