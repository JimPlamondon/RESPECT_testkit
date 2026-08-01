# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from respect_compat.xapi_result import inspect_scaled_scores


def test_inspects_scaled_scores_without_canapp_grading_assumptions():
    scores, valid = inspect_scaled_scores(
        [
            {"result": {"score": {"scaled": -1}}},
            {"result": {"score": {"scaled": 0.25, "raw": 500}}},
            {"result": {"score": {"scaled": 1}}},
            {"result": {"completion": True}},
        ]
    )

    assert scores == [-1, 0.25, 1]
    assert valid is True


def test_rejects_absent_non_numeric_and_out_of_bounds_scaled_scores():
    assert inspect_scaled_scores([{"result": {"completion": True}}]) == (
        [],
        False,
    )
    assert inspect_scaled_scores(
        [{"result": {"score": {"scaled": "0.7"}}}]
    )[1] is False
    assert inspect_scaled_scores(
        [{"result": {"score": {"scaled": 1.01}}}]
    )[1] is False
    assert inspect_scaled_scores(
        [{"result": {"score": {"scaled": True}}}]
    )[1] is False
