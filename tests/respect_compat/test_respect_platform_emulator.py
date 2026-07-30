# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import hashlib
import json
from pathlib import Path

import pytest

from respect_compat.respect_platform_emulator import (
    PLATFORM_ROW_IDS,
    evaluate_platform_observation,
    load_platform_scenario,
    run_respect_platform_emulator,
)
from respect_compat.respect_platform_adb_provider import (
    main as adb_provider_main,
    run_provider_scenario,
)
from respect_compat.engine import execute
from respect_compat.executors import build_registry
from respect_compat.matrix_runtime import load_matrix
from respect_compat.models import ResultState
from respect_compat.provisions import derive_provisions
from respect_compat.target import CanAppTarget


def test_adb_provider_help_does_not_require_provider_environment(
    capsys,
):
    with pytest.raises(SystemExit) as raised:
        adb_provider_main(["--help"])
    assert raised.value.code == 0
    assert "observation scenario" in capsys.readouterr().out


def _passing_observations():
    return {
        "AUTH-002": {
            "valid_status": 200,
            "missing_status": 403,
            "altered_status": 403,
            "effect_digest_before": "a" * 64,
            "effect_digest_after": "a" * 64,
        },
        "LAUNCH-001": {
            "api_level": 36,
            "native_attempted": True,
            "selected_package": "org.jims.mobilekb",
            "activity_package": "org.jims.mobilekb",
            "launch_url": "https://lessons.example/one",
            "expected_launch_url": "https://lessons.example/one",
        },
        "LAUNCH-002": {
            "native_failure": "ActivityNotFoundException",
            "selected_activity": "world.respect.WebViewActivity",
            "webview_url": "https://lessons.example/one",
            "expected_launch_url": "https://lessons.example/one",
            "page_loaded": True,
        },
        "LAUNCH-009": {
            "api_level": 29,
            "resolved_packages": [
                "com.android.chrome",
                "org.jims.mobilekb",
            ],
            "selected_package": "org.jims.mobilekb",
            "activity_package": "org.jims.mobilekb",
            "launch_url": "https://lessons.example/one",
            "expected_launch_url": "https://lessons.example/one",
        },
        "OFFLINE-001": {
            "declared_urls": [
                "https://lessons.example/lesson.json",
                "https://lessons.example/index.html",
            ],
            "requested_urls": [
                "https://lessons.example/lesson.json",
                "https://lessons.example/index.html",
            ],
            "unrelated_url": "https://lessons.example/unrelated.bin",
            "pin_state": "complete",
        },
        "OFFLINE-002": {
            "online_digest": "b" * 64,
            "offline_digest": "b" * 64,
            "remote_unavailable": True,
            "offline_usable": True,
            "never_fetched_available": False,
        },
        "REG-001": {
            "descriptor_url": "https://lessons.example/descriptor.json",
            "listed_object_urls": [
                "https://lessons.example/descriptor.json"
            ],
            "statement_ids": ["00000000-0000-4000-8000-000000000001"],
            "displayed_urls": [
                "https://lessons.example/descriptor.json"
            ],
        },
        "REG-002": {
            "active_statement_ids": [
                "00000000-0000-4000-8000-000000000001"
            ],
            "displayed_statement_ids": [
                "00000000-0000-4000-8000-000000000001"
            ],
            "opened_descriptor_url": (
                "https://lessons.example/descriptor.json"
            ),
            "expected_descriptor_url": (
                "https://lessons.example/descriptor.json"
            ),
        },
        "REG-003": {
            "removed_descriptor_url": (
                "https://lessons.example/descriptor.json"
            ),
            "voided_listing_id": (
                "00000000-0000-4000-8000-000000000001"
            ),
            "latest_listing_id": (
                "00000000-0000-4000-8000-000000000001"
            ),
            "active_urls_after": [
                "https://lessons.example/other.json"
            ],
            "unrelated_url": "https://lessons.example/other.json",
        },
        "REG-004": {
            "descriptor_url": "https://lessons.example/descriptor.json",
            "listing_statement_ids": [
                "00000000-0000-4000-8000-000000000001",
                "00000000-0000-4000-8000-000000000002",
            ],
        },
        "REG-005": {
            "active_actor": False,
            "requested_action": "add",
            "statement_digest_before": "c" * 64,
            "statement_digest_after": "c" * 64,
            "warning_observed": True,
        },
        "XAPI-012": {
            "assignment_id": "https://assignments.example/one",
            "stored_grouping_ids": [
                "https://assignments.example/one"
            ],
            "original_statement_digest": "d" * 64,
            "stored_statement_digest": "e" * 64,
            "storage_succeeded": True,
        },
        "XAPI-020": {
            "status": 200,
            "headers": {
                "last-modified": "Wed, 29 Jul 2026 01:02:03 GMT",
                "x-experience-api-version": "1.0.3",
                "x-experience-api-consistent-through": (
                    "2026-07-29T01:02:03Z"
                ),
            },
            "submitted_statement_ids": [
                "00000000-0000-4000-8000-000000000001"
            ],
            "returned_statement_ids": [
                "00000000-0000-4000-8000-000000000001"
            ],
            "nonmatching_statement_id": (
                "00000000-0000-4000-8000-000000000002"
            ),
        },
    }


