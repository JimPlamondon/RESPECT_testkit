# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import List

from .fixture_loader import read_json
from .models import ResultState, RuleResult
from .profile import Profile


def validate_opds(path: Path, profile: Profile, target: str, security_mode: str) -> List[RuleResult]:
    try:
        data = read_json(path)
    except Exception as exc:
        return [_result(ResultState.FAIL, path, "parseable OPDS JSON", type(exc).__name__, "OPDS JSON could not be parsed.", profile, target, security_mode)]
    metadata = data.get("metadata") if isinstance(data, dict) else None
    links = data.get("links") if isinstance(data, dict) else None
    publications = data.get("publications") if isinstance(data, dict) else None
    if isinstance(publications, list):
        bad = [item for item in publications if not isinstance(item, dict) or "metadata" not in item or "links" not in item]
        if bad:
            return [_result(ResultState.FAIL, path, "publication metadata and links", "missing", "OPDS publication is missing metadata or links.", profile, target, security_mode)]
    elif not metadata or not links:
        return [_result(ResultState.FAIL, path, "metadata and links", "missing", "OPDS publication is missing metadata or links.", profile, target, security_mode)]
    return [_result(ResultState.PASS, path, "publication metadata and launch/resource links", "present", "OPDS fixture passed.", profile, target, security_mode)]


def _result(state: ResultState, path: Path, expected: object, observed: object, message: str, profile: Profile, target: str, security_mode: str) -> RuleResult:
    return RuleResult(rule_id="RCS-005", result=state, source_uri=str(path), expected=expected, observed=observed, message=message, evidence="opds_validator", profile=profile.profile_id, target=target, security_mode=security_mode, disposition=profile.requirement("RCS-005").get("v0_1_disposition"))
