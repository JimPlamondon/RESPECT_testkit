# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .fixture_loader import load_fixture
from .resources import resource_path


@dataclass(frozen=True)
class HttpObservation:
    requested_url: str
    final_url: str
    status: int
    headers: Dict[str, str]
    body: bytes

    @property
    def json_data(self) -> Optional[Any]:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None


@dataclass
class CanAppTarget:
    uri: str
    adapter: str
    digest: str
    document: Dict[str, Any]
    source_root: Optional[Path] = None
    apk: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    observations: List[HttpObservation] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)

    @property
    def is_legacy_manifest(self) -> bool:
        return "defaultLaunchUri" in self.document

    @property
    def is_current_descriptor(self) -> bool:
        return isinstance(self.document.get("metadata"), dict) and isinstance(
            self.document.get("links"), list
        )


def _digest(adapter: str, uri: str, body: bytes, apk: Optional[Path]) -> str:
    hasher = hashlib.sha256()
    hasher.update(adapter.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(uri.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(body)
    if apk:
        hasher.update(b"\0apk\0")
        hasher.update(apk.read_bytes())
    return hasher.hexdigest()


def _fixture_digest(root: Path, uri: str, apk: Optional[Path]) -> str:
    hasher = hashlib.sha256()
    hasher.update(b"fixture\0")
    hasher.update(uri.encode("utf-8"))
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        hasher.update(b"\0path\0")
        hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
        hasher.update(b"\0content\0")
        hasher.update(path.read_bytes())
    if apk:
        hasher.update(b"\0apk\0")
        hasher.update(apk.read_bytes())
    return hasher.hexdigest()


def fetch(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 10.0,
    ca_cert: Optional[Path] = None,
) -> HttpObservation:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RESPECT-Compatible-Test-Suite/1.0", **(headers or {})},
    )
    context = (
        ssl.create_default_context(cafile=str(ca_cert.resolve(strict=True)))
        if ca_cert is not None
        else None
    )
    try:
        response = urllib.request.urlopen(
            request,
            timeout=timeout,
            context=context,
        )
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        return HttpObservation(
            requested_url=url,
            final_url=response.geturl(),
            status=response.status,
            headers={
                key.lower(): value
                for key, value in response.headers.items()
            },
            body=body,
        )


def load_fixture_target(root: Path, apk: Optional[Path] = None) -> CanAppTarget:
    case = load_fixture(root)
    body = case.manifest_path.read_bytes()
    document = json.loads(body.decode("utf-8"))
    digest = _fixture_digest(root, case.target, apk)
    with resource_path("data/fixtures/v1_0/positive/web_reference") as canonical_reference:
        trusted_reference = (
            apk is None
            and canonical_reference.is_dir()
            and digest == _fixture_digest(canonical_reference, case.target, None)
        )
    capabilities = {"fixture", "descriptor"}
    if trusted_reference:
        capabilities.add("suite_reference")
    if apk:
        capabilities.update({"apk", "native_android"})
    if isinstance(case.expected.get("opds"), str):
        capabilities.add("catalog")
    if case.expected.get("xapi_statement"):
        capabilities.add("xapi_submission")
    return CanAppTarget(
        uri=case.target,
        adapter="fixture",
        digest=digest,
        document=document,
        source_root=root,
        apk=apk,
        metadata={
            **case.metadata,
            "fixture_expected": case.expected,
            "_trusted_reference": trusted_reference,
            "_controlled_runtime": False,
        },
        capabilities=capabilities,
    )


def load_apk_target(apk: Path) -> CanAppTarget:
    resolved = apk.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("submitted APK must be a file")
    uri = f"android-apk://submitted/{resolved.name}"
    return CanAppTarget(
        uri=uri,
        adapter="apk_only",
        digest=_digest("apk_only", uri, b"", resolved),
        document={},
        apk=resolved,
        metadata={
            "descriptor_absent": True,
            "_trusted_reference": False,
            "_controlled_runtime": False,
        },
        capabilities={"apk", "native_android"},
    )


def load_url_target(
    url: str,
    apk: Optional[Path] = None,
    ca_cert: Optional[Path] = None,
) -> CanAppTarget:
    observation = fetch(url, ca_cert=ca_cert)
    data = observation.json_data
    if not isinstance(data, dict):
        raise ValueError(f"CanApp target did not return a JSON object: {url}")
    capabilities = {"remote_http", "descriptor"}
    if apk:
        capabilities.update({"apk", "native_android"})
    return CanAppTarget(
        uri=url,
        adapter="manifest_url",
        digest=_digest("manifest_url", observation.final_url, observation.body, apk),
        document=data,
        apk=apk,
        metadata={
            "tls_ca_cert": str(ca_cert.resolve(strict=True))
            if ca_cert is not None
            else None,
        },
        observations=[observation],
        capabilities=capabilities,
    )


def load_server_target(
    base_url: str,
    apk: Optional[Path] = None,
    ca_cert: Optional[Path] = None,
) -> CanAppTarget:
    normalized = base_url.rstrip("/") + "/"
    candidates = [
        normalized,
        urllib.parse.urljoin(normalized, "launchable-app.json"),
        urllib.parse.urljoin(normalized, "appmanifest.json"),
        urllib.parse.urljoin(normalized, "manifest.json"),
    ]
    failures: List[Tuple[str, str]] = []
    for candidate in dict.fromkeys(candidates):
        try:
            target = load_url_target(
                candidate,
                apk=apk,
                ca_cert=ca_cert,
            )
            target.adapter = "server_base_url"
            target.uri = base_url
            target.digest = _digest(
                "server_base_url",
                candidate,
                target.observations[0].body,
                apk,
            )
            target.metadata["descriptor_url"] = candidate
            return target
        except Exception as error:
            failures.append((candidate, type(error).__name__))
    raise ValueError(f"no CanApp descriptor found below {base_url}: {failures}")
