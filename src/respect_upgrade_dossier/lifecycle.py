# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Normative Upgrade Dossier lifecycle."""

from enum import Enum
from typing import Any, Mapping, Optional


class DossierState(str, Enum):
    IDENTIFIED = "identified"
    TRIAGED = "triaged"
    ACCEPTED = "accepted"
    IN_IMPLEMENTATION = "in_implementation"
    CANDIDATE_READY = "candidate_ready"
    INDEPENDENTLY_VERIFIED = "independently_verified"
    CLOSED = "closed"
    SPECIFICATION_BLOCKED = "specification_blocked"
    DUPLICATE = "duplicate"
    SUPERSEDED = "superseded"
    REJECTED_WITH_EVIDENCE = "rejected_with_evidence"


LINEAR_TRANSITIONS = {
    DossierState.IDENTIFIED: DossierState.TRIAGED,
    DossierState.TRIAGED: DossierState.ACCEPTED,
    DossierState.ACCEPTED: DossierState.IN_IMPLEMENTATION,
    DossierState.IN_IMPLEMENTATION: DossierState.CANDIDATE_READY,
    DossierState.CANDIDATE_READY: DossierState.INDEPENDENTLY_VERIFIED,
}
SIDE_DISPOSITIONS = {
    DossierState.SPECIFICATION_BLOCKED,
    DossierState.DUPLICATE,
    DossierState.SUPERSEDED,
    DossierState.REJECTED_WITH_EVIDENCE,
}
TERMINAL_STATES = SIDE_DISPOSITIONS | {DossierState.CLOSED}


def closure_evidence_is_qualifying(
    evidence: Mapping[str, Any],
    dossier: Mapping[str, Any],
) -> bool:
    pinned = dossier.get("pinned_respect", {})
    tests = evidence.get("acceptance_tests")
    return bool(
        evidence.get("evidence_type") == "real_platform_acceptance"
        and evidence.get("independently_attributable") is True
        and evidence.get("trust_approved") is True
        and evidence.get("real_build_id") == pinned.get("real_build_id")
        and evidence.get("respect_revision") == pinned.get("respect_revision")
        and isinstance(tests, list)
        and tests
        and all(
            isinstance(test, Mapping) and test.get("result") == "pass"
            for test in tests
        )
    )


def transition(
    current: DossierState,
    requested: DossierState,
    *,
    dossier: Optional[Mapping[str, Any]] = None,
    closure_evidence: Optional[Mapping[str, Any]] = None,
) -> DossierState:
    if current in TERMINAL_STATES:
        raise ValueError(f"terminal Dossier state cannot transition: {current.value}")
    if requested in SIDE_DISPOSITIONS:
        return requested
    if requested == DossierState.CLOSED:
        if current != DossierState.INDEPENDENTLY_VERIFIED:
            raise ValueError("closure requires independently_verified state")
        if dossier is None or closure_evidence is None:
            raise ValueError("closure requires preserved acceptance evidence")
        if not closure_evidence_is_qualifying(closure_evidence, dossier):
            raise ValueError(
                "closure evidence must be trusted independently-attributable "
                "acceptance against the pinned real build"
            )
        return requested
    if LINEAR_TRANSITIONS.get(current) != requested:
        raise ValueError(
            f"non-normative Dossier transition: {current.value} -> "
            f"{requested.value}"
        )
    return requested
