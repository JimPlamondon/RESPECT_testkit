# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import ipaddress
import urllib.parse
from typing import Any, Dict, Iterable, List

from .models import CertificationProvision


PUBLICATION_ROW_PREFIXES = {"ANDROID", "DESC", "HTTP", "LAUNCH", "OPDS"}


def _local_hostname(hostname: str) -> bool:
    normalized = hostname.rstrip(".").lower()
    if normalized in {"localhost"} or normalized.endswith(".localhost"):
        return True
    if normalized.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def classify_publication_environment(
    uri: str,
    adapter: str,
) -> Dict[str, str]:
    parsed = urllib.parse.urlsplit(uri)
    hostname = parsed.hostname or ""
    if adapter == "fixture":
        publication_kind = "fixture"
    elif parsed.scheme == "https" and _local_hostname(hostname):
        publication_kind = "local_https"
    elif parsed.scheme == "https":
        publication_kind = "remote_https"
    else:
        publication_kind = "non_https"
    return {
        "kind": publication_kind,
        "origin": (
            f"{parsed.scheme}://{parsed.netloc}"
            if parsed.scheme and parsed.netloc
            else uri
        ),
    }


def classify_evidence_environment(target: Any) -> Dict[str, Any]:
    publication = classify_publication_environment(target.uri, target.adapter)
    probe = target.metadata.get("device_probe")
    if isinstance(probe, dict) and probe.get("healthy"):
        if probe.get("emulator") is True:
            runtime_kind = "emulator"
        elif probe.get("emulator") is False:
            runtime_kind = "physical_device"
        else:
            runtime_kind = "unclassified_device"
        android_runtime = {
            "kind": runtime_kind,
            "device_id": probe.get("device_id")
            or target.metadata.get("device_id"),
            "probe": {
                key: probe.get(key)
                for key in (
                    "emulator",
                    "healthy",
                    "manufacturer",
                    "model",
                    "os_release",
                    "api_level",
                    "build_fingerprint",
                )
                if key in probe
            },
        }
    else:
        android_runtime = {"kind": "not_observed", "device_id": None, "probe": {}}
    return {
        "android_runtime": android_runtime,
        "publication": publication,
    }


def derive_provisions(
    selected_rows: Iterable[Any],
    evidence_environment: Dict[str, Any],
) -> List[CertificationProvision]:
    rows = list(selected_rows)
    provisions: List[CertificationProvision] = []
    runtime = evidence_environment.get("android_runtime", {})
    if runtime.get("kind") == "emulator":
        affected = sorted(
            row.row_id
            for row in rows
            if "tier_1_device" in row.required_tooling
        )
        if affected:
            provisions.append(
                CertificationProvision(
                    code="EMULATED_ANDROID_RUNTIME",
                    label="emulated Android runtime",
                    explanation=(
                        "The applicable Android behavior passed on an attributable "
                        "emulator; Foundation physical-device confirmation remains."
                    ),
                    affected_rows=affected,
                    evidence=runtime,
                    clearance=(
                        "Repeat the affected scenarios against the same submitted "
                        "artifact on an approved attributable physical Android device."
                    ),
                    rerun_scope="affected_rows",
                    responsible_party="certification_authority",
                )
            )
    publication = evidence_environment.get("publication", {})
    if publication.get("kind") == "local_https":
        affected = sorted(
            row.row_id
            for row in rows
            if row.owner == "canapp"
            and row.row_id.split("-", 1)[0] in PUBLICATION_ROW_PREFIXES
        )
        provisions.append(
            CertificationProvision(
                code="LOCAL_HTTPS_PUBLICATION",
                label="local HTTPS publication",
                explanation=(
                    "The publication relationships and HTTP behavior passed, but "
                    "the tested HTTPS origin is local rather than stable and "
                    "owner-controlled."
                ),
                affected_rows=affected,
                evidence=publication,
                clearance=(
                    "Deploy the unchanged publication at the declared stable "
                    "owner-controlled HTTPS origin and rerun the affected scenarios."
                ),
                rerun_scope="affected_rows",
                responsible_party="canapp_owner",
            )
        )
    return sorted(provisions, key=lambda item: item.code)


def provisional_display(provisions: Iterable[CertificationProvision]) -> str:
    labels = "; ".join(item.label for item in provisions)
    return f"Provisional ({labels})"
