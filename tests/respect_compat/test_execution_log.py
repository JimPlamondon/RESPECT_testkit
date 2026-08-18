# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json

from respect_compat.execution_log import ExecutionLog, sanitize_argv


def _expected_hash(event):
    candidate = dict(event)
    candidate.pop("event_hash")
    encoded = json.dumps(
        candidate, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_execution_log_is_append_only_hash_chained_and_redacted(tmp_path):
    path = tmp_path / "execution.jsonl"
    log = ExecutionLog(
        path,
        program="respect-ification",
        command="example",
        argv=[
            "--publication-authorization-token",
            "/private/token.jwt",
            "--manifest-url",
            "https://example.test/?auth=secret-value",
        ],
    )
    with log.step("work", {"authorization": "Bearer secret-value"}):
        pass
    log.finish(0)

    events = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [event["sequence"] for event in events] == list(
        range(1, len(events) + 1)
    )
    assert events[0]["previous_event_hash"] is None
    for prior, event in zip(events, events[1:]):
        assert event["previous_event_hash"] == prior["event_hash"]
    assert all(event["event_hash"] == _expected_hash(event) for event in events)
    serialized = path.read_text(encoding="utf-8")
    assert "secret-value" not in serialized
    assert "/private/token.jwt" not in serialized
    assert "[REDACTED]" in serialized


def test_sanitize_argv_preserves_nonsecret_arguments():
    assert sanitize_argv(["--profile", "PROFILE-WEB"]) == [
        "--profile",
        "PROFILE-WEB",
    ]


def test_execution_log_recursively_redacts_secret_key_families_and_url_userinfo(
    tmp_path,
):
    path = tmp_path / "execution.jsonl"
    log = ExecutionLog(
        path,
        program="respect-ification",
        command="example",
        argv=[
            "--api-key=argv-api-secret",
            "--aws-secret-access-key=argv-aws-secret",
            "--manifest-url",
            (
                "https://url-user:url-password@example.test/descriptor.json"
                "?access_token=url-access-secret&client_secret=url-client-secret"
                "&aws_secret_access_key=url-aws-secret"
            ),
        ],
    )
    log.emit(
        "nested",
        "observed",
        {
            "request": {
                "api_key": "nested-api-secret",
                "client-secret": "nested-client-secret",
                "aws_secret_access_key": "nested-aws-secret",
                "credentials": [
                    {"accessToken": "nested-access-secret"},
                    {"safe": "retained"},
                ],
            }
        },
    )
    log.finish(0)

    serialized = path.read_text(encoding="utf-8")
    for secret in (
        "argv-api-secret",
        "argv-aws-secret",
        "url-user",
        "url-password",
        "url-access-secret",
        "url-client-secret",
        "url-aws-secret",
        "nested-api-secret",
        "nested-client-secret",
        "nested-access-secret",
        "nested-aws-secret",
    ):
        assert secret not in serialized
    assert "retained" in serialized
