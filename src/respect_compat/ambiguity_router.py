# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from .models import ResultState, RuleResult
from .profile import Profile


DISPOSITION_TO_RESULT = {
    "suite_test_candidate": ResultState.DEFERRED,
    "spec_clarification_needed": ResultState.WARNING,
    "out_of_scope_for_v0_1": ResultState.SKIPPED,
}


def route_claim(
    candidate_requirement: str,
    disposition: str,
    profile: Profile,
    target: str,
    security_mode: str,
    source_uri: str = "fixture://expected.json",
) -> RuleResult:
    if disposition not in DISPOSITION_TO_RESULT:
        raise ValueError(f"unsupported ambiguity disposition: {disposition}")
    return RuleResult(
        rule_id="RCS-011",
        result=DISPOSITION_TO_RESULT[disposition],
        source_uri=source_uri,
        expected="active RESPECT code, tests, fixtures, or explicit owner decision",
        observed=candidate_requirement,
        message=f"Unsupported RESPECT-specific claim routed to {disposition}.",
        evidence="ambiguity_router",
        profile=profile.profile_id,
        target=target,
        security_mode=security_mode,
        disposition=disposition,
    )
