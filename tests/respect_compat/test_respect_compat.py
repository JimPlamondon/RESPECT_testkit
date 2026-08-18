# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

from respect_compat.cli import main, run_fixture
from respect_compat.fixture_loader import load_fixture
from respect_compat.models import ResultState
from respect_compat.profile import DEFAULT_PROFILE_NAME, load_profile
from respect_compat.resources import resource
from respect_compat.security_labels import SecurityContext
from respect_compat.target import load_fixture_target


FIXTURE_ROOT = resource("data/fixtures/v0_1")


def _forbid_external_read(monkeypatch, method_name, outside):
    original = getattr(Path, method_name)
    resolved_outside = outside.resolve()

    def guarded(path, *args, **kwargs):
        if path.resolve() == resolved_outside:
            pytest.fail(f"external fixture read attempted: {resolved_outside}")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, method_name, guarded)


def test_profile_loader_rejects_unknown_profile_before_fixture_io(tmp_path):
    with pytest.raises(ValueError):
        load_profile("unknown")
    assert not (tmp_path / "touched").exists()


def test_result_states_are_exact_canonical_values():
    assert {state.value for state in ResultState} == {
        "pass",
        "fail",
        "not_applicable",
        "incomplete",
        "deferred",
        "harness_error",
        "blocked",
    }


def test_security_context_rejects_production():
    with pytest.raises(ValueError):
        SecurityContext("production")


@pytest.mark.parametrize("case_dir", sorted((FIXTURE_ROOT / "positive").glob("*")) + sorted((FIXTURE_ROOT / "negative").glob("*")))
def test_fixture_expected_outcomes(case_dir):
    case = load_fixture(case_dir)
    results = run_fixture(case, DEFAULT_PROFILE_NAME, "test", None)
    expected = case.expected["expected_results"]
    observed_pairs = {(result.rule_id, result.result.value) for result in results}
    legacy_states = {"warning": "incomplete", "skipped": "not_applicable"}
    for item in expected:
        expected_state = legacy_states.get(item["result"], item["result"])
        assert (item["rule_id"], expected_state) in observed_pairs


def test_fixture_loader_rejects_parent_manifest_escape(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (fixture / "expected.json").write_text(
        json.dumps({"manifest": "../outside.json"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest path escapes fixture root"):
        load_fixture(fixture)


def test_fixture_loader_rejects_symlink_manifest_escape(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (fixture / "manifest.json").symlink_to(outside)
    (fixture / "expected.json").write_text(
        json.dumps({"manifest": "manifest.json"}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest path escapes fixture root"):
        load_fixture(fixture)


def test_fixture_loader_rejects_symlink_expected_without_external_read(
    tmp_path,
    monkeypatch,
):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    outside = tmp_path / "outside-expected.json"
    outside.write_text(
        json.dumps({"manifest": "descriptor.json"}),
        encoding="utf-8",
    )
    (fixture / "expected.json").symlink_to(outside)
    _forbid_external_read(monkeypatch, "read_text", outside)

    with pytest.raises(ValueError, match="expected.json must not be a symlink"):
        load_fixture(fixture)


def test_fixture_loader_rejects_symlink_metadata_without_external_read(
    tmp_path,
    monkeypatch,
):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "expected.json").write_text(
        json.dumps({"manifest": "descriptor.json"}),
        encoding="utf-8",
    )
    (fixture / "descriptor.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside-metadata.json"
    outside.write_text('{"private":"secret"}', encoding="utf-8")
    (fixture / "metadata.json").symlink_to(outside)
    _forbid_external_read(monkeypatch, "read_text", outside)

    with pytest.raises(ValueError, match="metadata.json must not be a symlink"):
        load_fixture(fixture)


def test_fixture_digest_rejects_unrelated_symlink_without_external_read(
    tmp_path,
    monkeypatch,
):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "expected.json").write_text(
        json.dumps({"manifest": "descriptor.json"}),
        encoding="utf-8",
    )
    (fixture / "descriptor.json").write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside-private.bin"
    outside.write_bytes(b"private fixture-adjacent bytes")
    (fixture / "unrelated.bin").symlink_to(outside)
    _forbid_external_read(monkeypatch, "read_bytes", outside)

    with pytest.raises(ValueError, match="fixture digest rejects symlinks"):
        load_fixture_target(fixture)


def test_cli_writes_parseable_reports_and_is_deterministic(tmp_path):
    fixture = FIXTURE_ROOT / "positive" / "native_valid"
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    assert main(["--fixture-dir", str(fixture), "--profile", "PROFILE-SUITE_QUALITY", "--mode", "test", "--run-seed", "deterministic-report", "--output-dir", str(out_a)]) == 0
    assert main(["--fixture-dir", str(fixture), "--profile", "PROFILE-SUITE_QUALITY", "--mode", "test", "--run-seed", "deterministic-report", "--output-dir", str(out_b)]) == 0
    json.loads((out_a / "respect-report.json").read_text(encoding="utf-8"))
    ElementTree.parse(out_a / "junit.xml")
    assert (out_a / "respect-report.json").read_bytes() == (out_b / "respect-report.json").read_bytes()


def test_cli_failure_exit_code_for_negative_fixture(tmp_path):
    fixture = FIXTURE_ROOT / "negative" / "invalid_license"
    assert main(["--fixture-dir", str(fixture), "--profile", "PROFILE-WEB", "--mode", "certification", "--output-dir", str(tmp_path)]) == 1


def test_cli_invocation_error_uses_exit_code_64():
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 64


def test_cli_apk_only_requires_submitted_apk(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--apk-only",
                "--profile",
                "PROFILE-NATIVE_ANDROID",
                "--mode",
                "test",
                "--output-dir",
                str(tmp_path),
            ]
        )
    assert error.value.code == 64
