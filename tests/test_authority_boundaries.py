# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def python_imports(package_root):
    imports = set()
    for path in package_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_test_suite_does_not_depend_on_kit_or_private_prep():
    imports = python_imports(ROOT / "src/respect_compat")
    assert not any(name.startswith("respect_ification") for name in imports)
    assert not any(name.startswith("private_prep") for name in imports)


def test_executable_code_has_no_checkout_or_author_path_dependencies():
    forbidden = (
        "/Users/jim",
        "licensing-public/",
        "Path(__file__).resolve().parents",
    )
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}: {token}")
    assert offenders == []


def test_kit_narrow_verifier_is_explicitly_non_certifying():
    verifier = (
        ROOT / "src/respect_ification/verifier.py"
    ).read_text(encoding="utf-8")
    assert '"mode": "narrow_non_certifying"' in verifier
    assert '"certified": False' in verifier


def test_no_generated_or_private_material_is_packaged():
    forbidden_names = {
        ".DS_Store",
        "matrix_validation_report.json",
    }
    forbidden_suffixes = {
        ".apk",
        ".env",
        ".jks",
        ".keystore",
    }
    offenders = []
    for path in (ROOT / "src").rglob("*"):
        if not path.is_file():
            continue
        if path.name in forbidden_names or path.suffix.lower() in forbidden_suffixes:
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
