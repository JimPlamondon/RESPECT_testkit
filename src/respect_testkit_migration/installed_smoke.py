#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from respect_compat.cli import main as suite_main
from respect_compat.matrix_runtime import load_matrix
from respect_compat.resources import resource, resource_path
from respect_ification.cli import main as kit_main


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--forbid-root", type=Path, action="append", default=[])
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    forbidden_roots = tuple(path.resolve() for path in args.forbid_root)
    for value in sys.path:
        if not value:
            continue
        resolved = Path(value).resolve()
        if any(resolved == root or root in resolved.parents for root in forbidden_roots):
            raise RuntimeError(f"checkout appears on sys.path: {resolved}")
    matrix = load_matrix()
    if (
        matrix.matrix_id != "respect-compatibility-matrix-v0.1"
        or matrix.matrix_version != "1.0.0"
        or matrix.semantic_hash != "5a059124de6875ad8fa2e23c7244343f70eab6033ad26fbefeb46407d20421ee"
        or len(matrix.features) != 45
        or len(matrix.rows) != 87
    ):
        raise RuntimeError("installed Matrix identity drift")
    with resource_path("data/fixtures/v1_0/positive/web_reference") as positive:
        positive_output = run_dir / "positive"
        positive_exit = suite_main(
            [
                "--fixture-dir",
                str(positive),
                "--profile",
                "PROFILE-WEB",
                "--mode",
                "certification",
                "--output-dir",
                str(positive_output),
            ]
        )
        if positive_exit != 2:
            raise RuntimeError(f"positive reference exit {positive_exit}")
        handback_output = run_dir / "handback"
        handback_exit = kit_main(
            [
                "full-test",
                "--fixture-dir",
                str(positive),
                "--profile",
                "PROFILE-WEB",
                "--output-dir",
                str(handback_output),
            ]
        )
        if handback_exit != positive_exit:
            raise RuntimeError("full Test Suite handback changed the exit code")
        positive_resource = str(positive.resolve())
    with resource_path("data/fixtures/v0_1/negative/invalid_license") as negative:
        negative_output = run_dir / "negative"
        negative_exit = suite_main(
            [
                "--fixture-dir",
                str(negative),
                "--profile",
                "PROFILE-WEB",
                "--mode",
                "certification",
                "--output-dir",
                str(negative_output),
            ]
        )
        if negative_exit != 1:
            raise RuntimeError(f"negative reference exit {negative_exit}")
    work_plan = run_dir / "work-plan.json"
    plan_exit = kit_main(
        [
            "plan",
            "--report",
            str(negative_output / "respect-report.json"),
            "--evidence-manifest",
            str(negative_output / "respect-evidence-manifest.json"),
            "--task-packet",
            str(negative_output / "respect-ification-task-packet.json"),
            "--output",
            str(work_plan),
        ]
    )
    if plan_exit != 0:
        raise RuntimeError(f"Kit plan exit {plan_exit}")
    plan = json.loads(work_plan.read_text(encoding="utf-8"))
    synthetic_source = run_dir / "synthetic-canapp"
    synthetic_source.mkdir()
    (synthetic_source / "main.py").write_text("print('synthetic')\n", encoding="utf-8")
    public_prep = run_dir / "public-prep.json"
    private_prep = run_dir / "private-prep.json"
    prep_exit = kit_main(
        [
            "prepare",
            "--source-root",
            str(synthetic_source),
            "--target-digest",
            plan["target_digest"],
            "--profile",
            plan["profile_id"],
            "--public-output",
            str(public_prep),
            "--private-output",
            str(private_prep),
        ]
    )
    if prep_exit != 0:
        raise RuntimeError(f"Prep exit {prep_exit}")
    public_data = public_prep.read_text(encoding="utf-8")
    if "source_inventory" in public_data or "main.py" in public_data:
        raise RuntimeError("public Prep leaked private source inventory")
    task = plan["tasks"][0]
    narrow_output = run_dir / "narrow.json"
    with resource_path("data/fixtures/v1_0/positive/web_reference") as positive:
        narrow_exit = kit_main(
            [
                "verify",
                "--work-plan",
                str(work_plan),
                "--task-id",
                task["task_id"],
                "--fixture-dir",
                str(positive),
                "--output",
                str(narrow_output),
            ]
        )
    if narrow_exit not in {0, 2}:
        raise RuntimeError(f"narrow verifier exit {narrow_exit}")
    narrow = json.loads(narrow_output.read_text(encoding="utf-8"))
    if narrow["mode"] != "narrow_non_certifying" or narrow["certified"] is not False:
        raise RuntimeError("narrow verifier claimed certification")
    emitted = [
        path
        for path in run_dir.rglob("*")
        if path.is_file()
    ]
    for path in emitted:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for forbidden_root in forbidden_roots:
            if str(forbidden_root) in text:
                raise RuntimeError(f"operational artifact contains checkout path: {path}")
    summary = {
        "handback_exit": handback_exit,
        "matrix_resource": str(resource("data/matrix/compatibility_matrix.json")),
        "narrow_exit": narrow_exit,
        "positive_artifacts": {
            path.name: file_hash(path)
            for path in sorted(positive_output.iterdir())
            if path.is_file()
        },
        "positive_exit": positive_exit,
        "positive_resource": positive_resource,
        "tasks": len(plan["tasks"]),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
