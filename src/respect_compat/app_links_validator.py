# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from typing import Dict, List

from .models import ResultState, RuleResult
from .profile import Profile


def validate_app_links(metadata: Dict[str, object], package_id: str, profile: Profile, target: str, security_mode: str) -> List[RuleResult]:
    fingerprints = metadata.get("fingerprints") or []
    statements = metadata.get("assetlinks")
    if not fingerprints:
        return [_result(ResultState.INCOMPLETE, "fingerprints", "certificate fingerprints supplied by APK or fixture metadata", "missing", "App Links metadata is incomplete without fingerprints.", profile, target, security_mode)]
    if statements is None:
        return [_result(ResultState.FAIL, "assetlinks.json", "assetlinks statement file", "missing", "assetlinks.json fixture is missing.", profile, target, security_mode)]
    for statement in statements if isinstance(statements, list) else []:
        target_info = statement.get("target", {}) if isinstance(statement, dict) else {}
        certs = target_info.get("sha256_cert_fingerprints", [])
        if target_info.get("package_name") == package_id and any(fingerprint in certs for fingerprint in fingerprints):
            return [_result(ResultState.PASS, "assetlinks", "matching package and fingerprint", package_id, "App Links statement matched.", profile, target, security_mode)]
    return [_result(ResultState.FAIL, "assetlinks", "matching package and fingerprint", package_id, "No App Links statement matched package and fingerprint.", profile, target, security_mode)]


def _result(state: ResultState, field: str, expected: object, observed: object, message: str, profile: Profile, target: str, security_mode: str) -> RuleResult:
    return RuleResult(rule_id="RCS-009", result=state, source_uri=target, expected=expected, observed=observed, message=message, evidence=f"app_links_validator.{field}", profile=profile.profile_id, target=target, security_mode=security_mode, field_path=field, disposition=profile.requirement("RCS-009").get("v0_1_disposition"))
