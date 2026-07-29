# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import base64
import binascii
import hashlib
import html
import ipaddress
import json
import re
import shutil
import ssl
import struct
import urllib.parse
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator
from respect_compat.handoff import canonical_hash

from .publication_server import make_publication_handler
from .resources import resource


DEFAULT_CATALOG_REL = (
    "https://respect.ustadmobile.com/ns/default-lesson-catalog"
)
OPEN_ACCESS_REL = "http://opds-spec.org/acquisition/open-access"
FINGERPRINT = re.compile(r"^(?:[0-9A-Fa-f]{2}:){31}[0-9A-Fa-f]{2}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
APPLICATION_ID = re.compile(
    r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$"
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _localized(value: Any, field: str) -> Dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field} must contain localized strings")
    result = {}
    for language, text in value.items():
        if (
            not isinstance(language, str)
            or not language.strip()
            or not isinstance(text, str)
            or not text.strip()
        ):
            raise ValueError(f"{field} contains an invalid localized string")
        result[language.strip()] = text.strip()
    return result


def _absolute_https(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    return value


def _origin(value: str, provision: str) -> str:
    value = _absolute_https(value, "origin").rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("origin must be a root HTTPS origin")
    if provision == "production":
        hostname = parsed.hostname or ""
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            raise ValueError(
                "production origin must use a public DNS hostname"
            )
        if hostname == "localhost" or "." not in hostname:
            raise ValueError(
                "production origin must use a public DNS hostname"
            )
    return value


def _public_path(value: Any, field: str, trailing: bool = False) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError(f"{field} must be a root-relative URL path")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.query
        or parsed.fragment
        or "//" in parsed.path
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise ValueError(f"{field} must be a safe root-relative URL path")
    normalized = parsed.path.rstrip("/")
    if not normalized:
        raise ValueError(f"{field} may not be the root path")
    return normalized + "/" if trailing else normalized


def _source_file(source_root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("lesson source path is missing")
    candidate = (source_root / value).resolve()
    if source_root != candidate and source_root not in candidate.parents:
        raise ValueError("lesson source must remain within the source root")
    if not candidate.is_file():
        raise ValueError(f"lesson source does not exist: {value}")
    return candidate


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF)
    )


def _generated_cover(title: str) -> bytes:
    width = height = 256
    digest = hashlib.sha256(title.encode("utf-8")).digest()
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            band = min(7, x // 32)
            height_value = 30 + digest[band] % 100
            color = (24, 27, 24)
            if 225 - height_value <= y <= 225 and x % 32 < 20:
                color = (
                    70 + digest[band] % 120,
                    70 + digest[band + 8] % 120,
                    70 + digest[band + 16] % 120,
                )
            rows.extend(color)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    title_text = b"Title\x00" + title.encode("utf-8")
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"tEXt", title_text)
        + _png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + _png_chunk(b"IEND", b"")
    )


def _integrity(body: bytes) -> str:
    digest = hashlib.sha256(body).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_integrity(path: Path) -> str:
    return "sha256-" + base64.b64encode(
        bytes.fromhex(_sha256(path))
    ).decode("ascii")


def _launch_html(title: str, publication_href: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <link rel="publication" type="application/webpub+json" '
        f'href="{html.escape(publication_href, quote=True)}">\n'
        f"  <title>{html.escape(title)}</title>\n"
        "</head>\n"
        "<body><main>"
        f"<h1>{html.escape(title)}</h1>"
        "<p>Acquire and open this lesson in its Candidate App.</p>"
        "</main></body>\n"
        "</html>\n"
    )


