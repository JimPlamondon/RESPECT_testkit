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
    prerequisites = target.metadata.get("_publication_prerequisites", {})
    if not isinstance(prerequisites, dict):
        prerequisites = {}
    return {
        "android_runtime": android_runtime,
        "publication": publication,
        "publication_prerequisites": prerequisites,
    }


def derive_provisions(
    selected_rows: Iterable[Any],
    evidence_environment: Dict[str, Any],
) -> List[CertificationProvision]:
    rows = list(selected_rows)
    row_ids = {row.row_id for row in rows}
    provisions: List[CertificationProvision] = []
    prerequisites = evidence_environment.get(
        "publication_prerequisites", {}
    )
    certification_key = prerequisites.get("certification_key", {})
    if "PUBLISH-003" in row_ids and certification_key.get(
        "status"
    ) != "valid":
        testing_only = certification_key.get("status") == "testing_only"
        provisions.append(
            CertificationProvision(
                code=(
                    "TESTING_ONLY_RESPECT_CERTIFICATION_KEY"
                    if testing_only
                    else "SPIX_CERTIFICATION_TRUST_ANCHOR_MISSING"
                ),
                label=(
                    "RESPECT certification key is testing-only"
                    if testing_only
                    else "Spix certification trust anchor missing"
                ),
                explanation=(
                    "The cryptographic publication-authorization path was "
                    "exercised with the Test Suite's persistent testing key; "
                    "that key cannot authorize Foundation certification."
                    if testing_only
                    else "Spix has not supplied an independently trusted "
                    "publication-authorization verification key."
                ),
                affected_rows=["PUBLISH-003"],
                evidence=certification_key,
                clearance=(
                    "Publish and source-lock the Spix certification public "
                    "key in the Test Suite, then rerun the affected rows."
                ),
                rerun_scope="affected_rows",
                responsible_party="spix_foundation",
            )
        )
    if "PUBLISH-002" in row_ids and prerequisites.get(
        "immutable_artifact", {}
    ).get("status") != "valid":
        evidence = prerequisites.get("immutable_artifact", {})
        provisions.append(
            CertificationProvision(
                code="IMMUTABLE_CERTIFIED_BUILD_URL_MISSING",
                label="immutable certified-build URL missing",
                explanation=(
                    "The exact tested artifact is not yet available from a "
                    "content-addressed HTTPS URL with immutable cache semantics."
                ),
                affected_rows=["PUBLISH-002"],
                evidence=evidence,
                clearance=(
                    "Publish the unchanged tested artifact at a URL containing "
                    "its SHA-256 digest, return the exact bytes with Cache-Control "
                    "immutable, and rerun PUBLISH-002."
                ),
                rerun_scope="affected_rows",
                responsible_party="publisher",
            )
        )
    if "PUBLISH-001" in row_ids and prerequisites.get(
        "authorization", {}
    ).get("status") != "valid":
        evidence = prerequisites.get("authorization", {})
        provisions.append(
            CertificationProvision(
                code="PUBLICATION_AUTHORIZATION_MISSING",
                label="publication authorization missing",
                explanation=(
                    "Spix has not supplied a valid publication-authorization "
                    "token proving publisher authority and permission to publish "
                    "this exact build."
                ),
                affected_rows=["PUBLISH-001"],
                evidence=evidence,
                clearance=(
                    "Complete the current Spix Publisher Agreement request and "
                    "supply the resulting Spix authorization token."
                ),
                rerun_scope="affected_rows",
                responsible_party="publisher",
            )
        )
    publication = evidence_environment.get("publication", {})
    if publication.get("kind") == "fixture":
        affected = sorted(
            row.row_id for row in rows if row.owner == "canapp"
        )
        provisions.append(
            CertificationProvision(
                code="SUITE_FIXTURE_EVIDENCE",
                label="suite fixture evidence",
                explanation=(
                    "The row behavior passed against a Test Suite fixture; "
                    "the fixture proves the oracle but not an arbitrary CanApp "
                    "or its live publication."
                ),
                affected_rows=affected,
                evidence=publication,
                clearance=(
                    "Run the complete selected profile against the submitted "
                    "CanApp and its live publication and runtime."
                ),
                rerun_scope="full_selected_profile",
                responsible_party="canapp_owner",
            )
        )
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