def test_every_mobile_platform_row_has_a_real_oracle():
    observations = _passing_observations()

    assert set(observations) == PLATFORM_ROW_IDS
    for row_id, observed in observations.items():
        passed, message = evaluate_platform_observation(row_id, observed)
        assert passed, f"{row_id}: {message}"


@pytest.mark.parametrize(
    ("row_id", "field", "bad_value"),
    [
        ("AUTH-002", "altered_status", 200),
        ("LAUNCH-001", "selected_package", "com.android.chrome"),
        ("LAUNCH-002", "page_loaded", False),
        ("LAUNCH-009", "selected_package", "com.android.chrome"),
        ("OFFLINE-001", "requested_urls", []),
        ("OFFLINE-002", "offline_digest", "f" * 64),
        ("REG-001", "listed_object_urls", []),
        ("REG-002", "displayed_statement_ids", []),
        (
            "REG-003",
            "active_urls_after",
            ["https://lessons.example/descriptor.json"],
        ),
        (
            "REG-004",
            "listing_statement_ids",
            ["00000000-0000-4000-8000-000000000001"],
        ),
        ("REG-005", "statement_digest_after", "f" * 64),
        ("XAPI-012", "stored_grouping_ids", []),
        ("XAPI-020", "headers", {}),
    ],
)
def test_each_platform_oracle_rejects_an_isolated_fault(
    row_id, field, bad_value
):
    observed = copy.deepcopy(_passing_observations()[row_id])
    observed[field] = bad_value

    passed, _message = evaluate_platform_observation(row_id, observed)

    assert not passed


def test_scenario_requires_suite_owned_command_and_all_selected_rows(
    tmp_path
):
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "artifact_type": (
                    "respect_platform_emulator_scenario"
                ),
                "format_version": "1.0.0",
                "respect_package": "world.respect.app",
                "canapp_package": "org.jims.mobilekb",
                "provider_command": ["python3", "provider.py"],
                "selected_rows": sorted(PLATFORM_ROW_IDS),
            }
        ),
        encoding="utf-8",
    )

    scenario = load_platform_scenario(scenario_path)

    assert set(scenario["selected_rows"]) == PLATFORM_ROW_IDS
    scenario_path.write_text(
        scenario_path.read_text(encoding="utf-8").replace(
            '"provider_command": ["python3", "provider.py"]',
            '"provider_command": "python3 provider.py"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="argument array"):
        load_platform_scenario(scenario_path)


def test_runner_binds_provider_output_to_apk_device_challenge_and_target(
    monkeypatch, tmp_path
):
    respect_apk = tmp_path / "respect.apk"
    respect_apk.write_bytes(b"respect-platform-apk")
    apk_digest = hashlib.sha256(respect_apk.read_bytes()).hexdigest()
    scenario_path = tmp_path / "scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "artifact_type": (
                    "respect_platform_emulator_scenario"
                ),
                "format_version": "1.0.0",
                "respect_package": "world.respect.app",
                "canapp_package": "org.jims.mobilekb",
                "provider_command": ["provider"],
                "selected_rows": sorted(PLATFORM_ROW_IDS),
                "row_devices": {"LAUNCH-009": "emulator-5556"},
            }
        ),
        encoding="utf-8",
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "artifact_type": "respect_platform_build_receipt",
                "format_version": "1.0.0",
                "apk_sha256": apk_digest,
                "package_id": "world.respect.app",
                "build_id": "respect-main-a1b2c3d",
                "respect_revision": "a1b2c3d4",
            }
        ),
        encoding="utf-8",
    )
    target = CanAppTarget(
        uri="https://lessons.example/descriptor.json",
        adapter="test",
        digest="9" * 64,
        document={"metadata": {}, "links": []},
        capabilities=set(),
    )
    provider_output = {
        "artifact_type": "respect_platform_raw_observations",
        "format_version": "1.0.0",
        "challenge": "challenge-123456",
        "target_digest": target.digest,
        "device_id": "emulator-5554",
        "respect_apk_sha256": apk_digest,
        "respect_package": "world.respect.app",
        "canapp_package": "org.jims.mobilekb",
        "observations": _passing_observations(),
    }

    class Completed:
        returncode = 0
        stdout = json.dumps(provider_output)
        stderr = ""

    monkeypatch.setattr(
        "respect_compat.respect_platform_emulator.inspect_apk",
        lambda _path: {"package_id": "world.respect.app"},
    )
    monkeypatch.setattr(
        "respect_compat.respect_platform_emulator.probe_android_device",
        lambda device, adb=None: {
            "healthy": True,
            "emulator": True,
            "api_level": "29" if device == "emulator-5556" else "36",
        },
    )

    observations = run_respect_platform_emulator(
        target,
        device_id="emulator-5554",
        respect_apk=respect_apk,
        build_receipt=receipt_path,
        scenario_path=scenario_path,
        challenge="challenge-123456",
        adb=Path("/test/adb"),
        command_runner=lambda *args, **kwargs: Completed(),
    )

    assert set(observations) == PLATFORM_ROW_IDS
    assert all(item["state"] == "pass" for item in observations.values())
    assert (
        observations["LAUNCH-009"]["platform_evidence"]["device_id"]
        == "emulator-5556"
    )
    assert (
        observations["LAUNCH-001"]["platform_evidence"]["device_id"]
        == "emulator-5554"
    )
    assert target.metadata["_controlled_respect_platform"] is True
    assert target.metadata["_controlled_runtime"] is True
    matrix = load_matrix()
    run = execute(
        matrix,
        target,
        "PROFILE-NATIVE_ANDROID",
        "test",
        build_registry(matrix),
        run_seed="platform-provider-connection",
        selected_row_ids=["AUTH-002"],
    )
    assert run.results[0].state == ResultState.PASS
    assert run.results[0].owner.value == "respect_service"
    selected_row = next(
        row
        for row in matrix.selected_rows("PROFILE-NATIVE_ANDROID")
        if row.row_id == "AUTH-002"
    )
    emulator_provision = next(
        provision
        for provision in derive_provisions(
            [selected_row],
            run.evidence_environment,
            run.results,
        )
        if provision.code == "EMULATED_ANDROID_RUNTIME"
    )
    assert emulator_provision.affected_rows == ["AUTH-002"]


