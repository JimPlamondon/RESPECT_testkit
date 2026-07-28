# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


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


def load_fixture(root: Path) -> FixtureCase:
    expected_path = root / "expected.json"
    if not expected_path.exists():
        raise FileNotFoundError(f"missing fixture expected.json: {expected_path}")
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    manifest_name = expected.get("manifest", "appmanifest.json")
    metadata_path = root / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    return FixtureCase(root=root, manifest_path=root / manifest_name, expected=expected, metadata=metadata)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
