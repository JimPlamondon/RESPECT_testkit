# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional


TRANSITIONS = {
    "pending": {"diagnosing", "blocked", "abandoned"},
    "diagnosing": {"implementing", "blocked", "abandoned"},
    "implementing": {"verifying", "blocked", "abandoned"},
    "verifying": {"locally_verified", "implementing", "blocked", "abandoned"},
    "locally_verified": {"implementing"},
    "blocked": {"diagnosing", "abandoned"},
    "abandoned": set(),
}


def _event_hash(event: Dict[str, Any]) -> str:
    candidate = dict(event)
    candidate.pop("event_hash", None)
    encoded = json.dumps(
        candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _task_map(plan: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {item["task_id"]: item for item in plan.get("tasks", [])}


def _load_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid ledger JSON at line {line_no}: {error}")
    return events


def read_ledger(path: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    from respect_compat.handoff import canonical_hash

    if plan.get("semantic_hash") != canonical_hash(plan, ("semantic_hash",)):
        raise ValueError("work plan semantic hash mismatch")
    tasks = _task_map(plan)
    states = {
        task_id: {"state": item.get("initial_state", "pending"), "events": []}
        for task_id, item in tasks.items()
    }
    prior_hash = None
    event_ids = set()
    for event in _load_events(path):
        if event.get("event_id") in event_ids:
            raise ValueError("duplicate ledger event identifier")
        event_ids.add(event.get("event_id"))
        if event.get("plan_semantic_hash") != plan.get("semantic_hash"):
            raise ValueError("ledger event work-plan binding mismatch")
        if event.get("prior_event_hash") != prior_hash:
            raise ValueError("ledger prior hash mismatch")
        if event.get("event_hash") != _event_hash(event):
            raise ValueError("ledger event hash mismatch")
        task_id = event.get("task_id")
        if task_id not in tasks:
            raise ValueError(f"unknown ledger task: {task_id}")
        previous = states[task_id]["state"]
        next_state = event.get("state")
        if next_state not in TRANSITIONS.get(previous, set()):
            raise ValueError(f"invalid repair-state transition: {previous} -> {next_state}")
        if next_state == "locally_verified" and not event.get("verifier_result_ref"):
            raise ValueError("locally_verified requires a verifier result reference")
        reference = event.get("verifier_result_ref")
        if reference:
            reference_path = PurePosixPath(reference)
            if (
                reference_path.is_absolute()
                or ".." in reference_path.parts
                or "\\" in reference
                or "://" in reference
            ):
                raise ValueError("unsafe verifier result reference")
        states[task_id]["state"] = next_state
        states[task_id]["events"].append(event["event_id"])
        prior_hash = event["event_hash"]
    return {"tasks": states, "last_event_hash": prior_hash}


def append_event(
    path: Path,
    plan: Dict[str, Any],
    task_id: str,
    state: str,
    note: str,
    verifier_result_ref: Optional[str] = None,
) -> Dict[str, Any]:
    current = read_ledger(path, plan)
    if task_id not in current["tasks"]:
        raise ValueError(f"unknown task: {task_id}")
    previous = current["tasks"][task_id]["state"]
    if state not in TRANSITIONS.get(previous, set()):
        raise ValueError(f"invalid repair-state transition: {previous} -> {state}")
    if state == "locally_verified" and not verifier_result_ref:
        raise ValueError("locally_verified requires a verifier result reference")
    if verifier_result_ref:
        reference_path = PurePosixPath(verifier_result_ref)
        if (
            reference_path.is_absolute()
            or ".." in reference_path.parts
            or "\\" in verifier_result_ref
            or "://" in verifier_result_ref
        ):
            raise ValueError("unsafe verifier result reference")
    if "RESPECT Compatible" in note or "certified" in note.lower():
        raise ValueError("repair ledger cannot record a conformance verdict")
    timestamp = datetime.now(timezone.utc).isoformat()
    ordinal = sum(
        len(item["events"]) for item in current["tasks"].values()
    ) + 1
    event = {
        "event_id": hashlib.sha256(
            f"{plan['semantic_hash']}:{ordinal}:{task_id}:{state}:{timestamp}".encode()
        ).hexdigest()[:24],
        "timestamp": timestamp,
        "plan_semantic_hash": plan["semantic_hash"],
        "task_id": task_id,
        "state_from": previous,
        "state": state,
        "note": note,
        "verifier_result_ref": verifier_result_ref,
        "prior_event_hash": current["last_event_hash"],
    }
    event["event_hash"] = _event_hash(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event
