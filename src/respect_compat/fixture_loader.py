# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FixtureCase:
    root: Path
    manifest_path: Path
    expected: Dict[str, Any]
    metadata: Dict[str, Any]

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def target(self) -> str:
        return f"fixture://{self.root.name}"


def _fixture_file(
    root: Path,
    path: Path,
    label: str,
    *,
    required: bool,
    reject_symlink_first: bool = True,
) -> Optional[Path]:
    if path.is_symlink() and reject_symlink_first:
        raise ValueError(f"fixture {label} must not be a symlink")
    if not path.exists():
        if required:
            raise FileNotFoundError(f"missing fixture {label}: {path}")
        return None
    resolved_root = root.resolve(strict=True)
    resolved_path = path.resolve(strict=True)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"fixture {label} path escapes fixture root") from error
    if path.is_symlink():
        raise ValueError(f"fixture {label} must not be a symlink")
    if not resolved_path.is_file():
        raise ValueError(f"fixture {label} must be a regular file")
    return resolved_path


def load_fixture(root: Path) -> FixtureCase:
    expected_path = root / "expected.json"
    expected_path = _fixture_file(
        root,
        expected_path,
        "expected.json",
        required=True,
    )
    assert expected_path is not None
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    manifest_name = expected.get("manifest", "appmanifest.json")
    if not isinstance(manifest_name, str) or not manifest_name:
        raise ValueError("fixture manifest path must be a non-empty string")
    resolved_root = root.resolve(strict=True)
    manifest_path = root / manifest_name
    manifest_path = _fixture_file(
        root,
        manifest_path,
        "manifest",
        required=True,
        reject_symlink_first=False,
    )
    assert manifest_path is not None
    metadata_path = root / "metadata.json"
    metadata_path = _fixture_file(
        root,
        metadata_path,
        "metadata.json",
        required=False,
    )
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata_path is not None
        else {}
    )
    return FixtureCase(
        root=resolved_root,
        manifest_path=manifest_path,
        expected=expected,
        metadata=metadata,
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
