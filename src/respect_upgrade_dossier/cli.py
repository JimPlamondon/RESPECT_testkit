# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""CLI for narrow, non-certifying Dossier verification."""

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from .verifier import verify_dossier


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="respect-upgrade-dossier")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("dossier", type=Path)
    arguments = parser.parse_args(argv)
    payload = json.loads(arguments.dossier.read_text(encoding="utf-8"))
    result = verify_dossier(payload)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 2
