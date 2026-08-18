# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Durable, hash-chained execution logging for every TestKit command."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Sequence


FORMAT_VERSION = "1.0.0"
LOG_FILENAME = "respect-execution-log.jsonl"
_SENSITIVE_FLAGS = {
    "--auth",
    "--authorization",
    "--keyfile",
    "--password",
    "--publication-authorization-token",
    "--secret",
    "--spix-private-key",
    "--token",
}
_URL_SECRET = re.compile(
    r"(?i)([?&](?:auth|authorization|password|secret|token|api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|private[_-]?key|aws[_-]?secret[_-]?access[_-]?key)=)[^&#\s]+"
)
_URL_USERINFO = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/@\s]+@")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_SENSITIVE_KEY_FAMILIES = (
    "auth",
    "authorization",
    "password",
    "passphrase",
    "secret",
    "token",
    "apikey",
    "clientsecret",
    "accesstoken",
    "refreshtoken",
    "privatekey",
    "keyfile",
    "secretaccesskey",
    "awssecretaccesskey",
)


def _is_sensitive_key(value: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", value.lower())
    return any(compact.endswith(family) for family in _SENSITIVE_KEY_FAMILIES)


def _sanitize_text(value: str) -> str:
    value = _URL_USERINFO.sub(r"\1[REDACTED]@", value)
    value = _URL_SECRET.sub(r"\1[REDACTED]", value)
    return _BEARER.sub("Bearer [REDACTED]", value)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if _is_sensitive_key(str(key))
                else _sanitize_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    return value


def sanitize_argv(argv: Sequence[str]) -> list[str]:
    sanitized: list[str] = []
    redact_next = False
    for value in argv:
        if redact_next:
            sanitized.append("[REDACTED]")
            redact_next = False
            continue
        flag = value.split("=", 1)[0].lower()
        if flag in _SENSITIVE_FLAGS or _is_sensitive_key(flag.lstrip("-")):
            if "=" in value:
                sanitized.append(f"{value.split('=', 1)[0]}=[REDACTED]")
            else:
                sanitized.append(value)
                redact_next = True
            continue
        sanitized.append(_sanitize_text(value))
    return sanitized


def execution_log_path(
    command: str, args: Any, *, suite: bool = False
) -> Path:
    """Return the mandatory, predictable log path for a parsed command."""
    if hasattr(args, "output_dir") and args.output_dir is not None:
        return Path(args.output_dir) / LOG_FILENAME
    if command == "publication-pack":
        output = Path(args.output)
        return output.parent / f"{output.name}.execution-log.jsonl"
    if command == "publication-serve":
        pack = Path(args.pack)
        return pack.parent / f"{pack.name}.serve.execution-log.jsonl"
    for name in (
        "receipt_output",
        "token_output",
        "prompt_output",
        "output",
        "public_output",
        "ledger",
        "state",
    ):
        value = getattr(args, name, None)
        if value is not None:
            path = Path(value)
            return path.parent / f"{path.name}.execution-log.jsonl"
    fallback = Path(os.environ.get("RESPECT_TESTKIT_LOG_DIR", ".respect-testkit/logs"))
    suffix = "suite" if suite else command
    return fallback / f"{suffix}-{os.getpid()}-{secrets.token_hex(6)}.jsonl"


def execution_log_path_from_argv(
    argv: Sequence[str],
    *,
    command: str,
    suite: bool = False,
) -> Path:
    """Resolve a log path before parsing so rejected invocations are logged."""

    def option_value(name: str) -> Optional[str]:
        for index, value in enumerate(argv):
            if value == name and index + 1 < len(argv):
                return argv[index + 1]
            if value.startswith(f"{name}="):
                return value.split("=", 1)[1]
        return None

    output_dir = option_value("--output-dir")
    if output_dir:
        return Path(output_dir) / LOG_FILENAME
    if command == "publication-pack":
        output = option_value("--output")
        if output:
            path = Path(output)
            return path.parent / f"{path.name}.execution-log.jsonl"
    if command == "publication-serve":
        pack = option_value("--pack")
        if pack:
            path = Path(pack)
            return path.parent / f"{path.name}.serve.execution-log.jsonl"
    for name in (
        "--receipt-output",
        "--token-output",
        "--prompt-output",
        "--output",
        "--public-output",
        "--ledger",
        "--state",
    ):
        value = option_value(name)
        if value:
            path = Path(value)
            return path.parent / f"{path.name}.execution-log.jsonl"
    fallback = Path(os.environ.get("RESPECT_TESTKIT_LOG_DIR", ".respect-testkit/logs"))
    suffix = "suite" if suite else command
    return fallback / f"{suffix}-{os.getpid()}-{secrets.token_hex(6)}.jsonl"


class ExecutionLog:
    """Append-only JSON Lines log whose entries form a SHA-256 hash chain."""

    def __init__(
        self,
        path: Path,
        *,
        program: str,
        command: str,
        argv: Sequence[str],
    ) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.program = program
        self.command = command
        self.invocation_id = secrets.token_hex(16)
        self.sequence = 0
        self.previous_event_hash: Optional[str] = None
        self.emit(
            "invocation",
            "started",
            {
                "argv": sanitize_argv(argv),
                "cwd": str(Path.cwd()),
                "pid": os.getpid(),
            },
        )

    def emit(
        self,
        step: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.sequence += 1
        event: Dict[str, Any] = {
            "artifact_type": "respect_testkit_execution_event",
            "format_version": FORMAT_VERSION,
            "invocation_id": self.invocation_id,
            "sequence": self.sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "program": self.program,
            "command": self.command,
            "step": step,
            "status": status,
            "details": _sanitize_value(details or {}),
            "previous_event_hash": self.previous_event_hash,
        }
        encoded = json.dumps(
            event, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        event["event_hash"] = hashlib.sha256(encoded).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.previous_event_hash = event["event_hash"]
        return event

    @contextmanager
    def step(
        self, name: str, details: Optional[Dict[str, Any]] = None
    ) -> Iterator[None]:
        self.emit(name, "started", details)
        try:
            yield
        except BaseException as error:
            self.emit(
                name,
                "failed",
                {
                    "error_type": type(error).__name__,
                    "error": _sanitize_text(str(error)),
                },
            )
            raise
        self.emit(name, "completed", details)

    def finish(self, exit_code: int) -> None:
        self.emit("invocation", "completed", {"exit_code": exit_code})
