# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from .models import ResultState, RuleResult
from .profile import Profile


ALLOWED_PACKAGE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._$")


def validate_android(manifest: Dict[str, object], profile: Profile, target: str, security_mode: str, apk: Optional[Path] = None) -> List[RuleResult]:
    android = manifest.get("android")
    if not isinstance(android, dict):
        return []
    package_id = str(android.get("packageId", ""))
    invalid = sorted({char for char in package_id if char not in ALLOWED_PACKAGE_CHARS})
    if invalid:
        return [_result(ResultState.FAIL, "package_id", "letters, digits, period, underscore, or dollar sign", "".join(invalid), "Android package ID contains invalid characters.", profile, target, security_mode)]
    results = [_result(ResultState.PASS, "package_id", "valid package ID characters", package_id, "Android package ID passed.", profile, target, security_mode)]
    if apk is not None:
        results.extend(validate_apk(apk, profile, target, security_mode))
    return results


def validate_apk(apk: Path, profile: Profile, target: str, security_mode: str) -> List[RuleResult]:
    results: List[RuleResult] = []
    with zipfile.ZipFile(apk) as archive:
        abis = sorted({name.split("/")[1] for name in archive.namelist() if name.startswith("lib/") and len(name.split("/")) > 2})
    results.append(_result(ResultState.PASS, "apk_size", "computable APK byte size", apk.stat().st_size, "APK size computed.", profile, target, security_mode))
    results.append(_result(ResultState.PASS, "apk_abi", "ABI list from lib/<abi>/ entries", abis, "APK ABI list computed.", profile, target, security_mode))
    if not (shutil.which("aapt2") or shutil.which("aapt")):
        results.append(_result(ResultState.SKIPPED, "aapt", "aapt2 or aapt available", "missing", "APK metadata requiring aapt was skipped.", profile, target, security_mode))
    if shutil.which("keytool"):
        subprocess.run(["keytool", "-printcert", "-jarfile", str(apk)], check=False, capture_output=True, text=True)
    return results


def _result(state: ResultState, field: str, expected: object, observed: object, message: str, profile: Profile, target: str, security_mode: str) -> RuleResult:
    return RuleResult(rule_id="RCS-004", result=state, source_uri=target, expected=expected, observed=observed, message=message, evidence=f"android_metadata_validator.{field}", profile=profile.profile_id, target=target, security_mode=security_mode, field_path=field, disposition=profile.requirement("RCS-004").get("v0_1_disposition"))
