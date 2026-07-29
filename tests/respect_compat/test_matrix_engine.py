# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from respect_compat.engine import ExecutorRegistry, execute
from respect_compat.cli import main
from respect_compat.executors import build_registry
from respect_compat.matrix_runtime import DEFAULT_MATRIX_PATH, load_matrix, semantic_hash
from respect_compat.models import RequirementOwner, ResultState
from respect_compat.report import (
    suite_json_payload,
    verify_suite_payload,
    write_suite_reports,
)
from respect_compat.resources import resource
from respect_compat.target import (
    CanAppTarget,
    HttpObservation,
    load_apk_target,
    load_fixture_target,
    load_url_target,
)


REFERENCE_FIXTURE = resource("data/fixtures/v1_0/positive/web_reference")


def target(document=None, digest="target-a"):
    return CanAppTarget(
        uri="https://canapp.invalid/descriptor.json",
        adapter="test",
        digest=digest,
        document=document or {"metadata": {}, "links": []},
        capabilities={"descriptor"},
    )


def passing_executor(context, row):
    evidence = [
        context.evidence(
            row,
            "test_observation",
            context.target.uri,
            {"target_digest": context.target.digest},
        )
    ]
    return context.result(row, ResultState.PASS, "observed", "passed", evidence)


def test_canonical_matrix_loads_and_selects_active_profiles():
    matrix = load_matrix()
    assert matrix.matrix_version == "1.0.0"
    assert len(matrix.features) == 45
    assert len(matrix.rows) == 87
    assert matrix.selected_rows("PROFILE-WEB")
    assert matrix.selected_rows("RESPECT Web and WebView active profile")
    assert matrix.selected_rows("PROFILE-NATIVE_ANDROID")


def test_stale_matrix_hash_is_rejected(tmp_path):
    data = json.loads(DEFAULT_MATRIX_PATH.read_text(encoding="utf-8"))
    data["matrix_version"] = "stale"
    stale = tmp_path / "matrix.json"
    stale.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="semantic hash mismatch"):
        load_matrix(stale)


def test_structurally_invalid_matrix_is_rejected_cleanly(tmp_path):
    data = json.loads(DEFAULT_MATRIX_PATH.read_text(encoding="utf-8"))
    data["profiles"] = {}
    data["semantic_hash"] = semantic_hash(data)
    invalid = tmp_path / "matrix.json"
    invalid.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="profiles must be an array"):
        load_matrix(invalid)


def test_missing_executors_prevent_certification():
    run = execute(
        load_matrix(),
        target(),
        "PROFILE-WEB",
        "certification",
        ExecutorRegistry(),
    )
    assert not run.verdict.certified
    assert run.coverage.selected == run.coverage.executed
    assert run.coverage.incomplete


def test_default_registry_covers_every_canonical_row():
    matrix = load_matrix()
    assert build_registry(matrix).row_ids == set(matrix.rows)


def test_current_descriptor_makes_legacy_manifest_rows_not_applicable():
    matrix = load_matrix()
    run = execute(
        matrix,
        target(
            {
                "metadata": {
                    "identifier": "urn:example:canapp",
                    "title": {"en": "CanApp"},
                },
                "links": [
                    {
                        "rel": "http://opds-spec.org/acquisition/open-access",
                        "href": "https://canapp.invalid/lesson",
                        "type": "text/html",
                    }
                ],
            }
        ),
        "PROFILE-WEB",
        "test",
        build_registry(matrix),
    )
    manifest_results = [
        result for result in run.results if result.row_id.startswith("MANIFEST-")
    ]
    assert manifest_results
    assert {result.state for result in manifest_results} == {
        ResultState.NOT_APPLICABLE
    }


def test_respect_owned_failure_does_not_fail_canapp_verdict():
    matrix = load_matrix()
    registry = ExecutorRegistry()

    def executor(context, row):
        state = (
            ResultState.FAIL
            if row.owner in {
                RequirementOwner.RESPECT_LAUNCHER.value,
                RequirementOwner.RESPECT_SERVICE.value,
            }
            else ResultState.PASS
        )
        evidence = [context.evidence(row, "test_observation", "test", state.value)]
        return context.result(row, state, state.value, "controlled result", evidence)

    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, executor)
    run = execute(matrix, target(), "PROFILE-WEB", "certification", registry)
    assert run.verdict.certified
    assert any(
        result.state == ResultState.FAIL
        and result.owner != RequirementOwner.CANAPP
        for result in run.results
    )


