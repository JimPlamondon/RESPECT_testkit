# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import pytest

from respect_compat.respect_platform_emulator import (
    PLATFORM_ROW_IDS,
    evaluate_platform_observation,
)
from respect_compat.school_harness import (
    API29_ROWS,
    API30_PLUS_ROWS,
    EVIDENCE_FILES,
    SCHOOL_ROW_ORDER,
    RunState,
    build_parser,
    build_run_manifest,
    validate_observation_sets,
    validate_row_record,
    validate_scenario_routing,
)


def _positive_observations() -> dict:
    return {
        "AUTH-002": {
            "valid_status": 204,
            "missing_status": 403,
            "altered_status": 403,
            "effect_digest_before": "same",
            "effect_digest_after": "same",
        },
        "LAUNCH-001": {
            "api_level": 36,
            "native_attempted": True,
            "selected_package": "org.example.canapp",
            "activity_package": "org.example.canapp",
            "launch_url": "https://example.test/launch",
            "expected_launch_url": "https://example.test/launch",
        },
        "LAUNCH-002": {
            "native_failure": "no native handler",
            "selected_activity": "world.respect.WebViewActivity",
            "page_loaded": True,
            "webview_url": "https://example.test/launch",
            "expected_launch_url": "https://example.test/launch",
        },
        "LAUNCH-009": {
            "api_level": 29,
            "selected_package": "org.example.canapp",
            "resolved_packages": [
                "com.android.chrome",
                "org.example.canapp",
            ],
            "activity_package": "org.example.canapp",
            "launch_url": "https://example.test/launch",
            "expected_launch_url": "https://example.test/launch",
        },
        "OFFLINE-001": {
            "declared_urls": ["https://example.test/a"],
            "requested_urls": ["https://example.test/a"],
            "unrelated_url": "https://example.test/unrelated",
            "pin_state": "complete",
        },
        "OFFLINE-002": {
            "remote_unavailable": True,
            "offline_usable": True,
            "never_fetched_available": False,
            "online_digest": "same",
            "offline_digest": "same",
        },
        "REG-001": {
            "descriptor_url": "https://example.test/descriptor.json",
            "listed_object_urls": [
                "https://example.test/descriptor.json"
            ],
            "displayed_urls": [
                "https://example.test/descriptor.json"
            ],
            "statement_ids": ["statement-1"],
        },
        "REG-002": {
            "active_statement_ids": ["statement-1"],
            "displayed_statement_ids": ["statement-1"],
            "opened_descriptor_url": (
                "https://example.test/descriptor.json"
            ),
            "expected_descriptor_url": (
                "https://example.test/descriptor.json"
            ),
        },
        "REG-003": {
            "voided_listing_id": "statement-2",
            "latest_listing_id": "statement-2",
            "removed_descriptor_url": (
                "https://example.test/descriptor.json"
            ),
            "active_urls_after": [
                "https://example.test/unrelated.json"
            ],
            "unrelated_url": "https://example.test/unrelated.json",
        },
        "REG-004": {
            "descriptor_url": "https://example.test/descriptor.json",
            "listing_statement_ids": ["statement-1", "statement-2"],
        },
        "REG-005": {
            "active_actor": False,
            "requested_action": "add",
            "warning_observed": True,
            "statement_digest_before": "same",
            "statement_digest_after": "same",
        },
        "XAPI-012": {
            "assignment_id": "assignment-1",
            "stored_grouping_ids": ["assignment-1"],
            "storage_succeeded": True,
            "original_statement_digest": "original",
            "stored_statement_digest": "stored",
        },
        "XAPI-020": {
            "status": 200,
            "headers": {
                "Last-Modified": "now",
                "X-Experience-API-Version": "1.0.3",
                "X-Experience-API-Consistent-Through": "now",
            },
            "submitted_statement_ids": ["statement-1"],
            "returned_statement_ids": ["statement-1"],
            "nonmatching_statement_id": "statement-other",
        },
    }


def _row_record(row_id: str, observed: dict) -> dict:
    negative = dict(observed)
    if row_id == "AUTH-002":
        negative["altered_status"] = 200
    elif row_id.startswith("LAUNCH-"):
        negative["expected_launch_url"] = (
            "https://example.test/different"
        )
    elif row_id == "OFFLINE-001":
        negative["pin_state"] = "partial"
    elif row_id == "OFFLINE-002":
        negative["offline_usable"] = False
    elif row_id == "REG-001":
        negative["statement_ids"] = []
    elif row_id == "REG-002":
        negative["displayed_statement_ids"] = ["different"]
    elif row_id == "REG-003":
        negative["voided_listing_id"] = "different"
    elif row_id == "REG-004":
        negative["listing_statement_ids"] = ["same", "same"]
    elif row_id == "REG-005":
        negative["warning_observed"] = False
    elif row_id == "XAPI-012":
        negative["stored_grouping_ids"] = []
    elif row_id == "XAPI-020":
        negative["headers"] = {}
    return {
        "row_id": row_id,
        "positive": observed,
        "isolated_negative": negative,
        "harness_health": {
            "before": "healthy",
            "after": "healthy",
        },
        "target_attribution": {
            "device_id": "emulator",
            "package_id": "org.example.canapp",
            "row_id": row_id,
        },
        "anti_replay": {
            "nonce": "fresh-nonce",
            "capture_sha256": "fresh-capture",
            "prior_capture_sha256": "prior-capture",
        },
        "regression_lock": f"school-harness:{row_id}",
        "capture_sources": [
            {
                "kind": "production",
                "command_id": f"command-{row_id}",
            }
        ],
    }


