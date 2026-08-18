# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import pytest

from respect_compat.xapi_actor import LogicalXapiActor


ACTOR = {
    "objectType": "Agent",
    "account": {"homePage": "https://example.invalid", "name": "learner"},
}
STATEMENT = {
    "id": "00000000-0000-4000-8000-000000000010",
    "actor": ACTOR,
    "verb": {"id": "https://example.invalid/verb/completed"},
    "object": {"id": "https://example.invalid/activity/lesson"},
    "result": {"score": {"scaled": 0.75}},
}


def test_xapi_actor_passes_positive_and_single_fault_negative_controls():
    health = LogicalXapiActor("Basic valid", ACTOR).health_check()
    assert health.healthy
    assert "accepted=True" in health.positive_control
    assert "status=403" in health.negative_control


def test_xapi_actor_submission_retrieval_duplicate_and_voiding():
    actor = LogicalXapiActor("Basic valid", ACTOR)
    first = actor.submit(STATEMENT, "Basic valid")
    duplicate = actor.submit(STATEMENT, "Basic valid")
    assert first["accepted"]
    assert duplicate["duplicate"]
    assert actor.retrieve(statement_id=STATEMENT["id"]) == [STATEMENT]
    assert actor.void(STATEMENT["id"], "Basic valid")["accepted"]
    assert actor.retrieve(statement_id=STATEMENT["id"]) == []
    assert actor.retrieve(voided_statement_id=STATEMENT["id"]) == [STATEMENT]


def test_xapi_actor_rejects_bad_auth_actor_iri_and_score():
    actor = LogicalXapiActor("Basic valid", ACTOR)
    assert actor.submit(STATEMENT, "Basic invalid")["status"] == 403
    assert actor.submit({**STATEMENT, "actor": {}}, "Basic valid")["error"] == "actor_mismatch"
    assert actor.submit(
        {**STATEMENT, "verb": {"id": "relative"}},
        "Basic valid",
    )["error"] == "invalid_iri"
    assert actor.submit(
        {**STATEMENT, "result": {"score": {"scaled": 2}}},
        "Basic valid",
    )["error"] == "invalid_score"


def test_xapi_actor_rejects_boolean_scaled_score():
    response = LogicalXapiActor("Basic valid", ACTOR).submit(
        {**STATEMENT, "result": {"score": {"scaled": True}}},
        "Basic valid",
    )

    assert response == {
        "accepted": False,
        "status": 400,
        "error": "invalid_score",
    }


@pytest.mark.parametrize("verb", [None, "completed", []])
def test_xapi_actor_gracefully_rejects_non_mapping_verb(verb):
    response = LogicalXapiActor("Basic valid", ACTOR).submit(
        {**STATEMENT, "verb": verb},
        "Basic valid",
    )

    assert response["accepted"] is False
    assert response["status"] == 400


@pytest.mark.parametrize("statement_object", [None, "lesson", []])
def test_xapi_actor_gracefully_rejects_non_mapping_object(statement_object):
    response = LogicalXapiActor("Basic valid", ACTOR).submit(
        {**STATEMENT, "object": statement_object},
        "Basic valid",
    )

    assert response["accepted"] is False
    assert response["status"] == 400


@pytest.mark.parametrize(
    "result",
    [
        "completed",
        [],
        {"score": "perfect"},
        {"score": []},
    ],
)
def test_xapi_actor_gracefully_rejects_non_mapping_result_or_score(result):
    response = LogicalXapiActor("Basic valid", ACTOR).submit(
        {**STATEMENT, "result": result},
        "Basic valid",
    )

    assert response["accepted"] is False
    assert response["status"] == 400