def test_target_substitution_invalidates_evidence():
    matrix = load_matrix()
    registry = ExecutorRegistry()

    def substituted(context, row):
        wrong_context = copy.copy(context)
        wrong_context.target = target(digest="different-target")
        evidence = [wrong_context.evidence(row, "test_observation", "test", "pass")]
        return context.result(row, ResultState.PASS, "pass", "substituted", evidence)

    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, substituted)
    run = execute(matrix, target(), "PROFILE-WEB", "certification", registry)
    assert not run.verdict.certified
    assert set(run.coverage.incomplete) == set(run.coverage.selected)


def test_live_runs_use_fresh_scenario_nonces():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    first = execute(matrix, target(), "PROFILE-WEB", "test", registry)
    second = execute(matrix, target(), "PROFILE-WEB", "test", registry)
    assert first.run_id != second.run_id
    assert first.scenario_nonce != second.scenario_nonce


def test_url_target_performs_real_http_request():
    descriptor = {
        "metadata": {"identifier": "urn:example:test", "title": "Test"},
        "links": [{"rel": "acquisition", "href": "/launch"}],
    }

    class Handler(BaseHTTPRequestHandler):
        requests = 0

        def do_GET(self):
            type(self).requests += 1
            body = json.dumps(descriptor).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/opds-publication+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/descriptor.json"
        loaded = load_url_target(url)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert Handler.requests == 1
    assert loaded.document == descriptor
    assert loaded.observations[0].status == 200


def test_apk_only_target_represents_an_absent_descriptor_without_invention(
    tmp_path,
):
    apk = tmp_path / "candidate.apk"
    apk.write_bytes(b"submitted apk bytes")

    loaded = load_apk_target(apk)

    assert loaded.adapter == "apk_only"
    assert loaded.document == {}
    assert loaded.metadata["descriptor_absent"] is True
    assert loaded.capabilities == {"apk", "native_android"}
    assert loaded.apk == apk.resolve()


def test_cli_apk_only_mode_writes_matrix_results(tmp_path):
    apk = tmp_path / "candidate.apk"
    apk.write_bytes(b"submitted apk bytes")
    output = tmp_path / "output"

    exit_code = main(
        [
            "--apk-only",
            "--apk",
            str(apk),
            "--profile",
            "PROFILE-SUITE_QUALITY",
            "--mode",
            "test",
            "--output-dir",
            str(output),
        ]
    )

    report = json.loads((output / "respect-report.json").read_text())
    assert exit_code == 0
    assert report["target_adapter"] == "apk_only"
    assert report["target_uri"].startswith("android-apk://submitted/")
    assert report["coverage"]["selected"] == report["coverage"]["executed"]