def _validated_manifest(
    manifest: Dict[str, Any],
    source_root: Path,
) -> Dict[str, Any]:
    if manifest.get("format_version") != "1.0.0":
        raise ValueError("publication manifest format_version must be 1.0.0")
    canapp = manifest.get("canapp")
    if not isinstance(canapp, dict):
        raise ValueError("publication manifest has no CanApp object")
    application_id = canapp.get("application_id")
    if (
        not isinstance(application_id, str)
        or not APPLICATION_ID.fullmatch(application_id)
    ):
        raise ValueError("CanApp application_id is invalid")
    result_canapp = {
        "identifier": _absolute_https(
            canapp.get("identifier"),
            "CanApp identifier",
        ),
        "title": _localized(canapp.get("title"), "CanApp title"),
        "application_id": application_id,
        "public_path": _public_path(
            canapp.get("public_path"),
            "CanApp public_path",
        ),
        "launch_path_prefix": _public_path(
            canapp.get("launch_path_prefix"),
            "CanApp launch_path_prefix",
            trailing=True,
        ),
    }
    lessons = manifest.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        raise ValueError("publication manifest must contain real lessons")
    result_lessons = []
    for index, lesson in enumerate(lessons):
        if not isinstance(lesson, dict):
            raise ValueError(f"lesson {index} must be an object")
        slug = lesson.get("slug")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise ValueError(f"lesson {index} slug is invalid")
        media_type = lesson.get("media_type")
        if (
            not isinstance(media_type, str)
            or "/" not in media_type
            or ";" in media_type
        ):
            raise ValueError(f"lesson {index} media_type is invalid")
        source = _source_file(source_root, lesson.get("source_path"))
        image_path = lesson.get("image_path")
        image = (
            _source_file(source_root, image_path)
            if image_path is not None
            else None
        )
        result_lessons.append(
            {
                "identifier": _absolute_https(
                    lesson.get("identifier"),
                    f"lesson {index} identifier",
                ),
                "title": _localized(
                    lesson.get("title"),
                    f"lesson {index} title",
                ),
                "slug": slug,
                "source_path": source.relative_to(source_root).as_posix(),
                "source": source,
                "media_type": media_type.lower(),
                "image_path": (
                    image.relative_to(source_root).as_posix()
                    if image is not None
                    else None
                ),
                "image": image,
            }
        )
    for field in ("identifier", "slug", "source_path"):
        values = [lesson[field] for lesson in result_lessons]
        if len(values) != len(set(values)):
            raise ValueError(f"publication lessons have duplicate {field}")
    default = manifest.get("default_lesson_identifier")
    if default not in {
        lesson["identifier"] for lesson in result_lessons
    }:
        raise ValueError(
            "default_lesson_identifier must identify one real lesson"
        )
    return {
        "format_version": "1.0.0",
        "canapp": result_canapp,
        "default_lesson_identifier": default,
        "lessons": result_lessons,
    }


def _public_file(
    public: Path,
    url_path: str,
) -> Path:
    return public / url_path.lstrip("/")


def build_publication_manifest_from_adapter(
    adapter: Dict[str, Any],
    source_root: Path,
    *,
    canapp_identifier: str,
    canapp_title: str,
    application_id: str,
    public_path: str,
    launch_path_prefix: str,
    lesson_identifier_root: str,
    lesson_media_type: str,
    confirmed_inventory: Dict[str, Any],
    language: str = "en",
) -> Dict[str, Any]:
    if (
        adapter.get("artifact_type")
        != "respect_ification_generated_repair_adapter"
    ):
        raise ValueError("publication derivation requires a repair adapter")
    if adapter.get("semantic_hash") != canonical_hash(
        adapter,
        ("semantic_hash",),
    ):
        raise ValueError("repair adapter semantic hash mismatch")
    source_root = source_root.resolve(strict=True)
    analysis = adapter.get("source_analysis")
    candidates = (
        analysis.get("content_candidates")
        if isinstance(analysis, dict)
        else None
    )
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("repair adapter contains no lesson candidates")
    if (
        not isinstance(confirmed_inventory, dict)
        or confirmed_inventory.get("artifact_type")
        != "respect_confirmed_lesson_inventory"
        or confirmed_inventory.get("format_version") != "1.0.0"
        or confirmed_inventory.get("source_tree_digest")
        != analysis.get("source_tree_digest")
        or confirmed_inventory.get("inventory_complete") is not True
    ):
        raise ValueError(
            "publication inventory requires a complete source-bound lesson "
            "confirmation"
        )
    confirmed_lessons = confirmed_inventory.get("lessons")
    if not isinstance(confirmed_lessons, list) or not confirmed_lessons:
        raise ValueError("confirmed lesson inventory is empty")
    if not all(isinstance(item, dict) for item in confirmed_lessons):
        raise ValueError(
            "confirmed lesson inventory entries must be objects"
        )
    candidates_by_path = {
        item.get("path"): item
        for item in candidates
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    selected_paths = [item.get("source_path") for item in confirmed_lessons]
    if not all(
        isinstance(path, str) and path for path in selected_paths
    ):
        raise ValueError(
            "confirmed lesson inventory entries require source paths"
        )
    if len(selected_paths) != len(set(selected_paths)):
        raise ValueError("confirmed lesson inventory contains duplicate paths")
    default_source_path = confirmed_inventory.get("default_source_path")
    if default_source_path not in selected_paths:
        raise ValueError(
            "confirmed default lesson is not in the lesson inventory"
        )
    lessons = []
    for confirmation in sorted(
        confirmed_lessons,
        key=lambda item: item.get("source_path", ""),
    ):
        path = confirmation.get("source_path")
        candidate = candidates_by_path.get(path)
        if candidate is None:
            raise ValueError(
                f"confirmed lesson is not a source-derived candidate: {path}"
            )
        source = _source_file(source_root, path)
        if (
            confirmation.get("sha256") != candidate.get("sha256")
            or _sha256(source) != candidate.get("sha256")
        ):
            raise ValueError(
                f"confirmed lesson digest does not match source analysis: {path}"
            )
        title = confirmation.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                f"confirmed lesson needs a truthful title: {path}"
            )
        requested_slug = confirmation.get("slug")
        stem = Path(path).stem.lower()
        slug = (
            requested_slug
            if isinstance(requested_slug, str)
            else re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
        )
        if not SLUG.fullmatch(slug):
            raise ValueError(
                f"lesson candidate has no usable slug: {path}"
            )
        lessons.append(
            {
                "identifier": (
                    f"{lesson_identifier_root.rstrip('/')}/{slug}"
                ),
                "title": {language: title.strip()},
                "slug": slug,
                "source_path": path,
                "media_type": lesson_media_type,
            }
        )
    manifest = {
        "format_version": "1.0.0",
        "canapp": {
            "identifier": canapp_identifier,
            "title": {language: canapp_title},
            "application_id": application_id,
            "public_path": public_path,
            "launch_path_prefix": launch_path_prefix,
        },
        "default_lesson_identifier": next(
            item["identifier"]
            for item in lessons
            if item["source_path"] == default_source_path
        ),
        "lessons": lessons,
    }
    _validated_manifest(manifest, source_root)
    return manifest


