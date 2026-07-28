# SPDX-FileCopyrightText: 2026 Jim Plamondon
# SPDX-License-Identifier: Apache-2.0

import hashlib
import urllib.parse
from dataclasses import dataclass
from typing import Dict

from .security_labels import SecurityContext


@dataclass(frozen=True)
class LaunchSession:
    session_id: str
    mode: str
    launch_url: str
    endpoint_base: str


def build_launch_session(manifest: Dict[str, object], seed: str, endpoint_base: str, context: SecurityContext) -> LaunchSession:
    version = manifest.get("respectLaunchVersion")
    if not version:
        raise ValueError("missing respectLaunchVersion")
    launch_uri = str(manifest.get("defaultLaunchUri", ""))
    if not endpoint_base:
        raise ValueError("missing endpoint base")
    session_id = hashlib.sha256(f"{seed}:{launch_uri}:{context.mode}".encode("utf-8")).hexdigest()[:16]
    query = urllib.parse.urlencode({"session_id": session_id, "mode": context.mode, "endpoint": endpoint_base, "respectLaunchVersion": version})
    separator = "&" if "?" in launch_uri else "?"
    return LaunchSession(session_id=session_id, mode=context.mode, launch_url=f"{launch_uri}{separator}{query}", endpoint_base=endpoint_base)
