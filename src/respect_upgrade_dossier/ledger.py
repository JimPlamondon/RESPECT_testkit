# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Append-only, hash-chained Dossier lifecycle ledger."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict


def _hash(event: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def append_event(path: Path, event: Dict[str, Any]) -> Dict[str, Any]:
    previous = "0" * 64
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines:
            previous = json.loads(lines[-1])["event_hash"]
    core = {**event, "previous_event_hash": previous}
    core["event_hash"] = _hash(core)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(core, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return core


def verify_ledger(path: Path) -> bool:
    previous = "0" * 64
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        claimed = event.pop("event_hash", None)
        if event.get("previous_event_hash") != previous:
            return False
        if claimed != _hash(event):
            return False
        previous = claimed
    return True