def build_publication_pack(
    manifest: Dict[str, Any],
    source_root: Path,
    origin: str,
    signing_fingerprint: str,
    output: Path,
    *,
    provision: str,
    signer_kind: Optional[str] = None,
    apk_binding: Optional[Dict[str, str]] = None,
    certified_artifact: Optional[Path] = None,
    publication_authorization_token: Optional[Path] = None,
) -> Dict[str, Any]:
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("source root must be a directory")
    if provision not in {"provisional", "production"}:
        raise ValueError("provision must be provisional or production")
    origin = _origin(origin, provision)
    if provision == "production" and signer_kind is None:
        raise ValueError(
            "production requires explicit release signing classification"
        )
    signer_kind = signer_kind or "debug"
    if signer_kind not in {"debug", "release"}:
        raise ValueError("signer kind must be debug or release")
    if provision == "production" and signer_kind != "release":
        raise ValueError("production requires a release signing certificate")
    if not isinstance(signing_fingerprint, str) or not FINGERPRINT.fullmatch(
        signing_fingerprint
    ):
        raise ValueError(
            "signing fingerprint must be one colon-delimited SHA-256 value"
        )
    fingerprint = signing_fingerprint.upper()
    normalized = _validated_manifest(manifest, source_root)
    if provision == "production":
        normalized_signer = fingerprint.replace(":", "")
        if (
            not isinstance(apk_binding, dict)
            or apk_binding.get("package_id")
            != normalized["canapp"]["application_id"]
            or apk_binding.get("signer_sha256") != normalized_signer
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                str(apk_binding.get("apk_sha256", "")),
            )
        ):
            raise ValueError(
                "production requires signing evidence bound to the submitted APK"
            )
        if certified_artifact is None:
            raise ValueError(
                "production requires the exact submitted APK in the publication pack"
            )
    artifact_source = (
        certified_artifact.resolve(strict=True)
        if certified_artifact is not None
        else None
    )
    if artifact_source is not None:
        if not artifact_source.is_file():
            raise ValueError("certified artifact must be a file")
        artifact_sha256 = _sha256(artifact_source)
        if (
            isinstance(apk_binding, dict)
            and apk_binding.get("apk_sha256") != artifact_sha256
        ):
            raise ValueError(
                "certified artifact bytes do not match the APK binding"
            )
    else:
        artifact_sha256 = None
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("publication pack output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    public = output / "public"
    public.mkdir()
    canapp = normalized["canapp"]
    public_path = canapp["public_path"]
    immutable_artifact_path = None
    immutable_artifact_url = None
    if artifact_source is not None and artifact_sha256 is not None:
        immutable_artifact_path = (
            f"{public_path}/builds/{artifact_sha256}/"
            f"{artifact_source.name}"
        )
        immutable_artifact_url = f"{origin}{immutable_artifact_path}"
        artifact_destination = _public_file(
            public, immutable_artifact_path
        )
        artifact_destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact_source, artifact_destination)
    default_lesson = next(
        lesson
        for lesson in normalized["lessons"]
        if lesson["identifier"] == normalized["default_lesson_identifier"]
    )
    publications = []
    media_types: Dict[str, str] = {}
    inventory = []
    for lesson in normalized["lessons"]:
        lesson_base = (
            f"{public_path}/lessons/{lesson['slug']}"
        )
        launch_path = (
            f"{canapp['launch_path_prefix']}{lesson['slug']}"
        )
        source_name = lesson["source"].name
        source_sha256 = _sha256(lesson["source"])
        integrity = _file_integrity(lesson["source"])
        publication_path = f"{lesson_base}/publication.json"
        resource_path = f"{lesson_base}/{source_name}"
        cover_path = f"{lesson_base}/cover.png"
        publication = {
            "metadata": {
                "identifier": lesson["identifier"],
                "title": lesson["title"],
            },
            "links": [
                {
                    "rel": ["self"],
                    "href": publication_path,
                    "type": "application/webpub+json",
                }
            ],
            "readingOrder": [
                {"href": launch_path, "type": "text/html"}
            ],
            "resources": [
                {
                    "href": source_name,
                    "type": lesson["media_type"],
                    "integrity": integrity,
                },
                {
                    "href": "cover.png",
                    "type": "image/png",
                    "rel": ["cover"],
                },
            ],
        }
        publications.append(
            {
                "metadata": publication["metadata"],
                "links": [
                    {
                        "rel": [OPEN_ACCESS_REL],
                        "href": launch_path,
                        "type": "text/html",
                    }
                ],
                "images": [
                    {"href": cover_path, "type": "image/png"}
                ],
                "resources": [
                    {
                        "href": publication_path,
                        "type": "application/webpub+json",
                    },
                    {
                        "href": resource_path,
                        "type": lesson["media_type"],
                        "integrity": integrity,
                    },
                ],
            }
        )
        _write_json(_public_file(public, publication_path), publication)
        destination = _public_file(public, resource_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(lesson["source"], destination)
        cover = _public_file(public, cover_path)
        if lesson["image"] is None:
            title = next(iter(lesson["title"].values()))
            cover.write_bytes(_generated_cover(title))
        else:
            shutil.copyfile(lesson["image"], cover)
        launch = _public_file(public, launch_path)
        launch.parent.mkdir(parents=True, exist_ok=True)
        launch.write_text(
            _launch_html(
                next(iter(lesson["title"].values())),
                publication_path,
            ),
            encoding="utf-8",
        )
        media_types.update(
            {
                publication_path: "application/webpub+json",
                resource_path: lesson["media_type"],
                cover_path: "image/png",
                launch_path: "text/html",
            }
        )
        inventory.append(
            {
                "identifier": lesson["identifier"],
                "title": lesson["title"],
                "slug": lesson["slug"],
                "source_path": lesson["source_path"],
                "source_sha256": source_sha256,
                "integrity": integrity,
                "media_type": lesson["media_type"],
                "publication_path": publication_path,
                "resource_path": resource_path,
                "launch_path": launch_path,
                "cover_path": cover_path,
                "cover_source": (
                    lesson["image_path"]
                    if lesson["image_path"] is not None
                    else "generated_from_localized_title"
                ),
            }
        )
    descriptor_path = f"{public_path}/descriptor.json"
    catalog_path = f"{public_path}/catalog.json"
    default_launch = (
        f"{canapp['launch_path_prefix']}{default_lesson['slug']}"
    )
    default_cover = (
        f"{public_path}/lessons/{default_lesson['slug']}/cover.png"
    )
    descriptor = {
        "metadata": {
            "identifier": canapp["identifier"],
            "title": canapp["title"],
        },
        "links": [
            {
                "rel": [OPEN_ACCESS_REL],
                "href": f"{origin}{default_launch}",
                "type": "text/html",
            },
            {
                "rel": [DEFAULT_CATALOG_REL],
                "href": f"{origin}{catalog_path}",
                "type": "application/opds+json",
            },
        ],
        "images": [
            {"href": f"{origin}{default_cover}", "type": "image/png"}
        ],
    }
    catalog = {
        "metadata": {
            "title": {
                language: f"{title} lesson catalog"
                for language, title in canapp["title"].items()
            }
        },
        "links": [
            {
                "rel": ["self"],
                "href": catalog_path,
                "type": "application/opds+json",
            }
        ],
        "publications": publications,
    }
    association = [
        {
            "relation": [
                "delegate_permission/common.handle_all_urls"
            ],
            "target": {
                "namespace": "android_app",
                "package_name": canapp["application_id"],
                "sha256_cert_fingerprints": [fingerprint],
            },
        }
    ]
    inventory_path = f"{public_path}/lesson-inventory.json"
    association_path = "/.well-known/assetlinks.json"
    _write_json(_public_file(public, descriptor_path), descriptor)
    _write_json(_public_file(public, catalog_path), catalog)
    _write_json(_public_file(public, inventory_path), inventory)
    _write_json(_public_file(public, association_path), association)
    media_types.update(
        {
            descriptor_path: "application/opds-publication+json",
            catalog_path: "application/opds+json",
            inventory_path: "application/json",
            association_path: "application/json",
        }
    )
    if immutable_artifact_path is not None:
        media_types[immutable_artifact_path] = (
            "application/vnd.android.package-archive"
            if artifact_source is not None
            and artifact_source.suffix.lower() == ".apk"
            else "application/octet-stream"
        )
    deployable_manifest = {
        "format_version": normalized["format_version"],
        "canapp": canapp,
        "default_lesson_identifier": (
            normalized["default_lesson_identifier"]
        ),
        "lessons": [
            {
                key: value
                for key, value in lesson.items()
                if key not in {"source", "image"}
            }
            for lesson in normalized["lessons"]
        ],
    }
    _write_json(output / "publication-manifest.json", deployable_manifest)
    (output / "publication-manifest.schema.json").write_bytes(
        resource(
            "data/publication/publication_manifest.schema.json"
        ).read_bytes()
    )
    authorization_ref = None
    if publication_authorization_token is not None:
        token_source = publication_authorization_token.resolve(strict=True)
        token = json.loads(token_source.read_text(encoding="utf-8"))
        if not isinstance(token, dict):
            raise ValueError(
                "publication authorization token must be a JSON object"
            )
        authorization_ref = "submission/publication-authorization.json"
        _write_json(output / authorization_ref, token)
    deployment = {
        "artifact_type": "respect_publication_pack_deployment",
        "format_version": "1.0.0",
        "origin": origin,
        "provision": provision,
        "signer_kind": signer_kind,
        "signing_fingerprint": fingerprint,
        "apk_binding": apk_binding,
        "immutable_artifact_path": immutable_artifact_path,
        "immutable_artifact_url": immutable_artifact_url,
        "publication_authorization_token": authorization_ref,
        "descriptor_path": descriptor_path,
        "catalog_path": catalog_path,
        "association_path": association_path,
        "media_types": dict(sorted(media_types.items())),
        "server_contract": {
            "https_required": True,
            "content_length_required": True,
            "etag_or_last_modified_required": True,
            "conditional_304_required": True,
        },
    }
    deployment["semantic_hash"] = canonical_hash(deployment)
    _write_json(output / "deployment.json", deployment)
    server_source = Path(__file__).with_name("publication_server.py")
    shutil.copyfile(server_source, output / "serve.py")
    (output / "Dockerfile").write_text(
        "FROM python:3.13-alpine\n"
        "WORKDIR /srv\n"
        "COPY . /srv\n"
        'EXPOSE 8080\n'
        'CMD ["python", "serve.py", "--pack", "/srv", '
        '"--bind", "0.0.0.0", "--port", "8080"]\n',
        encoding="utf-8",
    )
    (output / "DEPLOYMENT.md").write_text(
        "# RESPECT Publication Pack\n\n"
        "Serve the `public` directory at the exact HTTPS origin declared "
        "in `deployment.json`, or run the included reference server with "
        "a certificate and key. Production deployments must terminate "
        "Transport Layer Security at the declared owner-controlled "
        "origin and use the declared release signer.\n",
        encoding="utf-8",
    )
    artifact_paths = sorted(
        path
        for path in output.rglob("*")
        if path.is_file()
        and path.name != "respect-publication-receipt.json"
    )
    receipt_core = {
        "artifact_type": "respect_publication_pack_receipt",
        "format_version": "1.0.0",
        "origin": origin,
        "provision": provision,
        "signer_kind": signer_kind,
        "signing_fingerprint": fingerprint,
        "apk_binding": apk_binding,
        "immutable_artifact_url": immutable_artifact_url,
        "publication_authorization_token": authorization_ref,
        "canapp_identifier": canapp["identifier"],
        "application_id": canapp["application_id"],
        "lesson_count": len(inventory),
        "inventory": inventory,
        "artifacts": [
            {
                "path": path.relative_to(output).as_posix(),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in artifact_paths
        ],
    }
    receipt = {
        **receipt_core,
        "verification": {
            "scope": "pack_integrity_only",
            "valid": False,
            "deployed_origin_verified": False,
            "errors": [],
        },
    }
    receipt["semantic_hash"] = canonical_hash(receipt)
    receipt_path = output / "respect-publication-receipt.json"
    _write_json(receipt_path, receipt)
    errors = verify_publication_pack(output)
    receipt["verification"] = {
        "scope": "pack_integrity_only",
        "valid": not errors,
        "deployed_origin_verified": False,
        "errors": errors,
    }
    receipt["semantic_hash"] = canonical_hash(
        receipt,
        ("semantic_hash",),
    )
    _write_json(receipt_path, receipt)
    if errors:
        raise ValueError(f"generated publication pack is invalid: {errors}")
    return receipt


def verify_publication_pack(pack: Path) -> List[str]:
    pack = pack.resolve(strict=True)
    errors: List[str] = []
    try:
        deployment = json.loads(
            (pack / "deployment.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (pack / "publication-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        receipt = json.loads(
            (pack / "respect-publication-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        manifest_schema = json.loads(
            (pack / "publication-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
    except (FileNotFoundError, json.JSONDecodeError) as error:
        return [f"PACK_METADATA_INVALID: {error}"]
    errors.extend(
        f"PUBLICATION_MANIFEST_SCHEMA: {item.json_path}: {item.message}"
        for item in Draft202012Validator(
            manifest_schema,
        ).iter_errors(manifest)
    )
    if deployment.get("semantic_hash") != canonical_hash(
        deployment,
        ("semantic_hash",),
    ):
        errors.append("DEPLOYMENT_HASH_MISMATCH")
    if receipt.get("semantic_hash") != canonical_hash(
        receipt,
        ("semantic_hash",),
    ):
        errors.append("RECEIPT_HASH_MISMATCH")
    provision = deployment.get("provision")
    try:
        _origin(str(deployment.get("origin", "")), str(provision))
    except ValueError:
        errors.append("DEPLOYMENT_ORIGIN_OR_PROVISION_INVALID")
    if provision == "production":
        binding = deployment.get("apk_binding")
        signer = str(deployment.get("signing_fingerprint", "")).replace(
            ":",
            "",
        )
        if (
            deployment.get("signer_kind") != "release"
            or not isinstance(binding, dict)
            or binding.get("package_id")
            != manifest.get("canapp", {}).get("application_id")
            or binding.get("signer_sha256") != signer
            or not re.fullmatch(
                r"[0-9a-f]{64}",
                str(binding.get("apk_sha256", "")),
            )
        ):
            errors.append("PRODUCTION_APK_BINDING_INVALID")
        immutable_url = deployment.get("immutable_artifact_url")
        immutable_path = deployment.get("immutable_artifact_path")
        if (
            not isinstance(immutable_url, str)
            or not isinstance(immutable_path, str)
            or immutable_url
            != f"{str(deployment.get('origin', '')).rstrip('/')}"
            f"{immutable_path}"
        ):
            errors.append("PRODUCTION_IMMUTABLE_ARTIFACT_URL_INVALID")
        else:
            try:
                artifact = _public_file(pack / "public", immutable_path)
                if (
                    not artifact.is_file()
                    or _sha256(artifact) != binding.get("apk_sha256")
                    or binding.get("apk_sha256") not in immutable_path
                ):
                    errors.append(
                        "PRODUCTION_IMMUTABLE_ARTIFACT_INVALID"
                    )
            except ValueError:
                errors.append("PRODUCTION_IMMUTABLE_ARTIFACT_INVALID")
    for field in (
        "origin",
        "provision",
        "signer_kind",
        "signing_fingerprint",
        "apk_binding",
        "immutable_artifact_url",
        "publication_authorization_token",
    ):
        if receipt.get(field) != deployment.get(field):
            errors.append(f"RECEIPT_DEPLOYMENT_MISMATCH: {field}")
    verification = receipt.get("verification")
    if (
        not isinstance(verification, dict)
        or verification.get("scope") != "pack_integrity_only"
        or verification.get("deployed_origin_verified") is not False
    ):
        errors.append("PACK_RECEIPT_SCOPE_INVALID")
    for artifact in receipt.get("artifacts", []):
        path = pack / artifact.get("path", "")
        if not path.is_file():
            errors.append(
                f"ARTIFACT_MISSING: {artifact.get('path')}"
            )
            continue
        if path.stat().st_size != artifact.get("size"):
            errors.append(
                f"ARTIFACT_SIZE_MISMATCH: {artifact.get('path')}"
            )
        if _sha256(path) != artifact.get("sha256"):
            errors.append(
                f"ARTIFACT_HASH_MISMATCH: {artifact.get('path')}"
            )
    public = pack / "public"
    media_types = deployment.get("media_types", {})
    origin = deployment.get("origin", "")
    canapp = manifest.get("canapp", {})
    public_path = canapp.get("public_path", "")
    descriptor_path = deployment.get("descriptor_path", "")
    catalog_path = deployment.get("catalog_path", "")
    try:
        descriptor = json.loads(
            _public_file(public, descriptor_path).read_text(
                encoding="utf-8"
            )
        )
        catalog = json.loads(
            _public_file(public, catalog_path).read_text(
                encoding="utf-8"
            )
        )
        association = json.loads(
            _public_file(
                public,
                deployment.get("association_path", ""),
            ).read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError) as error:
        errors.append(f"PUBLICATION_DOCUMENT_INVALID: {error}")
        return sorted(set(errors))
    if descriptor.get("metadata", {}).get("identifier") != canapp.get(
        "identifier"
    ):
        errors.append("DESCRIPTOR_IDENTITY_MISMATCH")
    publications = catalog.get("publications", [])
    lessons = manifest.get("lessons", [])
    if len(publications) != len(lessons):
        errors.append("CATALOG_INVENTORY_MISMATCH")
    by_identifier = {
        item.get("metadata", {}).get("identifier"): item
        for item in publications
    }
    for lesson in lessons:
        identifier = lesson.get("identifier")
        publication = by_identifier.get(identifier)
        if publication is None:
            errors.append(f"CATALOG_LESSON_MISSING: {identifier}")
            continue
        slug = lesson.get("slug")
        source_name = Path(lesson.get("source_path", "")).name
        publication_path = (
            f"{public_path}/lessons/{slug}/publication.json"
        )
        resource_path = f"{public_path}/lessons/{slug}/{source_name}"
        cover_path = f"{public_path}/lessons/{slug}/cover.png"
        launch_path = (
            f"{canapp.get('launch_path_prefix', '')}{slug}"
        )
        acquisition_links = [
            link
            for link in publication.get("links", [])
            if OPEN_ACCESS_REL in (
                link.get("rel")
                if isinstance(link.get("rel"), list)
                else [link.get("rel")]
            )
        ]
        if (
            len(acquisition_links) != 1
            or acquisition_links[0].get("href") != launch_path
            or acquisition_links[0].get("type") != "text/html"
        ):
            errors.append(
                f"CATALOG_ACQUISITION_MISMATCH: {identifier}"
            )
        catalog_resources = publication.get("resources", [])
        if not any(
            item.get("href") == publication_path
            and item.get("type") == "application/webpub+json"
            for item in catalog_resources
        ):
            errors.append(
                f"CATALOG_READIUM_LINK_MISMATCH: {identifier}"
            )
        for path, media_type in (
            (publication_path, "application/webpub+json"),
            (resource_path, lesson.get("media_type")),
            (cover_path, "image/png"),
            (launch_path, "text/html"),
        ):
            if not _public_file(public, path).is_file():
                errors.append(f"PUBLIC_RESOURCE_MISSING: {path}")
            if media_types.get(path) != media_type:
                errors.append(f"MEDIA_TYPE_MISMATCH: {path}")
        try:
            wrapper = json.loads(
                _public_file(public, publication_path).read_text(
                    encoding="utf-8"
                )
            )
            native = next(
                item
                for item in wrapper.get("resources", [])
                if item.get("type") == lesson.get("media_type")
            )
            body = _public_file(public, resource_path).read_bytes()
            if wrapper.get("metadata", {}).get(
                "identifier"
            ) != identifier:
                errors.append(
                    f"READIUM_IDENTITY_MISMATCH: {identifier}"
                )
            if not any(
                item.get("href") == launch_path
                and item.get("type") == "text/html"
                for item in wrapper.get("readingOrder", [])
            ):
                errors.append(
                    f"READIUM_LAUNCH_MISMATCH: {identifier}"
                )
            if native.get("href") != source_name:
                errors.append(
                    f"READIUM_RESOURCE_MISMATCH: {identifier}"
                )
            if native.get("integrity") != _integrity(body):
                errors.append(
                    f"LESSON_INTEGRITY_MISMATCH: {identifier}"
                )
        except (
            FileNotFoundError,
            json.JSONDecodeError,
            StopIteration,
        ):
            errors.append(f"READIUM_WRAPPER_INVALID: {identifier}")
    target = (
        association[0].get("target", {})
        if isinstance(association, list) and association
        else {}
    )
    if target.get("package_name") != canapp.get("application_id"):
        errors.append("ASSOCIATION_PACKAGE_MISMATCH")
    if target.get("sha256_cert_fingerprints") != [
        deployment.get("signing_fingerprint")
    ]:
        errors.append("ASSOCIATION_SIGNER_MISMATCH")
    descriptor_links = descriptor.get("links", [])
    if not all(
        isinstance(link.get("href"), str)
        and link["href"].startswith(origin)
        for link in descriptor_links
    ):
        errors.append("DESCRIPTOR_ORIGIN_MISMATCH")
    return sorted(set(errors))


def verify_deployed_publication(
    pack: Path,
    *,
    deployed_origin: Optional[str] = None,
    ca_cert: Optional[Path] = None,
    opener=None,
) -> List[str]:
    pack = pack.resolve(strict=True)
    deployment = json.loads(
        (pack / "deployment.json").read_text(encoding="utf-8")
    )
    origin = _origin(
        deployed_origin or deployment.get("origin", ""),
        deployment.get("provision", "provisional"),
    )
    context = ssl.create_default_context(
        cafile=str(ca_cert) if ca_cert is not None else None
    )
    open_request = opener or urllib.request.urlopen
    public = pack / "public"
    errors: List[str] = []
    media_types = deployment.get("media_types")
    if not isinstance(media_types, dict):
        return ["DEPLOYMENT_MEDIA_TYPES_INVALID"]
    for path, expected_media_type in sorted(media_types.items()):
        url = origin + path
        request = urllib.request.Request(url, method="GET")
        try:
            with open_request(request, context=context) as response:
                status = response.status
                body = response.read()
                headers = response.headers
        except (OSError, urllib.error.URLError) as error:
            errors.append(f"DEPLOYED_REQUEST_FAILED: {path}: {error}")
            continue
        if status != 200:
            errors.append(f"DEPLOYED_STATUS_MISMATCH: {path}: {status}")
            continue
        media_type = headers.get("Content-Type", "").split(";", 1)[
            0
        ].strip().lower()
        if media_type != expected_media_type:
            errors.append(f"DEPLOYED_MEDIA_TYPE_MISMATCH: {path}")
        declared_length = headers.get("Content-Length")
        if (
            declared_length is None
            or not declared_length.isdigit()
            or int(declared_length) != len(body)
        ):
            errors.append(f"DEPLOYED_CONTENT_LENGTH_MISMATCH: {path}")
        local = _public_file(public, path)
        if not local.is_file() or body != local.read_bytes():
            errors.append(f"DEPLOYED_BYTES_MISMATCH: {path}")
        etag = headers.get("ETag")
        modified = headers.get("Last-Modified")
        if not etag and not modified:
            errors.append(f"DEPLOYED_VALIDATOR_MISSING: {path}")
            continue
        conditional_header = (
            ("If-None-Match", etag)
            if etag
            else ("If-Modified-Since", modified)
        )
        conditional = urllib.request.Request(
            url,
            headers={conditional_header[0]: conditional_header[1]},
            method="GET",
        )
        try:
            with open_request(conditional, context=context) as response:
                conditional_status = response.status
                response.read()
        except urllib.error.HTTPError as error:
            conditional_status = error.code
            error.read()
        except (OSError, urllib.error.URLError) as error:
            errors.append(
                f"DEPLOYED_CONDITIONAL_REQUEST_FAILED: {path}: {error}"
            )
            continue
        if conditional_status != 304:
            errors.append(
                f"DEPLOYED_CONDITIONAL_STATUS_MISMATCH: "
                f"{path}: {conditional_status}"
            )
    return sorted(set(errors))


def build_verification_receipt(
    pack: Path,
    errors: List[str],
    *,
    deployed_origin: Optional[str] = None,
) -> Dict[str, Any]:
    deployment = json.loads(
        (pack / "deployment.json").read_text(encoding="utf-8")
    )
    core = {
        "artifact_type": "respect_publication_pack_verification",
        "format_version": "1.0.0",
        "pack_semantic_hash": deployment.get("semantic_hash"),
        "origin": deployment.get("origin"),
        "provision": deployment.get("provision"),
        "deployed_origin": deployed_origin,
        "valid": not errors,
        "errors": errors,
    }
    return {**core, "semantic_hash": canonical_hash(core)}
