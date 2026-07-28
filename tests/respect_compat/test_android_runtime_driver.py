# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import json

from respect_compat.android_runtime_driver import (
    DRIVER_GATED_ROW_IDS,
    RuntimeBinding,
    project_runtime_observations,
)


ACTOR = {
    "objectType": "Agent",
    "account": {
        "homePage": "https://example.invalid",
        "name": "driver-actor",
    },
}
ENDPOINT = "https://lrs.example.invalid/xapi/"
AUTH = "Basic driver-control"
ACTIVITY = "https://lesson.example.invalid/activity/one"
DRIVER_PACKAGE = "org.respect.testkit.runtime"
STATEMENT_ID = "00000000-0000-4000-8000-000000000101"
VOIDING_ID = "00000000-0000-4000-8000-000000000102"


def _binding():
    return RuntimeBinding(
        target_digest="target-digest",
        apk_sha256="apk-digest",
        driver_sha256="driver-digest",
        device_id="device-1",
        scenario_nonce="nonce-1",
        canapp_package="org.example.canapp",
        driver_package=DRIVER_PACKAGE,
        endpoint=ENDPOINT,
        auth=AUTH,
        actor=ACTOR,
        activity_id=ACTIVITY,
    )


def _event(kind, **values):
    return {
        "kind": kind,
        "target_digest": "target-digest",
        "apk_sha256": "apk-digest",
        "driver_sha256": "driver-digest",
        "device_id": "device-1",
        "scenario_nonce": "nonce-1",
        **values,
    }


def _statement(statement_id=STATEMENT_ID, score=0.75):
    return {
        "id": statement_id,
        "actor": ACTOR,
        "verb": {"id": "https://w3id.org/xapi/adl/verbs/completed"},
        "object": {"id": ACTIVITY},
        "result": {"score": {"scaled": score}, "completion": True},
        "timestamp": "2026-07-28T00:00:00Z",
    }


def _passing_events():
    statement = _statement()
    voiding = {
        "id": VOIDING_ID,
        "actor": ACTOR,
        "verb": {"id": "http://adlnet.gov/expapi/verbs/voided"},
        "object": {
            "objectType": "StatementRef",
            "id": STATEMENT_ID,
        },
    }
    common_request = {
        "what": 1,
        "endpoint": ENDPOINT,
        "auth": AUTH,
        "client_package": "org.example.canapp",
        "has_reply_to": True,
    }
    return [
        _event(
            "app_link_resolved",
            resolved_package="org.example.canapp",
            domain_verified=True,
        ),
        _event(
            "service_bound",
            action="org.openeel.action.xapioveripc",
            explicit_package=DRIVER_PACKAGE,
            client_package="org.example.canapp",
        ),
        _event(
            "request",
            **common_request,
            request_id=1,
            operation=3,
            body=json.dumps([statement]),
        ),
        _event(
            "response",
            request_id=1,
            status=200,
            body=json.dumps([STATEMENT_ID]),
        ),
        _event(
            "request",
            **common_request,
            request_id=2,
            operation=3,
            body=json.dumps([statement]),
        ),
        _event(
            "response",
            request_id=2,
            status=200,
            body=json.dumps([STATEMENT_ID]),
        ),
        _event(
            "request",
            **common_request,
            request_id=3,
            operation=3,
            body=json.dumps([{**statement, "result": {"completion": False}}]),
        ),
        _event("response", request_id=3, status=409),
        _event(
            "request",
            **common_request,
            request_id=4,
            operation=3,
            body=json.dumps([voiding]),
        ),
        _event(
            "response",
            request_id=4,
            status=200,
            body=json.dumps([VOIDING_ID]),
        ),
        _event(
            "request",
            **common_request,
            request_id=5,
            operation=1,
            query_params={"statementId": [STATEMENT_ID]},
        ),
        _event(
            "response",
            request_id=5,
            status=200,
            body=json.dumps({"statements": [statement], "more": None}),
        ),
        _event(
            "request",
            **common_request,
            request_id=6,
            operation=1,
            query_params={"voidedStatementId": [STATEMENT_ID]},
        ),
        _event(
            "response",
            request_id=6,
            status=200,
            body=json.dumps({"statements": [statement], "more": None}),
        ),
        _event(
            "request",
            **common_request,
            request_id=7,
            operation=1,
            query_params={
                "agent": [json.dumps(ACTOR, sort_keys=True)],
                "verb": ["https://w3id.org/xapi/adl/verbs/completed"],
                "activity": [ACTIVITY],
            },
        ),
        _event(
            "response",
            request_id=7,
            status=200,
            body=json.dumps({"statements": [statement], "more": None}),
        ),
        _event(
            "request",
            **common_request,
            request_id=8,
            operation=1,
            query_params={
                "agent": [json.dumps(ACTOR, sort_keys=True)],
                "activity": [ACTIVITY],
                "related_agents": ["true"],
                "related_activities": ["true"],
            },
        ),
        _event(
            "response",
            request_id=8,
            status=200,
            body=json.dumps({"statements": [statement], "more": None}),
        ),
        _event(
            "request",
            **common_request,
            request_id=9,
            operation=1,
            query_params={
                "since": ["2026-07-27T00:00:00Z"],
                "until": ["2026-07-29T00:00:00Z"],
                "ascending": ["true"],
                "limit": ["1"],
            },
        ),
        _event(
            "response",
            request_id=9,
            status=200,
            body=json.dumps({"statements": [statement], "more": None}),
        ),
        _event(
            "request",
            **common_request,
            request_id=10,
            operation=1,
            query_params={"format": ["exact"]},
        ),
        _event(
            "response",
            request_id=10,
            status=200,
            body=json.dumps({"statements": [statement], "more": None}),
        ),
        _event(
            "request",
            **common_request,
            request_id=11,
            operation=2,
            query_params={},
        ),
        _event(
            "flow_emission",
            request_id=11,
            status=200,
            body=json.dumps({"statements": [statement], "more": None}),
        ),
        _event("flow_completed", request_id=11),
        _event("service_unbound", client_package="org.example.canapp"),
    ]


