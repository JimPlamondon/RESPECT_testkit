# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .xapi_actor import LogicalXapiActor


XAPI_IPC_ACTION = "org.openeel.action.xapioveripc"


@dataclass(frozen=True)
class LogicalLaunchData:
    endpoint: str
    auth: str
    actor: Dict[str, Any]
    activity_id: str
    xapi_ipc_package: Optional[str] = None

    def comparable(self) -> Dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "auth": self.auth,
            "actor": self.actor,
            "activity_id": self.activity_id,
        }


def launch_from_web_url(url: str) -> LogicalLaunchData:
    values = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return LogicalLaunchData(
        endpoint=values["endpoint"][0],
        auth=values["auth"][0],
        actor=json.loads(values["actor"][0]),
        activity_id=values["activity_id"][0],
        xapi_ipc_package=values.get("xapiIpcPackage", [None])[0],
    )


def launch_from_android_extras(extras: Dict[str, str]) -> LogicalLaunchData:
    return LogicalLaunchData(
        endpoint=extras["endpoint"],
        auth=extras["auth"],
        actor=json.loads(extras["actor"]),
        activity_id=extras["activity_id"],
        xapi_ipc_package=extras.get("xapiIpcPackage"),
    )


def launch_equivalence(
    web_url: str,
    android_extras: Dict[str, str],
) -> Dict[str, Any]:
    web = launch_from_web_url(web_url)
    android = launch_from_android_extras(android_extras)
    return {
        "equivalent": web.comparable() == android.comparable(),
        "web": web.comparable(),
        "android": android.comparable(),
        "binding_specific": {
            "android_xapi_ipc_package": android.xapi_ipc_package,
        },
    }


@dataclass(frozen=True)
class BindingResult:
    binding: str
    accepted: bool
    logical_status: str
    statement_id: Optional[str]
    persisted_effect_digest: str
    correlation_id: Optional[str] = None

    def comparable(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "logical_status": self.logical_status,
            "statement_id": self.statement_id,
            "persisted_effect_digest": self.persisted_effect_digest,
        }


def _effect_digest(actor: LogicalXapiActor) -> str:
    payload = {
        "statements": actor.statements,
        "voided": sorted(actor.voided),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _logical_status(receipt: Dict[str, Any]) -> str:
    if receipt.get("accepted"):
        return "accepted"
    return str(receipt.get("error", "rejected"))


def deliver_xapi_http(
    actor: LogicalXapiActor,
    method: str,
    path: str,
    authorization: str,
    statement: Dict[str, Any],
) -> BindingResult:
    if method not in {"POST", "PUT"} or path.rstrip("/") != "/xapi/statements":
        return BindingResult(
            binding="BIND-XAPI-HTTP",
            accepted=False,
            logical_status="unsupported_route",
            statement_id=None,
            persisted_effect_digest=_effect_digest(actor),
        )
    receipt = actor.submit(statement, authorization)
    return BindingResult(
        binding="BIND-XAPI-HTTP",
        accepted=bool(receipt.get("accepted")),
        logical_status=_logical_status(receipt),
        statement_id=receipt.get("statement_id"),
        persisted_effect_digest=_effect_digest(actor),
    )


def deliver_xapi_android_ipc(
    actor: LogicalXapiActor,
    action: str,
    correlation_id: str,
    operation: str,
    authorization: str,
    statement: Dict[str, Any],
) -> BindingResult:
    if action != XAPI_IPC_ACTION or operation != "post_statements":
        return BindingResult(
            binding="BIND-XAPI-ANDROID-IPC",
            accepted=False,
            logical_status="unsupported_route",
            statement_id=None,
            persisted_effect_digest=_effect_digest(actor),
            correlation_id=correlation_id,
        )
    receipt = actor.submit(statement, authorization)
    return BindingResult(
        binding="BIND-XAPI-ANDROID-IPC",
        accepted=bool(receipt.get("accepted")),
        logical_status=_logical_status(receipt),
        statement_id=receipt.get("statement_id"),
        persisted_effect_digest=_effect_digest(actor),
        correlation_id=correlation_id,
    )


def xapi_equivalence() -> Dict[str, Any]:
    actor_value = {
        "objectType": "Agent",
        "account": {
            "homePage": "https://example.invalid",
            "name": "equivalence",
        },
    }
    statement = {
        "id": "00000000-0000-4000-8000-000000000020",
        "actor": actor_value,
        "verb": {"id": "https://example.invalid/verb/completed"},
        "object": {"id": "https://example.invalid/activity/equivalence"},
    }
    http_actor = LogicalXapiActor("Basic equivalence", actor_value)
    ipc_actor = LogicalXapiActor("Basic equivalence", actor_value)
    http = deliver_xapi_http(
        http_actor,
        "PUT",
        "/xapi/statements",
        "Basic equivalence",
        statement,
    )
    ipc = deliver_xapi_android_ipc(
        ipc_actor,
        XAPI_IPC_ACTION,
        "correlation-1",
        "post_statements",
        "Basic equivalence",
        statement,
    )
    http_negative = deliver_xapi_http(
        LogicalXapiActor("Basic equivalence", actor_value),
        "PUT",
        "/xapi/statements",
        "Basic wrong",
        statement,
    )
    ipc_negative = deliver_xapi_android_ipc(
        LogicalXapiActor("Basic equivalence", actor_value),
        XAPI_IPC_ACTION,
        "correlation-2",
        "post_statements",
        "Basic wrong",
        statement,
    )
    return {
        "equivalent": (
            http.comparable() == ipc.comparable()
            and http_negative.comparable() == ipc_negative.comparable()
        ),
        "positive": {
            "http": http.comparable(),
            "android_ipc": ipc.comparable(),
        },
        "negative": {
            "http": http_negative.comparable(),
            "android_ipc": ipc_negative.comparable(),
        },
    }
