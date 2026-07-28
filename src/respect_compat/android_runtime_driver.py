# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


DRIVER_GATED_ROW_IDS = frozenset(
    {
        "ANDROID-001",
        "ANDROID-002",
        "AUTH-001",
        "AUTH-003",
        "LAUNCH-003",
        "LAUNCH-004",
        "LAUNCH-005",
        "LAUNCH-006",
        "LAUNCH-007",
        "LIFECYCLE-001",
        "XAPI-003",
        "XAPI-004",
        "XAPI-005",
        "XAPI-006",
        "XAPI-007",
        "XAPI-008",
        "XAPI-009",
        "XAPI-010",
        "XAPI-011",
        "XAPI-013",
        "XAPI-014",
        "XAPI-015",
        "XAPI-016",
        "XAPI-017",
        "XAPI-018",
        "XAPI-019",
    }
)
DRIVER_SOURCE = "suite-owned-android-runtime-driver"
XAPI_ACTION = "org.openeel.action.xapioveripc"


@dataclass(frozen=True)
class RuntimeBinding:
    target_digest: str
    apk_sha256: str
    driver_sha256: str
    device_id: str
    scenario_nonce: str
    canapp_package: str
    driver_package: str
    endpoint: str
    auth: str
    actor: Dict[str, Any]
    activity_id: str


def _result(state: str, observed: Any, message: str) -> Dict[str, Any]:
    return {
        "state": state,
        "observed": observed,
        "message": message,
        "source": DRIVER_SOURCE,
    }


def _binding_matches(event: Dict[str, Any], binding: RuntimeBinding) -> bool:
    return all(
        event.get(key) == expected
        for key, expected in {
            "target_digest": binding.target_digest,
            "apk_sha256": binding.apk_sha256,
            "driver_sha256": binding.driver_sha256,
            "device_id": binding.device_id,
            "scenario_nonce": binding.scenario_nonce,
        }.items()
    )


def _json(value: Any) -> Optional[Any]:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _requests(events: Iterable[Dict[str, Any]], operation: int) -> List[Dict[str, Any]]:
    return [
        item
        for item in events
        if item.get("kind") == "request"
        and item.get("what") == 1
        and item.get("operation") == operation
        and isinstance(item.get("request_id"), int)
        and item.get("request_id", 0) > 0
        and item.get("has_reply_to") is True
    ]


