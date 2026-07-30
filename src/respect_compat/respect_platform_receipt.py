# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Generate an immutable build receipt for a RESPECT Platform APK."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import List, Optional

from .android_apk import inspect_apk


def build_receipt(
    apk: Path,
    *,
    respect_revision: str,
    build_id: Optional[str] = None,
    apkanalyzer: Optional[Path] = None,
    java_home: Optional[Path] = None,
) -> dict:
    if not apk.is_file():
        raise ValueError("RESPECT Platform APK is missing")
    inspection = inspect_apk(
        apk,
        apkanalyzer=apkanalyzer,
        java_home=java_home,
    )
    package_id = inspection.get("package_id")
    if not isinstance(package_id, str) or not package_id:
        raise ValueError("RESPECT Platform APK package could not be read")
    apk_digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    return {
        "artifact_type": "respect_platform_build_receipt",
        "format_version": "1.0.0",
        "apk_sha256": apk_digest,
        "package_id": package_id,
        "build_id": build_id or f"{package_id}@{apk_digest[:16]}",
        "respect_revision": respect_revision,
    }


def _git_revision(source_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    revision = completed.stdout.strip()
    if completed.returncode != 0 or not revision:
        raise ValueError("could not determine RESPECT source revision")
    dirty = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if dirty.returncode != 0:
        raise ValueError("could not inspect RESPECT source state")
    if dirty.stdout.strip():
        raise ValueError("RESPECT source must be clean for a build receipt")
    return revision


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bind a RESPECT Platform APK to its source revision."
    )
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--build-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(
            args.apk,
            respect_revision=_git_revision(args.source_root),
            build_id=args.build_id,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Bound {receipt['package_id']} build {receipt['build_id']} "
        f"to RESPECT revision {receipt['respect_revision']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