def test_command_surface_is_one_flat_mutually_exclusive_parser():
    parser = build_parser()
    operation_actions = [
        action
        for group in parser._mutually_exclusive_groups
        if group.required
        for action in group._group_actions
    ]
    assert [action.dest for action in operation_actions] == [
        "provision",
        "build",
        "seed",
        "run_row",
        "run_all",
        "collect_evidence",
        "diagnose",
        "stop",
        "clean_ephemeral_state",
    ]
    assert not parser._subparsers
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--run-all", "--stop"])


def test_row_order_and_device_contract_are_complete():
    assert set(SCHOOL_ROW_ORDER) == PLATFORM_ROW_IDS
    assert set(API29_ROWS) == {"LAUNCH-009"}
    assert set(API30_PLUS_ROWS) == PLATFORM_ROW_IDS - set(API29_ROWS)
    assert SCHOOL_ROW_ORDER.index("OFFLINE-001") < SCHOOL_ROW_ORDER.index(
        "OFFLINE-002"
    )
    assert SCHOOL_ROW_ORDER.index("REG-004") < SCHOOL_ROW_ORDER.index(
        "REG-002"
    )
    assert SCHOOL_ROW_ORDER.index("REG-002") < SCHOOL_ROW_ORDER.index(
        "REG-003"
    )


def test_scenario_routing_requires_measured_launch_api_levels():
    scenario = {
        "selected_rows": list(SCHOOL_ROW_ORDER),
        "row_devices": {
            row_id: (
                "emulator-29"
                if row_id in API29_ROWS
                else "emulator-36"
            )
            for row_id in SCHOOL_ROW_ORDER
        },
    }
    validate_scenario_routing(
        scenario,
        {
            "emulator-29": {"healthy": True, "emulator": True, "api_level": 29},
            "emulator-36": {"healthy": True, "emulator": True, "api_level": 36},
        },
    )
    scenario["row_devices"]["LAUNCH-009"] = "emulator-36"
    with pytest.raises(ValueError, match="LAUNCH-009"):
        validate_scenario_routing(
            scenario,
            {
                "emulator-29": {
                    "healthy": True,
                    "emulator": True,
                    "api_level": 29,
                },
                "emulator-36": {
                    "healthy": True,
                    "emulator": True,
                    "api_level": 36,
                },
            },
        )


@pytest.mark.parametrize(
    ("row_id", "field"),
    [
        ("LAUNCH-009", "resolved_packages"),
        ("OFFLINE-001", "requested_urls"),
        ("REG-001", "statement_ids"),
        ("REG-002", "active_statement_ids"),
        ("REG-003", "active_urls_after"),
        ("REG-004", "listing_statement_ids"),
        ("XAPI-012", "stored_grouping_ids"),
        ("XAPI-020", "returned_statement_ids"),
    ],
)
@pytest.mark.parametrize("malformed", [["ok", ""], ["ok", None]])
def test_set_valued_observations_reject_blanks_and_nonstrings(
    row_id, field, malformed
):
    observed = _positive_observations()[row_id]
    observed[field] = malformed
    with pytest.raises(ValueError, match=field):
        validate_observation_sets(row_id, observed)


@pytest.mark.parametrize("row_id", SCHOOL_ROW_ORDER)
def test_every_row_record_proves_positive_negative_and_responsibility(
    row_id,
):
    observed = _positive_observations()[row_id]
    record = _row_record(row_id, observed)
    validate_row_record(
        record,
        run_nonce="fresh-nonce",
        expected_device="emulator",
        expected_package="org.example.canapp",
    )
    assert evaluate_platform_observation(row_id, record["positive"])[0]
    assert not evaluate_platform_observation(
        row_id,
        record["isolated_negative"],
    )[0]


def test_canned_capture_is_rejected_even_when_observation_would_pass():
    observed = _positive_observations()["AUTH-002"]
    record = _row_record("AUTH-002", observed)
    record["capture_sources"] = [
        {"kind": "canned", "command_id": "none"}
    ]
    with pytest.raises(ValueError, match="production"):
        validate_row_record(
            record,
            run_nonce="fresh-nonce",
            expected_device="emulator",
            expected_package="org.example.canapp",
        )


def test_evidence_manifest_enumerates_required_artifacts(tmp_path):
    manifest = build_run_manifest(
        run_id="run-1",
        nonce="nonce-1",
        evidence_dir=tmp_path,
        respect_revision="respect-revision",
        mobile_kb_revision="mobile-revision",
        respect_apk_sha256="respect-apk",
        mobile_kb_apk_sha256="mobile-apk",
        scenario_sha256="scenario",
        emulator_probes={
            "emulator-29": {"api_level": 29},
            "emulator-36": {"api_level": 36},
        },
    )
    assert manifest["run_id"] == "run-1"
    assert manifest["nonce"] == "nonce-1"
    assert set(manifest["evidence_files"]) == set(EVIDENCE_FILES)
    assert "password" not in json.dumps(manifest).lower()
    assert "private_key" not in json.dumps(manifest).lower()


def test_run_state_updates_are_idempotent(tmp_path):
    path = tmp_path / "state.json"
    state = RunState(path)
    state.mark_complete("provision", {"devices": ["a", "b"]})
    first = path.read_bytes()
    state.mark_complete("provision", {"devices": ["a", "b"]})
    assert path.read_bytes() == first
    assert RunState(path).completed("provision")


def test_run_state_refuses_cross_run_reuse(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"run_id": "old-run", "operations": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="run ID"):
        RunState(path, run_id="new-run")


def test_pyproject_declares_exactly_one_new_school_harness_script():
    root = Path(__file__).resolve().parents[2]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert (
        'respect-school-harness = "respect_compat.school_harness:main"'
        in pyproject
    )