def _responses(events: Iterable[Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    values: Dict[int, List[Dict[str, Any]]] = {}
    for item in events:
        if item.get("kind") not in {"response", "flow_emission"}:
            continue
        request_id = item.get("request_id")
        if isinstance(request_id, int):
            values.setdefault(request_id, []).append(item)
    return values


def _statements(requests: Iterable[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    values = []
    for request in requests:
        body = _json(request.get("body"))
        if not isinstance(body, list):
            continue
        for statement in body:
            if isinstance(statement, dict):
                values.append((request, statement))
    return values


def _absolute_iri(value: Any) -> bool:
    return isinstance(value, str) and bool(urllib.parse.urlparse(value).scheme)


def _query(request: Dict[str, Any]) -> Dict[str, List[str]]:
    value = request.get("query_params")
    if not isinstance(value, dict):
        return {}
    return {
        str(key): [str(item) for item in items]
        for key, items in value.items()
        if isinstance(items, list)
    }


def _has_success_response(
    request: Dict[str, Any], responses: Dict[int, List[Dict[str, Any]]]
) -> bool:
    return any(
        item.get("status") == 200
        for item in responses.get(request["request_id"], [])
    )


def _successful_results(
    request: Dict[str, Any], responses: Dict[int, List[Dict[str, Any]]]
) -> List[List[Dict[str, Any]]]:
    values = []
    for response in responses.get(request["request_id"], []):
        if response.get("status") != 200:
            continue
        body = _json(response.get("body"))
        if not isinstance(body, dict) or not isinstance(body.get("statements"), list):
            continue
        if all(isinstance(item, dict) for item in body["statements"]):
            values.append(body["statements"])
    return values


def _timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _same_json(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def _default_observations() -> Dict[str, Dict[str, Any]]:
    return {
        row_id: _result(
            "blocked",
            {"missing_prerequisite": "attributable suite-owned runtime evidence"},
            "Required suite-owned runtime observation was not captured.",
        )
        for row_id in DRIVER_GATED_ROW_IDS
    }


def project_runtime_observations(
    events: List[Dict[str, Any]],
    binding: RuntimeBinding,
) -> Dict[str, Dict[str, Any]]:
    observations = _default_observations()
    attributable = [
        item
        for item in events
        if isinstance(item, dict)
        and item.get("kind") != "owner_result"
    ]
    if not attributable:
        return observations
    if any(not _binding_matches(item, binding) for item in attributable):
        return {
            row_id: _result(
                "blocked",
                {"binding_valid": False},
                "Runtime evidence binding did not match the submitted target.",
            )
            for row_id in DRIVER_GATED_ROW_IDS
        }

    app_links = [
        item for item in attributable if item.get("kind") == "app_link_resolved"
    ]
    if app_links:
        app_link = app_links[-1]
        resolved = app_link.get("resolved_package") == binding.canapp_package
        observations["ANDROID-001"] = _result(
            "pass" if resolved else "fail",
            app_link,
            (
                "The production HTTPS App Link resolved to the submitted CanApp."
                if resolved
                else "The production HTTPS App Link did not resolve to the submitted CanApp."
            ),
        )
        associated = resolved and app_link.get("domain_verified") is True
        observations["ANDROID-002"] = _result(
            "pass" if associated else "fail",
            app_link,
            (
                "Android reported a verified domain association for the submitted CanApp."
                if associated
                else "Android did not report a verified domain association for the submitted CanApp."
            ),
        )

    binds = [
        item
        for item in attributable
        if item.get("kind") == "service_bound"
        and item.get("action") == XAPI_ACTION
        and item.get("explicit_package") == binding.driver_package
        and item.get("client_package") == binding.canapp_package
    ]
    if binds:
        bind = binds[-1]
        for row_id in ("LAUNCH-007", "XAPI-003", "XAPI-013"):
            observations[row_id] = _result(
                "pass",
                bind,
                "The CanApp explicitly bound the suite-owned xAPI IPC service.",
            )

    post_requests = _requests(attributable, 3)
    get_requests = _requests(attributable, 1)
    flow_requests = _requests(attributable, 2)
    response_map = _responses(attributable)
    statement_pairs = _statements(post_requests)
    regular_pairs = [
        pair
        for pair in statement_pairs
        if pair[1].get("verb", {}).get("id")
        != "http://adlnet.gov/expapi/verbs/voided"
    ]
    voiding_pairs = [
        pair
        for pair in statement_pairs
        if pair[1].get("verb", {}).get("id")
        == "http://adlnet.gov/expapi/verbs/voided"
    ]

    exact_transport = [
        request
        for request in post_requests
        if request.get("endpoint") == binding.endpoint
        and request.get("auth") == binding.auth
        and request.get("client_package") == binding.canapp_package
    ]
    if exact_transport:
        observations["AUTH-001"] = _result(
            "pass",
            {"request_ids": [item["request_id"] for item in exact_transport]},
            "The captured request used the controlled authenticated account route.",
        )
        observations["LAUNCH-003"] = _result(
            "pass",
            {"endpoint": binding.endpoint},
            "The captured request preserved the exact launch endpoint.",
        )
        observations["LAUNCH-005"] = _result(
            "pass",
            {"authorization_matched": True},
            "The captured request preserved the exact controlled authorization value.",
        )

    valid_statements = [
        statement
        for _, statement in regular_pairs
        if all(field in statement for field in ("actor", "verb", "object"))
    ]
    if valid_statements:
        observations["XAPI-006"] = _result(
            "pass",
            {"statement_count": len(valid_statements)},
            "Captured statements contained actor, verb, and object.",
        )
        identifiers_valid = all(
            _absolute_iri(statement.get("verb", {}).get("id"))
            and _absolute_iri(statement.get("object", {}).get("id"))
            for statement in valid_statements
        )
        observations["XAPI-007"] = _result(
            "pass" if identifiers_valid else "fail",
            {"identifiers_valid": identifiers_valid},
            (
                "Every captured statement identifier was an absolute IRI."
                if identifiers_valid
                else "A captured statement identifier was not an absolute IRI."
            ),
        )
        scores = [
            statement.get("result", {}).get("score", {}).get("scaled")
            for statement in valid_statements
            if "scaled" in statement.get("result", {}).get("score", {})
        ]
        scores_valid = bool(scores) and all(
            isinstance(value, (int, float)) and -1 <= value <= 1
            for value in scores
        )
        observations["XAPI-008"] = _result(
            "pass" if scores_valid else "fail",
            {"scaled_scores": scores},
            (
                "Every captured scaled score was within the active bounds."
                if scores_valid
                else "A captured scaled score was absent or outside the active bounds."
            ),
        )
        actors_valid = all(
            _same_json(statement.get("actor"), binding.actor)
            for statement in valid_statements
        )
        for row_id in ("AUTH-003", "LAUNCH-006", "XAPI-009"):
            observations[row_id] = _result(
                "pass" if actors_valid else "fail",
                {"actor_matched": actors_valid},
                (
                    "Every captured statement actor matched the controlled launch actor."
                    if actors_valid
                    else "A captured statement actor did not match the controlled launch actor."
                ),
            )
        activities_valid = all(
            statement.get("object", {}).get("id") == binding.activity_id
            for statement in valid_statements
        )
        observations["LAUNCH-004"] = _result(
            "pass" if activities_valid else "fail",
            {"activity_matched": activities_valid},
            (
                "Every captured statement used the controlled activity identifier."
                if activities_valid
                else "A captured statement used a different activity identifier."
            ),
        )

    correlated_posts = [
        request
        for request in post_requests
        if _has_success_response(request, response_map)
    ]
    if correlated_posts:
        observations["XAPI-004"] = _result(
            "pass",
            {"request_ids": [item["request_id"] for item in correlated_posts]},
            "Statement POST requests received correlated successful replies.",
        )

    by_statement_id: Dict[str, List[Tuple[Dict[str, Any], Dict[str, Any]]]] = {}
    for pair in regular_pairs:
        statement_id = pair[1].get("id")
        if isinstance(statement_id, str):
            by_statement_id.setdefault(statement_id, []).append(pair)
    duplicate_ok = False
    conflict_ok = False
    for pairs in by_statement_id.values():
        for index, left in enumerate(pairs):
            for right in pairs[index + 1 :]:
                same = _same_json(left[1], right[1])
                status = [
                    item.get("status")
                    for item in response_map.get(right[0]["request_id"], [])
                ]
                duplicate_ok = duplicate_ok or (same and 200 in status)
                conflict_ok = conflict_ok or (not same and 409 in status)
    if duplicate_ok or conflict_ok:
        accepted = duplicate_ok and conflict_ok
        observations["XAPI-010"] = _result(
            "pass" if accepted else "fail",
            {
                "identical_duplicate_accepted": duplicate_ok,
                "conflicting_duplicate_rejected": conflict_ok,
            },
            (
                "Duplicate identifier controls matched the active semantics."
                if accepted
                else "A duplicate identifier control did not match the active semantics."
            ),
        )

    completed_flows = {
        item.get("request_id")
        for item in attributable
        if item.get("kind") == "flow_completed"
    }
    flow_ok = any(
        request["request_id"] in completed_flows
        and any(
            response.get("kind") == "flow_emission"
            and response.get("status") == 200
            for response in response_map.get(request["request_id"], [])
        )
        for request in flow_requests
    )
    if get_requests or flow_requests:
        observations["XAPI-005"] = _result(
            "pass" if flow_ok and bool(get_requests) else "fail",
            {
                "get_request_count": len(get_requests),
                "flow_request_count": len(flow_requests),
                "flow_completed": flow_ok,
            },
            (
                "Statement retrieval and flow completion were captured."
                if flow_ok and get_requests
                else "Statement retrieval or flow completion evidence was incomplete."
            ),
        )

    submitted: Dict[str, Dict[str, Any]] = {}
    for _, statement in statement_pairs:
        statement_id = statement.get("id")
        if isinstance(statement_id, str):
            submitted.setdefault(statement_id, statement)

    def successful_query(predicate, result_predicate) -> Optional[Dict[str, Any]]:
        return next(
            (
                request
                for request in get_requests
                if predicate(_query(request))
                and any(
                    result_predicate(_query(request), result)
                    for result in _successful_results(request, response_map)
                )
            ),
            None,
        )

    def exact_identifier_result(
        key: str, query: Dict[str, List[str]], result: List[Dict[str, Any]]
    ) -> bool:
        identifiers = query.get(key, [])
        return (
            len(identifiers) == 1
            and identifiers[0] in submitted
            and len(result) == 1
            and _same_json(result[0], submitted[identifiers[0]])
        )

    def primary_filters_match(
        query: Dict[str, List[str]], result: List[Dict[str, Any]]
    ) -> bool:
        if not result:
            return False
        agent_values = query.get("agent", [])
        verb_values = query.get("verb", [])
        activity_values = query.get("activity", [])
        if not agent_values or not verb_values or not activity_values:
            return False
        agent = _json(agent_values[0])
        return all(
            _same_json(statement.get("actor"), agent)
            and statement.get("verb", {}).get("id") == verb_values[0]
            and statement.get("object", {}).get("id") == activity_values[0]
            and statement.get("id") in submitted
            for statement in result
        )

    def bounded_result(
        query: Dict[str, List[str]], result: List[Dict[str, Any]]
    ) -> bool:
        try:
            since = _timestamp(query["since"][0])
            until = _timestamp(query["until"][0])
            limit = int(query["limit"][0])
            ascending = query["ascending"][0].lower() == "true"
        except (KeyError, IndexError, ValueError):
            return False
        timestamps = [_timestamp(item.get("timestamp")) for item in result]
        if since is None or until is None or any(item is None for item in timestamps):
            return False
        ordered = timestamps == sorted(timestamps, reverse=not ascending)
        return (
            0 < len(result) <= limit
            and ordered
            and all(since <= item <= until for item in timestamps if item is not None)
            and all(item.get("id") in submitted for item in result)
        )

    query_rows = {
        "XAPI-014": (
            lambda query: "statementId" in query,
            lambda query, result: exact_identifier_result(
                "statementId", query, result
            ),
        ),
        "XAPI-015": (
            lambda query: "voidedStatementId" in query,
            lambda query, result: exact_identifier_result(
                "voidedStatementId", query, result
            ),
        ),
        "XAPI-016": (
            lambda query: all(
                key in query for key in ("agent", "verb", "activity")
            ),
            primary_filters_match,
        ),
        "XAPI-017": (
            lambda query: (
                "related_agents" in query or "relatedAgents" in query
            )
            and ("related_activities" in query or "relatedActivities" in query),
            lambda _query_value, result: bool(result)
            and all(item.get("id") in submitted for item in result),
        ),
        "XAPI-018": (
            lambda query: all(
                key in query for key in ("since", "until", "ascending", "limit")
            ),
            bounded_result,
        ),
        "XAPI-019": (
            lambda query: query.get("format", [None])[0]
            in {"exact", "canonical", "ids"},
            lambda query, result: (
                query.get("format", [None])[0] == "exact"
                and bool(result)
                and all(
                    item.get("id") in submitted
                    and _same_json(item, submitted[item["id"]])
                    for item in result
                )
            ),
        ),
    }
    for row_id, (request_predicate, result_predicate) in query_rows.items():
        candidates = [
            request
            for request in get_requests
            if request_predicate(_query(request))
        ]
        request = successful_query(request_predicate, result_predicate)
        if candidates:
            passed = request is not None
            if request is not None:
                observed_request = request
            else:
                observed_request = candidates[0]
            observations[row_id] = _result(
                "pass" if passed else "fail",
                {
                    "request_id": observed_request["request_id"],
                    "query_params": _query(observed_request),
                    "result_semantics_valid": passed,
                },
                (
                    "The controlled retrieval result matched the row-specific semantic oracle."
                    if passed
                    else "The controlled retrieval result did not match the row-specific semantic oracle."
                ),
            )

    voided_ids = {
        statement.get("object", {}).get("id")
        for _, statement in voiding_pairs
        if statement.get("object", {}).get("objectType") == "StatementRef"
    }
    void_retrieval = successful_query(
        lambda query: bool(set(query.get("voidedStatementId", [])) & voided_ids),
        lambda query, result: exact_identifier_result(
            "voidedStatementId", query, result
        ),
    )
    if voiding_pairs or void_retrieval is not None:
        accepted = bool(voiding_pairs) and void_retrieval is not None
        observations["XAPI-011"] = _result(
            "pass" if accepted else "fail",
            {
                "voiding_statement_count": len(voiding_pairs),
                "voided_retrieval": void_retrieval is not None,
            },
            (
                "The controlled voiding and retrieval sequence completed."
                if accepted
                else "The controlled voiding and retrieval sequence was incomplete."
            ),
        )

    unbound = any(
        item.get("kind") == "service_unbound"
        and item.get("client_package") == binding.canapp_package
        for item in attributable
    )
    if unbound:
        observations["LIFECYCLE-001"] = _result(
            "pass",
            {"service_unbound": True},
            "The CanApp released the suite-owned service connection.",
        )
    return observations
