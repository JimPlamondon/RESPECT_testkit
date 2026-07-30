# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_testkit_has_no_embedded_upgrade_dossier_package_or_cli():
    assert not (ROOT / "src/respect_upgrade_dossier").exists()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "respect-upgrade-dossier" not in pyproject
    assert "respect_upgrade_dossier" not in pyproject


def test_testkit_has_no_upgrade_matrix_or_dossier_packet_schema():
    names = {
        path.name
        for path in (ROOT / "src/respect_compat/data/schemas").glob("*.json")
    }
    assert "platform_gap_packet_v2.schema.json" not in names
    assert "upgrade_matrix.json" not in {
        path.name for path in (ROOT / "src").rglob("*.json")
    }
    assert "atomic_result_v3.schema.json" in names


def test_runtime_source_contains_no_upgrade_authority_vocabulary():
    forbidden = (
        "respect_upgrade_guidance",
        "feature_work_unit",
        "platform_gap_eligible",
        "dossier_acceptance_test",
        "dossier_eligible",
        "platform_gap_packet",
    )
    offenders = []
    for path in (ROOT / "src").rglob("*"):
        if (
            not path.is_file()
            or any(
                part.endswith(".egg-info") or part == "__pycache__"
                for part in path.parts
            )
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            if token in text:
                offenders.append(
                    f"{path.relative_to(ROOT).as_posix()}: {token}"
                )
    assert offenders == []
