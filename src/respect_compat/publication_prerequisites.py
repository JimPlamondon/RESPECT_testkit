# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .engine import ExecutionContext
from .matrix_runtime import MatrixRow
from .models import ResultState
from .target import fetch


def canonical_token_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _artifact(context: ExecutionContext) -> Tuple[Path, str]:
    configured = context.target.metadata.get("publication_artifact_path")
    path = Path(configured) if isinstance(configured, str) else context.target.apk
    if path is None:
        raise FileNotFoundError("certified publication artifact")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise FileNotFoundError("certified publication artifact")
    return resolved, hashlib.sha256(resolved.read_bytes()).hexdigest()


def _publication_state(
    context: ExecutionContext,
    key: str,
    status: str,
    details: Dict[str, Any],
) -> None:
    publication = context.target.metadata.setdefault(
        "_publication_prerequisites", {}
    )
    publication[key] = {"status": status, **details}


def _result(
    context: ExecutionContext,
    row: MatrixRow,
    state: ResultState,
    observed: Dict[str, Any],
    message: str,
):
    evidence = [
        context.evidence(
            row,
            "publication_prerequisite",
            context.target.uri,
            observed,
        )
    ]
    return context.result(row, state, observed, message, evidence)


def _load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.resolve(strict=True).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Spix publication key is not an Ed25519 public key")
    return key


