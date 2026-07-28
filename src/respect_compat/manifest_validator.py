# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Dict, List, Tuple

from .http_cache_validator import fixture_response, validate_response
from .models import ResultState, RuleResult
from .profile import Profile


KNOWN_LICENSES = {"AGPL-3.0", "Apache-2.0", "MPL-2.0", "MIT", "proprietary"}
REQUIRED_FIELDS = ("name", "license", "learningUnits", "defaultLaunchUri")


def localized_values(value: object) -> List[str]:
    if isinstance(value, dict):
        return [str(item) for item in value.values()]
    if isinstance(value, str):
        return [value]
    return []


def load_manifest(path: Path, profile: Profile, target: str, security_mode: str) -> Tuple[Dict[str, object], List[RuleResult]]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except Exception as exc:
        return {}, [
            RuleResult(
                rule_id="RCS-001",
                result=ResultState.FAIL,
                source_uri=str(path),
                expected="valid JSON manifest",
                observed=type(exc).__name__,
                message="Manifest JSON could not be parsed.",
                evidence="manifest_validator.parse",
                profile=profile.profile_id,
                target=target,
                security_mode=security_mode,
                disposition=profile.requirement("RCS-001").get("v0_1_disposition"),
            )
        ]


def validate_manifest(manifest: Dict[str, object], source_uri: str, profile: Profile, target: str, security_mode: str, metadata: Dict[str, object]) -> List[RuleResult]:
    results: List[RuleResult] = []
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            results.append(_result("RCS-001", ResultState.FAIL, source_uri, field, "present", "missing", f"Required manifest field {field} is missing.", profile, target, security_mode))
    for name in localized_values(manifest.get("name")):
        if not name.strip() or len(name) > 80:
            results.append(_result("RCS-002", ResultState.FAIL, source_uri, "name", "1..80 characters", len(name), "Manifest title length is invalid.", profile, target, security_mode))
    for description in localized_values(manifest.get("description")):
        if not description.strip() or len(description) > 4000:
            results.append(_result("RCS-002", ResultState.FAIL, source_uri, "description", "1..4000 characters", len(description), "Manifest description length is invalid.", profile, target, security_mode))
    license_id = str(manifest.get("license", ""))
    if license_id and license_id not in KNOWN_LICENSES:
        results.append(_result("RCS-002", ResultState.FAIL, source_uri, "license", "known SPDX identifier or proprietary", license_id, "Manifest license is invalid.", profile, target, security_mode))
    if "website" not in manifest:
        results.append(_result("RCS-003", ResultState.FAIL, source_uri, "website", "present and reachable", "missing", "Website is required.", profile, target, security_mode))
    if "icon" not in manifest and not metadata.get("has_favicon"):
        results.append(_result("RCS-003", ResultState.FAIL, source_uri, "icon", "explicit icon or acceptable favicon", "missing", "Icon evidence is absent and fixture metadata does not declare a valid favicon.", profile, target, security_mode))
    response_data = metadata.get("learning_units_response")
    if isinstance(response_data, dict):
        response_results = validate_response(fixture_response(response_data), {"application/json", "application/opds+json"}, profile, target, security_mode, rule_id="RCS-006")
        results.extend(response_results)
        if any(result.field_path == "content_type" for result in response_results):
            results.append(_result("RCS-003", ResultState.FAIL, source_uri, "learningUnits", "application/json or application/opds+json", response_data.get("content_type"), "Learning-units MIME type is not acceptable.", profile, target, security_mode))
    failed_manifest_rules = {result.rule_id for result in results if result.result == ResultState.FAIL}
    if "RCS-001" not in failed_manifest_rules:
        results.append(_result("RCS-001", ResultState.PASS, source_uri, "manifest", "parseable required fields", "valid", "Manifest parsed with required fields.", profile, target, security_mode))
    if "RCS-002" not in failed_manifest_rules:
        results.append(_result("RCS-002", ResultState.PASS, source_uri, "metadata", "valid title, description, and license", "valid", "Manifest metadata passed.", profile, target, security_mode))
    if "RCS-003" not in failed_manifest_rules:
        results.append(_result("RCS-003", ResultState.PASS, source_uri, "links", "reachable website, icon, and learningUnits", "fixture metadata valid", "Manifest links passed fixture checks.", profile, target, security_mode))
    if not results:
        results.extend([
            _result("RCS-001", ResultState.PASS, source_uri, "manifest", "parseable required fields", "valid", "Manifest parsed with required fields.", profile, target, security_mode),
            _result("RCS-002", ResultState.PASS, source_uri, "metadata", "valid title, description, and license", "valid", "Manifest metadata passed.", profile, target, security_mode),
            _result("RCS-003", ResultState.PASS, source_uri, "links", "reachable website, icon, and learningUnits", "fixture metadata valid", "Manifest links passed fixture checks.", profile, target, security_mode),
        ])
    return results


def _result(rule_id: str, state: ResultState, source_uri: str, field: str, expected: object, observed: object, message: str, profile: Profile, target: str, security_mode: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, result=state, source_uri=source_uri, expected=expected, observed=observed, message=message, evidence=f"manifest_validator.{field}", profile=profile.profile_id, target=target, security_mode=security_mode, field_path=field, disposition=profile.requirement(rule_id).get("v0_1_disposition"))
