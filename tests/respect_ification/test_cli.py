# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json

from respect_ification.cli import main
from respect_compat.resources import resource


def test_prepare_cli_writes_public_and_private_packets(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.py").write_text("print('ok')\n")
    public = tmp_path / "public.json"
    private = tmp_path / "private.json"
    assert (
        main(
            [
                "prepare",
                "--source-root",
                str(source),
                "--target-digest",
                "target-digest",
                "--profile",
                "PROFILE-WEB",
                "--public-output",
                str(public),
                "--private-output",
                str(private),
            ]
        )
        == 0
    )
    assert json.loads(public.read_text())["artifact_type"].endswith("public_prep")
    assert json.loads(private.read_text())["artifact_type"].endswith("private_prep")


def test_full_test_cli_preserves_test_suite_verdict(tmp_path):
    root = resource("data/fixtures/v1_0/positive/web_reference")
    output = tmp_path / "suite"
    assert (
        main(
            [
                "full-test",
                "--fixture-dir",
                str(root),
                "--profile",
                "PROFILE-WEB",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads((output / "respect-report.json").read_text())
    assert report["verdict"]["certified"] is True
    assert (output / "respect-evidence-manifest.json").is_file()
    assert (output / "respect-ification-task-packet.json").is_file()