def _decode_signature(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _authorization_executor(
    context: ExecutionContext,
    row: MatrixRow,
):
    token_value = context.target.metadata.get(
        "publication_authorization_token"
    )
    testing_private_value = context.target.metadata.get(
        "_testing_certification_private_key"
    )
    testing_token = (
        token_value is None
        and isinstance(testing_private_value, str)
        and context.target.metadata.get("_spix_key_provenance")
        == "testing_generated"
    )
    key_value = context.target.metadata.get("spix_public_key")
    missing = []
    if not isinstance(token_value, str) and not testing_token:
        missing.append("publication authorization token")
    if not isinstance(key_value, str):
        missing.append("Spix publication public key")
    try:
        _, artifact_sha256 = _artifact(context)
    except FileNotFoundError:
        artifact_sha256 = ""
        missing.append("certified publication artifact")
    immutable_url = context.target.metadata.get("immutable_artifact_url")
    if not isinstance(immutable_url, str):
        missing.append("immutable certified-build URL")
    metadata = context.target.document.get("metadata", {})
    app_id = metadata.get("identifier") if isinstance(metadata, dict) else None
    if not isinstance(app_id, str):
        missing.append("stable CanApp identifier")
    if missing:
        observed = {"missing": sorted(set(missing))}
        _publication_state(
            context, "authorization", "missing", observed
        )
        return _result(
            context,
            row,
            ResultState.INCOMPLETE,
            observed,
            "Publication authorization is not yet available.",
        )

    errors = []
    token_id = None
    try:
        if testing_token:
            private_key = serialization.load_pem_private_key(
                Path(testing_private_value)
                .resolve(strict=True)
                .read_bytes(),
                password=None,
            )
            if not isinstance(private_key, Ed25519PrivateKey):
                raise ValueError(
                    "testing certification private key is not Ed25519"
                )
            payload = {
                "format_version": "1.0.0",
                "issuer": "respect-testkit:testing-only",
                "publisher_id": "respect-testkit-testing-only",
                "app_id": app_id,
                "artifact_sha256": artifact_sha256,
                "immutable_artifact_url": immutable_url,
                "scope": ["registry:publish-if-certified"],
                "agreement": {
                    "version": "testing-only",
                    "docusign_envelope_id": "testing-only",
                },
                "issued_at": datetime.now(timezone.utc).isoformat(),
                "token_id": (
                    f"testing-{artifact_sha256[:24]}"
                ),
            }
            token = {
                "payload": payload,
                "signature": {
                    "algorithm": "Ed25519",
                    "key_id": context.target.metadata.get(
                        "_spix_key_id"
                    ),
                    "value": base64.urlsafe_b64encode(
                        private_key.sign(canonical_token_bytes(payload))
                    )
                    .decode("ascii")
                    .rstrip("="),
                },
            }
        else:
            token = json.loads(
                Path(token_value).resolve(strict=True).read_text()
            )
        payload = token["payload"]
        signature = token["signature"]
        if (
            not isinstance(payload, dict)
            or not isinstance(signature, dict)
            or signature.get("algorithm") != "Ed25519"
        ):
            raise ValueError("unsupported token structure or algorithm")
        public_key = _load_public_key(Path(key_value))
        public_key.verify(
            _decode_signature(str(signature.get("value", ""))),
            canonical_token_bytes(payload),
        )
        token_id = payload.get("token_id")
        expected = {
            "format_version": "1.0.0",
            "app_id": app_id,
            "artifact_sha256": artifact_sha256,
            "immutable_artifact_url": immutable_url,
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                errors.append(field)
        scope = payload.get("scope")
        if (
            not isinstance(scope, list)
            or "registry:publish-if-certified" not in scope
        ):
            errors.append("scope")
        agreement = payload.get("agreement")
        if not isinstance(agreement, dict) or not all(
            isinstance(agreement.get(field), str)
            and bool(agreement.get(field))
            for field in ("version", "docusign_envelope_id")
        ):
            errors.append("agreement")
        for field in ("issuer", "publisher_id", "issued_at", "token_id"):
            if not isinstance(payload.get(field), str) or not payload.get(field):
                errors.append(field)
    except InvalidSignature:
        errors.append("signature")
    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        errors.append(type(error).__name__)

    observed = {
        "token_id": token_id,
        "verified": not errors,
        "binding_errors": sorted(set(errors)),
        "artifact_sha256": artifact_sha256,
        "immutable_artifact_url": immutable_url,
        "app_id": app_id,
        "authorization_kind": (
            "testing_only" if testing_token else "spix_issued"
        ),
    }
    status = "valid" if not errors else "invalid"
    _publication_state(context, "authorization", status, observed)
    return _result(
        context,
        row,
        ResultState.PASS if not errors else ResultState.FAIL,
        observed,
        (
            "The Spix publication authorization is authentic and bound to "
            "the exact submitted build."
            if not errors
            else "The publication authorization is invalid or bound to a "
            "different app, artifact, or acquisition URL."
        ),
    )


def _immutable_artifact_executor(
    context: ExecutionContext,
    row: MatrixRow,
):
    url = context.target.metadata.get("immutable_artifact_url")
    try:
        artifact_path, expected_digest = _artifact(context)
    except FileNotFoundError:
        artifact_path = None
        expected_digest = ""
    missing = []
    if not isinstance(url, str):
        missing.append("immutable certified-build URL")
    if artifact_path is None:
        missing.append("certified publication artifact")
    if missing:
        observed = {"missing": missing}
        _publication_state(context, "immutable_artifact", "missing", observed)
        return _result(
            context,
            row,
            ResultState.INCOMPLETE,
            observed,
            "The immutable certified-build acquisition URL is not yet available.",
        )

    parsed = urllib.parse.urlsplit(url)
    errors = []
    if parsed.scheme != "https":
        errors.append("URL is not HTTPS")
    if expected_digest.lower() not in parsed.path.lower():
        errors.append("URL is not content-addressed by the artifact SHA-256")
    status = None
    observed_digest = None
    cache_control = ""
    try:
        observation = fetch(url)
        status = observation.status
        observed_digest = hashlib.sha256(observation.body).hexdigest()
        cache_control = observation.headers.get("cache-control", "")
        if status != 200:
            errors.append(f"HTTP status is {status}")
        if observed_digest != expected_digest:
            errors.append("served bytes do not match the submitted artifact")
        directives = {
            item.strip().lower() for item in cache_control.split(",")
        }
        if "immutable" not in directives:
            errors.append("Cache-Control does not declare immutable")
    except Exception as error:
        errors.append(f"fetch failed: {type(error).__name__}")

    observed = {
        "url": url,
        "http_status": status,
        "expected_sha256": expected_digest,
        "observed_sha256": observed_digest,
        "cache_control": cache_control,
        "verified": not errors,
        "errors": errors,
    }
    prerequisite_status = "valid" if not errors else "invalid"
    _publication_state(
        context, "immutable_artifact", prerequisite_status, observed
    )
    return _result(
        context,
        row,
        ResultState.PASS if not errors else ResultState.FAIL,
        observed,
        (
            "The content-addressed HTTPS URL serves the exact submitted "
            "artifact with immutable cache semantics."
            if not errors
            else "The certified-build URL is not an immutable acquisition "
            "of the exact submitted artifact."
        ),
    )


def _certification_key_executor(
    context: ExecutionContext,
    row: MatrixRow,
):
    key_value = context.target.metadata.get("spix_public_key")
    provenance = context.target.metadata.get("_spix_key_provenance")
    if not isinstance(key_value, str):
        observed = {"provenance": "missing", "fingerprint_sha256": None}
        _publication_state(
            context, "certification_key", "missing", observed
        )
        return _result(
            context,
            row,
            ResultState.INCOMPLETE,
            observed,
            "Spix has not supplied a certification trust anchor.",
        )
    errors = []
    fingerprint = None
    try:
        key_path = Path(key_value).resolve(strict=True)
        key_bytes = key_path.read_bytes()
        _load_public_key(key_path)
        fingerprint = hashlib.sha256(key_bytes).hexdigest()
    except (FileNotFoundError, TypeError, ValueError) as error:
        errors.append(type(error).__name__)
    if provenance == "official_bundled" and not errors:
        state = ResultState.PASS
        status = "valid"
        message = (
            "The Test Suite independently supplies the source-locked Spix "
            "certification trust anchor."
        )
    elif provenance == "testing_generated" and not errors:
        state = ResultState.INCOMPLETE
        status = "testing_only"
        message = (
            "The Test Suite is using its persistent testing-only "
            "certification key because no Spix key is available."
        )
    else:
        state = ResultState.FAIL
        status = "invalid"
        if provenance == "submitted_untrusted":
            errors.append("submission supplied its own trust anchor")
        message = (
            "The certification key is invalid or is not independently "
            "anchored by Spix."
        )
    observed = {
        "provenance": provenance or "unknown",
        "key_id": context.target.metadata.get("_spix_key_id"),
        "fingerprint_sha256": fingerprint,
        "errors": errors,
    }
    _publication_state(
        context, "certification_key", status, observed
    )
    return _result(context, row, state, observed, message)


def publication_prerequisite_executor(
    context: ExecutionContext,
    row: MatrixRow,
):
    if row.row_id == "PUBLISH-001":
        return _authorization_executor(context, row)
    if row.row_id == "PUBLISH-002":
        return _immutable_artifact_executor(context, row)
    if row.row_id == "PUBLISH-003":
        return _certification_key_executor(context, row)
    raise ValueError(f"unknown publication prerequisite row: {row.row_id}")
