# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, Optional

from respect_compat.engine import execute
from respect_compat.executors import build_registry
from respect_compat.handoff import canonical_hash
from respect_compat.matrix_runtime import load_matrix
from respect_compat.target import CanAppTarget


def run_narrow_verifier(
    verifier_id: str,
    row_id: str,
    target: CanAppTarget,
    profile_id: str,
    predecessor_target_digest: Optional[str] = None,
) -> Dict[str, Any]:
    expected = f"matrix-row:{row_id}"
    if verifier_id != expected:
        raise ValueError(f"unknown verifier identifier: {verifier_id}")
    matrix = load_matrix()
    run = execute(
        matrix,
        target,
        profile_id,
        "test",
        build_registry(matrix),
        run_seed=f"narrow:{target.digest}:{profile_id}:{row_id}",
        selected_row_ids=[row_id],
    )
    result = run.results[0]
    fixture_diagnostic = (
        target.adapter == "fixture"
        and any(tool != "tier_0" for tool in matrix.rows[row_id].required_tooling)
    )
    verification_eligible = (
        result.state.value == "pass" and not fixture_diagnostic
    )
    if result.state.value != "pass":
        eligibility_reason = "the Matrix row did not pass"
    elif fixture_diagnostic:
        eligibility_reason = (
            "fixture evidence is diagnostic for a row that requires live or "
            "runtime observation"
        )
    else:
        eligibility_reason = (
            "the passing observation uses an evidence environment permitted "
            "for this narrow local check"
        )
    core = {
        "artifact_type": "respect_ification_narrow_verifier_result",
        "format_version": "2.0.0",
        "mode": "narrow_non_certifying",
        "certified": False,
        "matrix_semantic_hash": matrix.semantic_hash,
        "profile_id": profile_id,
        "target_digest": target.digest,
        "challenge": run.challenge,
        "predecessor_target_digest": predecessor_target_digest,
        "target_lineage": (
            "same_artifact"
            if predecessor_target_digest == target.digest
            else "owner_supplied_repaired_successor"
        ),
        "row_id": row_id,
        "verifier_id": verifier_id,
        "state": result.state.value,
        "verification_eligible": verification_eligible,
        "eligibility_reason": eligibility_reason,
        "result": result.to_json_dict(),
    }
    return {**core, "semantic_hash": canonical_hash(core)}