def test_cli_url_mode_executes_and_writes_verified_report(tmp_path):
    descriptor = {
        "metadata": {"identifier": "urn:example:cli", "title": "CLI"},
        "links": [
            {
                "rel": "http://opds-spec.org/acquisition/open-access",
                "href": "/lesson",
                "type": "text/html",
            }
        ],
    }

    class Handler(BaseHTTPRequestHandler):
        requests = 0

        def do_GET(self):
            type(self).requests += 1
            body = json.dumps(descriptor).encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "application/opds-publication+json",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/descriptor.json"
        exit_code = main(
            [
                "--manifest-url",
                url,
                "--profile",
                "PROFILE-SUITE_QUALITY",
                "--mode",
                "test",
                "--output-dir",
                str(tmp_path),
            ]
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    report = json.loads((tmp_path / "respect-report.json").read_text())
    assert exit_code == 0
    assert Handler.requests == 1
    assert report["target_uri"] == url
    assert report["target_adapter"] == "manifest_url"
    assert report["independent_verification"]["passed"]


def test_real_http_target_executes_descriptor_opds_and_http_rows():
    publication = {
        "metadata": {
            "identifier": "urn:example:http",
            "title": {"en": "HTTP CanApp"},
        },
        "links": [
            {
                "rel": ["http://opds-spec.org/acquisition/open-access"],
                "href": "/lesson",
                "type": "text/html",
            }
        ],
        "images": [{"href": "/icon.png", "type": "image/png"}],
        "resources": [{"href": "/lesson.js", "type": "text/javascript"}],
    }
    descriptor = copy.deepcopy(publication)
    descriptor["links"].append(
        {
            "rel": [
                "https://respect.ustadmobile.com/ns/default-lesson-catalog"
            ],
            "href": "/catalog",
            "type": "application/opds+json",
        }
    )
    descriptor["unknownFixtureProperty"] = True
    catalog = {
        "metadata": {"title": "HTTP catalog"},
        "links": [
            {
                "rel": ["self"],
                "href": "/catalog",
                "type": "application/opds+json",
            }
        ],
        "publications": [publication],
    }
    webpub = {
        "metadata": {
            "identifier": "urn:example:http:webpub",
            "title": "HTTP publication",
        },
        "readingOrder": [{"href": "/lesson", "type": "text/html"}],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("If-None-Match") == '"controlled"':
                self.send_response(304)
                self.send_header("ETag", '"controlled"')
                self.end_headers()
                return
            if self.path == "/descriptor":
                body = json.dumps(descriptor).encode()
                content_type = "application/opds-publication+json"
            elif self.path == "/catalog":
                body = json.dumps(catalog).encode()
                content_type = "application/opds+json"
            elif self.path == "/lesson":
                body = (
                    b'<link rel="publication" type="application/webpub+json" '
                    b'href="/publication">'
                )
                content_type = "text/html"
            elif self.path == "/publication":
                body = json.dumps(webpub).encode()
                content_type = "application/webpub+json"
            elif self.path == "/icon.png":
                body = b"image"
                content_type = "image/png"
            elif self.path == "/lesson.js":
                body = b"globalThis.reference = true;"
                content_type = "text/javascript"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("ETag", '"controlled"')
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/descriptor"
        matrix = load_matrix()
        run = execute(
            matrix,
            load_url_target(url),
            "PROFILE-WEB",
            "test",
            build_registry(matrix),
            run_seed="real-http-static",
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    required = {
        *(f"DESC-{number:03d}" for number in range(1, 6)),
        *(f"HTTP-{number:03d}" for number in range(1, 6)),
        *(f"OPDS-{number:03d}" for number in range(1, 12)),
    }
    states = {result.row_id: result.state for result in run.results}
    assert {
        row_id: states[row_id]
        for row_id in required
        if states[row_id] != ResultState.PASS
    } == {}


def test_opds_005_does_not_vacuously_pass_without_an_acquisition_link():
    matrix = load_matrix()
    canapp = target(
        {
            "metadata": {
                "identifier": "https://canapp.example/app",
                "title": "Example",
            },
            "links": [],
        }
    )

    run = execute(
        matrix,
        canapp,
        "PROFILE-WEB",
        "test",
        build_registry(matrix),
        run_seed="no-acquisition",
        selected_row_ids=["OPDS-005"],
    )

    assert run.results[0].state == ResultState.NOT_APPLICABLE


def test_opds_009_requires_one_real_visit_for_a_repeated_url():
    resource_url = "https://canapp.example/lesson"
    document = {
        "metadata": {"title": "Catalog"},
        "publications": [
            {
                "metadata": {
                    "identifier": "https://canapp.example/lesson",
                    "title": "Lesson",
                },
                "links": [
                    {"href": resource_url, "type": "text/html"},
                    {"href": resource_url, "type": "text/html"},
                ],
            }
        ],
    }
    matrix = load_matrix()
    canapp = target(document)

    missing = execute(
        matrix,
        canapp,
        "PROFILE-WEB",
        "test",
        build_registry(matrix),
        run_seed="repeat-missing",
        selected_row_ids=["OPDS-009"],
    )

    assert missing.results[0].state != ResultState.PASS

    canapp.observations.append(
        HttpObservation(
            requested_url=resource_url,
            final_url=resource_url,
            status=200,
            headers={"content-type": "text/html"},
            body=b"lesson",
        )
    )
    observed = execute(
        matrix,
        canapp,
        "PROFILE-WEB",
        "test",
        build_registry(matrix),
        run_seed="repeat-observed",
        selected_row_ids=["OPDS-009"],
    )

    assert observed.results[0].state == ResultState.PASS
    assert observed.results[0].observed[resource_url] == 1


def test_opds_010_rejects_an_unsupported_catalog_media_type():
    matrix = load_matrix()
    document = {
        "metadata": {
            "identifier": "https://canapp.example/app",
            "title": "Example",
        },
        "links": [
            {
                "rel": [
                    "https://respect.ustadmobile.com/ns/default-lesson-catalog"
                ],
                "href": "catalog.bin",
                "type": "application/x-invented-catalog",
            }
        ],
    }

    run = execute(
        matrix,
        target(document),
        "PROFILE-WEB",
        "test",
        build_registry(matrix),
        run_seed="unsupported-catalog-type",
        selected_row_ids=["OPDS-010"],
    )

    assert run.results[0].state == ResultState.FAIL


def test_opds_011_requires_the_resolved_relative_resource_to_be_reached(
    tmp_path,
):
    matrix = load_matrix()
    document = {
        "metadata": {"title": "Catalog"},
        "publications": [
            {
                "metadata": {
                    "identifier": "https://canapp.example/lesson",
                    "title": "Lesson",
                },
                "links": [{"href": "missing.lesson", "type": "text/html"}],
            }
        ],
    }
    canapp = target(document)
    canapp.source_root = tmp_path

    missing = execute(
        matrix,
        canapp,
        "PROFILE-WEB",
        "test",
        build_registry(matrix),
        run_seed="relative-missing",
        selected_row_ids=["OPDS-011"],
    )

    assert missing.results[0].state == ResultState.FAIL

    (tmp_path / "missing.lesson").write_text("real lesson")
    reached = execute(
        matrix,
        canapp,
        "PROFILE-WEB",
        "test",
        build_registry(matrix),
        run_seed="relative-reached",
        selected_row_ids=["OPDS-011"],
    )

    assert reached.results[0].state == ResultState.PASS
    assert reached.results[0].observed[0]["status"] == 200


def test_independent_report_verifier_rejects_tampered_verdict():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, passing_executor)
    run = execute(matrix, target(), "PROFILE-WEB", "certification", registry)
    payload = suite_json_payload(run)
    payload["verdict"]["certified"] = False
    payload["verdict"]["state"] = "not_certified"
    assert verify_suite_payload(payload)


def test_emulator_preserves_row_passes_and_yields_named_provisional_approval():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    selected = matrix.selected_rows("PROFILE-NATIVE_ANDROID")
    for row in selected:
        registry.register(row.row_id, passing_executor)
    canapp = target()
    canapp.metadata["device_probe"] = {
        "device_id": "emulator-5554",
        "healthy": True,
        "emulator": True,
    }
    canapp.capabilities.add("controlled_android_runtime")

    run = execute(
        matrix,
        canapp,
        "PROFILE-NATIVE_ANDROID",
        "certification",
        registry,
    )

    assert all(result.state == ResultState.PASS for result in run.results)
    assert not run.verdict.certified
    assert run.verdict.state == "provisional"
    assert run.verdict.display == "Provisional (emulated Android runtime)"
    provision = run.verdict.provisions[0]
    assert provision.code == "EMULATED_ANDROID_RUNTIME"
    assert provision.affected_rows == sorted(
        row.row_id for row in selected if "tier_1_device" in row.required_tooling
    )


def test_local_https_preserves_row_passes_and_yields_named_provisional_approval(
    tmp_path,
):
    matrix = load_matrix()
    registry = ExecutorRegistry()
    selected = matrix.selected_rows("PROFILE-WEB")
    for row in selected:
        registry.register(row.row_id, passing_executor)
    canapp = target()
    canapp.uri = "https://127.0.0.1:8443/descriptor.json"

    run = execute(matrix, canapp, "PROFILE-WEB", "certification", registry)

    assert all(result.state == ResultState.PASS for result in run.results)
    assert not run.verdict.certified
    assert run.verdict.state == "provisional"
    assert run.verdict.display == "Provisional (local HTTPS publication)"
    assert [item.code for item in run.verdict.provisions] == [
        "LOCAL_HTTPS_PUBLICATION"
    ]
    write_suite_reports(run, tmp_path)
    report = json.loads((tmp_path / "respect-report.json").read_text())
    assert report["verdict"]["display"] == (
        "Provisional (local HTTPS publication)"
    )
    assert report["independent_verification"]["passed"] is True
    text_report = (tmp_path / "respect-report.txt").read_text()
    assert "Approval: Provisional (local HTTPS publication)" in text_report
    assert "Provision LOCAL_HTTPS_PUBLICATION:" in text_report


def test_multiple_provisional_reasons_are_retained_and_displayed_together():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    for row in matrix.selected_rows("PROFILE-NATIVE_ANDROID"):
        registry.register(row.row_id, passing_executor)
    canapp = target()
    canapp.uri = "https://localhost:8443/descriptor.json"
    canapp.metadata["device_probe"] = {
        "device_id": "emulator-5554",
        "healthy": True,
        "emulator": True,
    }

    run = execute(
        matrix,
        canapp,
        "PROFILE-NATIVE_ANDROID",
        "certification",
        registry,
    )

    assert run.verdict.display == (
        "Provisional (emulated Android runtime; local HTTPS publication)"
    )
    assert [item.code for item in run.verdict.provisions] == [
        "EMULATED_ANDROID_RUNTIME",
        "LOCAL_HTTPS_PUBLICATION",
    ]


def test_independent_report_verifier_rejects_tampered_provisions():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, passing_executor)
    canapp = target()
    canapp.uri = "https://localhost:8443/descriptor.json"
    run = execute(matrix, canapp, "PROFILE-WEB", "certification", registry)
    payload = suite_json_payload(run)
    payload["verdict"]["provisions"] = []
    assert any(
        "serialized verdict provisions" in error
        for error in verify_suite_payload(payload)
    )


def test_independent_report_verifier_rejects_tampered_owner():
    matrix = load_matrix()
    registry = ExecutorRegistry()
    for row in matrix.selected_rows("PROFILE-WEB"):
        registry.register(row.row_id, passing_executor)
    run = execute(matrix, target(), "PROFILE-WEB", "certification", registry)
    payload = suite_json_payload(run)
    canapp = next(
        item for item in payload["results"] if item["owner"] == "canapp"
    )
    canapp["owner"] = "respect_service"
    assert any("owner does not match" in error for error in verify_suite_payload(payload))


def test_reference_web_fixture_is_provisional_despite_passing_canapp_rows():
    fixture = REFERENCE_FIXTURE
    matrix = load_matrix()
    run = execute(
        matrix,
        load_fixture_target(fixture),
        "PROFILE-WEB",
        "certification",
        build_registry(matrix),
    )
    assert not run.verdict.certified
    assert run.verdict.state == "provisional"
    assert run.verdict.display == (
        "Provisional (immutable certified-build URL missing; "
        "publication authorization missing; "
        "Spix certification trust anchor missing; "
        "suite fixture evidence)"
    )
    assert [item.code for item in run.verdict.provisions] == [
        "IMMUTABLE_CERTIFIED_BUILD_URL_MISSING",
        "PUBLICATION_AUTHORIZATION_MISSING",
        "SPIX_CERTIFICATION_TRUST_ANCHOR_MISSING",
        "SUITE_FIXTURE_EVIDENCE"
    ]
    assert not [
        result
        for result in run.results
        if result.owner == RequirementOwner.CANAPP
        and result.state not in {ResultState.PASS, ResultState.NOT_APPLICABLE}
    ]
    assert run.coverage.blocked
    assert run.actor_health


def test_reference_single_fault_identity_mutation_fails_only_desc_002(tmp_path):
    source = REFERENCE_FIXTURE
    fixture = tmp_path / "identity-missing"
    shutil.copytree(source, fixture)
    descriptor_path = fixture / "descriptor.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    del descriptor["metadata"]["identifier"]
    descriptor_path.write_text(
        json.dumps(descriptor, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    matrix = load_matrix()
    run = execute(
        matrix,
        load_fixture_target(fixture),
        "PROFILE-WEB",
        "certification",
        build_registry(matrix),
    )
    failures = [
        result.row_id
        for result in run.results
        if result.owner == RequirementOwner.CANAPP
        and result.state == ResultState.FAIL
    ]
    assert failures == ["DESC-002"]
    assert not run.verdict.certified


def test_fixture_digest_binds_controlled_metadata(tmp_path):
    source = REFERENCE_FIXTURE
    fixture = tmp_path / "fixture"
    shutil.copytree(source, fixture)
    before = load_fixture_target(fixture).digest
    metadata_path = fixture / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["row_observations"]["AUTH-001"]["observed"] = "changed"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    changed_target = load_fixture_target(fixture)
    assert changed_target.digest != before
    assert "_trusted_reference" in changed_target.metadata
    assert not changed_target.metadata["_trusted_reference"]
    matrix = load_matrix()
    run = execute(
        matrix,
        changed_target,
        "PROFILE-WEB",
        "certification",
        build_registry(matrix),
    )
    assert not run.verdict.certified
    assert next(
        result for result in run.results if result.row_id == "AUTH-001"
    ).state == ResultState.BLOCKED
