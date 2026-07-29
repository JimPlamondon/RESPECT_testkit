# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List
from xml.etree.ElementTree import Element, ElementTree, SubElement

from .matrix_runtime import load_matrix
from .models import RequirementOwner, ResultState, RuleResult, SuiteRun
from .handoff import build_handoff, write_handoff
from .provisions import (
    classify_publication_environment,
    derive_provisions,
    provisional_display,
)


def ordered_results(results: Iterable[RuleResult]) -> List[RuleResult]:
    return sorted(results, key=lambda result: (result.rule_id, result.source_uri, result.message))


def json_payload(results: Iterable[RuleResult]) -> dict:
    ordered = ordered_results(results)
    return {
        "profile": ordered[0].profile if ordered else None,
        "target": ordered[0].target if ordered else None,
        "security_mode": ordered[0].security_mode if ordered else None,
        "results": [result.to_json_dict() for result in ordered],
    }


def write_reports(results: Iterable[RuleResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = ordered_results(results)
    (output_dir / "respect-report.json").write_text(
        json.dumps(json_payload(ordered), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "RESPECT Compatible Test Suite v0.1 report",
        f"Profile: {ordered[0].profile if ordered else 'unknown'}",
        f"Target: {ordered[0].target if ordered else 'unknown'}",
        f"Security mode: {ordered[0].security_mode if ordered else 'unknown'}",
        "",
    ]
    for result in ordered:
        lines.append(f"{result.rule_id} {result.result.value}: {result.message}")
    (output_dir / "respect-report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    testsuite = Element("testsuite", name="respect_compat", tests=str(len(ordered)))
    for result in ordered:
        case = SubElement(testsuite, "testcase", classname="respect_compat", name=result.rule_id)
        if result.result == ResultState.FAIL:
            failure = SubElement(case, "failure", message=result.message)
            failure.text = json.dumps(result.to_json_dict(), sort_keys=True)
        elif result.result in {ResultState.WARNING, ResultState.INCOMPLETE, ResultState.DEFERRED}:
            skipped = SubElement(case, "skipped", message=result.message)
            skipped.text = result.result.value
    ElementTree(testsuite).write(output_dir / "junit.xml", encoding="utf-8", xml_declaration=True)


def suite_json_payload(run: SuiteRun) -> Dict[str, Any]:
    payload = run.to_json_dict()
    payload["sections"] = {
        "canapp_conformance": [
            result.to_json_dict()
            for result in run.results
            if result.owner == RequirementOwner.CANAPP
        ],
        "publication_prerequisites": [
            result.to_json_dict()
            for result in run.results
            if result.owner
            in {
                RequirementOwner.PUBLISHER,
                RequirementOwner.SPIX_FOUNDATION,
            }
        ],
        "respect_environment": [
            result.to_json_dict()
            for result in run.results
            if result.owner
            in {RequirementOwner.RESPECT_LAUNCHER, RequirementOwner.RESPECT_SERVICE}
        ],
        "suite_assurance": [
            result.to_json_dict()
            for result in run.results
            if result.owner == RequirementOwner.TEST_SUITE
        ],
    }
    return payload


def recompute_serialized_verdict(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("mode") != "certification":
        return {
            "certified": False,
            "state": "non_certification_mode",
            "display": "Non-certification mode",
            "reason": f"mode {payload.get('mode')} cannot certify",
            "provisions": [],
        }
    coverage = payload.get("coverage", {})
    selected = coverage.get("selected", [])
    results = payload.get("results", [])
    result_ids = [item.get("row_id") for item in results]
    if len(selected) != len(set(selected)) or len(result_ids) != len(set(result_ids)):
        return {
            "certified": False,
            "state": "harness_error",
            "display": "Harness error",
            "reason": "duplicate selected or result row identifier",
            "provisions": [],
        }
    if set(selected) != set(result_ids):
        return {
            "certified": False,
            "state": "incomplete",
            "display": "Incomplete",
            "reason": "serialized selected and executed row sets differ",
            "provisions": [],
        }
    try:
        matrix = load_matrix()
    except Exception as error:
        return {
            "certified": False,
            "state": "harness_error",
            "display": "Harness error",
            "reason": f"canonical Matrix could not be loaded: {type(error).__name__}",
            "provisions": [],
        }
    if payload.get("matrix_semantic_hash") != matrix.semantic_hash:
        return {
            "certified": False,
            "state": "harness_error",
            "display": "Harness error",
            "reason": "report Matrix hash does not match canonical Matrix",
            "provisions": [],
        }
    provisions = derive_provisions(
        [matrix.rows[row_id] for row_id in selected if row_id in matrix.rows],
        payload.get("evidence_environment", {}),
    )
    serialized_provisions = [
        provision.to_json_dict() for provision in provisions
    ]
    canapp = [
        item
        for item in results
        if item.get("row_id") in matrix.rows
        and matrix.rows[item["row_id"]].owner == RequirementOwner.CANAPP.value
    ]
    nonpass = [
        item
        for item in canapp
        if item.get("state")
        not in {ResultState.PASS.value, ResultState.NOT_APPLICABLE.value}
    ]
    if not canapp:
        return {
            "certified": False,
            "state": "incomplete",
            "display": "Incomplete",
            "reason": "profile selected no CanApp-owned rows",
            "provisions": serialized_provisions,
        }
    if nonpass:
        return {
            "certified": False,
            "state": "not_certified",
            "display": "Not certified",
            "reason": "applicable CanApp rows did not pass: "
            + ", ".join(
                f"{item.get('row_id')}={item.get('state')}" for item in nonpass
            ),
            "provisions": serialized_provisions,
        }
    if provisions:
        return {
            "certified": False,
            "state": "provisional",
            "display": provisional_display(provisions),
            "reason": (
                "all applicable CanApp-owned rows passed; "
                f"{len(provisions)} certification provision(s) remain"
            ),
            "provisions": serialized_provisions,
        }
    return {
        "certified": True,
        "state": "certified",
        "display": "Certified",
        "reason": "all applicable CanApp-owned rows passed",
        "provisions": [],
    }


def verify_suite_payload(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    environment = payload.get("evidence_environment", {})
    publication = (
        environment.get("publication", {})
        if isinstance(environment, dict)
        else {}
    )
    expected_publication = classify_publication_environment(
        str(payload.get("target_uri", "")),
        str(payload.get("target_adapter", "")),
    )
    if publication != expected_publication:
        errors.append(
            "evidence environment publication classification does not match target"
        )
    runtime = (
        environment.get("android_runtime", {})
        if isinstance(environment, dict)
        else {}
    )
    runtime_kind = runtime.get("kind")
    runtime_probe = runtime.get("probe", {})
    if runtime_kind == "emulator" and runtime_probe.get("emulator") is not True:
        errors.append("emulator evidence environment lacks a matching device probe")
    if (
        runtime_kind == "physical_device"
        and runtime_probe.get("emulator") is not False
    ):
        errors.append(
            "physical-device evidence environment lacks a matching device probe"
        )
    try:
        matrix = load_matrix()
        profile = matrix.resolve_profile(str(payload.get("profile_id")))
        expected_selected = sorted(
            row.row_id for row in matrix.selected_rows(profile.profile_id)
        )
        if payload.get("matrix_id") != matrix.matrix_id:
            errors.append("report Matrix identifier does not match canonical Matrix")
        if payload.get("matrix_version") != matrix.matrix_version:
            errors.append("report Matrix version does not match canonical Matrix")
        if payload.get("matrix_semantic_hash") != matrix.semantic_hash:
            errors.append("report Matrix hash does not match canonical Matrix")
        if sorted(payload.get("coverage", {}).get("selected", [])) != expected_selected:
            errors.append("selected rows do not match the canonical profile")
        for item in payload.get("results", []):
            row_id = item.get("row_id")
            row = matrix.rows.get(row_id)
            if row is None:
                errors.append(f"unknown canonical Matrix row {row_id}")
                continue
            if item.get("owner") != row.owner:
                errors.append(f"row {row_id} owner does not match canonical Matrix")
            if item.get("feature_id") != row.feature_id:
                errors.append(
                    f"row {row_id} feature does not match canonical Matrix"
                )
            if item.get("test_case_ids") != row.test_case_ids:
                errors.append(
                    f"row {row_id} test-case identifiers do not match canonical Matrix"
                )
    except Exception as error:
        errors.append(
            f"canonical Matrix verification failed: {type(error).__name__}: {error}"
        )
    recomputed = recompute_serialized_verdict(payload)
    serialized = payload.get("verdict", {})
    for field in ("certified", "state", "display", "reason", "provisions"):
        if serialized.get(field) != recomputed.get(field):
            errors.append(
                f"serialized verdict {field}={serialized.get(field)!r} "
                f"does not match recomputed {recomputed.get(field)!r}"
            )
    coverage = payload.get("coverage", {})
    by_state = {
        state.value: sorted(
            item["row_id"]
            for item in payload.get("results", [])
            if item.get("state") == state.value
        )
        for state in ResultState
    }
    coverage_fields = {
        ResultState.PASS.value: "passed",
        ResultState.FAIL.value: "failed",
        ResultState.NOT_APPLICABLE.value: "not_applicable",
        ResultState.INCOMPLETE.value: "incomplete",
        ResultState.DEFERRED.value: "deferred",
        ResultState.HARNESS_ERROR.value: "harness_error",
        ResultState.BLOCKED.value: "blocked",
    }
    for state, field in coverage_fields.items():
        if sorted(coverage.get(field, [])) != by_state[state]:
            errors.append(f"coverage field {field} does not match row results")
    for item in payload.get("results", []):
        if not item.get("evidence"):
            errors.append(f"row {item.get('row_id')} has no evidence")
        for evidence in item.get("evidence", []):
            if evidence.get("target_digest") != payload.get("target_digest"):
                errors.append(
                    f"row {item.get('row_id')} evidence is not bound to target"
                )
            if evidence.get("scenario_nonce") != payload.get("scenario_nonce"):
                errors.append(
                    f"row {item.get('row_id')} evidence is not bound to scenario"
                )
    return sorted(set(errors))


def write_suite_reports(run: SuiteRun, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload, evidence_manifest, task_packet = build_handoff(run)
    verification_errors = payload["independent_verification"]["errors"]
    write_handoff(payload, evidence_manifest, task_packet, output_dir)
    lines = [
        f"RESPECT Compatible Test Suite {run.suite_version} report",
        f"Matrix: {run.matrix_id} {run.matrix_version} {run.matrix_semantic_hash}",
        f"Profile: {run.profile_id}",
        f"Target: {run.target_uri}",
        f"Target digest: {run.target_digest}",
        f"Adapter: {run.target_adapter}",
        f"Approval: {run.verdict.display}",
        f"Independent verification: {'pass' if not verification_errors else 'fail'}",
        "",
    ]
    for provision in run.verdict.provisions:
        lines.extend(
            [
                f"Provision {provision.code}: {provision.explanation}",
                f"  Affected rows: {', '.join(provision.affected_rows) or 'none'}",
                f"  To clear: {provision.clearance}",
            ]
        )
    if run.verdict.provisions:
        lines.append("")
    for result in sorted(run.results, key=lambda item: item.row_id):
        lines.append(
            f"{result.row_id} [{result.owner.value}] {result.state.value}: "
            f"{result.message}"
        )
        if result.repair_guidance:
            lines.append(f"  RESPECT-ification guidance: {result.repair_guidance}")
    (output_dir / "respect-report.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    testsuite = Element(
        "testsuite",
        name="respect_compatible",
        tests=str(len(run.results)),
        failures=str(sum(result.state == ResultState.FAIL for result in run.results)),
    )
    for result in sorted(run.results, key=lambda item: item.row_id):
        case = SubElement(
            testsuite,
            "testcase",
            classname=f"respect_compatible.{result.owner.value}",
            name=result.row_id,
        )
        if result.state == ResultState.FAIL:
            failure = SubElement(case, "failure", message=result.message)
            failure.text = json.dumps(result.to_json_dict(), sort_keys=True)
        elif result.state != ResultState.PASS:
            skipped = SubElement(case, "skipped", message=result.message)
            skipped.text = result.state.value
    ElementTree(testsuite).write(
        output_dir / "junit.xml",
        encoding="utf-8",
        xml_declaration=True,
    )
