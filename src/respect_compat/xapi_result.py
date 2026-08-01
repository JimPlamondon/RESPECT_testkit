# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Generic xAPI result inspection independent of any Candidate App policy."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Tuple


XAPI_SCALED_SCORE_MIN = -1
XAPI_SCALED_SCORE_MAX = 1


def inspect_scaled_scores(
    statements: Iterable[Mapping[str, Any]],
) -> Tuple[List[Any], bool]:
    """Return captured scaled scores and whether all satisfy xAPI bounds.

    The function deliberately knows nothing about a Candidate App's raw score
    range, mastery threshold, lesson format, or aggregation policy.
    """

    scores = []
    for statement in statements:
        result = statement.get("result")
        if not isinstance(result, Mapping):
            continue
        score = result.get("score")
        if not isinstance(score, Mapping) or "scaled" not in score:
            continue
        scores.append(score["scaled"])

    valid = bool(scores) and all(
        type(value) in {int, float}
        and XAPI_SCALED_SCORE_MIN <= value <= XAPI_SCALED_SCORE_MAX
        for value in scores
    )
    return scores, valid