def test_runner_rejects_provider_replay_from_another_challenge(
    monkeypatch, tmp_path
):
    observations = _passing_observations()
    artifact = {
        "artifact_type": "respect_platform_raw_observations",
        "format_version": "1.0.0",
        "challenge": "old-challenge",
        "target_digest": "9" * 64,
        "device_id": "emulator-5554",
        "respect_apk_sha256": "0" * 64,
        "respect_package": "world.respect.app",
        "canapp_package": "org.jims.mobilekb",
        "observations": observations,
    }

    from respect_compat.respect_platform_emulator import (
        validate_raw_observation_bundle,
    )

    with pytest.raises(ValueError, match="challenge"):
        validate_raw_observation_bundle(
            artifact,
            challenge="new-challenge",
            target_digest="9" * 64,
            device_id="emulator-5554",
            respect_apk_sha256="0" * 64,
            respect_package="world.respect.app",
            canapp_package="org.jims.mobilekb",
            selected_rows=PLATFORM_ROW_IDS,
        )


def test_suite_shipped_provider_projects_only_captured_process_evidence(
    tmp_path
):
    scenario = {
        "selected_rows": ["AUTH-002"],
        "row_workflows": {
            "AUTH-002": {
                "actions": [
                    {
                        "type": "command",
                        "capture": "statuses",
                        "argv": [
                            "/bin/sh",
                            "-c",
                            (
                                "printf "
                                "'{\"valid\":200,\"missing\":403,"
                                "\"altered\":403}'"
                            ),
                        ],
                        "parse": "json",
                    }
                ],
                "observation": {
                    "valid_status": {
                        "capture": "statuses.stdout.valid"
                    },
                    "missing_status": {
                        "capture": "statuses.stdout.missing"
                    },
                    "altered_status": {
                        "capture": "statuses.stdout.altered"
                    },
                },
            }
        },
    }

    observed = run_provider_scenario(
        scenario,
        root=tmp_path,
        environment={},
    )

    assert observed["AUTH-002"]["missing_status"] == 403
    scenario["row_workflows"]["AUTH-002"]["observation"][
        "missing_status"
    ] = {"capture": "not-captured.status"}
    with pytest.raises(ValueError, match="unknown provider capture"):
        run_provider_scenario(
            scenario,
            root=tmp_path,
            environment={},
        )


def test_suite_shipped_provider_binds_each_workflow_to_its_row_device(
    tmp_path
):
    scenario = {
        "selected_rows": ["LAUNCH-009"],
        "row_devices": {"LAUNCH-009": "emulator-5556"},
        "row_workflows": {
            "LAUNCH-009": {
                "actions": [],
                "observation": {
                    "row_id": "${RESPECT_TESTKIT_ROW_ID}",
                    "device_id": "${RESPECT_TESTKIT_ROW_DEVICE_ID}",
                },
            }
        },
    }

    observed = run_provider_scenario(
        scenario,
        root=tmp_path,
        environment={"RESPECT_TESTKIT_DEVICE_ID": "emulator-5554"},
    )

    assert observed["LAUNCH-009"] == {
        "row_id": "LAUNCH-009",
        "device_id": "emulator-5556",
    }
