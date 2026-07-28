# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
import hashlib
from types import SimpleNamespace

import pytest

import respect_compat.android_runtime_runner as runtime_runner
from respect_compat.android_runtime_runner import (
    DRIVER_PACKAGE,
    derive_catalog_launch_url,
    domain_is_verified,
    load_runtime_scenario,
    parse_driver_events,
    runtime_driver_source_hash,
    verify_runtime_driver_receipt,
)
from respect_compat.target import CanAppTarget, HttpObservation


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


def _catalog_target():
    descriptor_url = "https://canapp.example/descriptor.json"
    catalog_url = "https://canapp.example/catalog.json"
    descriptor = {
        "metadata": {
            "identifier": "https://canapp.example/app",
            "title": "Example CanApp",
        },
        "links": [
            {
                "rel": [
                    "https://respect.ustadmobile.com/ns/default-lesson-catalog"
                ],
                "href": catalog_url,
                "type": "application/opds+json",
            }
        ],
    }
    catalog = {
        "metadata": {"title": "Real lessons"},
        "publications": [
            {
                "metadata": {
                    "identifier": "https://lesson.example/activity",
                    "title": "Real lesson",
                },
                "links": [
                    {
                        "rel": [
                            "http://opds-spec.org/acquisition/open-access"
                        ],
                        "href": "lessons/real/launch",
                        "type": "text/html",
                    }
                ],
            }
        ],
    }
    return CanAppTarget(
        uri=descriptor_url,
        adapter="manifest_url",
        digest="target",
        document=descriptor,
        observations=[
            HttpObservation(
                requested_url=descriptor_url,
                final_url=descriptor_url,
                status=200,
                headers={"content-type": "application/opds+json"},
                body=json.dumps(descriptor).encode(),
            ),
            HttpObservation(
                requested_url=catalog_url,
                final_url=catalog_url,
                status=200,
                headers={"content-type": "application/opds+json"},
                body=json.dumps(catalog).encode(),
            ),
        ],
        capabilities={"remote_http"},
    )


def test_runtime_launch_is_derived_from_selected_catalog_publication():
    scenario = _scenario()
    scenario["launch_url"] = (
        "https://canapp.example/lessons/real/launch"
        "?endpoint=https%3A%2F%2Flrs.example%2Fxapi%2F"
        "&auth=Basic+local-control"
        "&actor=%7B%22objectType%22%3A%22Agent%22%2C%22account%22%3A"
        "%7B%22homePage%22%3A%22https%3A%2F%2Fexample.invalid%22%2C"
        "%22name%22%3A%22control%22%7D%7D"
        "&activity_id=https%3A%2F%2Flesson.example%2Factivity"
        "&xapiIpcPackage=org.respect.testkit.runtime"
    )

    assert derive_catalog_launch_url(_catalog_target(), scenario) == scenario[
        "launch_url"
    ]


def test_runtime_launch_rejects_url_disconnected_from_catalog():
    scenario = _scenario()

    with pytest.raises(ValueError, match="catalog-derived"):
        derive_catalog_launch_url(_catalog_target(), scenario)


def test_runtime_launch_rejects_invented_activity_identifier():
    scenario = _scenario()
    scenario["activity_id"] = "https://lesson.example/invented"

    with pytest.raises(ValueError, match="selected OPDS publication"):
        derive_catalog_launch_url(_catalog_target(), scenario)


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


def test_domain_verification_parser_does_not_accept_unrelated_verified_host():
    association = """
      other.example: verified
      canapp.example: 1024
    """

    assert domain_is_verified(association, "canapp.example")
    assert not domain_is_verified(association, "missing.example")


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


def test_certification_mode_does_not_reject_an_emulator_before_device_execution(
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
    monkeypatch.setattr(
        runtime_runner,
        "derive_catalog_launch_url",
        lambda *_args, **_kwargs: "https://canapp.example/lesson",
    )

    commands = []

    def command_runner(command, **_kwargs):
        commands.append(command)
        raise RuntimeError("execution reached the selected Android environment")

    with pytest.raises(
        RuntimeError, match="execution reached the selected Android environment"
    ):
        runtime_runner.run_native_android_runtime(
            target,
            device_id="emulator-5554",
            driver_apk=driver,
            driver_receipt=tmp_path / "receipt.json",
            scenario_path=scenario,
            scenario_nonce="nonce",
            certification_mode=True,
            adb=tmp_path / "adb",
            command_runner=command_runner,
        )
    assert commands
    assert commands[0][-3:-1] == ["install", "-r"]


def test_runtime_evidence_is_captured_before_forced_process_cleanup(
    tmp_path, monkeypatch
):
    target = _catalog_target()
    target.apk = tmp_path / "canapp.apk"
    target.apk.write_bytes(b"canapp")
    driver = tmp_path / "driver.apk"
    driver.write_bytes(b"driver")
    scenario_value = _scenario()
    scenario_value["launch_url"] = (
        "https://canapp.example/lessons/real/launch"
        "?endpoint=https%3A%2F%2Flrs.example%2Fxapi%2F"
        "&auth=Basic+local-control"
        "&actor=%7B%22objectType%22%3A%22Agent%22%2C%22account%22%3A"
        "%7B%22homePage%22%3A%22https%3A%2F%2Fexample.invalid%22%2C"
        "%22name%22%3A%22control%22%7D%7D"
        "&activity_id=https%3A%2F%2Flesson.example%2Factivity"
        "&xapiIpcPackage=org.respect.testkit.runtime"
    )
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps(scenario_value))
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
        lambda *_args, **_kwargs: {
            "healthy": True,
            "emulator": True,
            "device_id": "emulator-5554",
        },
    )
    commands = []
    events = "\n".join(
        [
            json.dumps(
                {
                    "kind": "driver_health",
                    "protocol_version": "1.0.0",
                    "package": DRIVER_PACKAGE,
                }
            ),
            json.dumps(
                {
                    "kind": "service_unbound",
                    "client_package": "org.example.canapp",
                }
            ),
        ]
    )

    def command_runner(command, **_kwargs):
        commands.append(command)
        joined = " ".join(command)
        if "pm get-app-links" in joined:
            stdout = "canapp.example: verified"
        elif "resolve-activity" in joined or "am start" in joined:
            stdout = "org.example.canapp/.MainActivity"
        elif "run-as" in joined:
            stdout = events
        else:
            stdout = ""
        return SimpleNamespace(
            returncode=0,
            stdout=stdout,
            stderr="",
        )

    observations = runtime_runner.run_native_android_runtime(
        target,
        device_id="emulator-5554",
        driver_apk=driver,
        driver_receipt=tmp_path / "receipt.json",
        scenario_path=scenario,
        scenario_nonce="nonce",
        adb=tmp_path / "adb",
        command_runner=command_runner,
        sleeper=lambda _seconds: None,
    )

    capture_index = next(
        index for index, command in enumerate(commands) if "run-as" in command
    )
    cleanup_indices = [
        index
        for index, command in enumerate(commands)
        if "force-stop" in command
    ]
    assert capture_index < cleanup_indices[-1]
    assert observations["LIFECYCLE-001"]["state"] == "pass"
