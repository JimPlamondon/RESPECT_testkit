# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from respect_testkit_migration.validator import active_authority_files


ROOT = Path(__file__).resolve().parents[1]


def test_src_packages_exist() -> None:
    assert (ROOT / "src/respect_compat/__init__.py").is_file()
    assert (ROOT / "src/respect_ification/__init__.py").is_file()


def test_single_matrix_and_historical_profile_layout() -> None:
    matrix = active_authority_files(ROOT, "compatibility_matrix.json")
    profile = active_authority_files(ROOT, "compatibility_matrix_v0_1.json")
    assert matrix == [
        ROOT / "src/respect_compat/data/matrix/compatibility_matrix.json"
    ]
    assert profile == [
        ROOT / "src/respect_compat/data/profiles/compatibility_matrix_v0_1.json"
    ]


def test_migration_authorities_exist() -> None:
    for relative in (
        "migration/source_inventory.json",
        "migration/source_manifest.schema.json",
        "migration/source_manifest.json",
        "migration/cutover_receipt.schema.json",
        "MIGRATION_PROVENANCE.md",
        "tools/validate_migration_manifest.py",
    ):
        assert (ROOT / relative).is_file(), relative


def test_four_console_scripts_are_declared() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in (
        "respect-compat",
        "respect-ification",
        "respect-matrix-validate",
        "respect-standards-bootstrap",
    ):
        assert f"{name} =" in pyproject
