# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from respect_compat.engine import ExecutorRegistry, execute
from respect_compat.executors import build_registry
from respect_compat.matrix_runtime import load_matrix
from respect_compat.models import RequirementOwner, ResultState
from respect_compat.publication_prerequisites import canonical_token_bytes
from respect_compat.target import CanAppTarget


def _target(tmp_path, artifact=b"exact certified artifact"):
    path = tmp_path / "candidate.apk"
    path.write_bytes(artifact)
    return CanAppTarget(
        uri="https://publisher.example/descriptor.json",
        adapter="test",
        digest="candidate-target",
        document={
            "metadata": {
                "identifier": "https://publisher.example/apps/candidate",
                "title": "Candidate",
            },
            "links": [],
        },
        apk=path,
        metadata={"publication_artifact_path": str(path)},
        capabilities={"descriptor", "apk", "native_android"},
    )


def _token(tmp_path, private_key, artifact, url, **overrides):
    payload = {
        "format_version": "1.0.0",
        "issuer": "https://registry.spix.example",
        "publisher_id": "publisher-123",
        "app_id": "https://publisher.example/apps/candidate",
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "immutable_artifact_url": url,
        "scope": ["registry:publish-if-certified"],
        "agreement": {
            "version": "2026-01",
            "docusign_envelope_id": "envelope-123",
        },
        "issued_at": "2026-07-29T00:00:00Z",
        "token_id": "authorization-123",
    }
    payload.update(overrides)
    signature = private_key.sign(canonical_token_bytes(payload))
    token = {
        "payload": payload,
        "signature": {
            "algorithm": "Ed25519",
            "key_id": "spix-publication-2026",
            "value": base64.urlsafe_b64encode(signature).decode().rstrip("="),
        },
    }
    path = tmp_path / "publication-authorization.json"
    path.write_text(json.dumps(token), encoding="utf-8")
    return path


