# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from respect_ification.publication_pack import (
    build_publication_manifest_from_adapter,
    build_publication_pack,
    make_publication_handler,
    verify_deployed_publication,
    verify_publication_pack,
)
from respect_compat.handoff import canonical_hash


FINGERPRINT = "AA:" * 31 + "AA"


def _manifest():
    return {
        "format_version": "1.0.0",
        "canapp": {
            "identifier": "https://owner.example/canapps/example",
            "title": {"en": "Example CanApp"},
            "application_id": "example.owner.canapp",
            "public_path": "/example",
            "launch_path_prefix": "/example/launch/",
        },
        "default_lesson_identifier": (
            "https://owner.example/lessons/opaque-one"
        ),
        "lessons": [
            {
                "identifier": (
                    "https://owner.example/lessons/opaque-one"
                ),
                "title": {"en": "Opaque One"},
                "slug": "opaque-one",
                "source_path": "shared/Opaque_One.lessonpack",
                "media_type": "application/vnd.example.lesson",
            },
            {
                "identifier": (
                    "https://owner.example/lessons/opaque-two"
                ),
                "title": {"en": "Opaque Two"},
                "slug": "opaque-two",
                "source_path": "shared/Opaque_Two.lessonpack",
                "media_type": "application/vnd.example.lesson",
            },
        ],
    }


def _source(tmp_path):
    source = tmp_path / "source"
    lessons = source / "shared"
    lessons.mkdir(parents=True)
    (lessons / "Opaque_One.lessonpack").write_bytes(
        b"\x00opaque proprietary lesson one"
    )
    (lessons / "Opaque_Two.lessonpack").write_bytes(
        b"\x00opaque proprietary lesson two"
    )
    return source


def test_builds_complete_content_agnostic_publication_pack(tmp_path):
    source = _source(tmp_path)
    output = tmp_path / "pack"

    receipt = build_publication_pack(
        _manifest(),
        source,
        "https://lessons.owner.example",
        FINGERPRINT,
        output,
        provision="provisional",
    )

    public = output / "public"
    descriptor = json.loads(
        (public / "example" / "descriptor.json").read_text()
    )
    catalog = json.loads(
        (public / "example" / "catalog.json").read_text()
    )
    association = json.loads(
        (public / ".well-known" / "assetlinks.json").read_text()
    )
    assert descriptor["metadata"]["identifier"] == (
        "https://owner.example/canapps/example"
    )
    assert len(catalog["publications"]) == 2
    assert association[0]["target"]["package_name"] == (
        "example.owner.canapp"
    )
    assert (
        public
        / "example"
        / "lessons"
        / "opaque-one"
        / "Opaque_One.lessonpack"
    ).read_bytes() == b"\x00opaque proprietary lesson one"
    assert (
        public
        / "example"
        / "lessons"
        / "opaque-one"
        / "cover.png"
    ).is_file()
    assert (output / "serve.py").is_file()
    assert (output / "Dockerfile").is_file()
    assert (output / "deployment.json").is_file()
    assert (output / "publication-manifest.schema.json").is_file()
    assert receipt["provision"] == "provisional"
    assert receipt["lesson_count"] == 2
    assert receipt["verification"]["valid"] is True
    assert verify_publication_pack(output) == []


def test_builds_publication_manifest_from_generic_repair_analysis(tmp_path):
    source = _source(tmp_path)
    candidates = [
        {
            "path": "shared/Opaque_One.lessonpack",
            "metadata_hint": {"title": "Opaque One"},
        },
        {
            "path": "shared/Opaque_Two.lessonpack",
            "metadata_hint": {"title": "Opaque Two"},
        },
    ]
    adapter = {
        "artifact_type": "respect_ification_generated_repair_adapter",
        "source_analysis": {"content_candidates": candidates},
    }
    adapter["semantic_hash"] = canonical_hash(adapter)

    manifest = build_publication_manifest_from_adapter(
        adapter,
        source,
        canapp_identifier="https://owner.example/canapps/example",
        canapp_title="Example CanApp",
        application_id="example.owner.canapp",
        public_path="/example",
        launch_path_prefix="/example/launch/",
        lesson_identifier_root="https://owner.example/lessons",
        lesson_media_type="application/vnd.example.lesson",
        confirm_all_candidates=True,
    )

    assert [item["source_path"] for item in manifest["lessons"]] == [
        "shared/Opaque_One.lessonpack",
        "shared/Opaque_Two.lessonpack",
    ]
    assert [item["slug"] for item in manifest["lessons"]] == [
        "opaque-one",
        "opaque-two",
    ]
    assert manifest["default_lesson_identifier"] == (
        "https://owner.example/lessons/opaque-one"
    )


