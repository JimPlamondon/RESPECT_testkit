#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import argparse
import os
import subprocess
from pathlib import Path
from typing import Optional


SOURCES = {
    "opds": (
        "https://github.com/opds-community/specs.git",
        "8fda670fc72f110abcf68ad5d26e99ecfeeabf03",
    ),
    "readium-webpub": (
        "https://github.com/readium/webpub-manifest.git",
        "655ee4bcea7f63e1226f166f6b128d9bea6c655b",
    ),
}


def default_cache() -> Path:
    configured = os.environ.get("RESPECT_STANDARDS_CACHE")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".cache" / "respect-compatible-test-suite" / "standards"
    )


def git(*args: str, cwd: Optional[Path] = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return completed.stdout.strip()


def provision(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for name, (url, revision) in SOURCES.items():
        destination = cache / name
        if not (destination / ".git").exists():
            git("clone", "--filter=blob:none", url, str(destination))
        git("fetch", "origin", revision, cwd=destination)
        git("checkout", "--detach", revision, cwd=destination)
        observed = git("rev-parse", "HEAD", cwd=destination)
        if observed != revision:
            raise RuntimeError(
                f"{name} revision mismatch: expected {revision}, observed {observed}"
            )
        schema_dir = destination / "schema"
        if not schema_dir.is_dir() or not list(schema_dir.rglob("*.schema.json")):
            raise RuntimeError(f"{name} checkout contains no schema files")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=default_cache())
    args = parser.parse_args()
    provision(args.cache.expanduser().resolve())
    print(args.cache.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
