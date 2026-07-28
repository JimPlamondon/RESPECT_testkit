# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .resources import resource

DEFAULT_PROFILE_NAME = "RESPECT Native Android Compatible v0.1"
DEFAULT_PROFILE_PATH = resource("data/profiles/compatibility_matrix_v0_1.json")


@dataclass(frozen=True)
class Profile:
    profile_id: str
    respect_code_commit: str
    generated_at: str
    requirements: List[Dict[str, Any]]

    def requirement(self, rule_id: str) -> Dict[str, Any]:
        for requirement in self.requirements:
            if requirement["id"] == rule_id:
                return requirement
        raise KeyError(rule_id)


def load_profile(profile_name: str, path: Path = DEFAULT_PROFILE_PATH) -> Profile:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("profile_id") != profile_name:
        raise ValueError(f"unknown profile: {profile_name}")
    return Profile(
        profile_id=data["profile_id"],
        respect_code_commit=data["respect_code_commit"],
        generated_at=data["generated_at"],
        requirements=data["requirements"],
    )
