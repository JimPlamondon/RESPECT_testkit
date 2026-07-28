# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass


ALLOWED_MODES = frozenset({"certification", "test", "replay"})


def validate_mode(mode: str) -> str:
    if mode not in ALLOWED_MODES:
        raise ValueError(f"security mode must be one of {sorted(ALLOWED_MODES)}")
    return mode


@dataclass(frozen=True)
class SecurityContext:
    mode: str

    def __post_init__(self) -> None:
        validate_mode(self.mode)
