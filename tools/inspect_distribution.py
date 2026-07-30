#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    errors = []
    with zipfile.ZipFile(args.wheel) as archive:
        names = archive.namelist()
        canonical = [name for name in names if name.endswith("/data/matrix/compatibility_matrix.json")]
        historical = [name for name in names if name.endswith("/data/profiles/compatibility_matrix_v0_1.json")]
        if len(canonical) != 1:
            errors.append(f"canonical Matrix count is {len(canonical)}")
        if len(historical) != 1:
            errors.append(f"historical profile count is {len(historical)}")
        if any(name.startswith("respect_upgrade_dossier/") for name in names):
            errors.append("wheel contains embedded Upgrade Dossier package")
        if any(name.endswith("/data/matrix/upgrade_matrix.json") for name in names):
            errors.append("wheel contains an Upgrade Matrix")
        entry_points = [
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        ]
        if len(entry_points) != 1:
            errors.append(
                f"entry-points metadata count is {len(entry_points)}"
            )
        else:
            entry_text = archive.read(entry_points[0]).decode(
                "utf-8", errors="replace"
            )
            if (
                "respect-upgrade-dossier" in entry_text
                or "respect_upgrade_dossier" in entry_text
            ):
                errors.append("wheel exposes the Upgrade Dossier CLI")
        forbidden_suffixes = (".apk", ".jks", ".keystore", ".env")
        for name in names:
            lowered = name.lower()
            if (
                name.endswith(".DS_Store")
                or name.endswith("matrix_validation_report.json")
                or lowered.endswith(forbidden_suffixes)
                or "Plans/ProgressLedger" in name
                or "/.git/" in name
                or "/__pycache__/" in name
            ):
                errors.append(f"forbidden wheel member: {name}")
            if name.endswith((".py", ".toml", ".cfg", ".ini")):
                text = archive.read(name).decode("utf-8", errors="replace")
                for pattern in (
                    r"/Users/",
                    r"licensing-public/",
                    r"Path\(__file__\).*parents",
                ):
                    if re.search(pattern, text):
                        errors.append(f"executable path dependency in {name}: {pattern}")
    print(json.dumps({"errors": errors, "valid": not errors}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
