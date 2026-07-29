# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json

from respect_ification.publication_authorization import (
    ensure_publication_authorization,
)


class FakeSpix:
    def __init__(self):
        self.ensure_calls = 0
        self.status_calls = 0
        self.status = "signature_pending"
        self.issue_calls = 0

    def ensure(self, request, idempotency_key):
        self.ensure_calls += 1
        return {
            "request_id": "request-123",
            "docusign_envelope_id": "envelope-123",
            "status": self.status,
            "status_url": "https://spix.example/requests/request-123",
            "signing_url": "https://docusign.example/sign/envelope-123",
        }

    def status_for(self, status_url):
        self.status_calls += 1
        result = {
            "request_id": "request-123",
            "docusign_envelope_id": "envelope-123",
            "status": self.status,
            "status_url": status_url,
        }
        if self.status == "authorized":
            result["authorization_token"] = {
                "payload": {"token_id": "authorization-123"},
                "signature": {"value": "signed"},
            }
        return result

    def issue_authorization(self, request, idempotency_key):
        self.issue_calls += 1
        return {
            "status": "authorized",
            "authorization_token": {
                "payload": {"token_id": "authorization-123"},
                "signature": {"value": "signed"},
            },
        }


def _request():
    return {
        "publisher_id": "publisher-123",
        "agreement_version": "2026-01",
        "app_id": "https://publisher.example/apps/candidate",
        "artifact_sha256": "ab" * 32,
        "immutable_artifact_url": (
            "https://publisher.example/builds/" + "ab" * 32 + "/candidate.apk"
        ),
    }


def test_pending_rerun_checks_existing_request_without_new_envelope(tmp_path):
    state_path = tmp_path / "authorization-state.json"
    token_path = tmp_path / "publication-authorization.json"
    spix = FakeSpix()
    opened = []

    first = ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
        open_signing=True,
        browser_open=opened.append,
    )
    second = ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
        open_signing=True,
        browser_open=opened.append,
    )

    assert first["status"] == second["status"] == "signature_pending"
    assert spix.ensure_calls == 1
    assert spix.status_calls == 1
    assert opened == ["https://docusign.example/sign/envelope-123"]
    persisted = json.loads(state_path.read_text())
    assert persisted["request_id"] == "request-123"
    assert persisted["docusign_envelope_id"] == "envelope-123"
    assert "oauth" not in json.dumps(persisted).lower()
    assert "docusign.example/sign" not in json.dumps(persisted)


def test_completed_request_writes_spix_token_without_replacing_envelope(tmp_path):
    state_path = tmp_path / "authorization-state.json"
    token_path = tmp_path / "publication-authorization.json"
    spix = FakeSpix()
    ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
    )
    spix.status = "authorized"

    state = ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
    )

    assert state["status"] == "authorized"
    assert spix.ensure_calls == 1
    assert token_path.is_file()
    assert json.loads(token_path.read_text())["payload"]["token_id"] == (
        "authorization-123"
    )


def test_changed_request_requires_explicit_replacement(tmp_path):
    state_path = tmp_path / "authorization-state.json"
    token_path = tmp_path / "publication-authorization.json"
    spix = FakeSpix()
    ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
    )
    changed = _request()
    changed["agreement_version"] = "2027-01"

    try:
        ensure_publication_authorization(
            state_path,
            token_path,
            changed,
            spix,
        )
    except ValueError as error:
        assert "explicit replacement" in str(error)
    else:
        raise AssertionError("changed legal request was silently replaced")

    assert spix.ensure_calls == 1


def test_terminal_request_is_replaced_only_after_explicit_approval(tmp_path):
    state_path = tmp_path / "authorization-state.json"
    token_path = tmp_path / "publication-authorization.json"
    spix = FakeSpix()
    spix.status = "expired"
    ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
    )

    ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
    )
    assert spix.ensure_calls == 1

    ensure_publication_authorization(
        state_path,
        token_path,
        _request(),
        spix,
        replace_terminal_request=True,
    )
    assert spix.ensure_calls == 2
