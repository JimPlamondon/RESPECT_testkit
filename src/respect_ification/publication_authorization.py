# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional


TERMINAL_STATES = {"declined", "voided", "expired"}
AGREEMENT_COMPLETE_STATES = {"completed", "authorized"}


def _canonical(value: Dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fingerprint(value: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _write(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_status_url(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Spix response has no status URL")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Spix status URL must be HTTPS and contain no embedded credential"
        )
    return value


class SpixPublicationClient:
    def __init__(self, base_url: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        url: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "RESPECT-ification-Kit/1.0",
        }
        data = None
        if body is not None:
            data = _canonical(body)
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        request = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Spix publication service returned a non-object")
        return value

    def ensure(self, request: Dict[str, Any], idempotency_key: str):
        return self._request(
            f"{self.base_url}/v1/publisher-agreements/ensure",
            body=request,
            idempotency_key=idempotency_key,
        )

    def status_for(self, status_url: str):
        return self._request(status_url)

    def issue_authorization(
        self,
        request: Dict[str, Any],
        idempotency_key: str,
    ):
        return self._request(
            f"{self.base_url}/v1/publication-authorizations/ensure",
            body=request,
            idempotency_key=idempotency_key,
        )


def ensure_publication_authorization(
    state_path: Path,
    token_path: Path,
    request: Dict[str, Any],
    client: Any,
    *,
    open_signing: bool = False,
    browser_open: Callable[[str], Any] = webbrowser.open,
    replace_terminal_request: bool = False,
) -> Dict[str, Any]:
    required = {
        "publisher_id",
        "agreement_version",
        "app_id",
        "artifact_sha256",
        "immutable_artifact_url",
    }
    missing = sorted(
        key for key in required if not isinstance(request.get(key), str)
        or not request.get(key)
    )
    if missing:
        raise ValueError(f"publication authorization request missing: {missing}")

    agreement = {
        "publisher_id": request["publisher_id"],
        "agreement_version": request["agreement_version"],
    }
    agreement_key = _fingerprint(agreement)
    build = {
        key: request[key]
        for key in (
            "publisher_id",
            "agreement_version",
            "app_id",
            "artifact_sha256",
            "immutable_artifact_url",
        )
    }
    build_key = _fingerprint(build)
    existing = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.is_file()
        else None
    )
    if existing is not None and not isinstance(existing, dict):
        raise ValueError("publication authorization state must be an object")
    if existing and existing.get("agreement_key") != agreement_key:
        if not (
            replace_terminal_request
            and existing.get("status") in TERMINAL_STATES
        ):
            raise ValueError(
                "agreement identity changed; explicit replacement is required "
                "after a declined, voided, or expired request"
            )
        existing = None
    replacement_request_id = None
    if (
        existing
        and existing.get("status") in TERMINAL_STATES
        and replace_terminal_request
    ):
        replacement_request_id = existing.get("request_id")
        existing = None

    signing_url = None
    if existing is None:
        ensure_request = dict(agreement)
        ensure_key = agreement_key
        if replacement_request_id is not None:
            ensure_request["replace_terminal_request_id"] = (
                replacement_request_id
            )
            ensure_key = _fingerprint(ensure_request)
        response = client.ensure(ensure_request, ensure_key)
        signing_url = response.get("signing_url")
        state = {
            "format_version": "1.0.0",
            "publisher_id": agreement["publisher_id"],
            "agreement_version": agreement["agreement_version"],
            "agreement_key": agreement_key,
            "request_id": response.get("request_id"),
            "docusign_envelope_id": response.get(
                "docusign_envelope_id"
            ),
            "status": response.get("status", "signature_pending"),
            "status_url": _safe_status_url(response.get("status_url")),
            "signing_prompt_presented": False,
        }
    else:
        state = dict(existing)
        status_url = state.get("status_url")
        status_url = _safe_status_url(status_url)
        response = client.status_for(status_url)
        signing_url = response.get("signing_url")
        for key in (
            "request_id",
            "docusign_envelope_id",
            "status",
            "status_url",
        ):
            if response.get(key) is not None:
                state[key] = response[key]
        state["status_url"] = _safe_status_url(state.get("status_url"))

    if (
        open_signing
        and isinstance(signing_url, str)
        and signing_url
        and not state.get("signing_prompt_presented")
    ):
        browser_open(signing_url)
        state["signing_prompt_presented"] = True

    token = response.get("authorization_token")
    if state.get("status") in AGREEMENT_COMPLETE_STATES and token is None:
        issue_request = {
            **build,
            "docusign_envelope_id": state.get("docusign_envelope_id"),
        }
        issued = client.issue_authorization(issue_request, build_key)
        token = issued.get("authorization_token")
        if issued.get("status"):
            state["status"] = issued["status"]
    if token is not None:
        if not isinstance(token, dict):
            raise ValueError("Spix authorization token must be an object")
        _write(token_path, token)
        state["status"] = "authorized"
        state["authorization_build_key"] = build_key
        state["authorization_token_path"] = str(token_path.resolve())

    state["checked_at"] = datetime.now(timezone.utc).isoformat()
    _write(state_path, state)
    return state
