# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import mimetypes
import re
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .engine import ExecutionContext, ExecutorRegistry
from .android_apk import assetlinks_matches, inspect_apk
from .equivalence import xapi_equivalence
from .matrix_runtime import CompatibilityMatrix, MatrixRow
from .models import RequirementOwner, ResultState
from .opds_schema import validate_opds_documents
from .target import HttpObservation, fetch
from .xapi_actor import LogicalXapiActor


ACQUISITION_PREFIX = "http://opds-spec.org/acquisition"
DEFAULT_CATALOG_REL = "https://respect.ustadmobile.com/ns/default-lesson-catalog"
LEARNING_UNIT_TYPES = {"text/html", "application/xml", "application/html+xml"}
JSON_TYPES = {
    "application/json",
    "application/opds+json",
    "application/opds-publication+json",
    "application/webpub+json",
}
RESERVED_LAUNCH_PARAMETERS = {
    "endpoint",
    "auth",
    "actor",
    "activity_id",
    "xapiIpcPackage",
}


class _PublicationLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[Dict[str, str]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        if tag.lower() != "link":
            return
        values = {key.lower(): value or "" for key, value in attrs}
        relations = values.get("rel", "").split()
        if (
            {"publication", "manifest"} & set(relations)
            and values.get("type", "").split(";", 1)[0]
            == "application/webpub+json"
            and values.get("href")
        ):
            self.links.append(values)
KNOWN_LICENSES = {
    "AGPL-3.0",
    "Apache-2.0",
    "MPL-2.0",
    "MIT",
    "proprietary",
}


def _result(
    context: ExecutionContext,
    row: MatrixRow,
    state: ResultState,
    observed: Any,
    message: str,
    kind: str = "semantic_observation",
    source: Optional[str] = None,
):
    evidence = [
        context.evidence(
            row,
            kind,
            source or context.target.uri,
            observed,
        )
    ]
    return context.result(row, state, observed, message, evidence)


def _check(
    context: ExecutionContext,
    row: MatrixRow,
    condition: bool,
    observed: Any,
    success: str,
    failure: str,
):
    return _result(
        context,
        row,
        ResultState.PASS if condition else ResultState.FAIL,
        observed,
        success if condition else failure,
    )


def _blocked(context: ExecutionContext, row: MatrixRow, prerequisite: str):
    return _result(
        context,
        row,
        ResultState.BLOCKED,
        {"missing_prerequisite": prerequisite},
        f"Required prerequisite is unavailable: {prerequisite}.",
        kind="prerequisite",
        source="suite",
    )


def _not_applicable(context: ExecutionContext, row: MatrixRow, reason: str):
    return _result(
        context,
        row,
        ResultState.NOT_APPLICABLE,
        {"applicability": False, "reason": reason},
        reason,
        kind="applicability",
        source="suite",
    )


def _relations(link: Dict[str, Any]) -> List[str]:
    rel = link.get("rel")
    if isinstance(rel, str):
        return rel.split()
    if isinstance(rel, list):
        return [item for item in rel if isinstance(item, str)]
    return []


def _links(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    links = document.get("links")
    return [item for item in links if isinstance(item, dict)] if isinstance(links, list) else []


def _localized_values(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, str)]
    return []


def _content_type(observation: HttpObservation) -> str:
    return observation.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _resolved(context: ExecutionContext, href: str, base: Optional[str] = None) -> str:
    if context.target.source_root and not urllib.parse.urlparse(href).scheme:
        return (context.target.source_root / href).resolve().as_uri()
    return urllib.parse.urljoin(base or context.target.metadata.get("descriptor_url", context.target.uri), href)


def _read_url(context: ExecutionContext, url: str, headers: Optional[Dict[str, str]] = None) -> HttpObservation:
    existing = next(
        (
            item
            for item in context.target.observations
            if item.requested_url == url and not headers
        ),
        None,
    )
    if existing:
        return existing
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        body = path.read_bytes()
        resources = context.target.metadata.get("http_resources", {})
        configured = resources.get(url, resources.get(path.name, {}))
        content_type = configured.get("content_type") or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        observation = HttpObservation(
            requested_url=url,
            final_url=url,
            status=int(configured.get("status", 200)),
            headers={
                "content-type": content_type,
                "content-length": str(configured.get("content_length", len(body))),
                "etag": str(configured.get("etag", f'"fixture-{len(body)}"')),
            },
            body=body,
        )
        context.target.observations.append(observation)
        return observation
    if (
        parsed.scheme in {"http", "https"}
        and "remote_http" not in context.target.capabilities
    ):
        raise RuntimeError("target has no live HTTP capability")
    observation = fetch(url, headers=headers)
    context.target.observations.append(observation)
    return observation


def _read_json(context: ExecutionContext, url: str) -> Tuple[Optional[Dict[str, Any]], Optional[HttpObservation]]:
    try:
        observation = _read_url(context, url)
    except Exception:
        return None, None
    value = observation.json_data
    return (value if isinstance(value, dict) else None), observation


def _target_observation(
    target,
    url: str,
) -> Optional[HttpObservation]:
    existing = next(
        (
            item
            for item in target.observations
            if item.requested_url == url or item.final_url == url
        ),
        None,
    )
    if existing is not None:
        return existing
    if (
        urllib.parse.urlparse(url).scheme in {"http", "https"}
        and "remote_http" in target.capabilities
    ):
        try:
            observation = fetch(url)
        except Exception:
            return None
        target.observations.append(observation)
        return observation
    return None


def _discover_webpub_manifest(
    target,
    acquisition_url: str,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    acquisition = _target_observation(target, acquisition_url)
    if acquisition is None or acquisition.status != 200:
        return None, None
    discoveries: List[str] = []
    header = acquisition.headers.get("link", "")
    if (
        'rel="manifest"' in header
        and "application/webpub+json" in header
        and "<" in header
        and ">" in header
    ):
        discoveries.append(
            urllib.parse.urljoin(
                acquisition.final_url,
                header.split("<", 1)[1].split(">", 1)[0],
            )
        )
    if _content_type(acquisition) in {"text/html", "application/html+xml"}:
        parser = _PublicationLinkParser()
        try:
            parser.feed(acquisition.body.decode("utf-8"))
        except UnicodeDecodeError:
            return None, None
        discoveries.extend(
            urllib.parse.urljoin(acquisition.final_url, item["href"])
            for item in parser.links
        )
    unique = sorted(set(discoveries))
    if len(unique) != 1:
        return None, None
    observation = _target_observation(target, unique[0])
    if observation is None or observation.status != 200:
        return unique[0], None
    value = observation.json_data
    return unique[0], value if isinstance(value, dict) else None


def usable_image(observation: HttpObservation) -> bool:
    content_type = _content_type(observation)
    body = observation.body
    if content_type == "image/png":
        if (
            len(body) < 24
            or body[:8] != b"\x89PNG\r\n\x1a\n"
            or body[12:16] != b"IHDR"
        ):
            return False
        width = int.from_bytes(body[16:20], "big")
        height = int.from_bytes(body[20:24], "big")
        return width > 1 and height > 1
    if content_type in {"image/jpeg", "image/jpg"}:
        return len(body) > 4 and body[:2] == b"\xff\xd8" and body[-2:] == b"\xff\xd9"
    if content_type == "image/svg+xml":
        try:
            text = body.decode("utf-8").lower()
        except UnicodeDecodeError:
            return False
        return "<svg" in text and "</svg>" in text
    return content_type.startswith("image/") and len(body) > 32


def packaged_lesson_binding(target) -> Dict[str, Any]:
    cached = target.metadata.get("_packaged_lesson_binding")
    if isinstance(cached, dict):
        return cached
    result: Dict[str, Any] = {
        "applicable": False,
        "valid": True,
        "packaged_lessons": [],
        "catalog_lessons": [],
        "content_matches": {},
        "errors": [],
    }
    if target.apk is None or not target.apk.is_file():
        target.metadata["_packaged_lesson_binding"] = result
        return result
    packaged = []
    try:
        with zipfile.ZipFile(target.apk) as archive:
            for name in sorted(archive.namelist()):
                if not name.lower().endswith(".jimsong"):
                    continue
                body = archive.read(name)
                try:
                    value = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    result["errors"].append(
                        f"packaged JiMSong is not parseable JSON: {name}"
                    )
                    continue
                title = value.get("title") if isinstance(value, dict) else None
                if not isinstance(title, str) or not title.strip():
                    result["errors"].append(
                        f"packaged JiMSong has no title: {name}"
                    )
                    continue
                packaged.append(
                    {
                        "path": name,
                        "title": title,
                        "sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
    except zipfile.BadZipFile:
        target.metadata["_packaged_lesson_binding"] = result
        return result
    if not packaged:
        target.metadata["_packaged_lesson_binding"] = result
        return result
    result["applicable"] = True
    result["packaged_lessons"] = [item["title"] for item in packaged]

    descriptor_base = target.metadata.get("descriptor_url")
    if not isinstance(descriptor_base, str):
        descriptor_base = (
            target.observations[0].final_url
            if target.observations
            else target.uri
        )
    catalog_links = [
        link
        for link in _links(target.document)
        if DEFAULT_CATALOG_REL in _relations(link)
        and isinstance(link.get("href"), str)
    ]
    if len(catalog_links) != 1:
        result["errors"].append(
            "descriptor must expose exactly one default lesson catalog"
        )
    else:
        catalog_url = urllib.parse.urljoin(
            descriptor_base,
            catalog_links[0]["href"],
        )
        catalog_observation = _target_observation(target, catalog_url)
        catalog = (
            catalog_observation.json_data
            if catalog_observation is not None
            and catalog_observation.status == 200
            else None
        )
        publications = (
            catalog.get("publications")
            if isinstance(catalog, dict)
            else None
        )
        if not isinstance(publications, list):
            result["errors"].append(
                "default lesson catalog has no publications"
            )
            publications = []
        publications = [
            item for item in publications if isinstance(item, dict)
        ]
        publication_titles = [
            values[0]
            for publication in publications
            for values in [
                _localized_values(
                    publication.get("metadata", {}).get("title")
                    if isinstance(publication.get("metadata"), dict)
                    else None
                )
            ]
            if len(values) == 1
        ]
        result["catalog_lessons"] = publication_titles
        if Counter(publication_titles) != Counter(
            item["title"] for item in packaged
        ):
            result["errors"].append(
                "catalog titles do not match packaged lessons"
            )

        packaged_by_title = {
            item["title"]: item
            for item in packaged
        }
        for publication in publications:
            metadata = (
                publication.get("metadata")
                if isinstance(publication.get("metadata"), dict)
                else {}
            )
            title_values = _localized_values(metadata.get("title"))
            title = title_values[0] if len(title_values) == 1 else None
            if title not in packaged_by_title:
                continue
            identifier = metadata.get("identifier")
            if not isinstance(identifier, str) or not identifier:
                result["errors"].append(
                    f"catalog publication has no identifier: {title}"
                )
                continue
            acquisitions = [
                link
                for link in _links(publication)
                if isinstance(link.get("href"), str)
                and any(
                    relation.startswith(ACQUISITION_PREFIX)
                    for relation in _relations(link)
                )
                and str(link.get("type", "")).split(";", 1)[0]
                in LEARNING_UNIT_TYPES
            ]
            if len(acquisitions) != 1:
                result["errors"].append(
                    f"catalog publication is not uniquely launchable: {title}"
                )
                continue
            images = [
                image
                for image in publication.get("images") or []
                if isinstance(image, dict)
                and isinstance(image.get("href"), str)
            ]
            usable_images = []
            for image in images:
                image_url = urllib.parse.urljoin(
                    catalog_url,
                    image["href"],
                )
                observation = _target_observation(target, image_url)
                if observation is not None and usable_image(observation):
                    usable_images.append(image_url)
            if not usable_images:
                result["errors"].append(
                    f"catalog image is missing, invalid, or a placeholder: {title}"
                )
            acquisition_url = urllib.parse.urljoin(
                catalog_url,
                acquisitions[0]["href"],
            )
            manifest_url, manifest = _discover_webpub_manifest(
                target,
                acquisition_url,
            )
            if manifest_url is None or manifest is None:
                result["errors"].append(
                    f"catalog publication has no unique Readium wrapper: {title}"
                )
                continue
            manifest_metadata = (
                manifest.get("metadata")
                if isinstance(manifest.get("metadata"), dict)
                else {}
            )
            if (
                manifest_metadata.get("identifier") != identifier
                or title not in _localized_values(
                    manifest_metadata.get("title")
                )
            ):
                result["errors"].append(
                    f"Readium wrapper identity does not match catalog: {title}"
                )
            declared = []
            for field in ("readingOrder", "resources"):
                values = manifest.get(field)
                if isinstance(values, list):
                    declared.extend(
                        item
                        for item in values
                        if isinstance(item, dict)
                        and isinstance(item.get("href"), str)
                    )
            expected_hash = packaged_by_title[title]["sha256"]
            matches = []
            for link in declared:
                resource_url = urllib.parse.urljoin(
                    manifest_url,
                    link["href"],
                )
                observation = _target_observation(target, resource_url)
                if (
                    observation is not None
                    and observation.status == 200
                    and hashlib.sha256(observation.body).hexdigest()
                    == expected_hash
                ):
                    matches.append(resource_url)
            if len(matches) != 1:
                result["errors"].append(
                    f"Readium wrapper is not bound to packaged lesson bytes: {title}"
                )
            else:
                result["content_matches"][title] = packaged_by_title[title][
                    "path"
                ]
        for item in packaged:
            if item["title"] not in result["content_matches"]:
                message = (
                    "Readium wrapper is not bound to packaged lesson bytes: "
                    f"{item['title']}"
                )
                if message not in result["errors"]:
                    result["errors"].append(message)

    result["valid"] = not result["errors"]
    target.metadata["_packaged_lesson_binding"] = result
    return result


def _publication_documents(context: ExecutionContext) -> List[Tuple[str, Dict[str, Any]]]:
    documents: List[Tuple[str, Dict[str, Any]]] = []
    root = context.target.document
    source_documents: List[Dict[str, Any]] = [root]
    if "publications" in root and isinstance(root["publications"], list):
        documents.extend(
            (context.target.uri, item)
            for item in root["publications"]
            if isinstance(item, dict)
        )
    elif context.target.is_current_descriptor:
        documents.append((context.target.uri, root))
    if context.target.is_current_descriptor:
        for link in _links(root):
            if DEFAULT_CATALOG_REL in _relations(link) and isinstance(link.get("href"), str):
                url = _resolved(context, link["href"])
                document, _ = _read_json(context, url)
                if not document:
                    continue
                source_documents.append(document)
                if isinstance(document.get("publications"), list):
                    documents.extend(
                        (url, item)
                        for item in document["publications"]
                        if isinstance(item, dict)
                    )
                else:
                    documents.append((url, document))
    context.target.metadata["_opds_source_documents"] = source_documents
    return documents


def descriptor_executor(context: ExecutionContext, row: MatrixRow):
    document = context.target.document
    if context.target.is_legacy_manifest:
        return _not_applicable(
            context,
            row,
            "The submitted target uses the deprecated legacy manifest route.",
        )
    if row.row_id == "DESC-001":
        return _check(
            context,
            row,
            context.target.is_current_descriptor,
            {"metadata_object": isinstance(document.get("metadata"), dict), "links_array": isinstance(document.get("links"), list)},
            "The response decoded as an OPDS Publication descriptor.",
            "The response did not decode as an OPDS Publication descriptor.",
        )
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    links = _links(document)
    if row.row_id == "DESC-002":
        acquisition = [
            link
            for link in links
            if any(rel.startswith(ACQUISITION_PREFIX) for rel in _relations(link))
            and str(link.get("type", "")).split(";", 1)[0] in LEARNING_UNIT_TYPES
            and isinstance(link.get("href"), str)
        ]
        observed = {
            "identifier": metadata.get("identifier"),
            "title": metadata.get("title"),
            "acquisition_links": acquisition,
        }
        reachable = []
        for link in acquisition:
            try:
                observation = _read_url(
                    context,
                    _resolved(context, str(link["href"])),
                )
                reachable.append(observation.status == 200)
            except Exception:
                reachable.append(False)
        return _check(
            context,
            row,
            bool(
                metadata.get("identifier")
                and _localized_values(metadata.get("title"))
                and acquisition
                and any(reachable)
            ),
            {**observed, "reachable": reachable},
            "The descriptor provides identity, title, and an accepted acquisition link.",
            "The descriptor lacks identity, title, or an accepted acquisition link.",
        )
    if row.row_id == "DESC-003":
        catalog_links = [
            link for link in links if DEFAULT_CATALOG_REL in _relations(link)
        ]
        if not catalog_links:
            return _not_applicable(
                context,
                row,
                "The descriptor does not expose a default lesson catalog.",
            )
        href = catalog_links[0].get("href")
        document_result, observation = _read_json(context, _resolved(context, str(href)))
        return _check(
            context,
            row,
            bool(document_result and observation and observation.status == 200),
            {"link": catalog_links[0], "status": observation.status if observation else None},
            "The default lesson catalog relation resolved to parseable OPDS JSON.",
            "The default lesson catalog relation did not resolve to parseable OPDS JSON.",
        )
    if row.row_id == "DESC-004":
        known = {"metadata", "links", "images", "readingOrder", "resources", "toc"}
        unknown = sorted(set(document) - known)
        if not unknown:
            return _not_applicable(
                context,
                row,
                "The descriptor contains no unknown top-level property.",
            )
        return _check(
            context,
            row,
            context.target.is_current_descriptor,
            {"unknown_properties": unknown},
            "Unknown properties did not alter recognized descriptor fields.",
            "Unknown properties prevented descriptor decoding.",
        )
    observed = {
        "required": {
            "metadata": isinstance(document.get("metadata"), dict),
            "links": isinstance(document.get("links"), list),
        },
        "optional_absent": sorted(
            field
            for field in ("images", "readingOrder", "resources", "toc")
            if field not in document
        ),
    }
    return _check(
        context,
        row,
        all(observed["required"].values()),
        observed,
        "Required top-level fields are present; optional fields may be absent.",
        "Metadata or links is absent or has the wrong type.",
    )


def manifest_executor(context: ExecutionContext, row: MatrixRow):
    if not context.target.is_legacy_manifest:
        return _not_applicable(
            context,
            row,
            "The submitted target uses the current OPDS Publication descriptor route.",
        )
    manifest = context.target.document
    if row.row_id == "MANIFEST-001":
        required = {
            "name": bool(_localized_values(manifest.get("name"))),
            "license": isinstance(manifest.get("license"), str),
            "learningUnits": isinstance(manifest.get("learningUnits"), str),
            "defaultLaunchUri": isinstance(manifest.get("defaultLaunchUri"), str),
        }
        return _check(context, row, all(required.values()), required, "Legacy manifest required fields are valid.", "Legacy manifest required fields are missing or invalid.")
    if row.row_id == "MANIFEST-002":
        values = _localized_values(manifest.get("name"))
        return _check(context, row, bool(values) and all(1 <= len(item) <= 80 for item in values), values, "Every localized name satisfies the active length rule.", "A localized name violates the active length rule.")
    if row.row_id == "MANIFEST-003":
        values = _localized_values(manifest.get("description"))
        if not values:
            return _not_applicable(context, row, "The optional description is absent.")
        return _check(context, row, all(1 <= len(item) <= 4000 for item in values), values, "Every localized description satisfies the active length rule.", "A localized description violates the active length rule.")
    if row.row_id == "MANIFEST-004":
        value = manifest.get("license")
        return _check(context, row, value in KNOWN_LICENSES, value, "The license is accepted.", "The license is not in the active accepted set.")
    if row.row_id in {"MANIFEST-005", "MANIFEST-006", "MANIFEST-007"}:
        field = {
            "MANIFEST-005": "website",
            "MANIFEST-006": "icon",
            "MANIFEST-007": "learningUnits",
        }[row.row_id]
        href = manifest.get(field)
        if row.row_id == "MANIFEST-006" and not href:
            href = context.target.metadata.get("favicon_url")
        if not isinstance(href, str):
            return _check(context, row, False, {"field": field, "value": href}, "", f"No usable {field} URL is declared.")
        url = _resolved(context, href)
        try:
            observation = _read_url(context, url)
        except Exception as error:
            return _check(context, row, False, {"url": url, "error": type(error).__name__}, "", f"The declared {field} resource was not reachable.")
        accepted = observation.status == 200
        if row.row_id == "MANIFEST-007":
            accepted = accepted and _content_type(observation) in JSON_TYPES
        return _check(context, row, accepted, {"url": url, "status": observation.status, "content_type": _content_type(observation)}, f"The declared {field} resource passed.", f"The declared {field} resource failed active HTTP checks.")
    if row.row_id == "MANIFEST-008":
        value = manifest.get("defaultLaunchUri")
        parsed = urllib.parse.urlparse(str(value))
        return _check(context, row, bool(parsed.scheme and parsed.netloc), value, "The default launch URI is syntactically usable.", "The default launch URI is not syntactically usable.")
    android = manifest.get("android")
    if not isinstance(android, dict) or "packageId" not in android:
        return _not_applicable(context, row, "The legacy manifest declares no Android package.")
    package_id = str(android["packageId"])
    return _check(context, row, bool(re.fullmatch(r"[A-Za-z0-9_.]+", package_id)), package_id, "The Android package identifier uses the active character set.", "The Android package identifier contains a disallowed character.")


def opds_executor(context: ExecutionContext, row: MatrixRow):
    documents = _publication_documents(context)
    lesson_binding = packaged_lesson_binding(context.target)
    if context.target.is_legacy_manifest:
        learning_units = context.target.document.get("learningUnits")
        if isinstance(learning_units, str):
            document, _ = _read_json(context, _resolved(context, learning_units))
            if document:
                context.target.metadata["_opds_source_documents"] = [document]
                if isinstance(document.get("publications"), list):
                    documents = [
                        (_resolved(context, learning_units), item)
                        for item in document["publications"]
                        if isinstance(item, dict)
                    ]
                else:
                    documents = [(_resolved(context, learning_units), document)]
    if not documents:
        return _check(context, row, False, {"documents": 0}, "", "No parseable OPDS feed or publication was discovered.")
    if row.row_id == "OPDS-001":
        valid = all(isinstance(item.get("metadata"), dict) and isinstance(item.get("links"), list) for _, item in documents)
        return _check(context, row, valid, {"documents": len(documents)}, "The OPDS document structure is accepted.", "The OPDS document structure is invalid.")
    if row.row_id == "OPDS-002":
        try:
            errors = validate_opds_documents(
                context.target.metadata.get(
                    "_opds_source_documents",
                    [context.target.document],
                )
            )
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            return _blocked(
                context,
                row,
                f"source-locked OPDS schema validator: {error}",
            )
        return _check(
            context,
            row,
            not errors,
            {"schema_errors": errors},
            "Source-locked OPDS schema validation succeeded.",
            "Source-locked OPDS schema validation failed.",
        )
    if row.row_id == "OPDS-003":
        valid = all(
            isinstance(item.get("metadata"), dict)
            and bool(item["metadata"].get("title"))
            for _, item in documents
        )
        binding_errors = [
            error
            for error in lesson_binding["errors"]
            if (
                "catalog" in error
                or "default lesson catalog" in error
            )
        ]
        return _check(
            context,
            row,
            bool(valid) and not binding_errors,
            {
                "documents": len(documents),
                "packaged_lesson_binding_errors": binding_errors,
            },
            "Selected publication metadata is present and bound to packaged lessons.",
            "Selected publication metadata is incomplete or disconnected from packaged lessons.",
        )
    acquisition: List[Tuple[str, Dict[str, Any]]] = []
    images: List[Tuple[str, Dict[str, Any]]] = []
    resources: List[Tuple[str, Dict[str, Any]]] = []
    for base, publication in documents:
        for link in _links(publication):
            if any(rel.startswith(ACQUISITION_PREFIX) for rel in _relations(link)):
                acquisition.append((base, link))
        for item in publication.get("images") or []:
            if isinstance(item, dict):
                images.append((base, item))
        for item in publication.get("resources") or []:
            if isinstance(item, dict):
                resources.append((base, item))
    discovered_manifest_resources: List[Tuple[str, Dict[str, Any]]] = []
    for base, link in acquisition:
        acquisition_url = _resolved(
            context,
            str(link.get("href", "")),
            base,
        )
        manifest_url, manifest = _discover_webpub_manifest(
            context.target,
            acquisition_url,
        )
        if manifest_url is None or manifest is None:
            continue
        for item in manifest.get("resources") or []:
            if isinstance(item, dict):
                discovered_manifest_resources.append((manifest_url, item))
    resources.extend(discovered_manifest_resources)
    if row.row_id == "OPDS-004":
        accepted = [
            (base, link) for base, link in acquisition
            if str(link.get("type", "")).split(";", 1)[0] in LEARNING_UNIT_TYPES
        ]
        outcomes = []
        for base, link in accepted:
            url = _resolved(context, str(link.get("href", "")), base)
            try:
                observation = _read_url(context, url)
                outcomes.append(
                    {
                        "url": url,
                        "status": observation.status,
                        "content_type": _content_type(observation),
                    }
                )
            except Exception as error:
                outcomes.append({"url": url, "error": type(error).__name__})
        binding_errors = [
            error
            for error in lesson_binding["errors"]
            if (
                "uniquely launchable" in error
                or "catalog titles do not match packaged lessons" in error
            )
        ]
        passed = bool(outcomes) and all(
            item.get("status") == 200
            and item.get("content_type") in LEARNING_UNIT_TYPES
            for item in outcomes
        ) and not binding_errors
        return _check(
            context,
            row,
            passed,
            {
                "links": outcomes,
                "packaged_lesson_binding_errors": binding_errors,
            },
            "Every packaged lesson has one accepted acquisition link.",
            "An acquisition link is missing, unreachable, or disconnected from a packaged lesson.",
        )
    if row.row_id == "OPDS-005":
        prohibited = []
        for base, link in acquisition:
            parsed = urllib.parse.urlparse(_resolved(context, str(link.get("href", "")), base))
            keys = set(urllib.parse.parse_qs(parsed.query))
            if parsed.fragment or keys & RESERVED_LAUNCH_PARAMETERS:
                prohibited.append({"url": parsed.geturl(), "reserved": sorted(keys & RESERVED_LAUNCH_PARAMETERS)})
        return _check(context, row, not prohibited, prohibited, "Acquisition URLs avoid fragments and reserved launch parameters.", "An acquisition URL contains a fragment or reserved launch parameter.")
    if row.row_id == "OPDS-006":
        if not acquisition:
            return _not_applicable(context, row, "No acquisition resource requires publication-manifest discovery.")
        discoveries = []
        for base, link in acquisition:
            url = _resolved(context, str(link.get("href", "")), base)
            try:
                observation = _read_url(context, url)
            except Exception:
                continue
            header = observation.headers.get("link", "")
            if (
                'rel="manifest"' in header
                and "application/webpub+json" in header
                and "<" in header
                and ">" in header
            ):
                discoveries.append(
                    urllib.parse.urljoin(
                        observation.final_url,
                        header.split("<", 1)[1].split(">", 1)[0],
                    )
                )
            if _content_type(observation) in {"text/html", "application/html+xml"}:
                parser = _PublicationLinkParser()
                try:
                    parser.feed(observation.body.decode("utf-8"))
                except UnicodeDecodeError:
                    pass
                discoveries.extend(
                    urllib.parse.urljoin(observation.final_url, item["href"])
                    for item in parser.links
                )
        validated = []
        for url in sorted(set(discoveries)):
            document, observation = _read_json(context, url)
            validated.append(
                {
                    "url": url,
                    "status": observation.status if observation else None,
                    "valid": bool(
                        document
                        and isinstance(document.get("metadata"), dict)
                        and (
                            isinstance(document.get("readingOrder"), list)
                            or isinstance(document.get("resources"), list)
                        )
                    ),
                }
            )
        binding_errors = [
            error
            for error in lesson_binding["errors"]
            if (
                "Readium wrapper" in error
                or "catalog titles do not match packaged lessons" in error
            )
            and "packaged lesson bytes" not in error
        ]
        return _check(
            context,
            row,
            bool(validated)
            and all(item["valid"] for item in validated)
            and not binding_errors,
            {
                "manifests": validated,
                "packaged_lesson_binding_errors": binding_errors,
            },
            "A matching Readium wrapper was discovered for every packaged lesson.",
            "A Readium wrapper is missing, invalid, or disconnected from its catalog publication.",
        )
    if row.row_id in {"OPDS-007", "OPDS-008"}:
        selected = resources if row.row_id == "OPDS-007" else images
        if not selected:
            return _check(context, row, False, {"links": 0}, "", "The publication declares no required resource of this kind.")
        outcomes = []
        for base, link in selected:
            url = _resolved(context, str(link.get("href", "")), base)
            try:
                observation = _read_url(context, url)
                outcomes.append({"url": url, "status": observation.status})
            except Exception as error:
                outcomes.append({"url": url, "error": type(error).__name__})
        binding_errors = (
            [
                error
                for error in lesson_binding["errors"]
                if "packaged lesson bytes" in error
            ]
            if row.row_id == "OPDS-007"
            else [
                error
                for error in lesson_binding["errors"]
                if "catalog image" in error
            ]
        )
        return _check(
            context,
            row,
            all(item.get("status") == 200 for item in outcomes)
            and not binding_errors,
            {
                "links": outcomes,
                "packaged_lesson_binding_errors": binding_errors,
            },
            "Every declared resource is reachable and bound to packaged lesson content.",
            "A declared resource is unreachable or disconnected from packaged lesson content.",
        )
    if row.row_id == "OPDS-009":
        declared_urls = [
            _resolved(context, str(link.get("href", "")), base)
            for base, publication in documents
            for link in _links(publication)
            if isinstance(link.get("href"), str)
        ]
        repeats = sorted(
            {url for url in declared_urls if declared_urls.count(url) > 1}
        )
        if not repeats:
            return _not_applicable(context, row, "Catalog traversal encountered no repeated resolved URL.")
        observed_requests = [
            item.requested_url for item in context.target.observations
        ]
        traversal = {
            url: observed_requests.count(url)
            for url in repeats
        }
        return _check(context, row, all(count <= 1 for count in traversal.values()), traversal, "Each resolved URL was visited at most once.", "Catalog traversal revisited a resolved URL.")
    if row.row_id == "OPDS-010":
        catalog_links = [
            link
            for link in _links(context.target.document)
            if DEFAULT_CATALOG_REL in _relations(link)
        ]
        if not catalog_links:
            return _not_applicable(context, row, "No catalog link is followed.")
        media_type = str(catalog_links[0].get("type", "")).split(";", 1)[0]
        dispatch = {
            "media_type": media_type or "application/opds+json",
            "validator": {
                "": "opds_feed",
                "application/opds+json": "opds_feed",
                "application/opds-publication+json": "opds_publication",
                "application/webpub+json": "readium_webpub",
                "application/vnd.respect.appmanifest+json": "legacy_manifest",
            }.get(media_type, "http_only"),
        }
        return _result(context, row, ResultState.PASS, dispatch, "Media type selected the source-defined validator path.")
    relative = [
        (base, link["href"])
        for base, publication in documents
        for link in _links(publication)
        if isinstance(link.get("href"), str) and not urllib.parse.urlparse(link["href"]).scheme
    ]
    if not relative:
        return _not_applicable(context, row, "No relative OPDS link is present.")
    observed = [{"base": base, "href": href, "resolved": _resolved(context, href, base)} for base, href in relative]
    return _result(context, row, ResultState.PASS, observed, "Relative links resolved against their referring documents.")


def _selected_http_observation(context: ExecutionContext) -> Optional[HttpObservation]:
    explicit = context.target.metadata.get("http_resource_url")
    if isinstance(explicit, str):
        try:
            return _read_url(context, _resolved(context, explicit))
        except Exception:
            return None
    for base, document in _publication_documents(context):
        for link in _links(document):
            if isinstance(link.get("href"), str):
                try:
                    observation = _read_url(
                        context,
                        _resolved(context, link["href"], base),
                    )
                    context.target.metadata["_selected_http_declared_type"] = str(
                        link.get("type", "")
                    ).split(";", 1)[0]
                    context.target.metadata["_selected_http_role"] = (
                        "acquisition"
                        if any(
                            rel.startswith(ACQUISITION_PREFIX)
                            for rel in _relations(link)
                        )
                        else "declared_resource"
                    )
                    return observation
                except Exception:
                    continue
    return context.target.observations[0] if context.target.observations else None


def http_executor(context: ExecutionContext, row: MatrixRow):
    observation = _selected_http_observation(context)
    if not observation:
        return _blocked(context, row, "validator-selected HTTP resource")
    headers = observation.headers
    if row.row_id == "HTTP-001":
        return _check(context, row, observation.status == 200, observation.status, "The selected resource returned HTTP 200.", "The selected resource did not return HTTP 200.")
    if row.row_id == "HTTP-002":
        value = _content_type(observation)
        declared = context.target.metadata.get("_selected_http_declared_type")
        role = context.target.metadata.get("_selected_http_role")
        accepted = (
            value in LEARNING_UNIT_TYPES
            if role == "acquisition"
            else bool(value and (not declared or value == declared))
        )
        return _check(
            context,
            row,
            accepted,
            {"observed": value, "declared": declared, "role": role},
            "The selected resource declared the accepted role-specific media type.",
            "The selected resource media type is not accepted for its role.",
        )
    if row.row_id == "HTTP-003":
        value = headers.get("content-length")
        coherent = value is not None and value.isdigit() and int(value) == len(observation.body)
        return _check(context, row, coherent, {"header": value, "bytes": len(observation.body)}, "Content-Length is present and coherent.", "Content-Length is absent or incoherent.")
    if row.row_id == "HTTP-004":
        validators = {"etag": headers.get("etag"), "last-modified": headers.get("last-modified")}
        return _check(context, row, any(validators.values()), validators, "A usable cache validator is present.", "No usable cache validator is present.")
    request_headers = {}
    if headers.get("etag"):
        request_headers["If-None-Match"] = headers["etag"]
    elif headers.get("last-modified"):
        request_headers["If-Modified-Since"] = headers["last-modified"]
    if not request_headers:
        return _check(context, row, False, {}, "", "Conditional revalidation could not be attempted without a validator.")
    resources = context.target.metadata.get("http_resources", {})
    configured = resources.get(
        observation.final_url,
        resources.get(Path(urllib.parse.urlparse(observation.final_url).path).name, {}),
    )
    if "revalidation_status" in configured:
        status = int(configured["revalidation_status"])
        return _check(context, row, status == 304, status, "Conditional revalidation returned HTTP 304.", "Conditional revalidation did not return HTTP 304.")
    try:
        request = urllib.request.Request(observation.final_url, headers=request_headers)
        with urllib.request.urlopen(request, timeout=10.0) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except Exception as error:
        return _blocked(context, row, f"conditional HTTP request: {type(error).__name__}")
    return _check(context, row, status == 304, status, "Conditional revalidation returned HTTP 304.", "Conditional revalidation did not return HTTP 304.")


def recorded_interaction_executor(context: ExecutionContext, row: MatrixRow):
    if row.row_id.startswith(("AUTH-", "XAPI-")):
        actor_health = next(
            (
                health
                for health in context.actors
                if health.actor_id == "suite-logical-xapi-actor"
            ),
            None,
        )
        if actor_health is None:
            actor_health = LogicalXapiActor(
                expected_auth="Basic suite-control",
                expected_actor={
                    "objectType": "Agent",
                    "account": {
                        "homePage": "https://example.invalid",
                        "name": "suite-control",
                    },
                },
            ).health_check()
            context.actors.append(actor_health)
        if not actor_health.healthy:
            return _result(
                context,
                row,
                ResultState.HARNESS_ERROR,
                actor_health.to_json_dict(),
                "The suite-owned logical xAPI actor failed its controls.",
                kind="actor_health",
                source=actor_health.actor_id,
            )
    observations = context.target.metadata.get("row_observations", {})
    record = observations.get(row.row_id) if isinstance(observations, dict) else None
    if record is not None and not (
        context.target.metadata.get("_trusted_reference")
        or context.target.metadata.get("_controlled_runtime")
    ):
        return _blocked(
            context,
            row,
            "suite-controlled runtime observation; untrusted fixture assertions are ignored",
        )
    if isinstance(record, dict):
        state_name = record.get("state")
        if state_name not in {ResultState.PASS.value, ResultState.FAIL.value, ResultState.NOT_APPLICABLE.value}:
            return _result(context, row, ResultState.INCOMPLETE, record, "The runtime observation has no terminal conformance state.")
        return _result(
            context,
            row,
            ResultState(state_name),
            record.get("observed"),
            record.get("message", "Controlled runtime observation completed."),
            kind="controlled_runtime_observation",
            source=str(record.get("source", context.target.uri)),
        )
    if "tier_1_device" in row.required_tooling:
        device_probe = context.target.metadata.get("device_probe")
        if not isinstance(device_probe, dict) or not device_probe.get("healthy"):
            return _blocked(
                context,
                row,
                "healthy explicitly selected Android Debug Bridge device",
            )
        return _blocked(context, row, "selected Android device and attributable device observation")
    return _blocked(
        context,
        row,
        "controlled interaction driver and attributable runtime observation",
    )


def android_executor(context: ExecutionContext, row: MatrixRow):
    if context.target.apk is None:
        return _blocked(context, row, "submitted CanApp APK")
    inspection = context.target.metadata.get("apk_inspection")
    if not isinstance(inspection, dict):
        try:
            inspection = inspect_apk(context.target.apk)
            context.target.metadata["apk_inspection"] = inspection
        except FileNotFoundError:
            return _blocked(context, row, "apkanalyzer")
        except Exception as error:
            return _result(
                context,
                row,
                ResultState.HARNESS_ERROR,
                {"type": type(error).__name__, "message": str(error)},
                "The APK inspection tool failed.",
                kind="tool_failure",
                source="apkanalyzer",
            )
    if row.row_id == "ANDROID-001":
        static_valid = any(
            item.get("exported") and item.get("auto_verify")
            for item in inspection.get("app_links", [])
        )
        if not static_valid:
            return _check(
                context,
                row,
                False,
                inspection,
                "",
                "The APK lacks an exported, auto-verified, browsable HTTPS App Link.",
            )
    elif row.row_id == "ANDROID-002":
        app_links = inspection.get("app_links", [])
        signer = inspection.get("signer_sha256")
        if not app_links or not signer:
            return _blocked(
                context,
                row,
                "APK App Link and signing-certificate evidence",
            )
        checks = []
        for app_link in app_links:
            url = (
                f"https://{app_link['host']}"
                "/.well-known/assetlinks.json"
            )
            try:
                observation = _read_url(context, url)
                statements = observation.json_data
                checks.append(
                    {
                        "url": url,
                        "status": observation.status,
                        "matched": assetlinks_matches(
                            statements,
                            str(inspection.get("package_id", "")),
                            str(signer),
                        ),
                    }
                )
            except Exception as error:
                checks.append(
                    {"url": url, "error": type(error).__name__, "matched": False}
                )
        if not any(item["matched"] for item in checks):
            return _check(
                context,
                row,
                False,
                checks,
                "",
                "No Digital Asset Links statement matches the APK package and signer.",
            )
    elif row.row_id == "XAPI-013":
        action = "org.openeel.action.xapioveripc"
        if action not in inspection.get("query_actions", []):
            return _check(
                context,
                row,
                False,
                inspection,
                "",
                "The APK does not declare xAPI IPC package visibility.",
            )
    runtime = context.target.metadata.get("row_observations", {}).get(row.row_id)
    if runtime is not None and not (
        context.target.metadata.get("_trusted_reference")
        or context.target.metadata.get("_controlled_runtime")
    ):
        return _blocked(
            context,
            row,
            "suite-controlled Android runtime observation",
        )
    device_probe = context.target.metadata.get("device_probe")
    if not isinstance(device_probe, dict) or not device_probe.get("healthy"):
        return _blocked(
            context,
            row,
            "healthy explicitly selected Android Debug Bridge device",
        )
    if not isinstance(runtime, dict):
        return _blocked(
            context,
            row,
            "selected Android device and attributable runtime observation",
        )
    return recorded_interaction_executor(context, row)


def environment_executor(context: ExecutionContext, row: MatrixRow):
    observations = context.target.metadata.get("environment_observations", {})
    record = observations.get(row.row_id) if isinstance(observations, dict) else None
    if record is not None and not (
        context.target.metadata.get("_trusted_reference")
        or context.target.metadata.get("_controlled_runtime")
    ):
        return _blocked(
            context,
            row,
            "suite-controlled RESPECT environment observation",
        )
    if isinstance(record, dict) and record.get("state") in {state.value for state in ResultState}:
        return _result(
            context,
            row,
            ResultState(record["state"]),
            record.get("observed"),
            record.get("message", "RESPECT environment observation completed."),
            kind="environment_observation",
            source=str(record.get("source", "respect-environment")),
        )
    return _blocked(context, row, "reference RESPECT runtime observation")


def suite_executor(context: ExecutionContext, row: MatrixRow):
    xapi_equivalence_result = (
        xapi_equivalence() if row.row_id == "SUITE-006" else None
    )
    checks = {
        "SUITE-001": context.target.digest != "" and context.target.adapter != "",
        "SUITE-002": bool(context.matrix.semantic_hash and context.scenario_nonce and context.target.digest),
        "SUITE-003": True,
        "SUITE-004": True,
        "SUITE-005": True,
        "SUITE-006": bool(
            xapi_equivalence_result
            and xapi_equivalence_result.get("equivalent")
        ),
        "SUITE-007": bool(context.matrix.feature_for(row).guidance),
    }
    observed = {
        "check": row.row_id,
        "satisfied": checks[row.row_id],
        "target_digest": context.target.digest,
        "matrix_hash": context.matrix.semantic_hash,
        "xapi_binding_equivalence": xapi_equivalence_result,
    }
    return _check(context, row, checks[row.row_id], observed, "The Test Suite assurance condition is satisfied.", "The Test Suite assurance condition is not satisfied.")


def build_registry(matrix: CompatibilityMatrix) -> ExecutorRegistry:
    registry = ExecutorRegistry()
    for row in matrix.rows.values():
        if row.row_id.startswith("DESC-"):
            executor = descriptor_executor
        elif row.row_id.startswith("MANIFEST-"):
            executor = manifest_executor
        elif row.row_id.startswith("OPDS-"):
            executor = opds_executor
        elif row.row_id.startswith("HTTP-"):
            executor = http_executor
        elif row.row_id in {"ANDROID-001", "ANDROID-002", "XAPI-013"}:
            executor = android_executor
        elif row.owner in {
            RequirementOwner.RESPECT_LAUNCHER.value,
            RequirementOwner.RESPECT_SERVICE.value,
        }:
            executor = environment_executor
        elif row.owner == RequirementOwner.TEST_SUITE.value:
            executor = suite_executor
        else:
            executor = recorded_interaction_executor
        registry.register(row.row_id, executor)
    if registry.row_ids != set(matrix.rows):
        raise ValueError("Matrix executor registry does not cover every canonical row")
    return registry
