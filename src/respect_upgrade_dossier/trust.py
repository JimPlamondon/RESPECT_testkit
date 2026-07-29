# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

"""Injected trust policy for Suite-issued platform-gap packets."""

import base64
from dataclasses import dataclass
from typing import Dict, Mapping, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class TrustPolicy(Protocol):
    def approve_platform_packet(self, packet: Mapping[str, object]) -> bool:
        """Return whether the packet is issued by an approved Suite key."""


@dataclass(frozen=True)
class FailClosedTrustPolicy:
    def approve_platform_packet(self, packet: Mapping[str, object]) -> bool:
        return False


@dataclass(frozen=True)
class Ed25519TrustPolicy:
    approved_keys: Dict[str, Ed25519PublicKey]

    def approve_platform_packet(self, packet: Mapping[str, object]) -> bool:
        issuance = packet.get("suite_issuance")
        if not isinstance(issuance, Mapping):
            return False
        if issuance.get("algorithm") != "Ed25519":
            return False
        key = self.approved_keys.get(str(issuance.get("key_id", "")))
        core_hash = packet.get("core_hash")
        signature = issuance.get("signature")
        if key is None or not isinstance(core_hash, str) or not isinstance(
            signature, str
        ):
            return False
        try:
            raw_signature = base64.b64decode(signature, validate=True)
            key.verify(raw_signature, core_hash.encode("ascii"))
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True
