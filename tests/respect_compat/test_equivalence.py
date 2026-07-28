# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
import urllib.parse

from respect_compat.equivalence import (
    XAPI_IPC_ACTION,
    deliver_xapi_android_ipc,
    launch_equivalence,
    xapi_equivalence,
)
from respect_compat.xapi_actor import LogicalXapiActor


def test_launch_bindings_preserve_logical_launch_data():
    actor = {
        "objectType": "Agent",
        "account": {"homePage": "https://example.invalid", "name": "learner"},
    }
    values = {
        "endpoint": "http://127.0.0.1/xapi",
        "auth": "Basic test",
        "actor": json.dumps(actor, sort_keys=True),
        "activity_id": "https://example.invalid/activity/1",
    }
    web_url = "https://canapp.invalid/launch?" + urllib.parse.urlencode(values)
    result = launch_equivalence(
        web_url,
        {**values, "xapiIpcPackage": "world.respect"},
    )
    assert result["equivalent"]
    assert result["binding_specific"]["android_xapi_ipc_package"] == "world.respect"


def test_launch_equivalence_detects_changed_logical_value():
    values = {
        "endpoint": "http://127.0.0.1/xapi",
        "auth": "Basic test",
        "actor": json.dumps({"objectType": "Agent"}),
        "activity_id": "https://example.invalid/activity/1",
    }
    web_url = "https://canapp.invalid/launch?" + urllib.parse.urlencode(values)
    result = launch_equivalence(
        web_url,
        {**values, "activity_id": "https://example.invalid/activity/other"},
    )
    assert not result["equivalent"]


def test_xapi_http_and_android_ipc_bindings_are_semantically_equivalent():
    assert xapi_equivalence()["equivalent"]


def test_android_ipc_binding_rejects_wrong_action_without_persisting():
    actor_value = {"objectType": "Agent", "mbox": "mailto:test@example.invalid"}
    actor = LogicalXapiActor("Basic valid", actor_value)
    result = deliver_xapi_android_ipc(
        actor,
        XAPI_IPC_ACTION + ".wrong",
        "correlation",
        "post_statements",
        "Basic valid",
        {
            "actor": actor_value,
            "verb": {"id": "https://example.invalid/verb"},
            "object": {"id": "https://example.invalid/activity"},
        },
    )
    assert not result.accepted
    assert result.logical_status == "unsupported_route"
    assert actor.statements == {}
