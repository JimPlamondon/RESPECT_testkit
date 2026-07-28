# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass
from typing import Dict, Iterable, List

from .models import ResultState, RuleResult
from .profile import Profile


@dataclass(frozen=True)
class ResponseFixture:
    url: str
    status: int = 200
    content_type: str = "application/json"
    content_length: str = "2"
    etag: str = '"fixture"'
    last_modified: str = ""
    revalidation_status: int = 304
    vary: str = ""


def fixture_response(data: Dict[str, object]) -> ResponseFixture:
    return ResponseFixture(**{key: value for key, value in data.items() if key in ResponseFixture.__annotations__})


def validate_response(
    response: ResponseFixture,
    acceptable_mime_types: Iterable[str],
    profile: Profile,
    target: str,
    security_mode: str,
    rule_id: str = "RCS-006",
) -> List[RuleResult]:
    failures = []
    if response.status != 200:
        failures.append(("status", 200, response.status, "Response status is not HTTP 200."))
    if acceptable_mime_types and response.content_type not in set(acceptable_mime_types):
        failures.append(("content_type", sorted(set(acceptable_mime_types)), response.content_type, "Response MIME type is not acceptable."))
    try:
        content_length = int(response.content_length)
    except (TypeError, ValueError):
        content_length = -1
    if content_length < 0:
        failures.append(("content_length", "integer >= 0", response.content_length, "Content-Length is missing or invalid."))
    if not response.etag and not response.last_modified:
        failures.append(("cache_validator", "ETag or Last-Modified", "", "No cache validator header found."))
    if (response.etag or response.last_modified) and response.revalidation_status != 304:
        failures.append(("revalidation_status", 304, response.revalidation_status, "Conditional revalidation did not return 304."))
    results = [
        RuleResult(
            rule_id=rule_id,
            result=ResultState.FAIL,
            source_uri=response.url,
            expected=expected,
            observed=observed,
            message=message,
            evidence=f"http_cache_validator.{field}",
            profile=profile.profile_id,
            target=target,
            security_mode=security_mode,
            field_path=field,
            disposition=profile.requirement(rule_id).get("v0_1_disposition"),
        )
        for field, expected, observed, message in failures
    ]
    if response.vary == "strict":
        results.append(
            RuleResult(
                rule_id="RCS-011",
                result=ResultState.WARNING,
                source_uri=response.url,
                expected="No hard Vary oracle in active RESPECT code.",
                observed="strict Vary policy requested",
                message="Strict Vary policy is routed to spec_clarification_needed.",
                evidence="ambiguity_router.vary",
                profile=profile.profile_id,
                target=target,
                security_mode=security_mode,
                disposition="spec_clarification_needed",
            )
        )
    if not results:
        results.append(
            RuleResult(
                rule_id=rule_id,
                result=ResultState.PASS,
                source_uri=response.url,
                expected="HTTP 200, acceptable MIME, Content-Length, validator, and 304 revalidation",
                observed="fixture response satisfied cache oracle",
                message="HTTP/cache fixture passed.",
                evidence="http_cache_validator",
                profile=profile.profile_id,
                target=target,
                security_mode=security_mode,
                disposition=profile.requirement(rule_id).get("v0_1_disposition"),
            )
        )
    return results