def _keys(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_key = tmp_path / "spix-public-key.pem"
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_key, public_key


def _passing_registry(matrix):
    registry = ExecutorRegistry()

    def passing(context, row):
        evidence = [context.evidence(row, "test", "test", {"passed": True})]
        return context.result(row, ResultState.PASS, True, "passed", evidence)

    production = build_registry(matrix)
    for row in matrix.selected_rows("PROFILE-NATIVE_ANDROID"):
        executor = (
            production.executor_for(row.row_id)
            if row.row_id.startswith("PUBLISH-")
            else passing
        )
        registry.register(row.row_id, executor)
    return registry


def test_missing_publication_inputs_are_named_provisions(tmp_path):
    matrix = load_matrix()
    run = execute(
        matrix,
        _target(tmp_path),
        "PROFILE-NATIVE_ANDROID",
        "certification",
        _passing_registry(matrix),
    )

    assert not run.verdict.certified
    assert run.verdict.display == (
        "Provisional (immutable certified-build URL missing; "
        "publication authorization missing; "
        "Spix certification trust anchor missing)"
    )
    assert {
        result.row_id: result.state
        for result in run.results
        if result.row_id.startswith("PUBLISH-")
    } == {
        "PUBLISH-001": ResultState.INCOMPLETE,
        "PUBLISH-002": ResultState.INCOMPLETE,
        "PUBLISH-003": ResultState.INCOMPLETE,
    }


def test_signed_authorization_and_exact_content_addressed_artifact_pass(
    tmp_path, monkeypatch
):
    artifact = b"exact certified artifact"
    digest = hashlib.sha256(artifact).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = artifact
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"https://downloads.example/apps/{digest}/candidate.apk"
        private_key, public_key = _keys(tmp_path)
        token = _token(tmp_path, private_key, artifact, url)
        canapp = _target(tmp_path, artifact)
        canapp.metadata.update(
            {
                "publication_authorization_token": str(token),
                "spix_public_key": str(public_key),
                "immutable_artifact_url": url,
                "_spix_key_provenance": "official_bundled",
            }
        )
        from respect_compat import publication_prerequisites

        original_fetch = publication_prerequisites.fetch
        monkeypatch.setattr(
            publication_prerequisites,
            "fetch",
            lambda requested_url, **kwargs: original_fetch(
                f"http://127.0.0.1:{server.server_port}/"
            ),
        )
        matrix = load_matrix()
        run = execute(
            matrix,
            canapp,
            "PROFILE-NATIVE_ANDROID",
            "certification",
            _passing_registry(matrix),
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    publication = {
        result.row_id: result
        for result in run.results
        if result.row_id.startswith("PUBLISH-")
    }
    assert publication["PUBLISH-001"].state == ResultState.PASS
    assert publication["PUBLISH-002"].state == ResultState.PASS
    assert run.verdict.certified


def test_authorization_binding_mismatch_and_wrong_artifact_bytes_fail(
    tmp_path, monkeypatch
):
    expected = b"exact certified artifact"
    served = b"different artifact"
    digest = hashlib.sha256(expected).hexdigest()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(served)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(served)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"https://downloads.example/apps/{digest}/candidate.apk"
        private_key, public_key = _keys(tmp_path)
        token = _token(
            tmp_path,
            private_key,
            expected,
            url,
            app_id="https://publisher.example/apps/not-candidate",
        )
        canapp = _target(tmp_path, expected)
        canapp.metadata.update(
            {
                "publication_authorization_token": str(token),
                "spix_public_key": str(public_key),
                "immutable_artifact_url": url,
                "_spix_key_provenance": "official_bundled",
            }
        )
        from respect_compat import publication_prerequisites

        original_fetch = publication_prerequisites.fetch
        monkeypatch.setattr(
            publication_prerequisites,
            "fetch",
            lambda requested_url, **kwargs: original_fetch(
                f"http://127.0.0.1:{server.server_port}/"
            ),
        )
        matrix = load_matrix()
        run = execute(
            matrix,
            canapp,
            "PROFILE-NATIVE_ANDROID",
            "certification",
            _passing_registry(matrix),
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    publication = {
        result.row_id: result.state
        for result in run.results
        if result.row_id.startswith("PUBLISH-")
    }
    assert publication == {
        "PUBLISH-001": ResultState.FAIL,
        "PUBLISH-002": ResultState.FAIL,
        "PUBLISH-003": ResultState.PASS,
    }
    owners = {
        result.row_id: result.owner
        for result in run.results
        if result.row_id.startswith("PUBLISH-")
    }
    assert owners == {
        "PUBLISH-001": RequirementOwner.PUBLISHER,
        "PUBLISH-002": RequirementOwner.PUBLISHER,
        "PUBLISH-003": RequirementOwner.SPIX_FOUNDATION,
    }


def test_testing_only_key_exercises_signature_path_but_remains_provisional(
    tmp_path, monkeypatch
):
    artifact = b"exact certified artifact"
    digest = hashlib.sha256(artifact).hexdigest()
    url = f"https://downloads.example/apps/{digest}/candidate.apk"
    from respect_compat.certification_keys import (
        ensure_testing_certification_key,
    )
    from respect_compat import publication_prerequisites

    keys = ensure_testing_certification_key(tmp_path / "keys")
    canapp = _target(tmp_path, artifact)
    canapp.metadata.update(
        {
            "spix_public_key": str(keys.public_key),
            "_testing_certification_private_key": str(keys.private_key),
            "_spix_key_provenance": keys.provenance,
            "_spix_key_id": keys.key_id,
            "immutable_artifact_url": url,
        }
    )
    monkeypatch.setattr(
        publication_prerequisites,
        "fetch",
        lambda requested_url, **kwargs: type(
            "Observation",
            (),
            {
                "status": 200,
                "body": artifact,
                "headers": {
                    "cache-control": (
                        "public, max-age=31536000, immutable"
                    )
                },
            },
        )(),
    )
    matrix = load_matrix()
    run = execute(
        matrix,
        canapp,
        "PROFILE-NATIVE_ANDROID",
        "certification",
        _passing_registry(matrix),
    )

    assert next(
        item for item in run.results if item.row_id == "PUBLISH-001"
    ).state == ResultState.PASS
    assert next(
        item for item in run.results if item.row_id == "PUBLISH-003"
    ).state == ResultState.INCOMPLETE
    assert run.verdict.display == (
        "Provisional (RESPECT certification key is testing-only)"
    )
