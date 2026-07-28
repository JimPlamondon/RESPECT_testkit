# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import ActorHealth


def _absolute_iri(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urllib.parse.urlparse(value)
    return bool(parsed.scheme)


@dataclass
class LogicalXapiActor:
    expected_auth: str
    expected_actor: Dict[str, Any]
    actor_id: str = "suite-logical-xapi-actor"
    statements: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    voided: set[str] = field(default_factory=set)

    def submit(
        self,
        statement: Dict[str, Any],
        authorization: str,
    ) -> Dict[str, Any]:
        if authorization != self.expected_auth:
            return {"accepted": False, "status": 403, "error": "invalid_auth"}
        missing = [
            field_name
            for field_name in ("actor", "verb", "object")
            if field_name not in statement
        ]
        if missing:
            return {
                "accepted": False,
                "status": 400,
                "error": "missing_fields",
                "fields": missing,
            }
        if statement["actor"] != self.expected_actor:
            return {"accepted": False, "status": 403, "error": "actor_mismatch"}
        verb_id = statement.get("verb", {}).get("id")
        object_id = statement.get("object", {}).get("id")
        if not _absolute_iri(verb_id) or not _absolute_iri(object_id):
            return {"accepted": False, "status": 400, "error": "invalid_iri"}
        scaled = statement.get("result", {}).get("score", {}).get("scaled")
        if scaled is not None and (
            not isinstance(scaled, (int, float)) or not -1 <= scaled <= 1
        ):
            return {"accepted": False, "status": 400, "error": "invalid_score"}
        statement_id = statement.get("id") or str(uuid.uuid4())
        candidate = copy.deepcopy(statement)
        candidate["id"] = statement_id
        existing = self.statements.get(statement_id)
        if existing is not None:
            if existing == candidate:
                return {
                    "accepted": True,
                    "status": 204,
                    "statement_id": statement_id,
                    "duplicate": True,
                }
            return {
                "accepted": False,
                "status": 409,
                "error": "conflicting_statement_id",
            }
        self.statements[statement_id] = candidate
        return {
            "accepted": True,
            "status": 204,
            "statement_id": statement_id,
            "duplicate": False,
        }

    def void(self, statement_id: str, authorization: str) -> Dict[str, Any]:
        if authorization != self.expected_auth:
            return {"accepted": False, "status": 403, "error": "invalid_auth"}
        if statement_id not in self.statements:
            return {"accepted": False, "status": 404, "error": "not_found"}
        self.voided.add(statement_id)
        return {"accepted": True, "status": 204, "statement_id": statement_id}

    def retrieve(
        self,
        *,
        statement_id: Optional[str] = None,
        voided_statement_id: Optional[str] = None,
        agent: Optional[Dict[str, Any]] = None,
        verb: Optional[str] = None,
        activity: Optional[str] = None,
        ascending: bool = True,
        limit: Optional[int] = None,
        format_name: str = "exact",
    ) -> List[Dict[str, Any]]:
        if statement_id:
            item = self.statements.get(statement_id)
            return [copy.deepcopy(item)] if item and statement_id not in self.voided else []
        if voided_statement_id:
            item = self.statements.get(voided_statement_id)
            return (
                [copy.deepcopy(item)]
                if item and voided_statement_id in self.voided
                else []
            )
        values = [
            item
            for key, item in self.statements.items()
            if key not in self.voided
            and (agent is None or item.get("actor") == agent)
            and (verb is None or item.get("verb", {}).get("id") == verb)
            and (activity is None or item.get("object", {}).get("id") == activity)
        ]
        values.sort(key=lambda item: item["id"], reverse=not ascending)
        if limit is not None:
            values = values[:limit]
        if format_name == "ids":
            return [
                {
                    "id": item["id"],
                    "actor": item["actor"],
                    "verb": {"id": item["verb"]["id"]},
                    "object": {"id": item["object"]["id"]},
                }
                for item in values
            ]
        return copy.deepcopy(values)

    def health_check(self) -> ActorHealth:
        self.statements.clear()
        self.voided.clear()
        statement = {
            "id": "00000000-0000-4000-8000-000000000001",
            "actor": copy.deepcopy(self.expected_actor),
            "verb": {"id": "https://example.invalid/verb/completed"},
            "object": {"id": "https://example.invalid/activity/control"},
            "result": {"score": {"scaled": 0.5}},
        }
        positive = self.submit(statement, self.expected_auth)
        negative = self.submit(
            {**statement, "id": "00000000-0000-4000-8000-000000000002"},
            "Basic invalid",
        )
        healthy = (
            positive.get("accepted") is True
            and negative.get("accepted") is False
            and negative.get("status") == 403
        )
        return ActorHealth(
            actor_id=self.actor_id,
            healthy=healthy,
            positive_control=f"accepted={positive.get('accepted')}",
            negative_control=(
                f"accepted={negative.get('accepted')},status={negative.get('status')}"
            ),
            details={"positive": positive, "negative": negative},
        )