def test_controller_evidence_projects_all_26_rows_without_imported_states():
    observations = project_runtime_observations(_passing_events(), _binding())

    assert set(observations) == DRIVER_GATED_ROW_IDS
    assert all(item["state"] == "pass" for item in observations.values())
    assert all(item["source"] == "suite-owned-android-runtime-driver" for item in observations.values())


def test_wrong_binding_blocks_every_runtime_row():
    events = _passing_events()
    events[1]["target_digest"] = "another-target"

    observations = project_runtime_observations(events, _binding())

    assert all(item["state"] == "blocked" for item in observations.values())
    assert all("binding" in item["message"].lower() for item in observations.values())


def test_verified_domain_is_reported_independently_of_current_user_resolution():
    events = [
        _event(
            "app_link_resolved",
            resolved_package="android/com.android.internal.app.ResolverActivity",
            domain_verified=True,
        )
    ]

    observations = project_runtime_observations(events, _binding())

    assert observations["ANDROID-001"]["state"] == "fail"
    assert observations["ANDROID-002"]["state"] == "pass"


def test_owner_authored_pass_field_is_ignored():
    event = _event("owner_result", row_id="AUTH-001", state="pass")

    observations = project_runtime_observations([event], _binding())

    assert observations["AUTH-001"]["state"] != "pass"


def test_invalid_score_fails_score_row_without_changing_other_statement_rows():
    events = _passing_events()
    first_post = next(
        item
        for item in events
        if item["kind"] == "request" and item.get("request_id") == 1
    )
    statement = _statement(score=2.0)
    first_post["body"] = json.dumps([statement])

    observations = project_runtime_observations(events, _binding())

    assert observations["XAPI-008"]["state"] == "fail"
    assert observations["XAPI-006"]["state"] == "pass"


def test_success_status_cannot_mask_a_wrong_retrieval_result():
    events = _passing_events()
    retrieval = next(
        item
        for item in events
        if item["kind"] == "response" and item.get("request_id") == 5
    )
    retrieval["body"] = json.dumps({"statements": [], "more": None})

    observations = project_runtime_observations(events, _binding())

    assert observations["XAPI-014"]["state"] == "fail"
    assert observations["XAPI-015"]["state"] == "pass"