def test_manifest_derivation_refuses_invented_lesson_titles(tmp_path):
    source = _source(tmp_path)
    adapter = {
        "artifact_type": "respect_ification_generated_repair_adapter",
        "source_analysis": {
            "content_candidates": [
                {
                    "path": "shared/Opaque_One.lessonpack",
                    "metadata_hint": {},
                }
            ]
        },
    }
    adapter["semantic_hash"] = canonical_hash(adapter)

    with pytest.raises(ValueError, match="truthful title"):
        build_publication_manifest_from_adapter(
            adapter,
            source,
            canapp_identifier="https://owner.example/canapps/example",
            canapp_title="Example CanApp",
            application_id="example.owner.canapp",
            public_path="/example",
            launch_path_prefix="/example/launch/",
            lesson_identifier_root="https://owner.example/lessons",
            lesson_media_type="application/vnd.example.lesson",
            confirm_all_candidates=True,
        )


def test_reference_server_supplies_types_validators_and_conditional_304(
    tmp_path,
):
    source = _source(tmp_path)
    output = tmp_path / "pack"
    build_publication_pack(
        _manifest(),
        source,
        "https://lessons.owner.example",
        FINGERPRINT,
        output,
        provision="provisional",
    )
    handler = make_publication_handler(output)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_address[1],
        )
        connection.request("GET", "/example/descriptor.json")
        response = connection.getresponse()
        body = response.read()
        etag = response.getheader("ETag")
        assert response.status == 200
        assert response.getheader("Content-Type") == (
            "application/opds-publication+json"
        )
        assert int(response.getheader("Content-Length")) == len(body)
        assert response.getheader("Last-Modified")
        assert etag
        connection.request(
            "GET",
            "/example/descriptor.json",
            headers={"If-None-Match": etag},
        )
        conditional = connection.getresponse()
        conditional.read()
        assert conditional.status == 304
    finally:
        server.shutdown()
        server.server_close()


def test_deployed_verifier_checks_bytes_headers_and_conditional_requests(
    tmp_path,
):
    source = _source(tmp_path)
    output = tmp_path / "pack"
    build_publication_pack(
        _manifest(),
        source,
        "https://lessons.owner.example",
        FINGERPRINT,
        output,
        provision="provisional",
    )
    calls = []

    class Response:
        def __init__(self, status, body, media_type, etag):
            self.status = status
            self._body = body
            self.headers = {
                "Content-Type": media_type,
                "Content-Length": str(len(body)),
                "ETag": etag,
            }

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *unused):
            return False

    deployment = json.loads((output / "deployment.json").read_text())
    public = output / "public"

    def opener(request, context=None):
        calls.append((request.full_url, dict(request.header_items())))
        path = request.full_url.removeprefix(
            "https://lessons.owner.example"
        )
        body = (public / path.lstrip("/")).read_bytes()
        media_type = deployment["media_types"][path]
        etag = '"' + __import__("hashlib").sha256(body).hexdigest() + '"'
        if request.get_header("If-none-match") == etag:
            return Response(304, b"", media_type, etag)
        return Response(200, body, media_type, etag)

    assert verify_deployed_publication(output, opener=opener) == []
    assert len(calls) == len(deployment["media_types"]) * 2


def test_rejects_missing_or_escaping_lesson_sources(tmp_path):
    source = _source(tmp_path)
    missing = _manifest()
    missing["lessons"][0]["source_path"] = "shared/missing.lessonpack"
    with pytest.raises(ValueError, match="lesson source"):
        build_publication_pack(
            missing,
            source,
            "https://lessons.owner.example",
            FINGERPRINT,
            tmp_path / "missing-pack",
            provision="provisional",
        )
    escaping = _manifest()
    escaping["lessons"][0]["source_path"] = "../outside.lessonpack"
    with pytest.raises(ValueError, match="within the source root"):
        build_publication_pack(
            escaping,
            source,
            "https://lessons.owner.example",
            FINGERPRINT,
            tmp_path / "escaping-pack",
            provision="provisional",
        )


def test_production_pack_rejects_non_public_origins_and_debug_signers(
    tmp_path,
):
    source = _source(tmp_path)
    with pytest.raises(ValueError, match="public DNS hostname"):
        build_publication_pack(
            _manifest(),
            source,
            "https://10.0.2.2:8443",
            FINGERPRINT,
            tmp_path / "pack",
            provision="production",
        )
    with pytest.raises(ValueError, match="release signing"):
        build_publication_pack(
            _manifest(),
            source,
            "https://lessons.owner.example",
            FINGERPRINT,
            tmp_path / "pack",
            provision="production",
            signer_kind="debug",
        )
    with pytest.raises(ValueError, match="explicit release signing"):
        build_publication_pack(
            _manifest(),
            source,
            "https://lessons.owner.example",
            FINGERPRINT,
            tmp_path / "pack",
            provision="production",
        )
