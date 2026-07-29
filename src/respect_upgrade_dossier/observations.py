# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Typed environment-observation provider boundary."""

from typing import Any, Dict, List, Protocol


class EnvironmentObservationProvider(Protocol):
    provider_id: str

    def observe(self) -> List[Dict[str, Any]]:
        """Return independently attributable observations, or an empty list."""


def collect_environment_observations(
    provider: EnvironmentObservationProvider,
) -> Dict[str, Any]:
    observations = provider.observe()
    if not isinstance(observations, list):
        raise TypeError("observation provider must return a list")
    for observation in observations:
        required = {
            "observation_id",
            "row_id",
            "real_build_id",
            "respect_revision",
            "independently_attributable",
            "signed",
        }
        if not isinstance(observation, dict) or not required.issubset(observation):
            raise ValueError("environment observation is incomplete")
    return {
        "artifact_type": "respect_environment_observations",
        "format_version": "2.0.0",
        "provider_id": provider.provider_id,
        "observations": observations,
    }
